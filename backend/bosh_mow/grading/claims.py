"""Claims on closed answers ("Je pense avoir juste", T5): Claude judges whether an
answer that the code found wrong is the expected one in another form (T6), on a single
criterion; the app concludes, as for an open answer."""

from typing import Any

from bosh_mow.grading.closed import parse_value
from bosh_mow.grading.open_answers import OpenQuestion


def claim_question(
    statement: str, form: str, content: dict[str, Any], answer: str
) -> OpenQuestion:
    """What Claude judges on a claim: whether the answer is the expected one, in an
    equivalent form; for a value, with what the app read in it and how far it is."""
    explanation = content.get("explanation") or ""
    if form == "value":
        expected = content["value"]
        read = parse_value(answer)
        if read is None:
            seen = "it read no number in the answer"
        elif expected == 0:
            seen = f"it read {read:g} in the answer"
        else:
            gap = abs(read - expected) / abs(expected) * 100
            seen = f"it read {read:g} in the answer, {gap:.1f} % away"
        criterion = (
            f"Gives the expected value, {expected:g}, in an equivalent form or as a"
            f" reasonable rounding (the app accepts {content['tolerance'] * 100:g} %"
            f" around it; {seen})"
        )
        return OpenQuestion(
            statement, f"{expected:g}. {explanation}".strip(), [criterion], []
        )
    if form == "short":
        criterion = (
            "Gives the expected answer, a synonym of it or an equivalent wording, in"
            " English or in French"
        )
        accepted = " / ".join(content["accepted"])
        return OpenQuestion(
            statement, f"{accepted}. {explanation}".strip(), [criterion], []
        )
    raise ValueError("Only a value or a short answer is claimed.")
