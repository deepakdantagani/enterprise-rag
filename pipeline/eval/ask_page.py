"""GEN-8b: the ask page, v4's answerer behind a demo-quality Gradio page, every step traced to Phoenix.

Before paying for the official judge (GEN-7), answers are checked by hand: type any question, read
the answer as gemma4 writes it, see the 10 documents it read, and for a benchmark question the
gold answer and its facts. qst_0009 ("In the EdgePath evaluation email thread, what alternative
Year 1 pricing package …") shows the whole EdgePath thread (dsid_85deb10a…, Gmail) as source 1.

Run (Qdrant and Ollama up; Phoenix optional, then open http://localhost:6006 for the traces):

    uv run --with arize-phoenix phoenix serve        # optional
    uv run python -m pipeline.eval.ask_page          # http://localhost:7860

    >>> answer_html("Two options:\\n- A\\n- B")
    '<p>Two options:</p><ul><li>A</li><li>B</li></ul>'
"""
import html
import json
import re
import time
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

from pipeline.eval.questions import Question

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "data/_full/documents.parquet"
QUESTIONS = ROOT / "data/_full/questions.jsonl"
QUESTION_VECTORS = ROOT / "data/_index/question_embeddings/voyage-4.jsonl"
CORPUS_SIZE = "511,962"
SOURCES = {"gmail": "Gmail", "slack": "Slack", "github": "GitHub", "jira": "Jira", "linear": "Linear",
           "confluence": "Confluence", "google_drive": "Google Drive", "hubspot": "HubSpot", "fireflies": "Fireflies"}
EXAMPLES = [  # real benchmark questions, one per source system, and one new question
    "In the EdgePath evaluation email thread, what alternative Year 1 pricing package did Redwood propose instead "
    "of matching the competitor's 50 percent first-year discount and migration credit?",
    "What are the default size limits for file uploads and total request size for the new multipart upload "
    "support on the OpenAI-compatible API endpoints?",
    "What caused the brief p99 latency jump on the hosted text generation endpoint in us-west-2, and what "
    "mitigation was applied to bring it back down?",
    "For the NorthPoint Signalworks dedicated pilot, what p95 latency target did they set for short chat interactions?",
    "What is Redwood Optimize?",
]
Source = Tuple[str, Optional[str], str, str]  # doc_id, source_type, title, content


def inline_html(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html.escape(text))


def answer_html(text: str) -> str:
    """The answer as paragraphs, lines starting '- ' or '* ' as a list, **bold** as bold (gemma4 writes
    markdown although rule 7 asks it not to; the judge ignores it, the page renders it)."""
    parts, items = [], []
    for line in text.strip().splitlines():
        line = line.strip()
        if line[:2] in ("- ", "* "):
            items.append(f"<li>{inline_html(line[2:])}</li>")
            continue
        if items:
            parts.append(f"<ul>{''.join(items)}</ul>")
            items = []
        if line:
            parts.append(f"<p>{inline_html(line)}</p>")
    if items:
        parts.append(f"<ul>{''.join(items)}</ul>")
    return "".join(parts)


def answer_card(text: str) -> str:
    return f'<div class="rw-answer-card">{answer_html(text)}</div>' if text.strip() else ""


def readable_opening(content: str, limit: int = 220) -> str:
    """A document's first words for a source card. Gmail threads are stored as a Python list string
    ("['From: …\\nTo: …', 'From: …']" with literal \\n), so its brackets, quotes and \\n are dropped."""
    text = content.strip()
    if text[:2] in ("['", '["'):
        text = text[2:]
    for separator in ("\\n", "', '", '", "', "', \"", "\", '", "']", '"]'):
        text = text.replace(separator, " ")
    text = " ".join(text.replace("\\", " ").split())  # some threads escape the line break twice
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def source_cards(sources: Sequence[Source]) -> str:
    """One card per document: rank, source system, title, id and its opening lines."""
    if not sources:
        return ""
    cards = []
    for number, (doc_id, source_type, title, content) in enumerate(sources, 1):
        label = SOURCES.get(source_type or "", "Document")
        kind = source_type if source_type in SOURCES else "other"
        opening = html.escape(readable_opening(content))
        cards.append(f'<div class="rw-card"><div class="rw-card-head"><span class="rw-num">{number}</span>'
                     f'<span class="rw-src rw-src-{kind}">{label}</span></div>'
                     f'<div class="rw-title">{html.escape(title or "(untitled)")}</div>'
                     f'<div class="rw-open">{opening}</div><div class="rw-id">{doc_id}</div></div>')
    return f'<div class="rw-label">Sources · {len(sources)}</div><div class="rw-cards">{"".join(cards)}</div>'


def benchmark_html(question: Optional[Question], gold_answer: str, facts: Sequence[str]) -> str:
    """For a benchmark question: what the judge will compare our answer with."""
    if question is None:
        return ""
    items = "".join(f"<li>{html.escape(fact)}</li>" for fact in facts)
    return (f'<div class="rw-bench"><div class="rw-label">Benchmark check · {question.question_id} · '
            f'{question.question_type.replace("_", " ")}</div><div class="rw-gold">{html.escape(gold_answer)}</div>'
            f'<div class="rw-label">Facts the judge looks for ({len(facts)})</div><ul>{items}</ul></div>')


def status_html(stage: str, seconds: float, busy: bool) -> str:
    dot = '<span class="rw-pulse"></span>' if busy else '<span class="rw-done"></span>'
    return f'<div class="rw-status">{dot}{html.escape(stage)}<span class="rw-time">{seconds:.1f} s</span></div>'


def benchmark_questions(path: Path = QUESTIONS) -> Dict[str, Tuple[Question, str, List[str]]]:
    """Every benchmark question by its text: (question, gold answer, answer facts)."""
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return {row["question"]: (Question(row["question_id"], row["question_type"], tuple(row["source_types"]),
                                       row["question"], tuple(row["expected_doc_ids"])),
                              row["gold_answer"], row["answer_facts"]) for row in rows}


def tokens_with_ticks(stream, tick: float = 0.5) -> Iterator[Optional[str]]:
    """The LLM's tokens, read on a thread, with a None every `tick` seconds while none arrive,
    so the page's clock keeps moving during the first 10-25 s before gemma4 writes its first word."""
    import queue
    import threading
    tokens: "queue.Queue" = queue.Queue()
    done = object()

    def read() -> None:
        try:
            for token in stream():
                tokens.put(token)
        finally:
            tokens.put(done)
    threading.Thread(target=read, daemon=True).start()
    while True:
        try:
            token = tokens.get(timeout=tick)
        except queue.Empty:
            yield None
            continue
        if token is done:
            return
        yield token


def stage_of(text: str, documents: int) -> str:
    return "Writing the answer" if text else f"Reading {documents} documents before writing"


def ask(engine, documents: Dict[str, Tuple[str, str]], benchmark: Dict, question: str) -> Iterator[Tuple[str, str, str, str]]:
    """Stream (status, answer, sources, benchmark) as each stage finishes."""
    from llama_index.core.schema import QueryBundle
    question, start = question.strip(), time.time()
    if not question:
        return
    found = benchmark.get(question)
    check = benchmark_html(*found) if found else ""
    yield status_html(f"Searching {CORPUS_SIZE} documents and reranking the best 100", 0, True), "", "", check
    nodes = engine.retrieve(QueryBundle(question))
    sources = [(n.node.metadata["doc_id"], n.node.metadata.get("source_type"), *documents[n.node.metadata["doc_id"]])
               for n in nodes]
    cards = source_cards(sources)
    yield status_html(stage_of("", len(nodes)), time.time() - start, True), "", cards, check
    text = ""
    for token in tokens_with_ticks(lambda: engine.synthesize(QueryBundle(question), nodes).response_gen):
        if token is None:  # no new words yet: gemma4 is still reading ~14K tokens of documents
            yield status_html(stage_of(text, len(nodes)), time.time() - start, True), answer_card(text), cards, check
            continue
        text += token
        yield status_html("Writing the answer", time.time() - start, True), answer_card(text), cards, check
    yield status_html(f"Answered from {len(nodes)} documents", time.time() - start, False), answer_card(text), cards, check


CSS = """
:root, .dark { --rw-muted: color-mix(in srgb, var(--body-text-color) 68%, transparent); }
.gradio-container { max-width: 980px !important; margin: 0 auto !important; font-family: 'IBM Plex Sans', system-ui, sans-serif; }
.rw-hero { padding: 28px 0 8px; }
.rw-hero h1 { font-size: 30px; font-weight: 600; margin: 0; letter-spacing: -0.01em; }
.rw-hero p { color: var(--rw-muted); margin: 6px 0 0; font-size: 15px; }
.rw-stats { display: flex; gap: 18px; flex-wrap: wrap; margin-top: 14px; font-size: 13px; color: var(--rw-muted); }
.rw-stats b { color: var(--body-text-color); font-weight: 600; }
.rw-status { display: flex; align-items: center; gap: 10px; font-size: 14px; color: var(--rw-muted); padding: 4px 2px; }
.rw-time { margin-left: auto; font-family: 'IBM Plex Mono', monospace; font-size: 13px; }
.rw-pulse, .rw-done { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
.rw-pulse { background: #2f6fdd; animation: rw-pulse 1s ease-in-out infinite; }
.rw-done { background: #1f9d63; }
@keyframes rw-pulse { 50% { opacity: .3; } }
.rw-answer-card { border: 1px solid var(--border-color-primary); border-radius: 12px; padding: 18px 22px; background: var(--background-fill-primary); font-size: 17px; line-height: 1.65; }
.rw-answer-card p { margin: 0 0 10px; } .rw-answer-card ul { margin: 0 0 10px; padding-left: 22px; } .rw-answer-card li { margin: 4px 0; }
.rw-answer-card > :last-child { margin-bottom: 0; }
.rw-label { font-size: 12px; letter-spacing: .06em; text-transform: uppercase; color: var(--rw-muted); margin: 4px 0 8px; }
.rw-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.rw-card { border: 1px solid var(--border-color-primary); border-radius: 10px; padding: 12px 14px; background: var(--background-fill-primary); display: grid; gap: 6px; }
.rw-card-head { display: flex; align-items: center; gap: 8px; }
.rw-num { font-family: 'IBM Plex Mono', monospace; font-size: 12px; color: var(--body-text-color-subdued); }
.rw-src { font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 999px; background: var(--background-fill-secondary); }
.rw-src-gmail { color: #c5221f; } .rw-src-slack { color: #7c3aed; } .rw-src-github { color: #57606a; } .rw-src-jira { color: #0c66e4; }
.rw-src-linear { color: #5e6ad2; } .rw-src-confluence { color: #1868db; } .rw-src-google_drive { color: #188038; }
.rw-src-hubspot { color: #e8590c; } .rw-src-fireflies { color: #c026d3; } .rw-src-other { color: var(--body-text-color-subdued); }
.rw-title { font-weight: 600; font-size: 14px; line-height: 1.35; }
.rw-open { font-size: 13px; color: var(--rw-muted); line-height: 1.5; }
.rw-id { font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: var(--body-text-color-subdued); overflow-wrap: anywhere; }
.rw-bench { border-left: 3px solid #1f9d63; padding: 4px 0 4px 14px; }
.rw-gold { font-size: 15px; line-height: 1.6; margin-bottom: 10px; }
.rw-bench ul { margin: 0; padding-left: 20px; font-size: 14px; line-height: 1.55; }
footer { display: none !important; }
"""
HEAD = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" '
        'href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">')


def build_page(engine, documents: Dict[str, Tuple[str, str]], benchmark: Dict):
    import gradio as gr
    with gr.Blocks(title="Redwood Answers") as page:
        gr.HTML('<div class="rw-hero"><h1>Redwood Answers</h1><p>Ask anything about Redwood Inference. '
                'Answers come only from the company\'s own Slack, email, tickets, docs and code.</p>'
                f'<div class="rw-stats"><span><b>{CORPUS_SIZE}</b> documents</span><span><b>9</b> source systems</span>'
                '<span>hybrid search · reranked · answered on this machine</span></div></div>')
        question = gr.Textbox(placeholder="Ask a question about Redwood…", show_label=False, submit_btn="Ask",
                              autofocus=True, lines=1)
        gr.Examples(EXAMPLES, inputs=question, label="Try one")
        status = gr.HTML()
        answer = gr.HTML()
        check = gr.HTML()
        sources = gr.HTML()
        question.submit(lambda text: (yield from ask(engine, documents, benchmark, text)), question,
                        [status, answer, sources, check], show_progress="hidden")  # our status line shows progress
    return page


def main() -> None:
    import os
    import gradio as gr
    from dotenv import load_dotenv
    from qdrant_client import QdrantClient
    from pipeline.eval.answers import answer_engine, answerer_llm, live_reranker, live_retriever
    from pipeline.eval.embedders import embed_model_named, saved_query_embeddings
    load_dotenv(ROOT / ".env")  # VOYAGE_API_KEY
    try:
        from pipeline.eval.tracing import trace_to_phoenix
        trace_to_phoenix()
    except Exception as error:  # Phoenix is optional
        print(f"Phoenix tracing off: {error}")
    key = os.environ.get("VOYAGE_API_KEY")
    questions = saved_query_embeddings(QUESTION_VECTORS, fallback=embed_model_named("voyage-4", voyage_api_key=key))
    documents: Dict[str, Tuple[str, str]] = {}
    engine = answer_engine(live_retriever(QdrantClient(url="http://localhost:6333", timeout=600), questions),
                           answerer_llm(), documents, reranker=live_reranker(api_key=key), corpus=CORPUS, streaming=True)
    build_page(engine, documents, benchmark_questions()).launch(server_port=7860, css=CSS, head=HEAD,
                                                                theme=gr.themes.Base(primary_hue="blue"))


if __name__ == "__main__":
    main()
