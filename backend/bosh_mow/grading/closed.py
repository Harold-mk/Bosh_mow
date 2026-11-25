"""T5: grading of closed questions by the code, without AI, in a fraction of a second.

An MCQ compares the option chosen with the correct one; a value, the number given with
the one expected, within a tolerance; a short answer, the words given with each
accepted answer once both are cleaned, with one typo tolerated.
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

# A number once the spaces are removed and the comma became a point: "4", "-2.5", ".5",
# "1.5e-3".
_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_MINUS = chr(0x2212)  # the minus sign of the statements, as in "n − 1"
_UNIT_SIGNS = "%°€$£"  # what a unit starts with, besides a letter: "kg", "m/s²", "%"
_KEPT_SIGNS = "+#"  # not punctuation: "C", "C++" and "C#" are three answers
_TYPO_FROM = 4  # characters: in a shorter answer a typo changes it, "n-1" and "n-2"


@dataclass(frozen=True)
class Option:
    """An option of an MCQ, with the explanation shown after the answer (in French)."""

    text: str
    correct: bool
    explanation: str


def mcq_options(content: dict[str, Any]) -> list[Option]:
    """The options of an MCQ, from the content of its question."""
    return [
        Option(option["text"], option["correct"], option["explanation"])
        for option in content["options"]
    ]


def grade_mcq(options: Sequence[Option], chosen: int | None) -> bool:
    """Whether the option chosen (from 1) is the correct one; None, "Je ne sais pas",
    is wrong."""
    if chosen is None:
        return False
    if not 1 <= chosen <= len(options):
        raise ValueError(f"There is no option {chosen}.")
    return options[chosen - 1].correct


def parse_value(text: str) -> float | None:
    """The number given in an answer, None if it is not one. A comma or a point marks
    the decimals, spaces are ignored ("1 000"), a fraction is computed ("20/3") and a
    unit after the number is ignored ("2,5 kg")."""
    compact = "".join(text.split()).replace(",", ".").replace(_MINUS, "-")
    number = _NUMBER.match(compact)
    if number is None:
        return None
    value = float(number.group())
    rest = compact[number.end() :]
    if rest.startswith("/"):
        denominator = _NUMBER.match(rest, 1)
        if denominator is None or float(denominator.group()) == 0:
            return None
        value /= float(denominator.group())
        rest = rest[denominator.end() :]
    if rest and not (rest[0].isalpha() or rest[0] in _UNIT_SIGNS):
        return None  # "4^2", "4 * 2": not a number with its unit
    return value


def grade_value(
    expected: float, tolerance: float, answer: str, accepted: Sequence[str] = ()
) -> bool:
    """Whether the answer gives the expected value within the relative `tolerance`
    (0.01: 1 %); a value of 0 is given exactly. A wording accepted after a claim ("Je
    pense avoir juste") is right too."""
    value = parse_value(answer)
    margin = abs(expected) * tolerance * (1 + 1e-9)  # 4.04 stays within 1 % of 4
    if value is not None and abs(value - expected) <= margin:
        return True
    return any(_alike(answer, wording) for wording in accepted)


def grade_short(accepted: Sequence[str], answer: str) -> bool:
    """Whether the answer is one of the accepted answers once both are cleaned, with one
    typo tolerated: a letter missing, added or replaced, or two letters swapped. A typo
    on a digit is a mistake, and so is a typo in an answer under 4 characters."""
    return any(
        _alike(answer, one) or _one_typo_apart(clean(answer), clean(one))
        for one in accepted
    )


def clean(text: str) -> str:
    """An answer as it is compared: in lower case, without accents, spaces or
    punctuation ("Écart-type" becomes "ecarttype")."""
    letters = unicodedata.normalize("NFKD", text)  # "é": "e" and its accent; "²": "2"
    without_accents = "".join(c for c in letters if not unicodedata.combining(c))
    return "".join(
        c for c in without_accents.casefold() if c.isalnum() or c in _KEPT_SIGNS
    )


def _alike(answer: str, accepted: str) -> bool:
    """Whether two answers are the same once cleaned. An answer made only of signs,
    such as "!=", is compared as it is written, spaces and case aside."""
    expected = clean(accepted)
    if not expected:
        return _compact(answer) == _compact(accepted)
    return clean(answer) == expected


def _one_typo_apart(given: str, expected: str) -> bool:
    return (
        len(expected) >= _TYPO_FROM
        and _digits(given) == _digits(expected)
        and _typos(given, expected) <= 1
    )


def _digits(text: str) -> list[str]:
    return [c for c in text if c.isdigit()]


def _compact(text: str) -> str:
    return "".join(text.split()).casefold()


def _typos(a: str, b: str) -> int:
    """How many typos turn `a` into `b`: letters added, removed or replaced, and two
    neighbours swapped (the optimal string alignment distance)."""
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(
                d[i - 1][j] + 1,  # a letter removed
                d[i][j - 1] + 1,  # a letter added
                d[i - 1][j - 1] + (a[i - 1] != b[j - 1]),  # replaced, or the same
            )
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)  # two letters swapped
    return d[len(a)][len(b)]
