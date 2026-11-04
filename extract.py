"""Step 1: extract faculty rows + profile links from the NMDSI directory PDF.

Usage: python extract.py [path/to/nmdsi_directory.pdf]
Writes data/directory_raw.json and prints a parse report.
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

import pdfplumber

PDF_PATH = Path(sys.argv[1] if len(sys.argv) > 1 else "nmdsi_directory.pdf")
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


def main():
    rows, unmatched_links, empty_links = [], [], 0
    with pdfplumber.open(PDF_PATH) as pdf:
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


if __name__ == "__main__":
    main()
