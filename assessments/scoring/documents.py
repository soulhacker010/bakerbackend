"""Reading an instrument's questions out of its source document.

Typing forty-eight questions by hand is where transcription errors come from, so
they are extracted instead. Extraction from prose is only safe when it can check
itself, so every extractor here verifies what it found against something the
document states independently — usually the question count written in the section
heading — and raises rather than returning a partial set.

The documents do not share a layout, so there is an extractor per shape rather
than one parser that guesses.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Sequence


class DocumentError(ValueError):
    """Raised when a document does not match the shape expected of it."""


@dataclass(frozen=True)
class ExtractedQuestion:
    number: int
    text: str
    section: str


# A heading that declares its own question count, e.g.
#   "Depression (5 questions, Score Range: 0–15)"
#   "Depression and Mood (6 questions, Score Range: 0–18)"
_COUNTED_HEADING = re.compile(
    r"^(?P<name>.+?)\s*\((?P<count>\d+)\s+questions?,\s*Score Range:",
    re.IGNORECASE,
)

# Lines that are never questions.
_SKIP = re.compile(
    r"^(scoring|instructions?|rating scale|administration|clinical notes|"
    r"interpretation|total score|subscale scores|purpose|time frame|"
    r"respondent|completion time|items)\b",
    re.IGNORECASE,
)


def _lines(text: str) -> List[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _looks_like_a_question(line: str) -> bool:
    if _SKIP.match(line):
        return False
    if _COUNTED_HEADING.match(line):
        return False
    # Answer options carry their own value in brackets or after a dash.
    if re.match(r"^\d+\s*[-–=]\s*\S", line):
        return False
    if re.match(r"^[☐•]\s", line):
        return False
    return len(line) > 12


def extract_by_counted_headings(text: str, expected: Sequence[tuple]) -> List[ExtractedQuestion]:
    """For documents whose section headings state how many questions follow.

    ``expected`` is ``(section key, count)`` in document order. Both the number of
    sections and each section's count are checked against the headings the
    document itself carries, so a layout change fails loudly instead of producing
    a plausible but wrong set.
    """
    lines = _lines(text)
    found: List[tuple] = []          # (heading name, declared count, index)
    for index, line in enumerate(lines):
        match = _COUNTED_HEADING.match(line)
        if match:
            found.append((match.group("name").strip(), int(match.group("count")), index))

    if len(found) != len(expected):
        raise DocumentError(
            f"Expected {len(expected)} sections but the document declares {len(found)}: "
            + ", ".join(name for name, _, _ in found)
        )

    questions: List[ExtractedQuestion] = []
    number = 0
    for (key, count), (name, declared, index) in zip(expected, found):
        if declared != count:
            raise DocumentError(
                f"Section {name!r} declares {declared} questions but {count} were expected."
            )
        collected: List[str] = []
        cursor = index + 1
        while cursor < len(lines) and len(collected) < declared:
            line = lines[cursor]
            if _COUNTED_HEADING.match(line):
                break
            if _looks_like_a_question(line):
                collected.append(line)
            cursor += 1

        if len(collected) != declared:
            raise DocumentError(
                f"Section {name!r} declares {declared} questions but {len(collected)} "
                "could be read from the document."
            )
        for entry in collected:
            number += 1
            questions.append(ExtractedQuestion(number=number, text=entry, section=key))

    return questions


def extract_by_numbered_sections(
    text: str,
    headings: Sequence[tuple],
    per_section: int,
) -> List[ExtractedQuestion]:
    """For documents with named section headings and a fixed number of items each.

    ``headings`` is ``(section key, heading text)`` in document order. Used where
    the heading does not state a count, so the count comes from the instrument's
    own scoring section instead and is checked per section.
    """
    lines = _lines(text)
    positions: List[tuple] = []
    for key, heading in headings:
        needle = heading.lower()
        index = next(
            (i for i, line in enumerate(lines) if line.lower().startswith(needle)),
            None,
        )
        if index is None:
            raise DocumentError(f"Could not find the section heading {heading!r}.")
        positions.append((key, index))

    if positions != sorted(positions, key=lambda item: item[1]):
        raise DocumentError("Section headings do not appear in the order given.")

    questions: List[ExtractedQuestion] = []
    number = 0
    for order, (key, index) in enumerate(positions):
        stop = positions[order + 1][1] if order + 1 < len(positions) else len(lines)
        collected = [
            line for line in lines[index + 1 : stop] if _looks_like_a_question(line)
        ][:per_section]

        if len(collected) != per_section:
            raise DocumentError(
                f"Section {key!r} should hold {per_section} questions but "
                f"{len(collected)} could be read from the document."
            )
        for entry in collected:
            number += 1
            questions.append(ExtractedQuestion(number=number, text=entry, section=key))

    return questions


def strip_leading_number(text: str) -> str:
    """Removes a leading "12." or "(R)" marker, keeping the question itself."""
    cleaned = re.sub(r"^\d+\.\s*", "", text)
    cleaned = re.sub(r"^\(R\)\s*", "", cleaned)
    return cleaned.strip()


def as_question_payload(
    questions: Sequence[ExtractedQuestion],
    options: Sequence[str],
    response_type: str = "likert",
) -> List[Dict]:
    """The shape the assessments API expects, ready to create."""
    return [
        {
            "identifier": f"q{question.number}",
            "order": question.number,
            "text": strip_leading_number(question.text),
            "help_text": "",
            "response_type": response_type,
            "required": True,
            "domain": question.section,
            "config": {"options": list(options), "domain": question.section},
        }
        for question in questions
    ]
