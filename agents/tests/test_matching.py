"""Description matching, travel-time checks and combining weak sightings (agents/matching.py)."""
import unittest

from agents.matching import (MATCH_AT, check_timing, combine, compare, features, field_agreement, judge, merge,
                             sighting_probability, text_agreement)

SUSPECT = features({"build": "slim", "height": "average", "shirt": "black hoodie", "pants": "dark grey pants",
                    "shoes": "black sneakers", "glasses": "no", "hair": "curly dark", "headwear": "none",
                    "bag": "none", "weapon": "none", "vehicle": "none"})
LEFT = (1.75, 10.25)   # clip 8 cam_01 on the run clock
SEEN = (11.25, 14.55)  # clip 8 cam_02


def answer(on_screen="fleeing", **fields):
    return {"what_happened": "someone", "on_screen": on_screen, "crime": "none", **fields}


class Features(unittest.TestCase):
    def test_unknown_and_filler_none_are_dropped(self):
        f = features({"shirt": "none", "pants": "unknown", "hair": "", "build": "unknown", "glasses": "no",
                      "headwear": "none", "bag": "No bag", "weapon": "nothing"})
        self.assertEqual(f, {"glasses": "no", "headwear": "none", "bag": "none", "weapon": "none"})


class Agreement(unittest.TestCase):
    def test_same_words_or_synonyms(self):
        self.assertEqual(text_agreement("black hoodie", "black hooded sweatshirt"), 1.0)
        self.assertEqual(text_agreement("grey jeans", "gray denim"), 1.0)
        self.assertEqual(text_agreement("dark grey pants", "black trousers"), 1.0)  # "dark" can be black

    def test_different(self):
        self.assertEqual(text_agreement("black hoodie", "red jacket"), 0.0)
        self.assertEqual(text_agreement("hoodie", "jacket"), 0.0)

    def test_same_colour_other_item_is_half(self):
        self.assertEqual(text_agreement("black hoodie", "black jacket"), 0.5)

    def test_nothing_comparable(self):
        self.assertIsNone(text_agreement("black", "hoodie"))

    def test_levels_glasses_and_items(self):
        self.assertEqual(field_agreement("build", "slim", "average"), 0.5)
        self.assertEqual(field_agreement("build", "slim", "heavy"), 0.0)
        self.assertEqual(field_agreement("glasses", "yes", "no"), 0.0)
        self.assertIsNone(field_agreement("bag", "none", "none"))
        self.assertEqual(field_agreement("bag", "none", "red backpack"), 0.0)

    def test_unknown_never_counts_against(self):
        self.assertEqual(compare(SUSPECT, {}), {})
        self.assertAlmostEqual(sighting_probability({}, "fleeing"), 0.5, places=2)  # behaviour only
        thin = compare(SUSPECT, features({"shirt": "black hoodie", "pants": "unknown"}))
        self.assertEqual(thin, {"shirt": 1.0})


class Combining(unittest.TestCase):
    def test_five_weak_sightings_beat_one_at_sixty(self):
        self.assertGreater(combine([0.2] * 5), 0.6)
        self.assertAlmostEqual(combine([0.5, 0.5]), 0.75)
        self.assertEqual(combine([]), 0.0)


class Timing(unittest.TestCase):
    def test_clip8_link_fits(self):
        ok, words = check_timing(LEFT, SEEN, 3.0, "cam_01")
        self.assertTrue(ok, words)

    def test_too_soon(self):
        ok, words = check_timing((0.0, 10.0), (10.0, 12.0), 60.0, "cam_01")
        self.assertFalse(ok)
        self.assertIn("Too soon", words)

    def test_too_late(self):
        ok, words = check_timing(LEFT, (500.0, 505.0), 3.0, "cam_01")
        self.assertFalse(ok)
        self.assertIn("Too late", words)

    def test_unknown_link_allows_two_minutes(self):
        self.assertTrue(check_timing(LEFT, (100.0, 104.0), None, "cam_01")[0])
        self.assertFalse(check_timing(LEFT, (200.0, 204.0), None, "cam_01")[0])


class Judge(unittest.TestCase):
    def test_same_description_is_a_match(self):
        same = answer(build="slim", shirt="black hoodie", pants="dark grey pants", hair="curly dark")
        j = judge(SUSPECT, same, LEFT, SEEN, 3.0, "cam_01")
        self.assertEqual(j.decision, "match")
        self.assertGreaterEqual(j.confidence, MATCH_AT)
        self.assertLessEqual(j.confidence, 0.95)
        self.assertTrue(j.keep_following)
        self.assertIn("match", j.reason)

    def test_different_shirt_is_no_match(self):
        j = judge(SUSPECT, answer(shirt="red jacket", pants="blue jeans"), LEFT, SEEN, 3.0, "cam_01")
        self.assertEqual(j.decision, "no_match")
        self.assertFalse(j.keep_following)

    def test_running_with_no_description_is_uncertain_and_followed(self):
        j = judge(SUSPECT, answer(shirt="none", pants="none"), LEFT, SEEN, 3.0, "cam_01")
        self.assertEqual(j.decision, "uncertain")
        self.assertTrue(j.keep_following)

    def test_calm_partial_match_is_uncertain_but_not_followed(self):
        calm = answer("none", shirt="black hoodie", hair="curly dark", pants="blue jeans")
        j = judge(SUSPECT, calm, LEFT, SEEN, 3.0, "cam_01")
        self.assertEqual(j.decision, "uncertain")
        self.assertFalse(j.keep_following)

    def test_nothing_seen_is_no_match(self):
        j = judge(SUSPECT, answer("none"), LEFT, SEEN, 3.0, "cam_01")
        self.assertEqual(j.decision, "no_match")

    def test_impossible_travel_time_drops_a_perfect_match(self):
        same = answer(build="slim", shirt="black hoodie", pants="dark grey pants")
        j = judge(SUSPECT, same, (0.0, 10.0), (10.0, 12.0), 60.0, "cam_01")
        self.assertEqual(j.decision, "no_match")
        self.assertIn("Too soon", j.reason)

    def test_weak_sightings_add_up(self):
        thin = answer(hair="curly dark", build="heavy")  # one feature agrees, one differs: 50% alone
        alone = judge(SUSPECT, thin, LEFT, SEEN, 3.0, "cam_01")
        self.assertEqual(alone.decision, "uncertain")
        after_weak = judge(SUSPECT, thin, LEFT, SEEN, 3.0, "cam_01", earlier_weak=[("cam_02", alone.sighting)])
        self.assertEqual(after_weak.decision, "match")
        self.assertGreater(after_weak.probability, alone.probability)
        self.assertIn("cam_02", after_weak.reason)

    def test_generic_fields_alone_never_match(self):
        # glasses / height agree for most people, so they can't be the agreeing feature (reviewer repro: p=0.62)
        for thin in (answer(glasses="no"), answer(height="average"), answer(glasses="no", height="average")):
            for weak in ([], [("cam_02", 0.5)] * 5):
                j = judge(SUSPECT, thin, LEFT, SEEN, 3.0, "cam_01", earlier_weak=weak)
                self.assertNotEqual(j.decision, "match")

    def test_no_agreeing_feature_is_never_a_match(self):
        # Two people running with no description used to add up to 75%, a "match" on behaviour alone.
        for thin in (answer(shirt="none"), answer(build="average")):  # nothing to compare / only "close"
            for weak in ([("cam_02", 0.5)], [("cam_02", 0.5)] * 5):
                j = judge(SUSPECT, thin, LEFT, SEEN, 3.0, "cam_01", earlier_weak=weak)
                self.assertEqual(j.decision, "uncertain")
                self.assertLess(j.probability, MATCH_AT)
                self.assertLessEqual(j.confidence, 0.5)
                self.assertIn("don't add up", j.reason)
        self.assertEqual(judge(SUSPECT, answer(shirt="none"), LEFT, SEEN, 3.0, "cam_01").decision, "uncertain")

    def test_reason_fits_the_contract(self):
        long_text = answer(shirt="black " * 100)
        self.assertLessEqual(len(judge(SUSPECT, long_text, LEFT, SEEN, 3.0, "cam_01").reason), 300)


class Merge(unittest.TestCase):
    def test_fills_unknowns_never_overwrites(self):
        self.assertEqual(merge({"shirt": "black hoodie"}, {"shirt": "red jacket", "hair": "curly"}),
                         {"shirt": "black hoodie", "hair": "curly"})


if __name__ == "__main__":
    unittest.main()
