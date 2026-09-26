"""EVAL-3d2: sample_corpus, a small corpus from every source to try the baseline in a minute.

The full baseline is ~2.5 h. Before it, `--sample` runs the same code on a corpus small enough
to finish in about a minute: from each of the 9 sources, its first single-source questions, the
documents they expect, and a few random other documents from that source to search past. With
the defaults (3 questions, 20 others per source) that is 27 questions and 207 documents, the
first sample run: 822 chunks, recall@10 0.96. That number is not the baseline, since the
haystack is 207 documents, not 511,962; the sample proves the wiring, not the quality.

    >>> from pipeline.eval.questions import Question
    >>> slack = Question("qst_x", "basic", ("slack",), "Who approved the pin?", ("dsid_s1",))
    >>> questions, doc_ids = sample_corpus([slack], {"dsid_s1": "slack", "dsid_s2": "slack"}, 1, 1)
    >>> [q.question_id for q in questions], sorted(doc_ids)
    (['qst_x'], ['dsid_s1', 'dsid_s2'])
"""
import random
from collections import defaultdict
from typing import Dict, List, Sequence, Set, Tuple

from pipeline.eval.questions import Question


def sample_corpus(questions: Sequence[Question], doc_sources: Dict[str, str], questions_per_source: int = 3,
                  others_per_source: int = 20, seed: int = 0) -> Tuple[List[Question], Set[str]]:
    """`doc_sources` maps every doc_id in the corpus to its source_type."""
    single_source = defaultdict(list)
    for question in questions:
        if len(question.source_types) == 1:
            single_source[question.source_types[0]].append(question)
    picked = [question for source in sorted(single_source) for question in single_source[source][:questions_per_source]]
    doc_ids = {doc_id for question in picked for doc_id in question.expected_doc_ids}
    others = defaultdict(list)
    for doc_id in sorted(doc_sources):
        if doc_id not in doc_ids:
            others[doc_sources[doc_id]].append(doc_id)
    for source in sorted(others):
        doc_ids.update(random.Random(seed).sample(others[source], min(others_per_source, len(others[source]))))
    return picked, doc_ids
