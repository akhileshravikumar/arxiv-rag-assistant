import re


TOKEN_PATTERN = re.compile(
    r"""
    [a-zA-Z0-9]+
    (?:[._+\-][a-zA-Z0-9]+)*
    """,
    re.VERBOSE,
)


def normalize_text(text: str) -> str:
    """
    Normalize text for lexical matching while preserving
    meaningful technical punctuation.
    """
    return " ".join(text.lower().split())


def tokenize_text(text: str) -> list[str]:
    """
    Convert text into lowercase lexical tokens.

    """
    normalized = normalize_text(text)

    return TOKEN_PATTERN.findall(normalized)