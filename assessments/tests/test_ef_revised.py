"""EF Adults and Adolescents, EFA-Revised format, held to Joe's 20 Oct 2026 answers.

Each item is how often (0-4) x how severe (0-2); Inhibitory Control and
Emotional Regulation are weighted x1.5; the total runs 0-288 in three levels.
"""
from django.test import SimpleTestCase

from assessments.models import AssessmentQuestion
from assessments.scoring import CardError, score_assessment
from assessments.scoring.executive_functioning import ef_revised
from assessments.scoring.loader import card_from_dict, card_to_dict
from assessments.scoring.validation import ERROR, achievable_range, validate_card

# Joe's labels carry their own numbers ("2-3 times/week"), so each option states its value.
FREQ_OPTIONS = [{"value": 0, "label": "Never"}, {"value": 1, "label": "Rarely (1 time/week or less)"},
                {"value": 2, "label": "Occasionally (2-3 times/week)"},
                {"value": 3, "label": "Frequently (4-5 times/week)"},
                {"value": 4, "label": "Almost Always (6 or more times/week)"}]
SEV_OPTIONS = [{"value": 0, "label": "Low (minimal disruption; manageable without intervention)"},
               {"value": 1, "label": "Moderate (noticeable disruption; requires redirection/support)"},
               {"value": 2, "label": "High (significant disruption; impacts task completion/social interactions)"}]
FREQ = [o["label"] for o in FREQ_OPTIONS]
SEV = [o["label"] for o in SEV_OPTIONS]
# Section membership, from the live assessment and the document.
SECTION = {}
for label, items in (("Planning/Organization", (1, 6, 18, 22, 25, 28)),
                     ("Emotional Regulation", (2, 8, 13, 17, 26, 30)),
                     ("Working Memory", (3, 5, 9, 11, 16, 21)),
                     ("Inhibitory Control", (4, 10, 12, 14, 20, 24)),
                     ("Cognitive Flexibility", (7, 15, 19, 23, 27, 29))):
    for n in items:
        SECTION[n] = label


def questions():
    built, order = [], 0
    for n in range(1, 31):
        for ident, options in ((f"q{n}", FREQ_OPTIONS), (f"q{n}_sev", SEV_OPTIONS)):
            order += 1
            built.append(AssessmentQuestion(
                identifier=ident, order=order, text=f"item {n}",
                response_type=AssessmentQuestion.ResponseType.LIKERT,
                config={"options": list(options)}, domain=SECTION[n],
            ))
    return built


class EfRevisedTests(SimpleTestCase):
    def setUp(self):
        self.card = ef_revised(questions())

    def score(self, freq, sev):
        answers = {}
        for n in range(1, 31):
            answers[f"q{n}"] = FREQ[freq(n)]
            answers[f"q{n}_sev"] = SEV[sev(n)]
        return score_assessment(self.card, answers)

    def test_card_is_sound(self):
        self.assertEqual([p.message for p in validate_card(self.card) if p.severity == ERROR], [])

    def test_the_documented_ranges(self):
        ranges = achievable_range(self.card)
        self.assertEqual(ranges["working_memory"], (0, 48))
        self.assertEqual(ranges["inhibitory_control"], (0, 72))
        self.assertEqual(ranges["emotional_regulation"], (0, 72))
        self.assertEqual(ranges["total"], (0, 288))
        self.assertEqual(ranges["frequency_total"], (0, 120))
        self.assertEqual(ranges["severity_total"], (0, 60))

    def test_an_item_scores_frequency_times_severity(self):
        # The document's example: item 1 at frequency 3, severity 1 scores 3.
        result = self.score(lambda n: 3 if n == 1 else 0, lambda n: 1 if n == 1 else 0)
        self.assertEqual(result.score("planning_organization").value, 3)
        self.assertEqual(result.score("frequency_total").value, 3)
        self.assertEqual(result.score("severity_total").value, 1)

    def test_weighted_sections(self):
        # The document's example: Inhibitory Control raw 20 -> weighted 30.
        ic = {4: (4, 2), 10: (4, 2), 12: (2, 1), 14: (1, 1), 20: (1, 1), 24: (0, 0)}  # 8+8+2+1+1 = 20
        result = self.score(lambda n: ic.get(n, (0, 0))[0], lambda n: ic.get(n, (0, 0))[1])
        self.assertEqual(result.score("inhibitory_control").value, 30)

    def test_most_severe_reaches_288_and_reads_significant(self):
        result = self.score(lambda n: 4, lambda n: 2)
        self.assertEqual(result.score("total").value, 288)
        self.assertEqual(result.score("total").band_id, "significant")
        self.assertEqual(result.score("inhibitory_control").band_id, "significant")
        self.assertTrue(any(f.id == "working_memory-significant" for f in result.flags))

    def test_frequency_with_no_severity_scores_zero(self):
        result = self.score(lambda n: 4, lambda n: 0)
        self.assertEqual(result.score("total").value, 0)
        self.assertEqual(result.score("total").band_id, "minimal")
        self.assertEqual(result.score("frequency_total").value, 120)

    def test_total_cut_offs(self):
        # 2 x 1 on every item: 12 per section; IC and ER weighted to 18. Total 72.
        result = self.score(lambda n: 2, lambda n: 1)
        self.assertEqual(result.score("total").value, 72)
        self.assertEqual(result.score("total").band_id, "minimal")
        # 4 x 1 everywhere: 24 per section, 36 weighted. Total 144: mild to moderate.
        result = self.score(lambda n: 4, lambda n: 1)
        self.assertEqual(result.score("total").value, 144)
        self.assertEqual(result.score("total").band_id, "mild-moderate")

    def test_an_item_with_only_one_answer_does_not_count(self):
        answers = {f"q{n}": FREQ[4] for n in range(1, 31)}
        answers.update({f"q{n}_sev": SEV[2] for n in range(1, 31)})
        del answers["q1_sev"]
        result = score_assessment(self.card, answers)
        self.assertEqual(result.score("planning_organization").status, "insufficient_data")

    def test_survives_being_stored_and_read_back(self):
        again = card_from_dict(card_to_dict(self.card))
        answers = {f"q{n}": FREQ[3] for n in range(1, 31)}
        answers.update({f"q{n}_sev": SEV[2] for n in range(1, 31)})
        self.assertEqual(score_assessment(again, answers).score("total").value,
                         score_assessment(self.card, answers).score("total").value)

    def test_refuses_a_missing_severity_partner(self):
        with self.assertRaises(CardError):
            ef_revised([q for q in questions() if q.identifier != "q5_sev"])
