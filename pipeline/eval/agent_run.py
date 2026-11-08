"""RET-10d: agent_answers, the loop (RET-10c) over a question set: one row per question for the judges, resumable, traced.

A run is 119 or 500 paid questions and takes minutes to hours. Three things follow. A crash must
never repeat a paid question: questions already in the output file are skipped, the pattern of
save_answers (GEN-2e) and rerank_saved (RET-5). Every read must not scan the 1.4 GB parquet
(2.1 s a miss, RET-10b): the documents a batch of questions may read are fetched in one scan
first: 10 questions are 1,671 candidate documents, 10.5 MB, one 3.7 s scan instead of a 2.1 s scan
per read (all 470 at once would be 290 MB, too much to hold). And a wrong answer must be explainable: a trace file keeps every tool call
with its arguments and result size, the model calls and the tokens, so nothing has to be re-run
to see what the agent did. The answers file is the artifact every re-score reads; the model
itself is not replayed.

The row is the leaderboard's shape (`question_id`, `answer`, `document_ids`, `quotes`, as
answer_row writes it) plus what RET-10e measures: `iterations`, `budget_exhausted`,
`input_tokens`, `output_tokens`. `document_ids` is the ledger, the documents the agent read.

    >>> from types import SimpleNamespace
    >>> usage_of({"usage": SimpleNamespace(input_tokens=1200, output_tokens=80)})
    (1200, 80)
    >>> usage_of(None)
    (0, 0)
"""
import asyncio
import json
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

from llama_index.core.agent.workflow import AgentOutput, FunctionAgent, ToolCallResult

from pipeline.eval.agent import MAX_ITERATIONS, aanswer_question
from pipeline.eval.answers import documents_by_id
from pipeline.eval.rerank import read_jsonl

BATCH = 10  # questions whose candidate documents are prefetched in one parquet scan


def usage_of(raw) -> Tuple[int, int]:
    """(input, output) tokens of one model call from the provider's raw response; (0, 0) when it reports none.

    Input counts cached reads and cache writes too (Anthropic reports them apart from input_tokens), so the total is right
    if prompt caching is ever turned on; the price per cached token differs, which RET-10e can read from the trace.
    """
    usage = (raw or {}).get("usage") if isinstance(raw, dict) else getattr(raw, "usage", None)
    if usage is None:
        return 0, 0
    field = (lambda name: usage.get(name) or 0) if isinstance(usage, dict) else (lambda name: getattr(usage, name, 0) or 0)
    return field("input_tokens") + field("cache_read_input_tokens") + field("cache_creation_input_tokens"), field("output_tokens")


def candidate_ids(candidates_path: Union[str, Path]) -> Dict[str, List[str]]:
    """question_id -> the distinct document ids of its saved search candidates, in rank order (RET-5's file)."""
    return {row["question_id"]: list(dict.fromkeys(c["ref_doc_id"] for c in row["candidates"])) for row in read_jsonl(candidates_path)}


def candidate_prefetcher(candidates: Dict[str, List[str]], documents: Dict[str, Tuple[str, str]],
                         parquet_path: Union[str, Path]) -> Callable[[Sequence[str]], None]:
    """A prefetch for agent_answers: one scan loads a batch's candidate documents into the read tool's cache."""
    def prefetch(question_ids: Sequence[str]) -> None:
        wanted = {doc_id for qid in question_ids for doc_id in candidates.get(qid, [])} - set(documents)
        if wanted:
            documents.update(documents_by_id(parquet_path, sorted(wanted)))
    return prefetch


class _Trace:
    """One question's events as they stream: tool calls with result sizes, model calls, tokens.

    It is the event sink (`on_event=trace`) and the per-question totals in one object, so nothing is passed back and forth.
    """

    def __init__(self) -> None:
        self.tool_calls: List[dict] = []
        self.model_calls, self.input_tokens, self.output_tokens = 0, 0, 0

    def __call__(self, event) -> None:
        if isinstance(event, ToolCallResult):
            self.tool_calls.append({"tool": event.tool_name, "args": event.tool_kwargs, "chars": len(str(event.tool_output.content))})
        elif isinstance(event, AgentOutput):
            tokens_in, tokens_out = usage_of(event.raw)
            self.model_calls, self.input_tokens, self.output_tokens = self.model_calls + 1, self.input_tokens + tokens_in, self.output_tokens + tokens_out


def finished_rows(path: Path) -> List[dict]:
    """The rows of a JSONL written so far; a last line cut by a crash is dropped from the file so appends stay well-formed."""
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    try:
        return [json.loads(line) for line in lines]
    except json.JSONDecodeError:
        path.write_text("".join(line + "\n" for line in lines[:-1]))
        return [json.loads(line) for line in lines[:-1]]


async def _answer_all(agent: FunctionAgent, todo: List[dict], out_path: Path, trace_path: Path,
                      prefetch: Optional[Callable[[Sequence[str]], None]], batch: int, max_iterations: int) -> None:
    with out_path.open("a") as out, trace_path.open("a") as trace_file:
        for start in range(0, len(todo), batch):
            group = todo[start:start + batch]
            if prefetch is not None:
                prefetch([q["question_id"] for q in group])
            for question in group:
                trace = _Trace()
                result = await aanswer_question(agent, question["question"], max_iterations, on_event=trace)
                trace_file.write(json.dumps({"question_id": question["question_id"], "tool_calls": trace.tool_calls,
                                             "model_calls": trace.model_calls}) + "\n"); trace_file.flush()
                row = {"question_id": question["question_id"], "answer": result.answer, "document_ids": result.read, "quotes": result.quotes,
                       "iterations": result.iterations, "budget_exhausted": result.budget_exhausted,
                       "input_tokens": trace.input_tokens, "output_tokens": trace.output_tokens}
                out.write(json.dumps(row) + "\n"); out.flush()


def agent_answers(agent: FunctionAgent, questions: Sequence[dict], out_path: Union[str, Path], trace_path: Union[str, Path],
                  prefetch: Optional[Callable[[Sequence[str]], None]] = None, batch: int = BATCH,
                  max_iterations: int = MAX_ITERATIONS) -> int:
    """Answer every question not yet in `out_path`, one flushed row each (and one trace line); returns how many this call.

    One event loop for the whole run: the Anthropic wrapper keeps an async client whose sockets belong to the loop that
    opened them, so a loop per question would fail on the second question.
    """
    out_path, trace_path = Path(out_path), Path(trace_path)
    done = {row["question_id"] for row in finished_rows(out_path)}
    todo = [q for q in questions if q["question_id"] not in done]
    asyncio.run(_answer_all(agent, todo, out_path, trace_path, prefetch, batch, max_iterations))
    return len(todo)
