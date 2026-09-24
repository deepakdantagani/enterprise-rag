"""SLACK-3: pipeline/observability.py, shared events and one JSON-lines handler (all sources).

Run: uv run python -m unittest discover tests
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llama_index.core.instrumentation import get_dispatcher, root_dispatcher  # noqa: E402
from llama_index.core.instrumentation.events.embedding import EmbeddingStartEvent  # noqa: E402

from pipeline.observability import (  # noqa: E402
    FileCleaned, FileFailed, StageDone, dispatcher, events_logged_to,
)


def read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


class EventsLoggedTo(unittest.TestCase):
    def setUp(self):
        self.log_path = Path(tempfile.mkdtemp()) / "slack" / "logs" / "run-1.jsonl"

    def test_each_event_becomes_one_json_line_with_its_fields(self):
        with events_logged_to(self.log_path):
            dispatcher.event(FileCleaned(
                source="slack", file="a.txt", rules_fired={"newline": 17}, bytes_in=1324, bytes_out=1318))
            dispatcher.event(FileFailed(
                source="slack", file="b.txt", error_type="UnicodeDecodeError", message="bad byte"))
            dispatcher.event(StageDone(source="slack", stage="clean", files=2, failed=1, seconds=0.5))
        lines = read_lines(self.log_path)
        self.assertEqual([line["event"] for line in lines], ["FileCleaned", "FileFailed", "StageDone"])
        self.assertEqual(lines[0]["rules_fired"], {"newline": 17})
        self.assertEqual(lines[0]["source"], "slack")
        self.assertEqual(lines[1]["error_type"], "UnicodeDecodeError")
        self.assertEqual(lines[2]["files"], 2)
        self.assertTrue(lines[0]["timestamp"].endswith("Z"))  # ISO 8601, UTC
        self.assertNotIn("id_", lines[0])
        self.assertNotIn("class_name", lines[0])

    def test_the_handler_is_detached_when_the_block_ends_even_on_an_error(self):
        handlers_before = list(root_dispatcher.event_handlers)
        with self.assertRaises(RuntimeError):
            with events_logged_to(self.log_path):
                raise RuntimeError("stage crashed")
        self.assertEqual(root_dispatcher.event_handlers, handlers_before)

    def test_llama_index_events_land_in_the_same_log(self):
        library_dispatcher = get_dispatcher("llama_index.core.base.embeddings.base")
        with events_logged_to(self.log_path):
            library_dispatcher.event(EmbeddingStartEvent(model_dict={"model": "test"}))
        self.assertEqual(read_lines(self.log_path)[0]["event"], "EmbeddingStartEvent")

    def test_a_span_id_ties_events_to_the_stage_that_emitted_them(self):
        @dispatcher.span
        def clean_stage():
            dispatcher.event(StageDone(source="gmail", stage="clean", files=0, failed=0, seconds=0.0))

        with events_logged_to(self.log_path):
            clean_stage()
        self.assertIn("clean_stage", read_lines(self.log_path)[0]["span_id"])


if __name__ == "__main__":
    unittest.main()
