"""Acceptance tests for the native markdown-it behaviour we rely on.

Run: uv run --with markdown-it-py==4.2.0 python -m unittest discover tests
"""
from pathlib import Path
import unittest

from markdown_it import MarkdownIt

PARSER = MarkdownIt("commonmark").enable("table")
PREVIEW = Path(__file__).resolve().parent / "fixtures"

# Each fixture specifies a source passage and required HTML structure/content.
CASES = [
    ("heading_levels", "## Parent\n### Child", "<h2>Parent</h2>\n<h3>Child</h3>"),
    ("paragraph_order", "First\n\nSecond", "<p>First</p>\n<p>Second</p>"),
    ("bullets", "- One\n- Two", "<li>One</li>\n<li>Two</li>"),
    ("numbering", "3) Three\n4) Four", '<ol start="3">'),
    ("nested_list", "- Parent\n  - Child", "<li>Parent\n<ul>\n<li>Child</li>"),
    ("list_continuation", "- First\n  continued", "<li>First\ncontinued</li>"),
    ("checkbox_text", "- [ ] Open\n- [x] Done", "<li>[x] Done</li>"),
    ("table_header", "| A | B |\n|---|---|\n| 1 | 2 |", "<th>A</th>\n<th>B</th>"),
    ("escaped_pipe", "| A | B |\n|---|---|\n| x\\|y | z |", "<td>x|y</td>\n<td>z</td>"),
    ("code_indentation", '```py\nif x:\n    run()\n```', '<code class="language-py">if x:\n    run()\n'),
    ("inline_code", "Use `x_y`.", "Use <code>x_y</code>."),
    ("blockquote", "> Warning", "<blockquote>\n<p>Warning</p>"),
    ("separator", "Paragraph\n\n---", "<p>Paragraph</p>\n<hr />"),
    ("underlined_heading", "Heading\n---", "<h2>Heading</h2>"),
    ("html_preserved", "<div>Example</div>", "<div>Example</div>"),
    ("html_in_code", "`<div>`", "<code>&lt;div&gt;</code>"),
    ("literal_escape_unicode", r"café → literal \n", r"café → literal \n"),
    ("no_final_newline", "Final", "<p>Final</p>"),
    ("crlf", "## Heading\r\n\r\nText", "<h2>Heading</h2>\n<p>Text</p>"),
    ("repeated_headings", "## Same\n## Same", "<h2>Same</h2>\n<h2>Same</h2>"),
    ("skipped_levels_empty_section", "# A\n### B", "<h1>A</h1>\n<h3>B</h3>"),
    ("heading_inside_code", "```\n## Not heading\n```", "<code>## Not heading\n"),
    ("heading_inside_table", "| A |\n|---|\n| ## Cell |", "<td>## Cell</td>"),
    ("unclosed_fence_preserves_text", "```\nremaining", "<code>remaining</code>"),
    ("malformed_table_preserves_text", "| A | B |\n| value |", "<p>| A | B |\n| value |</p>"),
    ("trailing_spaces", "One  \nTwo", "One<br />\nTwo"),
    ("link", "[Docs](https://example.org)", '<a href="https://example.org">Docs</a>'),
    ("image", "![Diagram](diagram.png)", '<img src="diagram.png" alt="Diagram" />'),
    ("broken_link", "[Docs](unfinished", "[Docs](unfinished"),
    ("mixed_order", "## A\n\nText\n\n- Item", "<h2>A</h2>\n<p>Text</p>\n<ul>"),
]


class MarkdownAcceptance(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(PARSER.parse(""), [])

    def test_duplicate_source_locations(self):
        tokens = PARSER.parse("Same\n\nSame")
        self.assertEqual([t.map for t in tokens if t.type == "inline"], [[0, 1], [2, 3]])

    def test_real_overview_location(self):
        source = (PREVIEW / "typical.md").read_text()
        token = next(t for t in PARSER.parse(source) if t.content == "Overview")
        self.assertEqual(token.map, [2, 3])
        self.assertEqual(source.splitlines()[2], token.content)

    def test_real_table_cells(self):
        tokens = PARSER.parse((PREVIEW / "typical.md").read_text())
        start = next(i for i, t in enumerate(tokens) if t.type == "table_open")
        end = next(i for i, t in enumerate(tokens) if t.type == "table_close")
        cells = [t.content for t in tokens[start:end] if t.type == "inline"]
        self.assertEqual(cells, [
            "Category", "Canonical metric name", "Description", "Min cardinality",
            "Ingress", "redwood.ingress.requests", "per-request ingress counter (labels: tenant_id, route_id)", "high",
            "Latency", "redwood.request.latency_ms", "request latency histogram (labels: tenant_id, model_id)", "high",
            "Tokens", "redwood.tokens.generated", "tokens generated per request", "medium",
            "Errors", "redwood.request.errors", "4xx/5xx error counter (labels: tenant_id, code)", "medium",
            "VM/GPU Util", "redwood.host.gpu.utilization", "GPU utilization gauge for Dedicated hosts", "low",
        ])

    def test_real_short_document(self):
        source = (PREVIEW / "short.md").read_text()
        self.assertEqual([t.content for t in PARSER.parse(source) if t.type == "inline"], source.strip().split("\n\n"))

    def test_real_long_heading_levels(self):
        tokens = PARSER.parse((PREVIEW / "long.md").read_text())
        headings = [(t.tag, tokens[i + 1].content) for i, t in enumerate(tokens) if t.type == "heading_open"]
        self.assertEqual(len(headings), 13)
        self.assertEqual(headings[:4], [("h2", "Purpose"), ("h2", "Definitions"),
                                      ("h2", "Permission naming conventions (RBAC v2)"), ("h3", "Format")])

    def test_real_code_bodies(self):
        source = (PREVIEW / "fenced_code.md").read_text()
        fences = [t for t in PARSER.parse(source) if t.type == "fence"]
        self.assertEqual([t.info for t in fences], ["json", "yaml", "js", "py"])
        for token in fences:
            start, end = token.map
            self.assertEqual(token.content, "\n".join(source.splitlines()[start + 1:end - 1]) + "\n")

    def test_real_plain_heading_is_not_native(self):
        """markdown-it alone does not see bare labels; the label rule does (see test_pipeline)."""
        source = (PREVIEW / "typical.md").read_text()
        tokens = PARSER.parse(source)
        headings = [tokens[i + 1].content for i, t in enumerate(tokens) if t.type == "heading_open"]
        self.assertNotIn("Overview", headings)


def acceptance_case(source, expected):
    def test(self):
        self.assertIn(expected, PARSER.render(source))
    return test


for name, source, expected in CASES:
    setattr(MarkdownAcceptance, "test_" + name, acceptance_case(source, expected))

if __name__ == "__main__":
    unittest.main(verbosity=2)
