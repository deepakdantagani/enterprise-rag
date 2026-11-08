"""RET-10d-a: usage_of, candidate_ids, candidate_prefetcher, finished_rows: what the agent runner (RET-10d-b) needs.

A run of the loop (RET-10c) over 119 or 500 paid questions takes minutes to hours. Four small pieces
make it safe before the runner itself exists. `finished_rows` reads the rows written so far and drops
a last line cut by a crash, so a re-run resumes and appends stay well-formed (the resume pattern of
save_answers, GEN-2e). `candidate_ids` and `candidate_prefetcher` load a batch's candidate documents
in one parquet scan: 10 questions are 1,671 documents, 10.5 MB, one 3.7 s scan instead of a 2.1 s
scan per read (RET-10b); all 470 at once would be 290 MB, too much to hold. `usage_of` reads the
tokens of one model call from the provider's raw response so RET-10e can price the 500-question
run from the first 119.

    >>> from types import SimpleNamespace
    >>> usage_of({"usage": SimpleNamespace(input_tokens=1200, output_tokens=80)})
    (1200, 80)
    >>> usage_of(None)
    (0, 0)
"""
import json
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Tuple, Union

from pipeline.eval.answers import documents_by_id
from pipeline.eval.rerank import read_jsonl

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
