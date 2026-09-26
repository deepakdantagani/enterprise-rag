"""GMAIL-7a: list the attachment file names written on labelled lines of a message.

Reads lines such as "Attachments: a.xlsx, b.docx" or "Attached: plan.pdf (application/pdf)".
Only file names are returned: prose ("Attached: sample invoice mock and mapping template"),
"none", sizes, versions and MIME types are not. Names on bracket lines and on bullet lines
below an empty label are GMAIL-7b. Pass the text after strip_quotes so a quoted copy of an
attachment line is not counted twice.
"""
import re

LABEL_LINE = re.compile(
    r"^\s*(?:[-*•]\s+)?(?:Attachments?(?:\(s\))?(?:\s+(?:referenced|included|stubs?))?|Attached)\s*:(?P<value>.*)$",
    re.IGNORECASE,
)
SEPARATORS = str.maketrans({character: " " for character in ',;()[]<>"\'“”‘’`'})
MIME_PREFIXES = ("application/", "text/", "image/", "audio/", "video/")
DOMAIN_ENDINGS = {"com", "net", "org", "io", "edu", "gov", "co", "app", "dev", "company"}
FILE_STEM = re.compile(r"[\w][\w\-]*(?:\.[\w\-]+)*")
TYPE_WRITTEN_IN_CAPITALS = re.compile(r"[A-Za-z.]+")  # "TAR.GZ" in "(TAR.GZ, 18MB)"


def attachment_names(text: str) -> list[str]:
    names: list[str] = []
    for line in text.split("\n"):
        match = LABEL_LINE.match(line)
        if match:
            names.extend(name for name in names_in(match["value"]) if name not in names)
    return names


def names_in(value: str) -> list[str]:
    names: list[str] = []
    for token in value.translate(SEPARATORS).split():
        name = file_name_of(token)
        if name and name not in names:
            names.append(name)
    return names


def file_name_of(token: str) -> str | None:
    """The file name a word stands for, or None: a name has a stem and a 2 to 8 character extension starting with a letter."""
    token = token.rstrip(".,:;")
    if "@" in token or token.lower().startswith(MIME_PREFIXES):
        return None
    name = token.rsplit("/", 1)[-1]
    stem, _, extension = name.rpartition(".")
    if not stem or not FILE_STEM.fullmatch(stem):
        return None
    if not extension[:1].isalpha() or not extension.isalnum() or not 2 <= len(extension) <= 8:
        return None
    if extension.lower() in DOMAIN_ENDINGS:
        return None
    if TYPE_WRITTEN_IN_CAPITALS.fullmatch(name) and name.isupper():
        return None
    return name
