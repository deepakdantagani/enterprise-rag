"""PARSE-17: the heading truth set. Real clean files whose heading lines a person decided.

`headings` is what a reader calls a heading ({line: level}). `known_gaps` lists the
lines where today's design is knowingly wrong ({line: reason}): a false heading when
the line is not in `headings`, a missed one when it is.
"""
import json
from dataclasses import dataclass
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures/headings"


@dataclass(frozen=True)
class Truth:
    name: str
    source: str
    why: str
    text: str
    headings: dict[int, int]
    known_gaps: dict[int, str]


def load_truth() -> list[Truth]:
    expected = json.loads((FIXTURE_DIR / "expected.json").read_text(encoding="utf-8"))
    return [
        Truth(
            name=name,
            source=entry["source"],
            why=entry["why"],
            text=(FIXTURE_DIR / name).read_text(encoding="utf-8"),
            headings={int(line): level for line, level in entry["headings"].items()},
            known_gaps={int(line): reason for line, reason in entry["known_gaps"].items()},
        )
        for name, entry in sorted(expected.items())
    ]


def disagreements(reported: set[int], truth: Truth) -> list[str]:
    """Every line where `reported` and the truth differ, known gaps excused.

    A known gap that no longer differs is a problem too, so the list stays honest.
    """
    wrong = reported ^ set(truth.headings)
    problems = []
    for line in sorted(wrong | set(truth.known_gaps)):
        if line in wrong and line in truth.known_gaps:
            continue
        if line in truth.known_gaps:
            problems.append(f"{truth.name}:{line} now correct, remove this known gap")
        elif line in reported:
            problems.append(f"{truth.name}:{line} reported, not a heading")
        else:
            problems.append(f"{truth.name}:{line} is a heading, not reported")
    return problems
