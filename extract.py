"""Step 1: build data/directory_raw.json from the NMDSI affiliated-faculty list.

Usage:
  python extract.py                     read the current list, data/affiliated_2026-09.xlsx (September 2026)
  python extract.py --pdf [file.pdf]    the old October 2025 PDF directory (nmdsi_directory.pdf)

The 2026 spreadsheet has no college or department columns, so those are carried over from the 2025 directory
(data/directory_2025.json) for returning faculty, taken from MSOE's directory for MSOE faculty, or read from
MCW profile links. Returning faculty keep their old id, so saved shortlists and share links keep working.
All MSOE faculty in data/msoe_directory.json (from msoe_directory.py) who aren't on the list are added with
nmdsi_affiliate = false. Email addresses in the list are not copied: the published data has no emails.
"""
import json
import re
import sys
import unicodedata
from pathlib import Path


OUT_PATH = Path("data/directory_raw.json")

# Column boundaries (PDF points). Names start at x~40, university at x~190, research at x~420.
COL1_X = 185
COL2_X = 415
LINE_TOL = 3  # words whose tops differ by less than this are on the same line

PAGE_CHROME = re.compile(
    r"^(Affiliated Faculty Directory|Full Name\s+University/College\s+Research Interest|Updated \d+ \w+ \d{4})$"
)
UNIVERSITY_START = re.compile(r"^(University of Wisconsin\s*-\s*Milwaukee|Marquette University)\s*(.*)$")
TITLE_START = re.compile(r"^(Professor|Assistant|Associate|Adjunct|Director|Lecturer|Chair|Dean|Senior|Clinical|"
                         r"Teaching|Research|Visiting|Distinguished|Instructor|Interim)", re.I)
COLLEGE_HINT = re.compile(r"College|School|Library|Institute|Graduate|Law|Center|Academic Affairs", re.I)
CONNECTOR_END = re.compile(r"\b(of|and|&|for|in|the)$", re.I)

KNOWN_NO_LINK = {"Jacob Rice", "Deepak Babu", "Mumin Cebe", "Laira Anne Stark"}


def fix_kerning(text):
    """Join single capitals split from their word by PDF kerning ("A ssociate" -> "Associate")."""
    return re.sub(r"\b([A-Z]) (?=[a-z]{2,})", r"\1", text)


def normalize_university(text):
    text = re.sub(r"\s*-\s*", "-", text)
    if text.startswith("University of Wisconsin"):
        return "UW-Milwaukee"
    if text.startswith("Marquette"):
        return "Marquette University"
    return text


def slugify(name):
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower().replace(".", "")).strip("-")


def page_lines(page):
    """Group words into visual lines, drop page header/footer, then split each line into 3 columns."""
    words = sorted(page.extract_words(), key=lambda w: (round(w["top"]), w["x0"]))
    lines = []
    for w in words:
        if lines and abs(lines[-1]["top"] - w["top"]) < LINE_TOL:
            lines[-1]["words"].append(w)
        else:
            lines.append({"top": w["top"], "bottom": w["bottom"], "words": [w]})
    out = []
    for line in lines:
        ws = sorted(line["words"], key=lambda w: w["x0"])
        if PAGE_CHROME.match(" ".join(w["text"] for w in ws)):
            continue
        cols = [[], [], []]
        for w in ws:
            cols[0 if w["x0"] < COL1_X else 1 if w["x0"] < COL2_X else 2].append(w)
        out.append({
            "top": line["top"],
            "cols": [" ".join(w["text"] for w in c) for c in cols],
            "name_words": cols[0],
        })
    return out


def link_for_line(line, links):
    """Return the URI of a link annotation whose box overlaps this line's name words."""
    for link in links:
        for w in line["name_words"]:
            if (link["x0"] < w["x1"] and w["x0"] < link["x1"]
                    and link["top"] < w["bottom"] and w["top"] < link["bottom"]):
                link["_used"] = True
                return link["uri"]
    return None


def split_college_department(lines):
    """Join wrapped lines, then treat the first college-like line as college, the rest as department."""
    merged = []
    for line in lines:
        if merged and (line[:1].islower() or CONNECTOR_END.search(merged[-1])):
            merged[-1] += " " + line
        else:
            merged.append(line)
    if merged and COLLEGE_HINT.search(merged[0]):
        college, rest = merged[0], merged[1:]
    else:
        college, rest = None, merged
    return college, (" ".join(rest) or None)


def starts_row(line, prev_row):
    """A row starts where the university column begins with a university name beside a name.
    "Marquette University Law School" under a bare "Marquette University" line is a college, not a new row."""
    col0, col1 = line["cols"][0], line["cols"][1]
    if not col0 or not UNIVERSITY_START.match(col1):
        return False
    if prev_row and prev_row["col0"] and re.search(r"[,-]$", prev_row["col0"][-1]):
        return False  # previous name wrapped onto this line
    if prev_row and len(prev_row["col1"]) == 1:
        return "," in col0 and not TITLE_START.match(col0)
    return True


def split_name_lines(col0):
    """Names can wrap ("Elsbeth Kalenderian, DDS," / "MPH, PhD"); a trailing comma or hyphen means it continues."""
    name, rest = col0[0], list(col0[1:])
    while rest and re.search(r"[,-]$", name):
        nxt = rest.pop(0)
        name = name + nxt if name.endswith("-") else f"{name} {nxt}"
    return name, rest


def build_record(row):
    name_line, title_lines = split_name_lines(row["col0"])
    name_line = re.sub(r"^Dr\.?\s+", "", fix_kerning(name_line))
    name, _, credentials = name_line.partition(",")
    title = " ".join(fix_kerning(t) for t in title_lines) or None
    uni_lines = [fix_kerning(t) for t in row["col1"]]
    # "Marquette University College of Nursing" -> university + college on one line
    uni_match = UNIVERSITY_START.match(uni_lines[0])
    if uni_match and uni_match.group(2):
        uni_lines[0:1] = [uni_match.group(1), uni_match.group(2)]
    college, department = split_college_department(uni_lines[1:])
    research_lines = row["col2"]
    return {
        "id": slugify(name.strip()),
        "name": name.strip(),
        "credentials": credentials.strip() or None,
        "title": title,
        "university": normalize_university(uni_lines[0]),
        "college": college,
        "department": department,
        "profile_url": row["url"],
        # line-wrapped hyphens: "well- being" -> "well-being"
        "directory_research": re.sub(r"(\w)- (\w)", r"\1-\2",
                                     re.sub(r"\s+", " ", " ".join(research_lines))).strip() or None,
        "directory_research_lines": research_lines,
        "source_page": row["page"],
    }


def main_pdf(pdf_path):
    import pdfplumber
    rows, unmatched_links, empty_links = [], [], 0
    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            links = [l for l in page.hyperlinks if l.get("uri")]
            for l in links:
                if l["x1"] - l["x0"] < 2:  # zero-size annotation; cannot be matched to text
                    l["_used"] = True
                    empty_links += 1
            for line in page_lines(page):
                if starts_row(line, rows[-1] if rows else None):
                    rows.append({"page": page_no, "col0": [], "col1": [], "col2": [], "url": None})
                if not rows:
                    continue  # anything before the first row on page 1
                # Wrapped names put the link on a later line, so keep checking name-column lines.
                if line["cols"][0] and not rows[-1]["url"] and len(rows[-1]["col0"]) < 3:
                    rows[-1]["url"] = link_for_line(line, links)
                elif line["cols"][0]:
                    link_for_line(line, links)  # marks a second box of an already-matched link as used
                # Lines before the first row on a page continue the previous page's last row.
                for i, text in enumerate(line["cols"]):
                    if text:
                        rows[-1][f"col{i}"].append(text)
            unmatched_links += [(page_no, l["uri"]) for l in links if not l.get("_used")]

    records, failures, seen = [], [], {}
    for row in rows:
        try:
            rec = build_record(row)
        except Exception as exc:  # report and keep going
            failures.append({"page": row["page"], "row": row, "error": repr(exc)})
            continue
        problems = [f for f in ("name", "university", "directory_research") if not rec[f]]
        if problems:
            failures.append({"page": row["page"], "name": rec["name"], "missing": problems})
        key = rec["name"].lower()
        if key in seen:
            prev = seen[key]
            prev["duplicate_pages"] = prev.get("duplicate_pages", []) + [rec["source_page"]]
            if not prev["profile_url"]:
                prev["profile_url"] = rec["profile_url"]
            continue
        seen[key] = rec
        records.append(rec)

    ids = {}
    for rec in records:  # make slugs unique
        n = ids.get(rec["id"], 0)
        ids[rec["id"]] = n + 1
        if n:
            rec["id"] = f"{rec['id']}-{n + 1}"

    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

    no_link = [r["name"] for r in records if not r["profile_url"]]
    print(f"Rows parsed: {len(rows)}  ->  unique faculty: {len(records)}  (wrote {OUT_PATH})")
    print(f"Duplicates merged: {[(r['name'], [r['source_page']] + r['duplicate_pages']) for r in records if 'duplicate_pages' in r]}")
    print(f"No profile link ({len(no_link)}): {no_link}")
    unexpected = sorted(set(no_link) - KNOWN_NO_LINK)
    if unexpected:
        print(f"  !! unexpected missing links: {unexpected}")
    print(f"No title: {[r['name'] for r in records if not r['title']]}")
    print(f"No college: {[r['name'] for r in records if not r['college']]}")
    print(f"No department: {[r['name'] for r in records if not r['department']]}")
    print(f"Zero-size link annotations skipped: {empty_links}")
    print(f"Link annotations not matched to a name: {unmatched_links or 'none'}")
    print(f"Rows that failed to parse ({len(failures)}):")
    for f in failures:
        print("  ", f)


# ---------------------------------------------------------------------------------------------------------
# September 2026 list (spreadsheet)
# ---------------------------------------------------------------------------------------------------------
XLSX_PATH = Path("data/affiliated_2026-09.xlsx")
OLD_DIRECTORY = Path("data/directory_2025.json")
MSOE_DIRECTORY = Path("data/msoe_directory.json")

UNIVERSITY_NAMES = {
    "university of wisconsin-milwaukee": "UW-Milwaukee",
    "marquette university": "Marquette University",
    "medical college of wisconsin": "Medical College of Wisconsin",
    "milwaukee school of engineering": "Milwaukee School of Engineering",
    "waukesha county technical college": "Waukesha County Technical College",
}
# Obvious typos in the list, checked against the person's own profile page.
NAME_FIXES = {"Micheal Zimmermann": "Michael Zimmermann"}  # MCW page: Michael T. Zimmermann
# MCW profile links name the department: /departments/<slug>/ or a department subdomain.
MCW_DEPT_HOSTS = {"obgyn.mcw.edu": "Obstetrics and Gynecology"}


def fold(text):
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower())


def name_key(name):
    """(first name, last name), ignoring middle names, initials, suffixes and nicknames in parentheses.
    The full first name is compared: "Somesh Roy" and "Sudeshna Roy" are different people. Nicknames
    ("Tony" Gamble) are matched by profile link instead."""
    words = [w for w in re.sub(r"\([^)]*\)", " ", name).replace(".", " ").replace(",", " ").split()
             if len(w) > 1 and w.lower() not in ("jr", "sr", "ii", "iii", "iv")]
    return (fold(words[0]), fold(words[-1])) if words else ("", "")


def norm_url(url):
    return re.sub(r"^https?://(www\.)?", "", (url or "").strip().lower()).rstrip("/")


# College / department named by the first part of a UWM or Marquette profile link, for people the list
# gives no department (the 2026 list has none; returning faculty keep their 2025 values).
URL_UNITS = {
    # UWM: uwm.edu/<unit>/...
    "uwm.edu/business": ("Lubar College of Business", None),
    "uwm.edu/math": ("College of Letters & Science", "Department of Mathematical Sciences"),
    "uwm.edu/informationstudies": ("College of Community Engagement and Professions", "School of Information Studies"),
    "uwm.edu/engineering": ("College of Engineering & Applied Science", None),
    "uwm.edu/freshwater": ("School of Freshwater Sciences", None),
    "uwm.edu/communication": ("College of Letters & Science", "Department of Communication"),
    "uwm.edu/physics": ("College of Letters & Science", "Department of Physics"),
    "uwm.edu/english": ("College of Letters & Science", "Department of English"),
    "uwm.edu/sociology": ("College of Letters & Science", "Department of Sociology"),
    "uwm.edu/drug-discovery": ("College of Letters & Science", "Milwaukee Institute for Drug Discovery"),
    "uwm.edu/publichealth": ("Zilber College of Public Health", None),
    "uwm.edu/nursing": ("College of Nursing", None),
    "uwm.edu/academicaffairs": ("Academic Affairs", None),
    "uwm.edu/biomedical-sciences-healthcare-administration":
        ("College of Health Professions & Sciences", "Biomedical Sciences & Healthcare Administration"),
    # Marquette: marquette.edu/<unit>/...
    "law.marquette.edu": ("Law School", None),
    "marquette.edu/mathematical-and-statistical-sciences":
        ("Klingler College of Arts and Sciences", "Department of Mathematical and Statistical Sciences"),
    "marquette.edu/business": ("College of Business Administration", None),
    "marquette.edu/communication": ("Diederich College of Communication", None),
    "marquette.edu/dentistry": ("School of Dentistry", None),
    "marquette.edu/physical-therapy": ("College of Health Sciences", "Department of Physical Therapy"),
    "marquette.edu/nursing": ("College of Nursing", None),
    "marquette.edu/library": ("Raynor Library", None),
    "marquette.edu/research-sponsored-programs": ("Office of Research and Sponsored Programs", None),
    "marquette.edu/peacemaking": ("Center for Peacemaking", None),
}


def url_units(url):
    path = norm_url(url)
    for prefix, units in URL_UNITS.items():
        if path == prefix or path.startswith(prefix + "/"):
            return units
    return None, None


def mcw_department(url):
    host = re.sub(r"^https?://", "", url or "").split("/")[0].lower()
    if host in MCW_DEPT_HOSTS:
        return MCW_DEPT_HOSTS[host]
    m = re.search(r"mcw\.edu/departments/([a-z0-9-]+)/", url or "")
    if not m:
        return None
    words = m.group(1).split("-")
    small = {"and", "of", "for", "the", "in"}
    return " ".join(w if i and w in small else w.capitalize() for i, w in enumerate(words))


def match_old(row, old, overrides):
    """The 2025 record for this person: same id, same profile link (or override), or same first + last name
    at the same university."""
    by_id = {o["id"]: o for o in old}
    if row["id"] in by_id:
        return by_id[row["id"]]
    url = norm_url(row["profile_url"])
    if url:
        for o in old:
            if url in (norm_url(o["profile_url"]), norm_url(overrides.get(o["id"]))):
                return o
    key = name_key(row["name"])
    same = [o for o in old if name_key(o["name"]) == key and o["university"] == row["university"]]
    return same[0] if len(same) == 1 else None


def main_xlsx():
    import openpyxl
    from scrape import URL_OVERRIDES

    old = json.loads(OLD_DIRECTORY.read_text(encoding="utf-8")) if OLD_DIRECTORY.exists() else []
    msoe = json.loads(MSOE_DIRECTORY.read_text(encoding="utf-8")) if MSOE_DIRECTORY.exists() else []
    msoe_by_key = {name_key(m["name"]): m for m in msoe}
    sheet = openpyxl.load_workbook(XLSX_PATH, read_only=True).active

    records, seen, carried, report = [], {}, 0, {"duplicates": [], "no_link": [], "fixed_names": []}
    for row_no, row in enumerate(sheet.iter_rows(values_only=True), start=1):
        first, last, _email, cred, uni, title, research, category, url = (list(row) + [None] * 9)[:9]
        if not (first or last):
            continue
        name = " ".join(f"{first or ''} {last or ''}".split())
        if name in NAME_FIXES:
            report["fixed_names"].append(f"{name} -> {NAME_FIXES[name]}")
            name = NAME_FIXES[name]
        url = (url or "").strip() or None
        university = UNIVERSITY_NAMES.get((uni or "").strip().lower(), (uni or "").strip())
        rec = {
            "id": slugify(name), "name": name, "credentials": (cred or "").strip() or None,
            "title": " ".join((title or "").split()) or None, "university": university,
            "college": None, "department": None, "profile_url": url,
            "directory_research": " ".join((research or "").split()) or None,
            "directory_research_lines": [l.strip() for l in (research or "").splitlines() if l.strip()],
            "nmdsi_category": (category or "").strip() or None,
            "nmdsi_affiliate": True, "source_row": row_no,
        }
        prev = match_old(rec, old, URL_OVERRIDES)
        if prev:
            carried += 1
            rec["id"] = prev["id"]
            rec["college"], rec["department"] = prev["college"], prev["department"]
            rec["directory_research"] = rec["directory_research"] or prev["directory_research"]
            rec["directory_research_lines"] = rec["directory_research_lines"] or prev["directory_research_lines"]
            rec["title"] = rec["title"] or prev["title"]
        if university == "Medical College of Wisconsin" and not rec["department"]:
            rec["department"] = mcw_department(url)
        if university in ("UW-Milwaukee", "Marquette University") and not rec["department"]:
            college, department = url_units(url)
            rec["college"] = rec["college"] or college
            rec["department"] = department
        if university == "Milwaukee School of Engineering":
            m = msoe_by_key.get(name_key(name))
            if m:
                rec["department"] = rec["department"] or m["department"]
                rec["msoe_photo"] = m["photo_url"]
                if not url or "/directory/?" in url:  # list gave a directory search page, not a profile
                    rec["profile_url"] = m["profile_url"]
        if rec["id"] in seen:  # listed twice (e.g. two email addresses): keep the first, fill gaps from the second
            first_rec = seen[rec["id"]]
            report["duplicates"].append(f"{name} (rows {first_rec['source_row']} and {row_no})")
            for k, v in rec.items():
                if first_rec.get(k) in (None, [], "") and v:
                    first_rec[k] = v
            continue
        seen[rec["id"]] = rec
        records.append(rec)

    listed = len(records)
    listed_keys = {name_key(r["name"]) for r in records if r["university"] == "Milwaukee School of Engineering"}
    for m in msoe:
        if name_key(m["name"]) in listed_keys:
            continue
        rid = slugify(m["name"])
        if rid in seen:
            rid += "-msoe"
        rec = {"id": rid, "name": m["name"], "credentials": None, "title": m["title"],
               "university": "Milwaukee School of Engineering", "college": None, "department": m["department"],
               "profile_url": m["profile_url"], "directory_research": None, "directory_research_lines": [],
               "nmdsi_category": None, "nmdsi_affiliate": False, "msoe_photo": m["photo_url"]}
        seen[rid] = rec
        records.append(rec)

    for rec in records:
        if not rec["profile_url"]:
            report["no_link"].append(rec["name"])
    OUT_PATH.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

    from collections import Counter
    print(f"Read {XLSX_PATH}: {listed} people on the NMDSI list, plus {len(records) - listed} other MSOE faculty "
          f"= {len(records)} records (wrote {OUT_PATH})")
    print("NMDSI list by institution:", dict(Counter(r["university"] for r in records if r["nmdsi_affiliate"])))
    print(f"Returning from the 2025 directory (id, college, department kept): {carried}")
    new_ids = {r["id"] for r in records}
    print(f"In the 2025 directory but not on the 2026 list: {[o['id'] for o in old if o['id'] not in new_ids]}")
    print(f"Listed twice, merged: {report['duplicates']}")
    print(f"Names corrected: {report['fixed_names']}")
    print(f"No profile link: {report['no_link']}")
    print(f"No department: {[r['id'] for r in records if r['nmdsi_affiliate'] and not r['department']]}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--pdf":
        main_pdf(Path(sys.argv[2] if len(sys.argv) > 2 else "nmdsi_directory.pdf"))
    else:
        main_xlsx()


