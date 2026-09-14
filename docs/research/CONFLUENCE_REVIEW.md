# Confluence Data — First Review

Downloaded all **5,189 documents** from the official [v1.0.0 Confluence exports](https://github.com/onyx-dot-app/EnterpriseRAG-Bench/releases/tag/v1.0.0). Both archive SHA-256 checksums match the release. These exports are from GitHub; equivalence to the current Hugging Face revision has not been checked.

Original text files: `data/confluence/raw/` (51.2 MB). Archive URLs and checksums: `data/confluence/manifest.json`. The data directory is excluded from Git.

## What the scan found

| Measurement | Result |
|---|---:|
| Minimum / median / maximum words | 7 / 1,247 / 3,457 |
| Pages under 500 words | 165 |
| Pages over 2,000 words | 259 |
| Pages with detected Markdown headings | 2,170 |
| Pages with detected lists | 4,271 |
| Pages with detected Markdown tables | 2,142 |
| Pages with detected code fences | 745 |
| Pages containing literal `\n` sequences | 1,117 |

Words are whitespace-separated. Structure counts use text patterns, overlap, and are approximate: plain section labels and unfenced code can be missed. Literal escapes may be intentional inside code; do not replace them globally.

## Read these examples

Use an editor's Markdown preview alongside the source text. These `.md` copies preserve the original bytes; they do not recreate the original Confluence layout.

- [Typical-length playbook](../data/confluence/preview/typical.md)
- [Runbook with tables and code](../data/confluence/preview/markdown_tables.md)
- [Code example](../data/confluence/preview/fenced_code.md)
- [Longest document](../data/confluence/preview/long.md)
- [Shortest record: a small configuration fragment](../data/confluence/preview/short.md)

## Initial implications

Preserve document IDs from filenames. Recognize both Markdown headings and plain section labels. Keep table headers with their rows and code with its explanation. Inspect tiny records and escaped formatting before deciding how to handle them.

These observations guide experiments; no chunk size or parsing strategy has been validated yet.
