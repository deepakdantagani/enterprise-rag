"""PARSE-4: the plain-label heading rule.

53% of clean files have headings with no markup: a short bare line such as
"Overview:" or "High-level design" with a blank line above it. This module flags
those lines. Two halves:

    shape       does this one line look like a label?          (4a, 4b)
    neighbours  is it in a place where a label can be?         (4c, 4d)

Pure module: it is handed lines and returns booleans.
"""
import re

SENTENCE_STARTER = re.compile(r"^(We|This|The|It|If|You|Use|All) ")
KEY_COLON_VALUE = re.compile(r"^[^:]{1,40}: (.+)$")                    # "Owner: Identity team ..."
LABEL_LIKE_KEY = re.compile(                                            # "Stage 4:", "Q:", "Appendix B:"
    r"^(?:[A-Za-z]+ ?\d+[A-Za-z]?|[A-Za-z]+ [A-Z]|Q|Step|Phase|Stage|Case|Pattern|Example|Issue"
    r"|Scenario|Week|Day|Option|Playbook|Mitigation|Appendix|Part|Section|Tier|Level|Note):", re.I)


def looks_like_a_sentence(line: str) -> bool:
    """Prose, not a label: starts like a sentence, or is a long clause with a comma.

    Input -> output:
        >>> looks_like_a_sentence("The service restarts on failure")
        True
        >>> looks_like_a_sentence("Manual triage is slow, remediation must be conservative, safe, and audited")
        True
        >>> looks_like_a_sentence("Testing, canaries and chaos simulation:")   # short: still a label
        False

    Edge cases:
        >>> looks_like_a_sentence("")
        False
    """
    has_comma_and_many_words = "," in line and len(line.split()) > 8
    return has_comma_and_many_words or SENTENCE_STARTER.match(line) is not None


def is_key_with_long_value(line: str) -> bool:
    """A field like "Owner: Identity and Access team ..." is data, not a heading.

    "Long" means the value has 6 or more words. Allowed as labels: a trailing colon
    ("Goals:"), a short value ("Appendix: Mappings"), or a label-like key
    ("Stage 4: ...", "Q: ...", "Appendix B: ...").

    Input -> output:
        >>> is_key_with_long_value("Owner: Identity and Access team second approver required")
        True
        >>> is_key_with_long_value("Goals:")
        False
        >>> is_key_with_long_value("Appendix: Example Mappings")
        False
        >>> is_key_with_long_value("Stage 4: Expand to Dedicated deployments today")
        False
        >>> is_key_with_long_value("Q: Can we extend a lease mid-window?")
        False

    Edge cases:
        >>> is_key_with_long_value("High-level design")     # no colon
        False
        >>> is_key_with_long_value("Owner: one two three four five")        # 5 words: short
        False
        >>> is_key_with_long_value("Owner: one two three four five six")    # 6 words: long
        True
    """
    if line.endswith(":") or LABEL_LIKE_KEY.match(line):
        return False
    match = KEY_COLON_VALUE.match(line)
    if match is None:
        return False
    return len(match.group(1).split()) >= 6
