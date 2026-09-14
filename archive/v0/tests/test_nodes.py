"""Tests for pipeline.nodes (LlamaIndex node parser). Run: uv run python -m unittest discover tests"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llama_index.core.schema import Document  # noqa: E402
from pipeline.nodes import ConfluenceNodeParser  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def nodes_for(name, **kw):
    text = (FIXTURES / name).read_text()
    doc = Document(id_=name, text=text, metadata={"title": text.splitlines()[0]})
    return text, ConfluenceNodeParser(**kw).get_nodes_from_documents([doc])


class NodeParserTests(unittest.TestCase):
    def test_every_nonblank_line_lands_in_exactly_one_node(self):
        for name in ("typical.md", "long.md", "fenced_code.md", "escaped_table.md", "setext.md"):
            text, nodes = nodes_for(name)
            lines = text.splitlines()
            covered = {}
            for n in nodes:
                for ln in range(n.metadata["line_start"], n.metadata["line_end"] + 1):
                    self.assertNotIn(ln, covered, f"{name}: line {ln} in two nodes")
                    covered[ln] = n
            heading_lines = {i + 1 for i, l in enumerate(lines) if l.strip()} - set(covered)
            for ln in heading_lines:  # only headings (and setext underlines) may be outside a node body
                l = lines[ln - 1]
                self.assertTrue(l.startswith("#") or set(l.strip()) <= set("-=") or ln == 1 or l.strip() in {h for n in nodes for h in n.metadata["heading_path"]},
                                f"{name}: line {ln} {l[:40]!r} not covered")

    def test_typical_sections_and_breadcrumb(self):
        _, nodes = nodes_for("typical.md")
        headings = [n.metadata["heading"] for n in nodes]
        for h in ("Overview", "Goals", "Scope", "Escalation matrix", "Contacts"):
            self.assertIn(h, headings)
        goals = next(n for n in nodes if n.metadata["heading"] == "Goals")
        self.assertTrue(goals.text.startswith("Telemetry Normalization and Fidelity Acceptance Playbook for Enterprise Tenants > Goals\n\n"))
        self.assertIn("- Provide a repeatable acceptance checklist", goals.text)

    def test_table_and_code_stay_whole(self):
        _, nodes = nodes_for("typical.md")
        table_nodes = [n for n in nodes if "table_open" in n.metadata["block_types"]]
        self.assertEqual(len(table_nodes), 1)
        self.assertEqual(table_nodes[0].text.count("\n| "), 6)  # header + 5 rows, plus separator row starts with |-
        _, nodes = nodes_for("fenced_code.md")
        fence_nodes = [n for n in nodes if "fence" in n.metadata["block_types"]]
        for n in fence_nodes:
            self.assertEqual(n.text.count("```") % 2, 0, "fence opened and closed inside one node")

    def test_max_chars_respected_except_single_atomic_block(self):
        _, nodes = nodes_for("long.md", max_chars=800)
        for n in nodes:
            body_len = len(n.text.split("\n\n", 1)[1]) if "\n\n" in n.text else len(n.text)
            if body_len > 800:
                self.assertEqual(len(n.metadata["block_types"]), 1, "oversize node must be a single atomic block")

    def test_native_heading_levels_nest(self):
        _, nodes = nodes_for("long.md")
        fmt = next(n for n in nodes if n.metadata["heading"] == "Format")
        self.assertEqual(fmt.metadata["heading_path"][-2:], ["Permission naming conventions (RBAC v2)", "Format"])

    def test_no_markup_file_still_chunks(self):
        text, nodes = nodes_for("no_markup.md")
        self.assertGreater(len(nodes), 1)
        self.assertTrue(all(n.text.startswith(text.splitlines()[0]) for n in nodes))


if __name__ == "__main__":
    unittest.main()
