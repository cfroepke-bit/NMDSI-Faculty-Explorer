"""Step 0b: list every MSOE faculty member from MSOE's public directory (https://www.msoe.edu/directory/).

NMDSI said all MSOE faculty can be included, not only the 7 on the affiliate list. extract.py adds the ones
that aren't on the list, marked nmdsi_affiliate = false.

Usage: python msoe_directory.py
Writes data/msoe_directory.json: [{name, title, department, profile_url, photo_url}]. Pages are fetched politely
(robots.txt checked, 3-6 s apart) with the same User-Agent as scrape.py.
"""
import json
import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrape import USER_AGENT, fetch, robots_for

BASE = "https://www.msoe.edu/directory/?type=faculty&page={}"
OUT = Path("data/msoe_directory.json")
MAX_PAGES = 60  # safety stop


def clean_name(text):
    return re.sub(r"^(Dr|Prof|Professor)\.?\s+", "", " ".join(text.split()))


def parse_page(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    people = []
    for item in soup.select(".directory_item_inner"):
        name_el = item.select_one(".directory_item_name")
        if not name_el:
            continue
        title = item.select_one(".directory_item_title")
        dept = next((d.get_text(" ", strip=True).split(":", 1)[1].strip()
                     for d in item.select(".directory_item_detail") if d.get_text().strip().startswith("Department")), None)
        link = item.select_one('a[href*="/directory/profile/"]')
        img = item.select_one("img.directory_item_image")
        photo = urljoin(page_url, img["src"]) if img and img.get("src") else None
        if photo and re.search(r"placeholder", photo, re.I):
            photo = None
        people.append({
            "name": clean_name(name_el.get_text()),
            "title": " ".join(title.get_text().split()) if title else None,
            "department": dept,
            "profile_url": urljoin(page_url, link["href"]) if link else None,
            "photo_url": photo,
        })
    return people


def main():
    rp = robots_for(BASE.format(1))
    people, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        url = BASE.format(page)
        if rp is not None and not rp.can_fetch(USER_AGENT, url):
            print(f"robots.txt disallows {url}; stopping")
            break
        response, notes = fetch(url, rp.crawl_delay(USER_AGENT) if rp else None)
        if response is None or response.status_code != 200:
            print(f"page {page}: failed ({response.status_code if response else notes})")
            break
        found = [p for p in parse_page(response.text, url) if p["name"] not in seen]
        print(f"page {page}: {len(found)} people")
        if not found:
            break
        for p in found:
            seen.add(p["name"])
        people += found
    OUT.write_text(json.dumps(people, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(people)} MSOE faculty to {OUT}")


if __name__ == "__main__":
    main()
