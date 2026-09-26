"""SLACK-9 (review fix): the clean Slack threads as LlamaIndex Documents, tagged with their dsid.

The docstore recognises a thread on a re-run by its Document id, so the id has to be the
thread's dsid (`a4e702bd...`) before the IngestionPipeline sees it: its cache recognises input
by text and metadata, not by id, so a wrong id slips past any check further down the line.

LlamaIndex's SimpleDirectoryReader does the reading; this only configures it and sets the id:
- only `.txt` files, so `_manifest.json` beside the threads is never read;
- only `file_name` as metadata. The reader's defaults (file_path, creation_date,
  last_modified_date, file_size) would make the Document's hash depend on where and when the
  file was copied, and the docstore would re-embed every thread after a re-copy or a move.

A `.txt` whose name is not a thread file name raises (thread.py's `id_and_slug`), before the
pipeline has touched any store.
"""
from pathlib import Path
from typing import Iterator

from llama_index.core import Document, SimpleDirectoryReader

from pipeline.slack.thread import id_and_slug

THREAD_FILE_SUFFIX = ".txt"


def thread_documents(clean_dir: Path, show_progress: bool = False) -> Iterator[Document]:
    """Each clean thread file in clean_dir as a Document whose id is its dsid, one at a time."""
    reader = SimpleDirectoryReader(
        input_dir=str(clean_dir), required_exts=[THREAD_FILE_SUFFIX], file_metadata=only_the_file_name,
        exclude_hidden=False,  # it counts a dotted folder anywhere in the path (.claude/worktrees/...)
    )                          # as hidden and finds no file; required_exts already skips .DS_Store
    for documents in reader.iter_data(show_progress=show_progress):
        for document in documents:
            document.id_ = id_and_slug(document.metadata["file_name"])[0]
            yield document


def only_the_file_name(path: str) -> dict:
    """The Document's metadata: its file name, nothing that depends on where the file sits."""
    return {"file_name": Path(path).name}
