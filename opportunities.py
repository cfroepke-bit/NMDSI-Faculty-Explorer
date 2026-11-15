"""Step 2d: open and upcoming federal funding opportunities from Grants.gov.

Usage: python opportunities.py [--refresh]
Writes data/opportunities.json. Raw answers are saved in cache/grantsgov_*.json; --refresh downloads them again.

Searches Grants.gov (POST https://api.grants.gov/v1/api/search2) for posted and forecasted opportunities that
universities can apply to, using the topic keywords in KEYWORDS, then reads each one's details
(POST /v1/api/fetchOpportunity): description, close date, award ceiling and eligibility.
The dashboard matches a team's request against these descriptions and plans backward from the close date.
"""
import argparse
import html
import json
import re
from datetime import date, datetime
from pathlib import Path

from funding import get_json

SEARCH = "https://api.grants.gov/v1/api/search2"
FETCH = "https://api.grants.gov/v1/api/fetchOpportunity"
OUT = Path("data/opportunities.json")
# Topics NMDSI faculty work on. Each keyword's top ROWS results are kept.
KEYWORDS = [
    "data science", "machine learning", "artificial intelligence", "big data", "data analytics", "statistics",
    "computational", "cybersecurity", "privacy", "health informatics", "biomedical informatics", "biostatistics",
    "digital health", "public health data", "natural language processing", "computer vision", "robotics",
    "supply chain", "manufacturing", "financial", "insurance", "economics", "climate", "water", "environmental data",
    "geospatial", "social science data", "misinformation", "education data", "workforce", "STEM education",
    "networks", "imaging", "genomics", "neuroscience data", "smart health", "cyber-physical", "quantum",
]
ROWS = 40
# Grants.gov eligibility codes: 06 public/state universities, 20 private universities, 25 others, 99 unrestricted.
ELIGIBLE = "06|20|25|99"
HIGHER_ED = {"06", "20", "25", "99"}


# Grants.gov agency code prefix -> the name people use ("HHS-NIH11" -> "NIH").
AGENCY_SHORT = [("HHS-NIH", "NIH"), ("HHS-CDC", "CDC"), ("HHS-FDA", "FDA"), ("HHS-HRSA", "HRSA"), ("HHS-AHRQ", "AHRQ"),
                ("HHS-SAMHSA", "SAMHSA"), ("HHS-ACF", "ACF"), ("HHS", "HHS"), ("NSF", "NSF"), ("DOD", "DoD"), ("DOE", "DOE"),
                ("NASA", "NASA"), ("DOI-USGS", "USGS"), ("DOI", "Interior"), ("DOC-DOCNOAA", "NOAA"), ("DOC-NIST", "NIST"),
                ("DOC", "Commerce"), ("USDA", "USDA"), ("ED", "Dept. of Education"), ("EPA", "EPA"), ("DOT", "DOT"),
                ("DOJ", "DOJ"), ("NEH", "NEH"), ("IMLS", "IMLS"), ("DHS", "DHS"), ("VA", "VA")]


# Agencies that fund university research. Embassy public-diplomacy calls ("U.S. Mission to ..."), State Department
# bureaus and similar are left out: they match data-science words but aren't research grants.
RESEARCH_AGENCIES = {"NIH", "NSF", "DoD", "DOE", "Office of Science", "NASA", "NOAA", "NIST", "Commerce", "USDA", "CDC",
                     "FDA", "HRSA", "AHRQ", "SAMHSA", "HHS", "ACF", "EPA", "DHS", "DOT", "NEH", "IMLS", "USGS", "VA",
                     "Dept. of Education", "National Institute of Justice", "SMART", "Department of Housing and Urban Development"}
# Cooperative agreements with one named partner unit (e.g. a Cooperative Ecosystem Studies Unit) aren't open calls.
NOT_OPEN_CALLS = re.compile(r"Cooperative Ecosystem Studies Unit|\bCESU\b|affiliated Partner with", re.I)
# Training grants, fellowships and career awards fund one trainee or an institution's program, not a team project.
NOT_TEAM_FUNDING = re.compile(r"\((T|F|K)\d\d\b|\b(T|F|K)\d\d (Independent )?Clinical|Institutional (Research )?Training|"
                              r"Training Grants?|Fellowships?\b|Career Development Award", re.I)


def agency_short(code, name):
    for prefix, short in AGENCY_SHORT:
        if (code or "").upper().startswith(prefix):
            return short
    return name or code


def parse_date(text):
    """'Jan 14, 2027 12:00:00 AM EST' or '01/14/2027' or '2027-01-14...' -> '2027-01-14'."""
    if not text:
        return None
    for fmt in ("%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(" ".join(text.split()[:3]) if fmt == "%b %d, %Y" else text[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return None


def plain(text, limit=1200):
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def money(value):
    try:
        return int(float(value)) or None
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    hits = {}
    for kw in KEYWORDS:
        body = {"keyword": kw, "oppStatuses": "forecasted|posted", "eligibilities": ELIGIBLE, "rows": ROWS}
        data = get_json("POST", SEARCH, f"grantsgov_search_{re.sub(r'[^a-z]+', '_', kw.lower())}.json",
                        args.refresh, json_body=body)["data"]
        for h in data.get("oppHits", []):
            hits.setdefault(h["id"], {"hit": h, "keywords": []})["keywords"].append(kw)
        print(f"{kw!r}: {data.get('hitCount')} hits, kept {len(data.get('oppHits', []))}")

    today = date.today().isoformat()
    out = []
    for i, (oid, entry) in enumerate(hits.items(), start=1):
        h = entry["hit"]
        title = h.get("title") or ""
        if (agency_short(h.get("agencyCode"), h.get("agency")) not in RESEARCH_AGENCIES or NOT_OPEN_CALLS.search(title)
                or NOT_TEAM_FUNDING.search(title)):
            continue
        d = get_json("POST", FETCH, f"grantsgov_opp_{oid}.json", args.refresh, json_body={"opportunityId": int(oid)})
        d = d.get("data") or {}
        syn, fc = d.get("synopsis") or {}, d.get("forecast") or {}
        info = syn or fc
        eligible = {a.get("id") for a in info.get("applicantTypes") or []}
        if eligible and not eligible & HIGHER_ED:
            continue
        status = h.get("oppStatus")
        close = parse_date(syn.get("responseDate") or h.get("closeDate"))
        estimated = None
        if status == "forecasted":
            estimated = parse_date(fc.get("estApplicationResponseDate"))
            if estimated and estimated < today:
                estimated = None  # a stale forecast: the agency hasn't posted it yet, so the date is unknown
        if close and close < today:
            continue  # already closed
        out.append({
            "id": oid, "number": h.get("number"), "title": html.unescape(h.get("title") or ""),
            "agency": agency_short(h.get("agencyCode"), h.get("agency")), "agency_code": h.get("agencyCode"),
            "agency_name": h.get("agency"),
            "status": status, "close_date": close, "estimated_close_date": estimated,
            "close_note": plain(syn.get("responseDateDesc") or fc.get("estApplicationResponseDateDesc"), 300) or None,
            "posted": parse_date(syn.get("postingDate") or fc.get("postingDate") or h.get("openDate")),
            "award_ceiling": money(info.get("awardCeiling")), "award_floor": money(info.get("awardFloor")),
            "expected_awards": money(info.get("numberOfAwards")),
            "description": plain(syn.get("synopsisDesc") or fc.get("forecastDesc")),
            "eligibility": [a.get("description", "").split(" (")[0] for a in info.get("applicantTypes") or []][:4],
            "keywords": entry["keywords"],
            "url": f"https://www.grants.gov/search-results-detail/{oid}",
        })
        if i % 25 == 0:
            print(f"  details read: {i} of {len(hits)}")
    out.sort(key=lambda o: (o["close_date"] or o["estimated_close_date"] or "9999", o["title"]))
    OUT.write_text(json.dumps({"meta": {"retrieved": today, "source": "https://www.grants.gov (search2, fetchOpportunity)",
                                        "keywords": KEYWORDS}, "opportunities": out},
                              indent=1, ensure_ascii=False), encoding="utf-8")
    dated = sum(1 for o in out if o["close_date"] or o["estimated_close_date"])
    print(f"Wrote {OUT}: {len(out)} opportunities open to universities ({dated} with a deadline; "
          f"{sum(o['status'] == 'forecasted' for o in out)} forecasted)")


if __name__ == "__main__":
    main()
