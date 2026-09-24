"""SLACK-3: what a pipeline run did, as LlamaIndex instrumentation events. Shared by every source.

A stage emits one event per file and one at the end, on `dispatcher`. `events_logged_to`
writes every event to a JSON-lines file while its block runs:

    with events_logged_to(Path("data/slack/logs/run-1.jsonl")):
        dispatcher.event(FileCleaned(source="slack", file="a.txt", rules_fired={"newline": 17},
                                     bytes_in=1324, bytes_out=1318))

gives one line:

    {"event": "FileCleaned", "timestamp": "...", "span_id": null, "source": "slack",
     "file": "a.txt", "rules_fired": {"newline": 17}, "bytes_in": 1324, "bytes_out": 1318}

Events carry `source` ("slack", "gmail", "linear"), so a new source adds a value, not a module.
Observing never changes a pipeline's output: the handler only writes to its log file.
"""
import json
from collections.abc import Iterator
from contextlib import contextmanager
from io import TextIOBase
from pathlib import Path
from typing import Any

from llama_index.core.instrumentation import get_dispatcher
from llama_index.core.instrumentation.event_handlers.base import BaseEventHandler
from llama_index.core.instrumentation.events.base import BaseEvent

dispatcher = get_dispatcher("pipeline")
FIELDS_NOT_LOGGED = {"id_", "tags", "class_name"}  # LlamaIndex bookkeeping, same on every line


class FileCleaned(BaseEvent):
    source: str
    file: str
    rules_fired: dict[str, int]
    bytes_in: int
    bytes_out: int


class FileFailed(BaseEvent):
    source: str
    file: str
    error_type: str
    message: str


class StageDone(BaseEvent):
    source: str
    stage: str
    files: int
    failed: int
    seconds: float


class JsonLinesHandler(BaseEventHandler):
    """Writes each event as one line of JSON: its name first, then its fields."""

    log_file: TextIOBase

    def handle(self, event: BaseEvent, **kwargs: Any) -> None:
        fields = {name: value for name, value in event.model_dump().items() if name not in FIELDS_NOT_LOGGED}
        line = {"event": type(event).__name__} | fields
        self.log_file.write(json.dumps(line, default=str) + "\n")


@contextmanager
def events_logged_to(log_path: Path) -> Iterator[None]:
    """Log every event on the dispatcher to log_path while the block runs, then detach."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as log_file:
        handler = JsonLinesHandler(log_file=log_file)
        dispatcher.add_event_handler(handler)
        try:
            yield
        finally:
            dispatcher.event_handlers.remove(handler)
