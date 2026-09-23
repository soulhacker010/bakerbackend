"""Checks a card before it is allowed to be saved.

Three assessments on the live site return a number with no interpretation
attached, because the ranges written against them do not cover the scores their
questions can actually produce. The Executive Functioning assessment for adults
can reach 90 while its ranges stop at 36, and has a dead gap between 11 and 17.

Nobody noticed because the failure is silent: the respondent simply sees a score
with nothing beside it. So the check belongs at save time, where a person is
there to read it, rather than at scoring time in front of a patient.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .card import (
    AVERAGE,
    SUM,
    THRESHOLD_COUNT,
    CardError,
    ScoreRule,
    ScoringCard,
)

ERROR = "error"      # refuse to save
WARNING = "warning"  # allow, but say so


@dataclass(frozen=True)
class Problem:
    score_id: str
    severity: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - display helper
        return f"[{self.severity}] {self.score_id}: {self.message}"


def _round(value: float) -> float:
    # Ranges are compared, not reported, so a little tidying keeps floating point
    # noise out of the messages.
    return round(value, 6)


def _question_range(card: ScoringCard, score: ScoreRule) -> Optional[Tuple[float, float]]:
    rules = card.questions_for(score)
    if not rules:
        return None

    if score.method == THRESHOLD_COUNT:
        return (0.0, float(len(rules)))

    lows = [r.min_contribution() for r in rules]
    highs = [r.max_contribution() for r in rules]
    any_na = any(r.allow_na for r in rules)

    if score.method == AVERAGE:
        if any_na:
            # A respondent may answer only the single most extreme item, so the
            # average can reach that item's own bounds.
            return (min(lows), max(highs))
        return (sum(lows) / len(lows), sum(highs) / len(highs))

    high = sum(highs)
    if any_na:
        # Answer only the cheapest items the score will accept.
        low = sum(sorted(lows)[: score.min_answered])
    else:
        low = sum(lows)
    return (low, high)


def _apply_transform(score: ScoreRule, low: float, high: float) -> Tuple[float, float]:
    if score.transform is None:
        return (low, high)
    if score.transform.kind == "linear":
        return (
            score.transform.apply(low, high),
            score.transform.apply(high, high),
        )
    # Normalising divides by whatever the applicable maximum turns out to be, so
    # the top always lands on the target and the bottom scales with it.
    if high == 0:
        return (0.0, score.transform.to)
    return ((low / high) * score.transform.to, score.transform.to)


def achievable_range(card: ScoringCard) -> Dict[str, Tuple[float, float]]:
    """The lowest and highest value each score on the card can actually produce."""
    ranges: Dict[str, Tuple[float, float]] = {}

    for score in card.ordered_scores():
        if score.scores is not None:
            parts = [ranges[i] for i in score.scores if i in ranges]
            if not parts:
                continue
            lows = [p[0] for p in parts]
            highs = [p[1] for p in parts]
            if score.method == AVERAGE:
                low, high = sum(lows) / len(lows), sum(highs) / len(highs)
            else:
                low, high = sum(lows), sum(highs)
        else:
            found = _question_range(card, score)
            if found is None:
                continue
            low, high = found

        low, high = _apply_transform(score, low, high)
        ranges[score.id] = (_round(low), _round(high))

    return ranges


def validate_card(card: ScoringCard) -> List[Problem]:
    """Every reason this card should not be saved, worst first."""
    problems: List[Problem] = []
    ranges = achievable_range(card)

    for score in card.scores:
        if not score.bands:
            # A subscale reported as a raw figure is legitimate; the EFAA relies
            # on domain thresholds rather than bands.
            continue

        bands = sorted(score.bands, key=lambda b: (b.minimum, b.maximum))

        for earlier, later in zip(bands, bands[1:]):
            if later.minimum <= earlier.maximum:
                problems.append(Problem(
                    score.id, ERROR,
                    f"bands {earlier.id!r} and {later.id!r} overlap at "
                    f"{later.minimum:g}; a score there would match both and the "
                    f"first listed would silently win",
                ))
            elif later.minimum > earlier.maximum + _smallest_step(score):
                problems.append(Problem(
                    score.id, ERROR,
                    f"nothing covers {earlier.maximum:g} to {later.minimum:g}; a "
                    f"score in that gap returns no interpretation",
                ))

        window = ranges.get(score.id)
        if window is None:
            continue
        low, high = window
        covered_low = bands[0].minimum
        covered_high = bands[-1].maximum

        if covered_low > low:
            problems.append(Problem(
                score.id, ERROR,
                f"scores can go down to {low:g} but the lowest band starts at "
                f"{covered_low:g}",
            ))
        if covered_high < high:
            problems.append(Problem(
                score.id, ERROR,
                f"scores can reach {high:g} but the highest band stops at "
                f"{covered_high:g}; {_round(high - covered_high):g} points return "
                f"no interpretation",
            ))
        if covered_high > high:
            problems.append(Problem(
                score.id, WARNING,
                f"bands run to {covered_high:g} but the highest achievable score "
                f"is {high:g}, so the top band can never be reached",
            ))
        if covered_low < low:
            problems.append(Problem(
                score.id, WARNING,
                f"bands start at {covered_low:g} but the lowest achievable score "
                f"is {low:g}, so the bottom band can never be reached",
            ))

    problems.sort(key=lambda p: 0 if p.severity == ERROR else 1)
    return problems


def _smallest_step(score: ScoreRule) -> float:
    """How far apart two adjacent bands may sit before a real gap opens up.

    A gap exists only when a reachable score falls between two bands. On a
    whole-number scale, 0-15 followed by 16-30 leaves nothing uncovered, while
    0-10 followed by 18-24 strands everything from 11 to 17.
    """
    return score.granularity


def assert_valid(card: ScoringCard) -> None:
    """Raise if the card must not be saved. Warnings pass."""
    problems = [p for p in validate_card(card) if p.severity == ERROR]
    if problems:
        raise CardError(
            "This scoring card cannot be saved:\n"
            + "\n".join(f"  - {p.score_id}: {p.message}" for p in problems)
        )
