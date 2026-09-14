"""The one markdown-it parser, shared by headings.py and blocks.py.

Headings and blocks must come from the same parser configuration, or a table could
be one block in one view and three paragraphs in the other, and the chunker's line
ranges would disagree. One instance makes that impossible by construction.
"""
from markdown_it import MarkdownIt

MARKDOWN = MarkdownIt("commonmark").enable("table")
