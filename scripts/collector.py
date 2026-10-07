#!/usr/bin/env python3
"""Collects the Design Studies BA elective lists and the sections NC State Class Search shows for them.

Usage:  python scripts/collector.py
Writes data/electives.json and data/electives.csv. The "generated" time is the moment of collection.
Once a week it also refreshes data/catalog.json, the catalog description of each course.

The parsing functions (parse_catalog, parse_search, parse_course_pages, candidate_terms, to_csv) do no
network access, so tests can run them against saved pages.
"""
import copy
import csv
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

CATALOG_URL = "https://catalog.ncsu.edu/undergraduate/design/art-design/design-studies-ba/"
SEARCH_URL = "https://webappprd.acs.ncsu.edu/php/coursecat/search.php"
COURSE_PAGE_URL = "https://catalog.ncsu.edu/course-descriptions/{}/"
CATALOG_MAX_AGE_DAYS = 7
HEADERS = {"User-Agent": "design-studies-elective-finder (GitHub Actions, public course data)"}
CONCURRENCY = 3   # keep the load on NC State's servers small
PAUSE_SECONDS = 0.15

# Catalog headings that hold elective lists, mapped to the label shown on the site.
LISTS = {
    "Advanced Writing Electives": "Advanced Writing",
    "Humanities Electives": "Humanities",
    "Intermediate World Languages, Literature and Culture Electives": "World Language",
    "Art History Survey Electives": "Art History Survey",
    "Design History Electives": "Design History",
    "Application Unit Electives": "Application Unit",
    "Theory Unit Electives": "Theory Unit",
    "History Unit Electives": "History Unit",
    "Advised Electives": "Advised (general)",
}
# Catalog course pages are named by the lowercase subject code, except for the world language subjects.
PAGE_NAME = {"WLAR": "fla", "WLCH": "flc", "WLFR": "flf", "WLGE": "flg", "WLGR": "grk", "WLHU": "fln", "WLIT": "fli",
             "WLJA": "flj", "WLLA": "lat", "WLPE": "per", "WLPO": "flp", "WLRU": "flr", "WLSP": "fls"}
DAY = {"Sunday": "Su", "Monday": "M", "Tuesday": "T", "Wednesday": "W", "Thursday": "Th", "Friday": "F", "Saturday": "Sa"}


def squash(text):
    return re.sub(r"\s+", " ", text.replace(" ", " ")).strip()


def soup_of(html):
    return BeautifulSoup(html, "html.parser")


# ---------------------------------------------------------------- catalog

def parse_catalog(html):
    """Returns {'ADN 219': {'title', 'credits', 'lists': [...]}}.
    Group labels and wildcard rows such as 'WL 2**' are skipped."""
    soup = soup_of(html)
    courses = {}
    for h in soup.find_all("h3"):
        label = LISTS.get(squash(h.get_text()))
        if not label:
            continue
        el, table = h.find_next_sibling(), None
        while el is not None and el.name != "h3":
            table = el if el.name == "table" else el.find("table")
            if table is not None:
                break
            el = el.find_next_sibling()
        if table is None:
            continue
        for tr in table.find_all("tr"):
            td = tr.find_all("td", recursive=False)
            if len(td) < 2:
                continue
            m = re.match(r"^([A-Z]{1,4}(?:/[A-Z]{1,4})?)\s+(\d{3})$", squash(td[0].get_text()))
            if not m:
                continue
            subject = m.group(1).split("/")[-1]   # 'ANT/WLJA 351' is filed under WLJA
            key = f"{subject} {m.group(2)}"
            title = squash(td[1].get_text())
            credits = squash(td[2].get_text()) if len(td) > 2 else ""
            entry = courses.setdefault(key, {"title": title, "credits": credits, "lists": []})
            if not entry["title"] and title:
                entry["title"] = title
            if label not in entry["lists"]:
                entry["lists"].append(label)
    return courses


# ---------------------------------------------------------------- class search

def cell_text(el):
    c = copy.copy(el)
    for br in c.find_all("br"):
        br.replace_with(" / ")
    for x in c.select(".popover-close, .screen-reader-only-text"):
        x.decompose()
    return squash(c.get_text())


def time_text(el):
    ul = el.select_one("ul.weekdisplay")
    if ul is None:
        return cell_text(el)
    days = "".join(DAY.get((a.get("title") or "").replace(" - meet", ""), "?") for a in ul.select("li.meet abbr"))
    c = copy.copy(el)
    for x in c.select("ul, .visible-xs, .print-only"):
        x.decompose()
    clock = re.sub(r"\s*-\s*", "-", squash(c.get_text()), count=1)
    return f"{days} {clock}".strip()


def parse_availability(text):
    """'Open / 2/18' -> status 'Open', 2 seats left of 18."""
    m = re.match(r"^(.*?)\s*/\s*(\d+)/(\d+)$", text)
    if m:
        return {"status": m.group(1) or "Unknown", "left": int(m.group(2)), "cap": int(m.group(3))}
    return {"status": text, "left": None, "cap": None}


def parse_search(html, wanted=None):
    """Reads one Class Search response (its 'html' field).
    Returns {'ADN 219': {'title', 'credits', 'sections': [section, ...]}}.
    Pass `wanted` (a set of course keys) to keep only electives."""
    soup = soup_of(html)
    out = {}
    for sec in soup.select("section.course"):
        key = (sec.get("id") or "").replace("-", " ", 1)
        if wanted is not None and key not in wanted:
            continue
        small, units = sec.select_one("h1 small"), sec.select_one("h1 .units")
        credits = re.sub(r"\s*-\s*", "-", re.sub(r"^Units:\s*", "", squash(units.get_text()))) if units else ""
        sections = []
        for tr in sec.select("table tr"):
            td = tr.find_all("td", recursive=False)
            if not td:
                continue
            if len(td) >= 8:
                req = tr.select_one('a[id^="reqs-"]')
                req_text = squash(soup_of(f"<div>{req.get('data-content') or ''}</div>").get_text(" ")) if req else ""
                sections.append({
                    "section": cell_text(td[0]),
                    "component": cell_text(td[1]),
                    **parse_availability(cell_text(td[3])),
                    "time": time_text(td[4]),
                    "location": cell_text(td[5]),
                    "instructor": re.sub(r",\s*", ", ", cell_text(td[6]), count=1),
                    "dates": cell_text(td[7]),
                    "topic": cell_text(td[8]) if len(td) > 8 else "",
                    "restrictions": re.sub(r"^(Restriction|R):\s*", "", req_text),
                })
            elif sections:
                # Extra meeting pattern for the previous section, such as a second day and time.
                wk = next((x for x in td if x.select_one("ul.weekdisplay")), None)
                rest = " ".join(cell_text(x) for x in td if x is not wk)
                sections[-1]["time"] += f" // {time_text(wk) if wk is not None else ''} {rest}".rstrip()
        out[key] = {"title": squash(small.get_text()) if small else "", "credits": credits, "sections": sections}
    return out


# ---------------------------------------------------------------- catalog course pages

def parse_course_pages(html):
    """Reads one catalog course page. Returns {'DS 451': {'t': title, 'h': hours, 'd': description,
    'p': prerequisites, 'co': corequisites, 'o': 'in Fall and Spring', 'n': [other notes]}}.
    A cross-listed course such as 'ANT 351/WLJA 351' is filed under each of its codes."""
    out = {}
    for block in soup_of(html).select(".courseblock"):
        code, title, hours = (block.select_one(f".detail-{k}") for k in ("coursecode", "title", "hours_html"))
        if not (code and title):
            continue
        d = {"t": squash(title.get_text()), "h": squash(hours.get_text()).strip("()") if hours else "",
             "d": "", "p": "", "co": "", "o": "", "n": []}
        for para in block.select("p.courseblockextra"):
            text = squash(para.get_text())
            if re.match(r"Prerequisites?\b", text, re.I):
                d["p"] = re.sub(r"^Prerequisites?\b[:,]?\s*", "", text, flags=re.I)
            elif re.match(r"Co-?requisites?\b", text, re.I):
                d["co"] = re.sub(r"^Co-?requisites?\b[:,]?\s*", "", text, flags=re.I)
            elif text.startswith("Typically offered"):
                d["o"] = text[len("Typically offered"):].strip()
            elif text and not d["d"] and "noindent" not in (para.get("class") or []):
                d["d"] = text
            elif text:
                d["n"].append(text)
        for c in squash(code.get_text()).split("/"):
            out[c.strip()] = d
    return out


# ---------------------------------------------------------------- terms

def current_term_code(today):
    m = today.month
    return "1" if m <= 4 else "6" if m <= 6 else "7" if m == 7 else "8"


def candidate_terms(today=None):
    """Terms from the one in progress (or about to start) through the end of next year."""
    today = today or date.today()
    floor = f"2{str(today.year)[2:]}{current_term_code(today)}"
    out = []
    for year in (today.year, today.year + 1):
        for code, name in (("1", "Spring"), ("6", "Summer I"), ("7", "Summer II"), ("8", "Fall")):
            term_id = f"2{str(year)[2:]}{code}"
            if term_id >= floor:
                out.append({"id": term_id, "label": f"{name} {year}", "short": f"{name} {str(year)[2:]}"})
    return out


def start_date(dates):
    m = re.search(r"(\d{2})/(\d{2})/(\d{2})", dates or "")
    return f"20{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else ""


# ---------------------------------------------------------------- supplement

def load_supplement(path):
    """supplement.json lists courses that are not on the catalog's elective lists but usually count
    with advisor approval: {"label": "...", "courses": [{"code": "DS 492", "title": "..."}]}."""
    if not path.exists():
        return {"label": "", "courses": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"label": data["label"], "courses": [{"code": squash(c["code"]), "title": squash(c.get("title", ""))}
                                                  for c in data.get("courses", [])]}


def merge_supplement(catalog, supplement):
    """Adds supplement courses that the catalog lists do not already carry. Returns the set of added keys."""
    added = set()
    for c in supplement["courses"]:
        if c["code"] in catalog:
            continue                       # already on a catalog list, so it keeps those labels
        catalog[c["code"]] = {"title": c["title"], "credits": "", "lists": [supplement["label"]]}
        added.add(c["code"])
    return added


# ---------------------------------------------------------------- output

CSV_HEADER = ["Course", "Title", "Credits", "Elective category", "Term", "Offered", "Section", "Component",
              "Availability (open/limit)", "Days and time", "Location", "Instructor", "Dates", "Topic", "Restrictions"]


def to_csv(data):
    """One row per course, term and section. A course with no section in any posted term gets a single 'No' row."""
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    w.writerow(CSV_HEADER)
    for c in data["courses"]:
        base = [c["code"], c["title"], c["credits"], "; ".join(c["lists"])]
        if not c["terms"]:
            w.writerow(base + ["All posted terms", "No"] + [""] * 9)
            continue
        for t in data["terms"]:
            for s in c["terms"].get(t["id"], []):
                avail = s["status"] if s["left"] is None else f"{s['status']} {s['left']}/{s['cap']}"
                w.writerow(base + [t["label"], "Yes", s["section"], s["component"], avail, s["time"], s["location"],
                                   s["instructor"], s["dates"], s["topic"], s["restrictions"]])
    return "\ufeff" + buf.getvalue()


# ---------------------------------------------------------------- network

def retry(label, fn, tries=4):
    last = None
    for i in range(1, tries + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - report the last failure after all tries
            last = e
            time.sleep(0.8 * i)
    raise RuntimeError(f"{label} failed after {tries} tries: {last}")


def get_catalog():
    def go():
        req = urllib.request.Request(CATALOG_URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read().decode("utf-8", "replace")
    return retry("catalog", go)


def get_course_page(subject):
    def go():
        req = urllib.request.Request(COURSE_PAGE_URL.format(PAGE_NAME.get(subject, subject.lower())), headers=HEADERS)
        with urllib.request.urlopen(req, timeout=60) as r:
            time.sleep(PAUSE_SECONDS)
            return r.read().decode("utf-8", "replace")
    return retry(f"catalog page {subject}", go)


def refresh_catalog_details(path, keys, subjects):
    """Course descriptions change rarely, so data/catalog.json is rebuilt once a week, not every day.
    A failure here never blocks the daily data: the previous file stays in place."""
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    age = (date.today() - date.fromisoformat(old["collected"])).days if old.get("collected") else None
    if age is not None and age < CATALOG_MAX_AGE_DAYS and set(keys) <= set(old.get("checked", [])):
        print(f"Catalog descriptions are {age} days old; keeping them.")
        return
    try:
        found = {}
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            for subject, html in zip(subjects, pool.map(get_course_page, subjects)):
                for code, detail in parse_course_pages(html).items():
                    if code not in found or code.split(" ")[0] == subject:   # a subject's own page wins over cross-listings
                        found[code] = detail
        courses = {k: found[k] for k in keys if k in found}
        if len(courses) < 300:
            raise RuntimeError(f"only {len(courses)} descriptions found, so the page layout may have changed")
    except Exception as e:  # noqa: BLE001 - keep the old file and say why
        print(f"Catalog descriptions not updated: {e}")
        return
    body = {"collected": date.today().isoformat(), "checked": keys, "courses": courses}
    path.write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote data/catalog.json with {len(courses)} descriptions")


def search(term, subject, current_term):
    def go():
        body = urllib.parse.urlencode({"term": term, "subject": subject, "current_strm": current_term}).encode()
        req = urllib.request.Request(SEARCH_URL, data=body, method="POST", headers={
            **HEADERS, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
        with urllib.request.urlopen(req, timeout=60) as r:
            time.sleep(PAUSE_SECONDS)
            return json.loads(r.read().decode("utf-8", "replace")).get("html") or ""
    return retry(f"search {term} {subject}", go)


# ---------------------------------------------------------------- main

def main():
    catalog = parse_catalog(get_catalog())
    # Guard: a layout change on the catalog page must not wipe the published data.
    if len(catalog) < 300:
        raise SystemExit(f"Only {len(catalog)} electives found on the catalog page. The page layout may have changed.")
    added = merge_supplement(catalog, load_supplement(Path("supplement.json")))
    keys = sorted(catalog)
    wanted = set(keys)
    subjects = sorted({k.split(" ")[0] for k in keys})
    print(f"Catalog: {len(keys) - len(added)} electives plus {len(added)} supplement courses, {len(subjects)} subjects")

    candidates = candidate_terms()
    current = candidates[0]["id"]
    probe = "ENG" if "ENG" in subjects else subjects[0]
    terms = [t for t in candidates if len(search(t["id"], probe, current)) > 500]
    if not terms:
        raise SystemExit("No term with a posted schedule was found.")
    print("Terms with posted schedules: " + ", ".join(t["label"] for t in terms))

    found = {}
    jobs = [(t["id"], s) for t in terms for s in subjects]

    def work(job):
        term, subject = job
        html = search(term, subject, current)
        return term, parse_search(html, wanted) if html else {}

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        for term, parsed in pool.map(work, jobs):
            for key, course in parsed.items():
                found.setdefault(key, {})[term] = course["sections"]
                if key in added:              # supplement courses take credits (and a missing title) from Class Search
                    if course["credits"]:
                        catalog[key]["credits"] = course["credits"]
                    if not catalog[key]["title"]:
                        catalog[key]["title"] = course["title"]

    # Most common date range per term; the site shows dates only on sections that differ.
    for t in terms:
        tally = Counter(s["dates"] for c in found.values() for s in c.get(t["id"], []))
        t["dates"] = tally.most_common(1)[0][0] if tally else ""
        t["start"] = start_date(t["dates"])

    courses = [{"code": k, "title": catalog[k]["title"], "credits": catalog[k]["credits"],
                "lists": catalog[k]["lists"], "terms": found.get(k, {})} for k in keys]
    offered = sum(1 for c in courses if c["terms"])
    if not offered:
        raise SystemExit("No elective has any posted section. Refusing to overwrite the data.")
    print(f"{offered} of {len(courses)} electives have posted sections")

    data = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "terms": terms, "courses": courses}
    out_dir = Path("data")
    out_dir.mkdir(exist_ok=True)
    (out_dir / "electives.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out_dir / "electives.csv").write_text(to_csv(data), encoding="utf-8", newline="")
    print("Wrote data/electives.json and data/electives.csv")
    refresh_catalog_details(out_dir / "catalog.json", keys, subjects)


if __name__ == "__main__":
    sys.exit(main())
