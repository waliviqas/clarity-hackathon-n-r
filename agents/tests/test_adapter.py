"""Spotter answer -> detection: name mapping, honesty about missing numbers, contract validity.

    python -m unittest discover -s agents/tests -t .
"""
import unittest

from agents.adapter import activity_of, appearance_text, crime_to_activity, to_detection
from agents.matching import features
from contracts.validate import check

SNATCH = {"what_happened": "suspect grabs a phone from a man at the bus stop and runs", "on_screen": "crime",
          "crime": "stealing", "build": "slim", "height": "average", "shirt": "black hoodie",
          "pants": "dark grey pants", "shoes": "black sneakers", "glasses": "no", "headwear": "none",
          "hair": "curly dark", "bag": "none", "weapon": "none", "vehicle": "none"}
EMPTY = {"what_happened": "two people walk past", "on_screen": "none", "crime": "none", "build": "unknown",
         "height": "unknown", "shirt": "none", "pants": "none", "shoes": "none", "glasses": "unknown",
         "headwear": "none", "hair": "none", "bag": "none", "weapon": "none", "vehicle": "none"}


def detection(answer):
    return to_detection(answer, event_id="det_x_1", track_id="trk_x_1", camera_id="cam_01", ts=10.25,
                        window=(1.75, 10.25), run_id="run_test", extra={"spotter_model": "m"})


class CrimeNames(unittest.TestCase):
    def test_spotter_names_map_to_the_contract(self):
        self.assertEqual(crime_to_activity("stabbing"), "stabbing")
        self.assertEqual(crime_to_activity("assault"), "fistfight")
        self.assertEqual(crime_to_activity("stealing"), "purse_snatch")
        self.assertEqual(crime_to_activity("none"), "none")

    def test_anything_else_is_none(self):
        for odd in ("robbery", "", None, "fleeing", 3):
            self.assertEqual(crime_to_activity(odd), "none")

    def test_case_and_contract_names(self):
        self.assertEqual(crime_to_activity(" Assault "), "fistfight")
        self.assertEqual(crime_to_activity("purse_snatch"), "purse_snatch")

    def test_activity_only_on_the_camera_that_sees_the_crime(self):
        self.assertEqual(activity_of({"on_screen": "crime", "crime": "stealing"}), "purse_snatch")
        self.assertEqual(activity_of({"on_screen": "fleeing", "crime": "stealing"}), "none")
        self.assertEqual(activity_of({"on_screen": "none", "crime": "assault"}), "none")
        self.assertEqual(activity_of({"on_screen": "crime", "crime": "none"}), "none")


class Detection(unittest.TestCase):
    def test_valid_contract_event(self):
        for answer in (SNATCH, EMPTY, {}, {"on_screen": "crime", "crime": "assault", "shirt": 7}):
            self.assertEqual(check(detection(answer)), [], answer)

    def test_no_invented_numbers(self):
        d = detection(SNATCH)
        self.assertEqual(d["confidence"], 0.5)  # contract requires a number; flagged as not known
        self.assertIs(d["confidence_known"], False)
        self.assertNotIn("activity_confidence", d)
        self.assertIsNone(d["direction"])
        self.assertIsNone(d["bbox"])

    def test_fields_from_the_answer(self):
        d = detection(SNATCH)
        self.assertEqual((d["activity"], d["camera_id"], d["ts"]), ("purse_snatch", "cam_01", 10.25))
        self.assertEqual((d["on_screen"], d["spotter_crime"]), ("crime", "stealing"))
        self.assertEqual(d["what_happened"], SNATCH["what_happened"])
        self.assertEqual(d["window_ts"], [1.75, 10.25])
        self.assertEqual((d["run_id"], d["source"], d["spotter_model"]), ("run_test", "agents", "m"))


class Appearance(unittest.TestCase):
    def test_only_what_was_seen(self):
        self.assertEqual(appearance_text(features(SNATCH)),
                         "slim build, average height, black hoodie, dark grey pants, black sneakers, curly dark hair")

    def test_nothing_seen_is_null(self):
        self.assertIsNone(appearance_text(features(EMPTY)))

    def test_items_and_glasses(self):
        feats = features({"glasses": "yes", "headwear": "red cap", "bag": "none", "vehicle": "blue bike"})
        self.assertEqual(appearance_text(feats), "glasses, red cap, vehicle: blue bike")


if __name__ == "__main__":
    unittest.main()
