"""The scoring card: how one assessment turns answers into results.

A card is plain data, not code. It is stored on the assessment and read by the
engine, so a new instrument means a new card rather than a new code path.

Everything here is deliberately free of Django imports. The card can be built
from a JSON blob, a dict typed into the editor, or a literal in a test, and the
engine can be exercised without a database.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence


class CardError(ValueError):
    """Raised when a card is malformed. Never raised for a respondent's answers."""


# --------------------------------------------------------------------------- #
# Questions
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class QuestionRule:
    """How one question contributes to scoring.

    ``scale_max`` is required whenever ``reverse`` is set, because reversing is
    ``scale_max - answer`` and different questions in the same assessment can sit
    on different scales. Return to Play uses 0-4 for items 9-22 and 0-10 for
    items 23-32.
    """

    identifier: str
    domain: Optional[str] = None
    weight: float = 1.0
    reverse: bool = False
    # Not every scale starts at zero. The ABA Caregiver Stress Assessment runs
    # 1-5, so its 13 items can never total less than 13, and bands written from
    # zero would leave the bottom of the range unreachable.
    scale_min: float = 0.0
    scale_max: Optional[float] = None
    # False for questions that are collected but must never reach a total, such
    # as the Sleep & Recovery red flags (items 16-22) or a free-text comment.
    scored: bool = True
    allow_na: bool = False
    # Only used by the threshold_count method: the answers that count as a hit.
    qualifying_values: Optional[frozenset] = None
    # Respondents submit the option text, not a number: live answers look like
    # "Moderate (2)" or "0 - Never". This maps every form an answer may arrive in
    # to the value it carries, so nothing has to be guessed at scoring time.
    options: Optional[Dict[str, float]] = None

    def __post_init__(self) -> None:
        if self.reverse and self.scale_max is None:
            raise CardError(
                f"Question {self.identifier!r} is reverse-scored, so scale_max must be set."
            )
        if self.weight == 0:
            raise CardError(
                f"Question {self.identifier!r} has weight 0. Use scored=False to exclude it, "
                "so the intent is explicit."
            )

    def value_of(self, answer: Any) -> Optional[float]:
        """The number an answer is worth, or None when it carries none.

        Deliberately refuses to dig a number out of arbitrary text. The engine
        this replaces ran a regular expression over every answer, so a written
        reply of "about 3 times a week" added 3 to a clinical total.
        """
        if self.options:
            if isinstance(answer, str):
                found = self.options.get(answer.strip())
                if found is None:
                    found = self.options.get(answer.strip().lower())
                if found is not None:
                    return found
            elif isinstance(answer, (int, float)) and not isinstance(answer, bool):
                return float(answer)
            return None

        if isinstance(answer, bool):
            return 1.0 if answer else 0.0
        if isinstance(answer, (int, float)):
            return float(answer)
        if isinstance(answer, str):
            try:
                return float(answer.strip())
            except ValueError:
                return None
        return None

    def contribution(self, answer: float) -> float:
        """The value this answer adds, after reversing and weighting."""
        value = float(answer)
        if self.reverse:
            # Documented in the source instruments as, for example, 0->3, 1->2,
            # 2->1, 3->0 on the EFAA.
            value = float(self.scale_max) - value
        return value * self.weight

    def max_contribution(self) -> float:
        """The most this question can add. Used to build the denominator."""
        return max(self._bounds())

    def min_contribution(self) -> float:
        """The least this question can add when it is answered at all."""
        return min(self._bounds())

    def _bounds(self) -> tuple:
        if self.scale_max is None:
            raise CardError(
                f"Question {self.identifier!r} needs scale_max to take part in a "
                "normalised or averaged score."
            )
        # Reversing turns the scale around, so the bounds swap with it: an item
        # answered at the top of a reversed 1-5 scale contributes zero, not five.
        low = self.contribution(self.scale_min)
        high = self.contribution(self.scale_max)
        return (low, high)


# --------------------------------------------------------------------------- #
# Bands
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Band:
    """One interpretation range. Both ends are inclusive."""

    id: str
    label: str
    minimum: float
    maximum: float
    description: str = ""

    def __post_init__(self) -> None:
        if self.minimum > self.maximum:
            raise CardError(f"Band {self.id!r} has minimum above maximum.")

    def contains(self, value: float) -> bool:
        return self.minimum <= value <= self.maximum


# --------------------------------------------------------------------------- #
# Transforms
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Transform:
    """Converts a raw figure onto the scale the instrument reports on.

    ``linear``     multiply then divide. Foot Health: (sum x 5) / 3 -> 0-100.
    ``normalize``  (raw / max possible) x ``to``. Return to Play scales every
                   domain onto 0-20 so the five add up to 0-100, and because the
                   denominator shrinks when items are marked N/A, this has to be
                   computed per submission rather than baked into the card.
    """

    kind: str  # "linear" | "normalize"
    multiply: float = 1.0
    divide: float = 1.0
    to: float = 1.0

    def __post_init__(self) -> None:
        if self.kind not in {"linear", "normalize"}:
            raise CardError(f"Unknown transform {self.kind!r}.")
        if self.divide == 0:
            raise CardError("Transform divide cannot be zero.")

    def apply(self, raw: float, max_possible: float) -> float:
        if self.kind == "linear":
            return raw * self.multiply / self.divide
        if max_possible == 0:
            # Caller guards this; returning 0 here would invent a score.
            raise CardError("Cannot normalise against a maximum of zero.")
        return (raw / max_possible) * self.to


# --------------------------------------------------------------------------- #
# Scores
# --------------------------------------------------------------------------- #

SUM = "sum"
AVERAGE = "average"
THRESHOLD_COUNT = "threshold_count"

EXCLUDE = "exclude"      # N/A leaves the calculation entirely, shrinking the denominator
AS_ZERO = "as_zero"      # N/A counts as zero


@dataclass(frozen=True)
class ScoreRule:
    """One number the assessment reports.

    An assessment produces several: a score per subscale plus an overall, and
    sometimes an overall derived from the subscales rather than from the answers
    (Return to Play sums its five domain scores; Mental Skills averages its eight
    domain averages).
    """

    id: str
    label: str
    method: str = SUM
    # Exactly one source must be given.
    domain: Optional[str] = None
    questions: Optional[Sequence[str]] = None
    scores: Optional[Sequence[str]] = None
    na_policy: str = EXCLUDE
    min_answered: int = 1
    transform: Optional[Transform] = None
    bands: Sequence[Band] = field(default_factory=tuple)
    precision: int = 2
    # The smallest step between two possible scores. Most instruments move in
    # whole numbers, so bands of 0-15 and 16-30 sit flush against each other.
    # The Postpartum screener weights items by 1.5 and lands on half points.
    granularity: float = 1.0
    # threshold_count only: how many qualifying answers make the screen positive.
    positive_at: Optional[int] = None

    def __post_init__(self) -> None:
        sources = [s for s in (self.domain, self.questions, self.scores) if s is not None]
        if len(sources) != 1:
            raise CardError(
                f"Score {self.id!r} must draw from exactly one of domain, questions or scores."
            )
        if self.method not in {SUM, AVERAGE, THRESHOLD_COUNT}:
            raise CardError(f"Score {self.id!r} has unknown method {self.method!r}.")
        if self.na_policy not in {EXCLUDE, AS_ZERO}:
            raise CardError(f"Score {self.id!r} has unknown na_policy {self.na_policy!r}.")
        if self.method == THRESHOLD_COUNT and self.positive_at is None:
            raise CardError(f"Score {self.id!r} counts thresholds, so positive_at is required.")
        if self.min_answered < 1:
            raise CardError(f"Score {self.id!r} must require at least one answer.")

    def band_for(self, value: float) -> Optional[Band]:
        for band in self.bands:
            if band.contains(value):
                return band
        return None


# --------------------------------------------------------------------------- #
# Flags
# --------------------------------------------------------------------------- #

INFO = "info"
REVIEW = "review"
URGENT = "urgent"

PATIENT = "patient"
CLINICIAN = "clinician"
BOTH = "both"


@dataclass(frozen=True)
class FlagRule:
    """A warning that fires independently of any total.

    Two shapes are needed. A question flag fires on the answers themselves, which
    is how the Postpartum screener raises "contact a healthcare provider
    immediately" from question 6 alone whatever the totals say. A score flag fires
    on a computed score, which is how Return to Play marks a domain below 15/20.
    """

    id: str
    message: str
    severity: str = REVIEW
    audience: str = CLINICIAN
    # Question flags
    questions: Optional[Sequence[str]] = None
    operator: str = ">="
    value: Optional[float] = None
    match: str = "any"  # "any" | "all"
    # Score flags
    score_id: Optional[str] = None

    _OPS = {
        ">=": lambda a, b: a >= b,
        ">": lambda a, b: a > b,
        "<=": lambda a, b: a <= b,
        "<": lambda a, b: a < b,
        "==": lambda a, b: a == b,
    }

    def __post_init__(self) -> None:
        if (self.questions is None) == (self.score_id is None):
            raise CardError(
                f"Flag {self.id!r} must watch either questions or one score, not both."
            )
        if self.value is None:
            raise CardError(f"Flag {self.id!r} needs a value to compare against.")
        if self.operator not in self._OPS:
            raise CardError(f"Flag {self.id!r} has unknown operator {self.operator!r}.")
        if self.severity not in {INFO, REVIEW, URGENT}:
            raise CardError(f"Flag {self.id!r} has unknown severity {self.severity!r}.")
        if self.audience not in {PATIENT, CLINICIAN, BOTH}:
            raise CardError(f"Flag {self.id!r} has unknown audience {self.audience!r}.")
        if self.match not in {"any", "all"}:
            raise CardError(f"Flag {self.id!r} has unknown match {self.match!r}.")

    def compare(self, value: float) -> bool:
        return self._OPS[self.operator](value, self.value)


# --------------------------------------------------------------------------- #
# The card
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ScoringCard:
    """Everything one assessment needs in order to be scored."""

    questions: Sequence[QuestionRule]
    scores: Sequence[ScoreRule] = field(default_factory=tuple)
    flags: Sequence[FlagRule] = field(default_factory=tuple)
    # Which score fills the headline figure a result is filed under. Left unset,
    # an overall or total is preferred, falling back to the last score declared.
    primary_score: Optional[str] = None
    # Printed on every report for this instrument, e.g. the Sleep & Recovery and
    # Return to Play statements that their cut-offs are provisional.
    standing_notice: str = ""

    def __post_init__(self) -> None:
        seen = set()
        for question in self.questions:
            if question.identifier in seen:
                raise CardError(f"Question {question.identifier!r} appears twice.")
            seen.add(question.identifier)

        score_ids = set()
        for score in self.scores:
            if score.id in score_ids:
                raise CardError(f"Score {score.id!r} appears twice.")
            score_ids.add(score.id)

        for score in self.scores:
            for identifier in score.questions or ():
                if identifier not in seen:
                    raise CardError(
                        f"Score {score.id!r} refers to unknown question {identifier!r}."
                    )
            for other in score.scores or ():
                if other not in score_ids:
                    raise CardError(f"Score {score.id!r} refers to unknown score {other!r}.")
                if other == score.id:
                    raise CardError(f"Score {score.id!r} refers to itself.")

        for flag in self.flags:
            for identifier in flag.questions or ():
                if identifier not in seen:
                    raise CardError(
                        f"Flag {flag.id!r} refers to unknown question {identifier!r}."
                    )
            if flag.score_id is not None and flag.score_id not in score_ids:
                raise CardError(f"Flag {flag.id!r} refers to unknown score {flag.score_id!r}.")

        # Resolve the dependency order now rather than at scoring time, so a card
        # that cannot be scored is refused when it is built instead of failing in
        # front of a respondent who has just filled the form in.
        self.ordered_scores()

    def primary(self) -> Optional[ScoreRule]:
        """The score a result is headlined by."""
        if not self.scores:
            return None
        if self.primary_score:
            for score in self.scores:
                if score.id == self.primary_score:
                    return score
            raise CardError(f"primary_score {self.primary_score!r} is not a score on this card.")
        for preferred in ("overall", "total"):
            for score in self.scores:
                if score.id == preferred:
                    return score
        return self.scores[-1]

    def question(self, identifier: str) -> Optional[QuestionRule]:
        for rule in self.questions:
            if rule.identifier == identifier:
                return rule
        return None

    def questions_for(self, score: ScoreRule) -> List[QuestionRule]:
        """The questions a score draws on, in card order, skipping unscored ones."""
        if score.questions is not None:
            wanted = list(score.questions)
            by_id = {q.identifier: q for q in self.questions}
            return [by_id[i] for i in wanted if by_id[i].scored]
        if score.domain is not None:
            return [q for q in self.questions if q.domain == score.domain and q.scored]
        return []

    def ordered_scores(self) -> List[ScoreRule]:
        """Scores sorted so that any score is computed after the ones it depends on."""
        remaining = list(self.scores)
        resolved: List[ScoreRule] = []
        done: set = set()
        while remaining:
            progressed = False
            for score in list(remaining):
                needs = set(score.scores or ())
                if needs <= done:
                    resolved.append(score)
                    done.add(score.id)
                    remaining.remove(score)
                    progressed = True
            if not progressed:
                stuck = ", ".join(sorted(s.id for s in remaining))
                raise CardError(f"Scores depend on each other in a loop: {stuck}")
        return resolved
