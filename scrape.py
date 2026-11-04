"""Step 2: politely fetch each profile page, cache the HTML, and parse it.

Usage: python scrape.py [--limit N]
Reads data/directory_raw.json, writes cache/<id>.html, scrape_log.csv and data/scraped.json.
Cached pages are never refetched, so the script can be stopped and rerun at any time.
"""
import argparse
import csv
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from parsers import parse_profile

# Polite scraping: site owners can see who to contact. Set your own address before fetching, e.g.
#   PowerShell: $env:NMDSI_CONTACT_EMAIL = "you@example.com"     bash: export NMDSI_CONTACT_EMAIL=you@example.com
CONTACT_EMAIL = os.environ.get("NMDSI_CONTACT_EMAIL", "").strip()
CONTACT_URL = ""  # optional: a page describing this project, e.g. a GitHub repo
BOT_NAME = "NMDSI-FacultyDirectoryBot"
USER_AGENT = (f"{BOT_NAME}/1.0 (academic directory research, low-rate; "
              f"contact: {CONTACT_EMAIL}{'; ' + CONTACT_URL if CONTACT_URL else ''})")

DIRECTORY = Path("data/directory_raw.json")
OUT = Path("data/scraped.json")
CACHE = Path("cache")
LOG = Path("scrape_log.csv")
# Better pages for people whose directory link is missing, broken or only a contact card.
# Changing a URL here discards that person's cached page on the next run.
URL_OVERRIDES = {
    "rina-ghose": "https://sites.uwm.edu/rghose/sample-page/about/",  # directory link is a contact-only home page
    # Directory links that 404 (checked Nov 2026); new pages found in the current department listings.
    "aki-roberts": "https://uwm.edu/sociology/about/directory/roberts-aki/",
    "john-roberts": "https://uwm.edu/sociology/about/directory/roberts-john/",
    "daniel-gervini": "https://uwm.edu/math/about/directory/gervini-daniel/",
    "vytaras-brazauskas": "https://uwm.edu/math/about/directory/brazauskas-vytaras/",
    "hyunkyoung-oh": "https://uwm.edu/nursing/directory/oh-hyunkyoung-young/",
    "maria-novotny": "https://uwm.edu/english/about/directory/novotny-maria/",
    "dietmar-wolfram": "https://uwm.edu/informationstudies/directory/wolfram-dietmar/",  # now emeritus
    "maria-haigh": "https://uwm.edu/informationstudies/directory/haigh-maria/",
    "shana-ponelis": "https://uwm.edu/informationstudies/directory/ponelis-shana/",
    "xiangming-mu": "https://uwm.edu/informationstudies/directory/mu-xiangming-simon/",
    "clark-evans": "https://uwm.edu/freshwater/directory/evans-clark/",  # now adjunct; main role at NOAA
    "henry-duah": "https://www.marquette.edu/nursing/directory/henry-duah.php",  # PDF had "henry-dual"
    "jenna-green": "https://www.marquette.edu/english/directory/jenna-green.php",
    "edward-blumenthal": "https://www.marquette.edu/biology/directory/blumenthal.php",
    "jim-pokrywczynski": "https://www.marquette.edu/communication/directory/james-pokrywczynski.php",  # emeritus
    "shengtong-han": "https://www.marquette.edu/dentistry/directory/shengtong-han.php",  # PDF had a UWM link
}
DELAY_RANGE = (3, 6)
MAX_RETRIES = 2
TIMEOUT = 25

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})
robots = {}
last_request = 0.0


def polite_wait(crawl_delay=None):
    """Sleep a random 3-6 s (or the site's Crawl-delay, if longer) since the previous request."""
    global last_request
    delay = max(random.uniform(*DELAY_RANGE), crawl_delay or 0)
    remaining = last_request + delay - time.time()
    if remaining > 0:
        time.sleep(remaining)
    last_request = time.time()


def robots_for(url):
    """Return a RobotFileParser for the URL's host, or None if robots.txt could not be read."""
    parts = urlparse(url)
    host = f"{parts.scheme}://{parts.netloc}"
    if host not in robots:
        rp = RobotFileParser()
        polite_wait()
        try:
            r = session.get(f"{host}/robots.txt", timeout=TIMEOUT)
            if r.status_code >= 500:
                rp = None
            else:
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except requests.RequestException:
            rp = None
        robots[host] = rp
    return robots[host]


def fetch(url, crawl_delay):
    """GET with up to MAX_RETRIES retries on timeouts, connection errors, 429 and 5xx."""
    notes = []
    for attempt in range(MAX_RETRIES + 1):
        if attempt:
            backoff = 5 * 2 ** attempt + random.uniform(0, 2)
            notes.append(f"retry {attempt} after {backoff:.0f}s")
            time.sleep(backoff)
        polite_wait(crawl_delay)
        try:
            r = session.get(url, timeout=TIMEOUT)
        except (requests.Timeout, requests.ConnectionError) as exc:
            notes.append(type(exc).__name__)
            continue
        except requests.RequestException as exc:
            notes.append(repr(exc))
            return None, notes
        if r.status_code == 429 or r.status_code >= 500:
            notes.append(f"HTTP {r.status_code}")
            continue
        return r, notes
    return None, notes


def url_slug(url):
    """Last path segment, e.g. 'tripathi-swapnil'. Valid profile redirects keep it unchanged."""
    return urlparse(url).path.rstrip("/").rsplit("/", 1)[-1].lower()


def log_row(writer, rec_id, url, status_code, result, notes=""):
    writer.writerow([rec_id, url or "", status_code or "", result, notes])
    print(f"  {rec_id:40s} {str(status_code or ''):4s} {result:20s} {notes}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="only process the first N people that have a profile URL")
    ap.add_argument("--offline", action="store_true",
                    help="no network: re-parse cached pages only (use after editing parsers.py)")
    ap.add_argument("--only", nargs="+", metavar="ID", help="only process these people, e.g. --only rina-ghose")
    args = ap.parse_args()
    if not args.offline and not CONTACT_EMAIL:
        sys.exit("Set NMDSI_CONTACT_EMAIL to your email before fetching pages (see the top of scrape.py), "
                 "or use --offline to re-parse cached pages.")

    people = json.loads(DIRECTORY.read_text(encoding="utf-8"))
    results = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    CACHE.mkdir(exist_ok=True)
    new_log = not LOG.exists()
    processed = 0

    with LOG.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if new_log:
            writer.writerow(["id", "url", "status_code", "result", "notes"])
        try:
            for person in people:
                pid = person["id"]
                url = URL_OVERRIDES.get(pid, person["profile_url"])
                if args.only and pid not in args.only:
                    continue
                entry = results.get(pid, {"scrape_status": "not_attempted"})
                if entry.get("url") and entry["url"] != url:
                    # the URL changed (e.g. a new override): the cached page belongs to the old one
                    (CACHE / f"{pid}.html").unlink(missing_ok=True)
                    for key in ("final_url", "http_status", "parsed"):
                        entry.pop(key, None)
                entry["url"] = url
                results[pid] = entry
                if not url:
                    if entry["scrape_status"] != "no_url":
                        log_row(writer, pid, None, None, "no_url")
                    entry["scrape_status"] = "no_url"
                    continue
                if args.limit is not None and processed >= args.limit:
                    continue
                processed += 1
                cache_file = CACHE / f"{pid}.html"

                if not cache_file.exists() and args.offline:
                    continue  # keep the status from the last online run
                if not cache_file.exists():
                    try:
                        rp = robots_for(url)
                        if rp is None:
                            entry["scrape_status"] = "robots_unavailable"
                            log_row(writer, pid, url, None, "robots_unavailable", "could not read robots.txt; skipped")
                            continue
                        if not rp.can_fetch(USER_AGENT, url):
                            entry["scrape_status"] = "robots_disallowed"
                            log_row(writer, pid, url, None, "robots_disallowed")
                            continue
                        response, notes = fetch(url, rp.crawl_delay(USER_AGENT))
                    except Exception as exc:  # never let one page kill the run
                        response, notes = None, [repr(exc)]
                    if response is None:
                        entry["scrape_status"] = "fetch_error"
                        log_row(writer, pid, url, None, "fetch_error", "; ".join(notes))
                        continue
                    if response.status_code != 200:
                        entry["scrape_status"] = "http_error"
                        entry["http_status"] = response.status_code
                        log_row(writer, pid, url, response.status_code, "http_error", "; ".join(notes))
                        continue
                    if "html" not in response.headers.get("Content-Type", "html"):
                        entry["scrape_status"] = "non_html"
                        log_row(writer, pid, url, 200, "non_html", response.headers.get("Content-Type", ""))
                        continue
                    cache_file.write_bytes(response.content)
                    if response.url != url:
                        notes.append(f"redirected to {response.url}")
                        entry["final_url"] = response.url
                    log_row(writer, pid, url, 200, "fetched", "; ".join(notes))
                elif not args.offline:
                    log_row(writer, pid, url, None, "cached")

                final_url = entry.get("final_url")
                if final_url and url_slug(final_url) != url_slug(url):
                    # e.g. a retired profile redirecting to a department notice: not this person's page
                    entry["scrape_status"] = "redirected_away"
                    entry.pop("parsed", None)
                    if not args.offline:
                        log_row(writer, pid, url, 200, "redirected_away", f"landed on {final_url}")
                    continue

                try:
                    parsed = parse_profile(cache_file.read_bytes(), entry.get("final_url", url))
                except Exception as exc:
                    entry["scrape_status"] = "parse_error"
                    log_row(writer, pid, url, None, "parse_error", repr(exc))
                    continue
                has_content = parsed["research"] or parsed["courses"] or parsed["bio"]
                entry.update({
                    "scrape_status": "ok" if has_content else "parsed_empty",
                    "last_scraped": datetime.fromtimestamp(cache_file.stat().st_mtime, timezone.utc)
                                            .isoformat(timespec="seconds"),
                    "parsed": parsed,
                })
                fh.flush()
                if processed % 10 == 0:
                    OUT.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
        except KeyboardInterrupt:
            print("Interrupted - saving progress.")
        finally:
            OUT.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")

    counts = {}
    for entry in results.values():
        counts[entry["scrape_status"]] = counts.get(entry["scrape_status"], 0) + 1
    print(f"\nStatus counts: {counts}  (wrote {OUT})")


if __name__ == "__main__":
    main()
