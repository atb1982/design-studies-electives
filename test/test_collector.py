"""Offline tests: run the parsers against pages saved from the real sites.
Run with:  python -m unittest discover -s test -v
"""
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import collector as C  # noqa: E402

SAMPLES = ROOT / "test-samples"


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = C.parse_catalog((SAMPLES / "catalog-design-studies-ba.html").read_text(encoding="utf-8"))

    def test_course_count(self):
        self.assertGreaterEqual(len(self.cat), 300)

    def test_list_membership(self):
        self.assertEqual(self.cat["ADN 219"]["lists"], ["Application Unit"])
        self.assertIn("Design History", self.cat["GD 203"]["lists"])
        self.assertIn("Theory Unit", self.cat["D 492"]["lists"])

    def test_cross_listed_code_uses_world_language_subject(self):
        self.assertIn("WLJA 351", self.cat)
        self.assertNotIn("ANT 351", self.cat)

    def test_wildcards_and_group_labels_are_skipped(self):
        self.assertFalse([k for k in self.cat if "*" in k or k.startswith(("WL ", "Humanities"))])

    def test_title_whitespace_is_normalized(self):
        self.assertTrue(all("  " not in c["title"] for c in self.cat.values()))


class SearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        html = json.loads((SAMPLES / "search-ADN-2271.json").read_text(encoding="utf-8"))["html"]
        cls.found = C.parse_search(html)

    def test_sections_for_digital_imaging(self):
        secs = self.found["ADN 219"]["sections"]
        self.assertEqual([s["section"] for s in secs], ["601", "602"])
        first = secs[0]
        self.assertEqual((first["status"], first["left"], first["cap"]), ("Open", 50, 50))
        self.assertEqual(first["instructor"], "Fitzgerald, Patrick J")
        self.assertEqual(first["location"], "Distance Education - Online")
        self.assertEqual(first["dates"], "01/11/27 - 04/27/27")
        self.assertIn("DS majors", first["restrictions"])

    def test_meeting_days_are_readable(self):
        times = [s["time"] for course in self.found.values() for s in course["sections"]]
        self.assertFalse([t for t in times if "meets" in t])
        self.assertTrue(any(t[:2] in ("MW", "TT", "M ", "T ", "W ", "F ") or t.startswith("Th") for t in times if t != "TBD"))

    def test_wanted_filter(self):
        html = json.loads((SAMPLES / "search-ADN-2271.json").read_text(encoding="utf-8"))["html"]
        self.assertEqual(set(C.parse_search(html, {"ADN 219"})), {"ADN 219"})

    def test_availability(self):
        self.assertEqual(C.parse_availability("Closed / 0/51"), {"status": "Closed", "left": 0, "cap": 51})
        self.assertEqual(C.parse_availability("Waitlist"), {"status": "Waitlist", "left": None, "cap": None})


class TermTests(unittest.TestCase):
    def test_candidates_from_october(self):
        ids = [t["id"] for t in C.candidate_terms(date(2026, 10, 7))]
        self.assertEqual(ids, ["2268", "2271", "2276", "2277", "2278"])

    def test_candidates_from_february(self):
        ids = [t["id"] for t in C.candidate_terms(date(2027, 2, 1))]
        self.assertEqual(ids[:3], ["2271", "2276", "2277"])
        self.assertEqual(ids[-1], "2288")

    def test_start_date(self):
        self.assertEqual(C.start_date("08/17/26 - 12/01/26"), "2026-08-17")


class CsvTests(unittest.TestCase):
    def test_rows(self):
        data = json.loads((ROOT / "data" / "electives.json").read_text(encoding="utf-8"))
        text = C.to_csv(data)
        lines = text.strip().split("\r\n")
        self.assertTrue(lines[0].lstrip("﻿").startswith('"Course","Title"'))
        sections = sum(len(v) for c in data["courses"] for v in c["terms"].values())
        never = sum(1 for c in data["courses"] if not c["terms"])
        self.assertEqual(len(lines) - 1, sections + never)



class SupplementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = json.loads((SAMPLES / "search-DS-2268.json").read_text(encoding="utf-8"))["html"]
        cls.sup = C.load_supplement(ROOT / "supplement.json")
        cls.cat = C.parse_catalog((SAMPLES / "catalog-design-studies-ba.html").read_text(encoding="utf-8"))

    def test_supplement_file_lists_the_advisor_courses(self):
        codes = [c["code"] for c in self.sup["courses"]]
        for code in ("DS 492", "DS 292", "DS 451", "D 231", "D 292", "D 492"):
            self.assertIn(code, codes)

    def test_merge_adds_only_courses_missing_from_catalog(self):
        cat = dict(self.cat)
        added = C.merge_supplement(cat, self.sup)
        self.assertEqual(added, {"DS 492", "DS 292", "DS 451", "D 231"} - set(self.cat))
        self.assertIn("DS 492", added)
        self.assertEqual(cat["DS 492"]["lists"], [self.sup["label"]])
        self.assertNotIn("D 492", added)                 # already a Theory Unit elective
        self.assertNotIn(self.sup["label"], cat["D 492"]["lists"])

    def test_course_heading_gives_title_and_credit_range(self):
        found = C.parse_search(self.html)
        self.assertEqual((found["DS 492"]["title"], found["DS 492"]["credits"]), ("Special Topics in Design Studies", "1-6"))
        self.assertEqual(found["DS 451"]["credits"], "3")

    def test_special_topics_sections_carry_topic_and_restrictions(self):
        secs = C.parse_search(self.html, {"DS 492"})["DS 492"]["sections"]
        self.assertGreaterEqual(len(secs), 2)
        self.assertTrue(all(s["topic"] for s in secs))
        self.assertIn("Departmental Approval Required", secs[0]["restrictions"])
        self.assertEqual(secs[0]["time"], "W 1:30 PM-4:15 PM")


class CatalogDetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ds = C.parse_course_pages((SAMPLES / "catalog-courses-ds.html").read_text(encoding="utf-8"))
        cls.jp = C.parse_course_pages((SAMPLES / "catalog-courses-flj.html").read_text(encoding="utf-8"))

    def test_description_prerequisite_and_offering(self):
        d = self.ds["DS 451"]
        self.assertEqual(d["t"], "Design Writing: Insight and Critique")
        self.assertEqual(d["h"], "3 credit hours")
        self.assertTrue(d["d"].startswith("This course will use writing to evaluate"))
        self.assertEqual(d["p"], "ENG 101 and Sophomore Standing or above.")
        self.assertEqual(d["o"], "in Fall and Spring")
        self.assertEqual(d["n"], [])

    def test_prerequisite_label_is_removed(self):
        self.assertFalse(self.ds["DS 100"]["p"].startswith("Prerequisite"))

    def test_cross_listed_course_is_filed_under_every_code(self):
        self.assertIn("WLJA 351", self.jp)
        self.assertIn("ANT 351", self.jp)
        self.assertEqual(self.jp["WLJA 351"]["t"], "Contemporary Culture in Japan")

    def test_extra_notes_are_kept(self):
        notes = [n for d in self.jp.values() for n in d["n"]]
        self.assertTrue(any("GEP" in n for n in notes))

    def test_fresh_file_is_not_collected_again(self):
        import tempfile
        from datetime import date
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalog.json"
            path.write_text(json.dumps({"collected": date.today().isoformat(), "checked": ["DS 451"], "courses": {}}))
            C.get_course_page = lambda subject: self.fail("should not fetch")
            C.refresh_catalog_details(path, ["DS 451"], ["DS"])    # fresh and complete, so nothing is fetched


if __name__ == "__main__":
    unittest.main()
