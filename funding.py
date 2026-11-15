"""Step 2c: federal research awards each person has led, from the NSF and NIH public APIs.

Usage: python funding.py [--refresh]
Reads data/directory_raw.json; writes data/awards.json ({"meta": ..., "awards": {id: [award, ...]}}).
Raw API answers are saved in cache/ (not published); --refresh downloads them again.

- NSF (https://api.nsf.gov/services/v1/awards.json): every award whose awardee is one of the five NMDSI
  institutions. Matched to a person when the PI or a co-PI has the same first and last name at the same institution.
- NIH RePORTER (https://api.reporter.nih.gov/v2/projects/search): projects searched by PI name, limited to the
  NMDSI institutions. Yearly records of one project are combined into a single award.

Only awards starting in or after FIRST_YEAR are kept: older ones are more likely to be someone else with the same
name, and say less about current work. Awards a person won at a previous employer are not found.
"""
import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scrape import USER_AGENT

DIRECTORY = Path("data/directory_raw.json")
OUT = Path("data/awards.json")
CACHE = Path("cache")
FIRST_YEAR = 2010

NSF_URL = "https://api.nsf.gov/services/v1/awards.json"
NSF_FIELDS = ("id,title,piFirstName,piLastName,coPDPI,startDate,expDate,fundsObligatedAmt,estimatedTotalAmt,"
              "awardeeName,fundProgramName,dirAbbr,abstractText")
NSF_AWARDEES = {  # NSF awardee name -> our university name
    "Marquette University": "Marquette University",
    "University of Wisconsin-Milwaukee": "UW-Milwaukee",
    "Medical College of Wisconsin": "Medical College of Wisconsin",
    "Milwaukee School of Engineering": "Milwaukee School of Engineering",
    "Waukesha County Technical College": "Waukesha County Technical College",
}
NIH_URL = "https://api.reporter.nih.gov/v2/projects/search"
NIH_ORGS = {  # RePORTER organization name -> our university name
    "MARQUETTE UNIVERSITY": "Marquette University",
    "UNIVERSITY OF WISCONSIN MILWAUKEE": "UW-Milwaukee",
    "MEDICAL COLLEGE OF WISCONSIN": "Medical College of Wisconsin",
    "MILWAUKEE SCHOOL OF ENGINEERING": "Milwaukee School of Engineering",
}
NIH_FIELDS = ["ApplId", "CoreProjectNum", "ProjectTitle", "PrincipalInvestigators", "FiscalYear", "AwardAmount",
              "ActivityCode", "Organization", "AgencyIcAdmin", "ProjectStartDate", "ProjectEndDate", "AbstractText"]
NIH_PUBS_URL = "https://api.reporter.nih.gov/v2/publications/search"
ABSTRACT_MAX = 900  # characters kept from each abstract: enough for search and a preview


def nih_publications(cores, refresh):
    """{core project number: [PMID, ...]} for papers NIH links to each project (/v2/publications/search)."""
    pmids, cores = {}, sorted(cores)
    for start in range(0, len(cores), 50):
        batch, offset = cores[start:start + 50], 0
        while True:
            data = get_json("POST", NIH_PUBS_URL, f"nihpubs_{start}_{offset}.json", refresh,
                            json_body={"criteria": {"core_project_nums": batch}, "offset": offset, "limit": 500})
            for r in data.get("results", []):
                pmids.setdefault(r["coreproject"], []).append(r["pmid"])
            offset += 500
            if offset >= data["meta"]["total"] or offset >= 9500:
                break
    return pmids
# A few common nicknames, so "Tony" on an award matches "Anthony" on the list.
NICKNAMES = {"tony": "anthony", "mike": "michael", "nick": "nicholas", "bill": "william", "bob": "robert",
             "jim": "james", "joe": "joseph", "dan": "daniel", "dave": "david", "tom": "thomas", "steve": "stephen",
             "chris": "christopher", "matt": "matthew", "pat": "patrick", "kate": "katherine", "katie": "katherine",
             "jeff": "jeffrey", "greg": "gregory", "andy": "andrew", "rick": "richard", "gerry": "gerard"}

def fold(text):
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower())


def first_last(name):
    words = [w for w in re.sub(r"\([^)]*\)", " ", name).replace(".", " ").replace(",", " ").split()
             if len(w) > 1 and w.lower() not in ("jr", "sr", "ii", "iii", "iv", "dr")]
    return (fold(words[0]), fold(words[-1])) if words else ("", "")


def same_first(a, b):
    a, b = NICKNAMES.get(a, a), NICKNAMES.get(b, b)
    return a == b or (min(len(a), len(b)) >= 3 and (a.startswith(b) or b.startswith(a)))


class People:
    """Look up our people by (institution, first name, last name)."""
    def __init__(self, records):
        self.by_last = {}
        for r in records:
            first, last = first_last(r["name"])
            self.by_last.setdefault((r["university"], last), []).append((first, r["id"]))

    def find(self, university, first, last):
        first, last = fold(first.split()[0] if first.split() else ""), fold(last)
        hits = [pid for f, pid in self.by_last.get((university, last), []) if same_first(f, first)]
        return hits[0] if len(hits) == 1 else None


def get_json(method, url, cache_name, refresh, params=None, json_body=None):
    """GET/POST with the standard library: the NSF server resets connections from the requests library."""
    path = CACHE / cache_name
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    full = url + ("?" + urlencode(params) if params else "")
    data = json.dumps(json_body).encode() if json_body is not None else None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/json"
    for attempt in range(4):
        time.sleep(1.0 + attempt * 3)  # both APIs ask for about one request per second
        try:
            with urlopen(Request(full, data=data, headers=headers, method=method), timeout=60) as r:
                result = json.loads(r.read().decode("utf-8"))
            path.write_text(json.dumps(result), encoding="utf-8")
            return result
        except (HTTPError, URLError, TimeoutError, ConnectionError) as exc:
            print(f"  {exc!r} from {url}; retrying")
    sys.exit(f"Could not read {full}")


def year_of(mmddyyyy):
    m = re.search(r"(\d{4})$", mmddyyyy or "")
    return int(m.group(1)) if m else None


def iso(mmddyyyy):
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", mmddyyyy or "")
    return f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else None


def nsf_awards(people, refresh):
    found = {}
    for awardee, university in NSF_AWARDEES.items():
        offset, total = 1, None
        slug = fold(awardee)[:24]
        while total is None or offset <= total:
            data = get_json("GET", NSF_URL, f"nsf_{slug}_{offset}.json", refresh,
                            params={"awardeeName": f'"{awardee}"', "printFields": NSF_FIELDS, "rpp": 25,
                                    "offset": offset})["response"]
            total = data.get("metadata", {}).get("totalCount", 0)
            for a in data.get("award", []):
                if a.get("awardeeName") != awardee or (year_of(a.get("startDate")) or 0) < FIRST_YEAR:
                    continue
                team = [("PI", a.get("piFirstName", ""), a.get("piLastName", ""))]
                for co in a.get("coPDPI") or []:  # "First Last ~000123"
                    parts = co.split("~")[0].split()
                    if len(parts) >= 2:
                        team.append(("Co-PI", parts[0], parts[-1]))
                for role, first, last in team:
                    pid = people.find(university, first, last)
                    if pid:
                        found.setdefault(pid, []).append({
                            "agency": "NSF", "id": a["id"], "title": a.get("title"),
                            "program": a.get("fundProgramName"), "directorate": a.get("dirAbbr"),
                            "start": iso(a.get("startDate")), "end": iso(a.get("expDate")),
                            "amount": int(a.get("estimatedTotalAmt") or a.get("fundsObligatedAmt") or 0) or None,
                            "role": role, "institution": university,
                            "abstract": (lambda t: t[:ABSTRACT_MAX] + ("…" if len(t) > ABSTRACT_MAX else "") if t else None)(
                                " ".join((a.get("abstractText") or "").split())),
                            "url": f"https://www.nsf.gov/awardsearch/showAward?AWD_ID={a['id']}",
                        })
            offset += 25
        print(f"NSF {awardee}: {total} awards checked")
    return found


def nih_awards(records, people, refresh):
    names = sorted({first_last(r["name"]) for r in records if r["university"] in NIH_ORGS.values()})
    projects = {}
    for start in range(0, len(names), 50):
        batch = names[start:start + 50]
        offset = 0
        while True:
            body = {"criteria": {"pi_names": [{"first_name": f, "last_name": l} for f, l in batch],
                                 "org_names": list(NIH_ORGS), "fiscal_years": list(range(FIRST_YEAR, date.today().year + 2))},
                    "include_fields": NIH_FIELDS, "offset": offset, "limit": 500}
            data = get_json("POST", NIH_URL, f"nih_{start}_{offset}.json", refresh, json_body=body)
            for p in data.get("results", []):
                projects.setdefault(p["core_project_num"] or p["appl_id"], []).append(p)
            offset += 500
            if offset >= data["meta"]["total"]:
                break
    found = {}
    pubs = nih_publications(projects.keys(), refresh)
    for core, years in projects.items():
        years.sort(key=lambda p: p["fiscal_year"])
        latest = years[-1]
        university = NIH_ORGS.get(latest["organization"]["org_name"])
        if not university:
            continue
        award = {
            "agency": "NIH", "id": core, "title": latest["project_title"],
            "program": (latest.get("agency_ic_admin") or {}).get("name"),
            "directorate": (latest.get("agency_ic_admin") or {}).get("abbreviation"),
            "activity": latest.get("activity_code"),
            "start": (latest.get("project_start_date") or "")[:10] or None,
            "end": (latest.get("project_end_date") or "")[:10] or None,
            "amount": sum(p.get("award_amount") or 0 for p in years) or None,
            "fiscal_years": [years[0]["fiscal_year"], latest["fiscal_year"]],
            "institution": university,
            "url": f"https://reporter.nih.gov/project-details/{latest['appl_id']}",
        }
        abstract = " ".join((latest.get("abstract_text") or "").split())
        if abstract:
            award["abstract"] = abstract[:ABSTRACT_MAX] + ("…" if len(abstract) > ABSTRACT_MAX else "")
        papers = sorted(set(pubs.get(core, [])), reverse=True)
        if papers:
            award["publications"] = len(papers)
            # PubMed lists comma-separated PMIDs as a result set (newest 200)
            award["publications_url"] = "https://pubmed.ncbi.nlm.nih.gov/?term=" + ",".join(map(str, papers[:200]))
        for pi in latest.get("principal_investigators", []):
            pid = people.find(university, pi.get("first_name", ""), pi.get("last_name", ""))
            if pid:
                found.setdefault(pid, []).append(dict(award, role="PI" if pi.get("is_contact_pi") else "Multi-PI"))
    print(f"NIH: {len(projects)} projects found for {len(names)} names")
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="download again instead of using cache/")
    args = ap.parse_args()
    CACHE.mkdir(exist_ok=True)
    records = json.loads(DIRECTORY.read_text(encoding="utf-8"))
    people = People(records)
    awards = {}
    for source in (nsf_awards(people, args.refresh), nih_awards(records, people, args.refresh)):
        for pid, items in source.items():
            awards.setdefault(pid, []).extend(items)
    for items in awards.values():
        items.sort(key=lambda a: a.get("start") or "", reverse=True)
    OUT.write_text(json.dumps({
        "meta": {"retrieved": date.today().isoformat(), "first_year": FIRST_YEAR,
                 "sources": {"NSF": NSF_URL, "NIH": NIH_URL}},
        "awards": awards}, indent=1, ensure_ascii=False), encoding="utf-8")
    listed = {r["id"] for r in records if r.get("nmdsi_affiliate", True)}
    n_listed = sum(1 for pid in awards if pid in listed)
    print(f"Wrote {OUT}: {sum(len(v) for v in awards.values())} awards for {len(awards)} people "
          f"({n_listed} of {len(listed)} on the NMDSI list)")
    for agency in ("NSF", "NIH"):
        print(f"  {agency}: {sum(1 for v in awards.values() for a in v if a['agency'] == agency)} awards, "
              f"{sum(1 for v in awards.values() if any(a['agency'] == agency for a in v))} people")


if __name__ == "__main__":
    main()
