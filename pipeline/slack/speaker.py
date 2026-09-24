"""SLACK-7: read who spoke off the speaker line that opens a message.

The input is a message from `split_messages` (SLACK-6), or just its first line. SLACK-6 has
already decided the line opens a message, so this only reads its parts. It reuses SLACK-6's
SPEAKER_AT_LINE_START, so the two can never disagree on what a speaker line looks like.
Measured over the 5,741,020 messages:

    tom_ae:                   4,978,937   name only
    Aisha (CS):                 744,702   role in brackets
    Noah - AE:                   17,247   team after a dash, kept as the role
    Dan - HelixEdge (SI):           134   both; the role in brackets wins

Nothing is lost when the team is dropped: the speaker line stays in the message text.
Some lines are written team first (`Legal - Priya:`; roughly 800 by a first-name check, not
pinned); they are read as written, name `Legal`, since nothing in the line says which part
is the person. SLACK-8's truth set can measure how often that matters.

A bot is a speaker that one of BOT_RULES fires on; messages per rule, first rule that fires:

    name_ends_in_bot      deploy-bot, Incident Bot, DeployBot   573,157
    name_starts_with_bot  bot-ci, bot_deploy                        444
    role_is_bot           Front Desk (bot):                         196

No person named like a bot was found (`talbot: talbot (srebot) here` is a bot too); `Botty` and
`both` are not bots. About 114 bot messages are missed (`BotCI:`, `bench-bot-2:`,
`ops-bot FYI:`, `X - metrics-bot:`), 0.02% of bot messages. SLACK-6's `is_speaker` has its own,
narrower bot test (last word is `Bot`) for a different question: is this a label?

    >>> parse_speaker("Aisha (CS): Hey team")
    Speaker(name='Aisha', role='CS', is_bot=False)
    >>> parse_speaker("questionnaire-bot: Received nova-care_vra_2026.pdf")
    Speaker(name='questionnaire-bot', role=None, is_bot=True)
"""
from typing import NamedTuple, Optional

from pipeline.slack.messages import SPEAKER_AT_LINE_START

BOT_RULES = {  # rule name -> test on (name, role); checked in this order
    "name_ends_in_bot": lambda name, role: name.lower().endswith("bot"),
    "name_starts_with_bot": lambda name, role: name.lower().startswith(("bot-", "bot_")),
    "role_is_bot": lambda name, role: (role or "").lower() == "bot",
}


class Speaker(NamedTuple):
    name: str
    role: Optional[str]  # from (brackets), else from "- Team"; None if neither
    is_bot: bool


def parse_speaker(line: str) -> Speaker:
    """Name, role and bot flag of the speaker line at the start of line."""
    match = SPEAKER_AT_LINE_START.match(line)
    if match is None:
        raise ValueError(f"not a speaker line: {line[:60]!r}")
    role = match["role"] or match["team"]
    return Speaker(match["name"], role, bot_rule(match["name"], role) is not None)


def bot_rule(name: str, role: Optional[str]) -> Optional[str]:
    """The first of BOT_RULES that says this speaker is a bot, or None for a person.

    >>> bot_rule("Incident Bot", None), bot_rule("Front Desk", "bot"), bot_rule("Botty", None)
    ('name_ends_in_bot', 'role_is_bot', None)
    """
    return next((rule for rule, says_bot in BOT_RULES.items() if says_bot(name, role)), None)
