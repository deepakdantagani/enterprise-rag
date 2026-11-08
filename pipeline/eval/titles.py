"""RET-9a: titles_like, every document whose title contains a pattern, capped, with the total.

Search returns a sample, not a set. qst_0437 asks "Across all incident postmortems, which Redwood
team was assigned the most follow-up action items?": 9 gold Confluence pages, and hybrid search
plus rerank plus the gap loop submitted 40 documents holding none of them (recall 0.0), because
every postmortem page has an action-items section and none matches the question
better than the rest. Listing the Confluence titles that contain "Postmortem" returns 73 rows
(38 `Postmortem: …` pages, 6 `P0`/`P1 Incident Postmortem: …`, 29 playbooks and templates that
name postmortems), about 2.5K tokens, with all 9 gold pages inside; an agent then reads the ones the question needs.

The title column is read once from documents.parquet (511,962 rows, three columns, no content).
A match is pyarrow's vectorised case-insensitive substring test over it: milliseconds, no index,
no model call. Rows come back in title byte order (uppercase before lowercase), then doc_id, so a
family such as "Postmortem: …" sits together and the cut is the same on every run,
and carry source_type because doc_id is not unique: 3 ids exist in two sources. More matches
than `limit` (default 200) returns the first `limit` rows and the full total, so the caller sees
"200 of 12,432" for the Slack channel eng-security and narrows instead of listing a channel.

    >>> import pyarrow as pa
    >>> table = pa.Table.from_pylist([
    ...     {"doc_id": "dsid_a", "source_type": "confluence", "title": "Postmortem: Streaming stalls"},
    ...     {"doc_id": "dsid_b", "source_type": "confluence", "title": "P0 Incident Postmortem: API outage"},
    ...     {"doc_id": "dsid_c", "source_type": "slack", "title": "postmortems"}])
    >>> titles_like(table, "confluence", "postmortem")
    TitleList(rows=[('confluence', 'dsid_b', 'P0 Incident Postmortem: API outage'), ('confluence', 'dsid_a', 'Postmortem: Streaming stalls')], total=2)
    >>> titles_like(table, None, "Postmortem", limit=1)
    TitleList(rows=[('confluence', 'dsid_b', 'P0 Incident Postmortem: API outage')], total=3)
"""
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple, Union

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

TITLE_COLUMNS = ["doc_id", "source_type", "title"]
DEFAULT_LIMIT = 200  # lists 6,171 of the 6,230 title families with >= 2 docs whole (audit 2026-11-08); ~7K tokens


class TitleList(NamedTuple):
    rows: List[Tuple[str, str, str]]  # (source_type, doc_id, title), in title order, at most `limit`
    total: int  # matches before the cap; larger than len(rows) means the list was cut


def document_titles(path: Union[str, Path]) -> pa.Table:
    """The doc_id, source_type and title columns of documents.parquet, nothing else."""
    return pq.read_table(path, columns=TITLE_COLUMNS)


def titles_like(table: pa.Table, source_type: Optional[str], pattern: str, limit: int = DEFAULT_LIMIT) -> TitleList:
    """Rows of `source_type` (every source when None) whose non-empty title contains `pattern`, any case."""
    title = table.column("title")
    non_empty = pc.greater(pc.utf8_length(title), 0)  # only an empty pattern could match the 15 empty Slack titles
    matches = pc.and_(pc.match_substring(title, pattern, ignore_case=True), non_empty)
    if source_type is not None:
        matches = pc.and_(matches, pc.equal(table.column("source_type"), source_type))
    found = table.filter(pc.fill_null(matches, False)).sort_by([("title", "ascending"), ("doc_id", "ascending")])
    rows = [(row["source_type"], row["doc_id"], row["title"]) for row in found.slice(0, limit).to_pylist()]
    return TitleList(rows=rows, total=found.num_rows)
