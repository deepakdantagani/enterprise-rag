"""SLACK-3: what a pipeline run did, as LlamaIndex instrumentation events. Shared by every source.

A stage emits one event per file and one at the end, on `dispatcher`. `events_logged_to`
writes every event to a JSON-lines file while its block runs:

    with events_logged_to(Path("data/slack/logs/run-1.jsonl")):
        dispatcher.event(FileCleaned(source="slack", file="a.txt", rules_fired={"newline": 17},
                                     bytes_in=1324, bytes_out=1318))

gives one line:

    {"event": "FileCleaned", "timestamp": "2026-09-23T21:29:43.109153Z", "span_id": null,
     "tags": {}, "source": "slack", "file": "a.txt", "rules_fired": {"newline": 17}, ...}

The handler sits on LlamaIndex's root dispatcher, so the same log also holds the library's
own events (embedding, retrieval) when a later stage runs them: one trace per run.
Events carry `source` ("slack", "gmail", "linear"), so a new source adds a value, not a module.
`only=PipelineEvent` keeps just our events: a run that embeds ~1.3M chunks would otherwise log
every vector, since LlamaIndex's embedding events carry them (EVAL-3d3).
Observing never changes a pipeline's output: the handler only writes to its log file. The
dispatcher swallows handler errors, so a log line lost to a full disk is lost silently.
"""
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llama_index.core.instrumentation import get_dispatcher, root_dispatcher
from llama_index.core.instrumentation.event_handlers.base import BaseEventHandler
from llama_index.core.instrumentation.events.base import BaseEvent
from pydantic import Field, PrivateAttr

dispatcher = get_dispatcher("pipeline")
FIELDS_NOT_LOGGED = {"id_", "class_name"}  # a random id; "BaseEvent" (the name is logged as "event")


class PipelineEvent(BaseEvent):
    """Our events: timestamps in UTC, so logs from two machines line up."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FileCleaned(PipelineEvent):
    source: str
    file: str
    rules_fired: dict[str, int]
    bytes_in: int
    bytes_out: int


class FileFailed(PipelineEvent):
    source: str
    file: str
    error_type: str
    message: str


class StageDone(PipelineEvent):
    source: str
    stage: str
    files: int
    failed: int
    seconds: float


class JsonLinesEventHandler(BaseEventHandler):
    """Writes each event as one line of JSON: its name first, then its fields."""

    log_path: Path
    only: type[BaseEvent] = BaseEvent
    _log_file: Any = PrivateAttr(default=None)

    def open(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_file = open(self.log_path, "w", encoding="utf-8")

    def close(self) -> None:
        self._log_file.close()

    def handle(self, event: BaseEvent, **kwargs: Any) -> None:
        if not isinstance(event, self.only):
            return
        fields = {name: value for name, value in event.model_dump(mode="json").items()
                  if name not in FIELDS_NOT_LOGGED}
        self._log_file.write(json.dumps({"event": type(event).__name__} | fields) + "\n")


@contextmanager
def events_logged_to(log_path: Path, only: type[BaseEvent] = BaseEvent) -> Iterator[None]:
    """Log every event of type `only` (by default ours and LlamaIndex's) to log_path while the block runs, then detach."""
    handler = JsonLinesEventHandler(log_path=log_path, only=only)
    handler.open()
    root_dispatcher.add_event_handler(handler)
    try:
        yield
    finally:
        root_dispatcher.event_handlers = [h for h in root_dispatcher.event_handlers if h is not handler]
        handler.close()
