"""Step 2b: find each person's headshot in their saved profile page (no new fetching).

Usage: python photos.py
Reads data/directory_raw.json, data/scraped.json and cache/<id>.html; writes data/photos.json ({id: image URL}).
The dashboard loads images from the universities' own servers and falls back to initials if one fails,
so no photos are copied into this project.
"""
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from parsers import decode

DIRECTORY = Path("data/directory_raw.json")
SCRAPED = Path("data/scraped.json")
CACHE = Path("cache")
OUT = Path("data/photos.json")

# Images that are never headshots.
# Checked against the image file name only (e.g. "lubar-people-default.png", "reiter-labgrp.png").
SKIP = re.compile(r"logo|icon|sprite|banner|header|footer|social|facebook|twitter|linkedin|instagram|youtube|"
                  r"placeholder|default|no[-_]?photo|lab[-_]?gr(ou)?p|fig[-_]?\d|silhouette|\bseal\b|wordmark|"
                  r"pixel|badge|button|\barrow|map[-_]|campus|building|\bhall\b|group|\bteam\b|classroom",
                  re.I)
# Image descriptions that mean "not a headshot" (narrower: alt text like "Social Work Professor Ai Bo" is fine).
ALT_SKIP = re.compile(r"\blogo\b|\bicon\b|\bmenu\b|\bsearch\b|\barrow\b|\bbanner\b|\bseal\b|wordmark|"
                      r"group photo|lab group|\bstudents\b|\bclassroom\b", re.I)
# Places universities keep faculty headshots.
PHOTO_PATH = re.compile(r"/directory/images/|profile-images|ls-people|wp-content/uploads|headshot|portrait|"
                        r"/people/|/faculty/|/staff/", re.I)


def fold(text):
    """Lowercase ASCII letters only, so "Núñez" matches "nunez"."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", text.lower())


def name_parts(name):
    words = [w for w in re.split(r"[\s\-]+", re.sub(r"\b(Dr|Jr|Sr|II|III)\b\.?", "", name)) if len(w) > 1]
    words = [w for w in words if not re.fullmatch(r"[A-Z]\.?", w)]
    return fold(words[0]) if words else "", fold(words[-1]) if words else ""


def size_of(img):
    try:
        return int(img.get("width") or 0), int(img.get("height") or 0)
    except ValueError:
        return 0, 0


def find_photo(html_bytes, page_url, name):
    """Return the most likely headshot URL on a profile page, or None."""
    soup = BeautifulSoup(decode(html_bytes), "html.parser")
    first, last = name_parts(name)
    best, best_score = None, 0
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src and img.get("srcset"):
            src = img["srcset"].split(",")[0].split()[0]
        # Check the file name, not the folder: "/socialwelfare/ai-bo.jpg" is fine, "social-icons.png" is not.
        if not src or src.startswith("data:") or src.lower().split("?")[0].endswith(".svg") or SKIP.search(Path(urlparse(src).path).name):
            continue
        alt, cls = img.get("alt") or "", " ".join(img.get("class") or [])
        if ALT_SKIP.search(alt) or (img.find_parent(["header", "footer", "nav"]) is not None):
            continue
        file_part, alt_f = fold(Path(urlparse(src).path).stem), fold(alt)
        score = 0
        if last and last in alt_f: score += 4
        if first and first in alt_f: score += 2
        if last and last in file_part: score += 4
        if first and first in file_part: score += 1
        if "wp-post-image" in cls: score += 3                     # UWM WordPress featured image
        if PHOTO_PATH.search(src): score += 1
        w, h = size_of(img)
        if w and h:
            if w > 2 * h: score -= 4                              # wide banner crop
            elif 0.6 <= w / h <= 1.4 or h > w: score += 1         # portrait or square
            if w < 60 or h < 60: score -= 5                       # thumbnails, icons
        if score > best_score:
            best, best_score = urljoin(page_url, src.replace("&amp;", "&")), score
    # Must match the person's name or be the page's marked featured image.
    return best if best_score >= 4 else None


def main():
    people = json.loads(DIRECTORY.read_text(encoding="utf-8"))
    scraped = json.loads(SCRAPED.read_text(encoding="utf-8"))
    photos, missing = {}, []
    for p in people:
        entry = scraped.get(p["id"]) or {}
        cache_file = CACHE / f"{p['id']}.html"
        if entry.get("scrape_status") != "ok" or not cache_file.exists():
            continue
        url = entry.get("final_url") or entry.get("url") or p.get("profile_url")
        photo = find_photo(cache_file.read_bytes(), url, p["name"])
        if photo:
            photos[p["id"]] = photo
        else:
            missing.append(p["id"])
    OUT.write_text(json.dumps(photos, indent=1, sort_keys=True), encoding="utf-8")
    print(f"Photos found: {len(photos)} of {len(photos) + len(missing)} readable profiles  (wrote {OUT})")
    if missing:
        print(f"No photo found ({len(missing)}): {missing}")


if __name__ == "__main__":
    main()
