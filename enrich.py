"""Step 3 + 4: merge directory rows with scraped profiles, apply rules.py, write faculty.json and groupings.

Usage: python enrich.py
Reads data/directory_raw.json and data/scraped.json (if present).
Writes faculty.json and data/groupings.json, then prints a report of anything that looks off.
"""
import json
import re
from collections import Counter
from pathlib import Path

import rules

DIRECTORY = Path("data/directory_raw.json")
SCRAPED = Path("data/scraped.json")
OUT = Path("faculty.json")
GROUPS = Path("data/groupings.json")


def keyword_regex(keyword):
    """Whole-word match; trailing * = prefix match; all-caps keywords are case-sensitive."""
    body = re.escape(keyword.rstrip("*")) + (r"\w*" if keyword.endswith("*") else r"\b")
    flags = 0 if keyword.rstrip("*").isupper() else re.I
    return re.compile(r"(?<![\w-])" + body, flags)


COMPILED = {}


def hits(keywords, text):
    """Return the keywords that occur in text."""
    found = []
    for kw in keywords:
        if kw not in COMPILED:
            COMPILED[kw] = keyword_regex(kw)
        if text and COMPILED[kw].search(text):
            found.append(kw)
    return found


def canonical_college(college):
    if not college:
        return None
    for pattern, name in rules.COLLEGE_ALIASES.items():
        if re.match(pattern, college, re.I):
            return name
    return college


def org_units(person):
    """(college, department, college_source). college_source is "directory", or "inferred" when the college
    was filled in from the department or a school listed as the college was moved to the department."""
    college, department = person["college"], person["department"]
    if college in rules.COLLEGE_IS_DEPARTMENT:
        if not department:
            department = college
        return rules.COLLEGE_IS_DEPARTMENT[college], department, "inferred"
    if not college and department:
        for uni, pattern, name in rules.COLLEGE_FROM_DEPARTMENT:
            if person["university"] == uni and re.search(pattern, department):
                return name, department, "inferred"
    return canonical_college(college), department, "directory" if college else None


CONNECTOR_END = re.compile(r"(\b(and|of|the|in|for|with|to|on|&|a|an)|[,(/-])$", re.I)


def is_wrapped(prev, line, all_lines):
    """True if a PDF line continues the previous one instead of starting a new research item."""
    if CONNECTOR_END.search(prev) or line[0].islower() or line[0] == "&":
        return True
    if prev.endswith((",", ";")):
        return False
    # Mostly comma/semicolon-delimited text: line breaks are only wrapping ("Parallel and Distributed" / "Computing,")
    if any(";" in l for l in all_lines) or sum(bool(re.search(r"[,;]", l)) for l in all_lines) >= len(all_lines) / 2:
        return True
    # Otherwise only a short phrase that clearly ends on this line: "Syriac Studies and Early" / "Christianity, ..."
    first = re.split(r"[,;]", line)
    tail = re.split(r"[,;]", prev)[-1]
    return len(first) > 1 and len((tail + " " + first[0]).split()) <= 5


def list_items(lines):
    """Research given as a short list ("Criminology", "GIS", "Watershed and urban hydrology", ...) -> items.
    Prose (sentences, long clauses) -> []."""
    merged = []
    lines = [l.strip() for l in lines if l.strip()]
    for line in lines:
        if merged and is_wrapped(merged[-1], line, lines):
            merged[-1] += " " + line
        else:
            merged.append(line)
    if merged:
        merged[0] = re.sub(rules.TAG_LEADIN, "", merged[0], flags=re.I)
    items = []
    for line in merged:
        line = re.sub(r"\s*\([^)]*\)", "", line)  # "Systems modeling (machine learning, ...)" -> "Systems modeling"
        # a missing comma before "Research on ..." still starts a new item
        items += [re.sub(r"^(and|&)\s+", "", p.strip(" .:")) for p in re.split(r"[,;]|\s+(?=Research on\b)", line)]
    items = [re.sub(rules.TAG_ITEM_PREFIX, "", i, flags=re.I) for i in items if i and i.lower() not in ("etc", "etc.")]
    prose = [i for i in items if re.match(rules.PROSE_ITEM_START, i, re.I)]
    if any(len(i.split()) > 6 for i in prose):
        return []  # a long clause: the blurb is a sentence, not a list
    items = [i for i in items if i not in prose]  # drop short clauses, keep the real items around them
    if not items or re.search(r"[a-z]\.\s+[A-Z]", re.sub(r"\bDr\.", "Dr", " ".join(merged))) or any(len(i.split()) > 12 for i in items):
        return []
    short = [i for i in items if 1 < len(i) <= rules.MAX_TAG_LENGTH and len(i.split()) <= 6]
    return short if len(short) >= 0.6 * len(items) else []


NOT_RESEARCH = re.compile(r"https?://|www\.|see more|learn more|click|visit|join(ing)? the lab|contact", re.I)


def profile_items(lines):
    """Profile research lines come from <li>/<p> elements, so each short line is already one interest."""
    lines = [l.strip(" :;.") for l in lines if l.strip(" :;.") and not NOT_RESEARCH.search(l)]
    if len(lines) < 2:
        return []
    return [l for l in lines if len(l) <= rules.MAX_TAG_LENGTH and len(l.split()) <= 6]


def tagify(text):
    text = re.sub(r"\s*\(.*?\)\s*", " ", text).strip(" :;,.")
    return " ".join(w if (w.isupper() or re.search(r"[A-Z].*[A-Z]", w)) else w.lower() for w in text.split())


def research_tags(profile_lines, directory_lines, prose):
    tags, sources = [], set()

    def add(tag, source):
        # skip a tag an existing one already covers: "atmospheric" after "atmospheric science", "robotic" after "robotics"
        covered = tag and any(t.lower().startswith(tag.lower()) for t in tags)
        if tag and not covered and len(tags) < rules.MAX_TAGS:
            tags.append(tag)
            sources.add(source)

    for item in profile_items(profile_lines):
        add(tagify(item), "profile")
    if len(tags) < rules.MIN_TAGS:
        for item in list_items(directory_lines):
            add(tagify(item), "directory")
    if len(tags) < rules.MIN_TAGS:
        for kw in sorted(hits(rules.TAG_VOCAB, prose), key=lambda k: COMPILED[k].search(prose).start()):
            add(rules.TAG_VOCAB[kw], "inferred")
    if len(tags) < rules.MIN_TAGS:  # last resort: the words that matched theme keywords, in text order
        theme_kws = {kw for kws in rules.THEMES.values() for kw in kws}
        matches = sorted((COMPILED[kw].search(prose) for kw in hits(theme_kws, prose)), key=lambda m: m.start())
        for m in matches:
            add(m.group(0) if m.group(0).isupper() else m.group(0).lower(), "inferred")
    source = sources.pop() if len(sources) == 1 else ("mixed" if sources else None)
    return tags, source


SUMMARY_MAX = 3000  # a whole research statement (e.g. rina-ghose, ~19k chars) is too long for a card


def shorten(text):
    """Cut text longer than SUMMARY_MAX at the last sentence end before the limit."""
    if not text or len(text) <= SUMMARY_MAX:
        return text
    cut = text[:SUMMARY_MAX]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return (cut[:end + 1] if end > SUMMARY_MAX // 2 else cut.rstrip()) + " …"


def split_sentences(text):
    return [s for s in re.split(r"(?<=[.!?;])\s+|\n", text) if s.strip()]


def find_funding(parsed):
    """Sponsors explicitly named on the profile. Grants-section lines always count; elsewhere a
    sentence must also mention funding (grant, funded by, award, ...). Never guesses."""
    if not parsed:
        return []
    candidates = [(line, True) for line in parsed.get("grants", [])]
    prose = parsed.get("research", []) + parsed.get("bio", [])
    if parsed.get("parser", "").startswith("generic") or "generic" in parsed.get("parser", ""):
        prose.append(parsed.get("full_text", ""))
    candidates += [(s, False) for p in prose for s in split_sentences(p)]

    found = {}
    for text, in_grants_section in candidates:
        if not in_grants_section:
            if not re.search(rules.FUNDING_CONTEXT, text, re.I):
                continue
            if re.search(rules.HONOR_CONTEXT, text, re.I) and not re.search(rules.STRONG_FUNDING_CONTEXT, text, re.I):
                continue
        remaining = text
        for sponsor, patterns in rules.FUNDING_SPONSORS.items():
            for pattern in patterns:
                flags = 0 if sponsor in ("foundation",) else re.I
                m = re.search(pattern, remaining, flags)
                if m:
                    if sponsor not in found:
                        found[sponsor] = {"name": sponsor, "source": "profile", "evidence": text[:240]}
                    remaining = remaining[:m.start()] + " " + remaining[m.end():]  # NSF is not also a "foundation"
    return list(found.values())


def score_theme(research_text, org_text):
    scores, evidence = {}, {}
    for theme, keywords in rules.THEMES.items():
        r_hits, o_hits = hits(keywords, research_text), hits(keywords, org_text)
        scores[theme] = len(r_hits) + rules.DEPARTMENT_WEIGHT * len(o_hits)
        evidence[theme] = sorted(set(r_hits + o_hits))
    best = max(scores, key=lambda t: scores[t])  # max() keeps the first theme on ties
    if scores[best] == 0:
        return "Unclassified", "none", []
    return best, "inferred", evidence[best]


def enrich(person, scraped):
    entry = scraped.get(person["id"], {})
    parsed = entry.get("parsed") or {}
    profile_research = [l for l in parsed.get("research", []) if not NOT_RESEARCH.search(l)]
    if profile_research:
        # a list of interests reads better with separators; prose paragraphs are joined as-is
        is_list = len(profile_research) > 1 and not any(l.rstrip().endswith(".") for l in profile_research)
        summary = ("; " if is_list else " ").join(l.strip(" :;") for l in profile_research)
        summary_source = "profile"
    else:
        summary, summary_source = person["directory_research"], "directory"

    prose = " ".join(filter(None, [summary, person["directory_research"]]))  # full text, for tags and theme
    summary = shorten(summary)
    tags, tags_source = research_tags(profile_research, person["directory_research_lines"], prose)
    college, department, college_source = org_units(person)
    topical_college = None if college in rules.NON_TOPICAL_COLLEGES else college
    org_text = " ".join(filter(None, [department, topical_college]))
    research_text = " ".join([prose] + tags)

    theme, theme_source, theme_evidence = score_theme(research_text, org_text)
    industries = [{"name": name, "source": "inferred", "evidence": found}
                  for name, keywords in rules.INDUSTRIES.items()
                  if (found := hits(keywords, research_text + " " + org_text))]
    funding = find_funding(parsed)
    classes = [dict(c, source="profile") for c in parsed.get("courses", [])]

    return {
        "id": person["id"],
        "name": person["name"],
        "credentials": person["credentials"],
        "title": person["title"],
        "university": person["university"],
        "college": college,
        "college_raw": person["college"],
        "college_source": college_source,
        "department": department,
        "profile_url": person["profile_url"],
        "directory_research": person["directory_research"],
        "research_summary": summary,
        "research_summary_source": summary_source,
        "research_tags": tags,
        "research_tags_source": tags_source,
        "classes": classes,
        "industries": industries,
        "funding": funding,
        "funding_status": "named" if funding else "unknown",
        "theme": theme,
        "theme_source": theme_source,
        "theme_evidence": theme_evidence,
        "bio": " ".join(parsed.get("bio", []))[:1500] or None,
        "scrape_status": entry.get("scrape_status", "not_attempted"),
        "last_scraped": entry.get("last_scraped"),
    }


def group(records, key_fn):
    out = {}
    for r in records:
        for key in key_fn(r):
            out.setdefault(key, []).append(r["id"])
    return {k: {"count": len(v), "ids": v} for k, v in sorted(out.items(), key=lambda kv: (-len(kv[1]), kv[0]))}


def build_groupings(records):
    by_org = {}
    for r in records:
        uni = by_org.setdefault(r["university"], {"count": 0, "ids": [], "colleges": {}})
        col = uni["colleges"].setdefault(r["college"] or "(no college listed)", {"count": 0, "ids": [], "departments": {}})
        dep = col["departments"].setdefault(r["department"] or "(no department listed)", {"count": 0, "ids": []})
        for node in (uni, col, dep):
            node["count"] += 1
            node["ids"].append(r["id"])

    preset_ids = [r["id"] for r in records
                  if r["theme"] in rules.PRESET_THEMES
                  or hits(rules.PRESET_KEYWORDS, " ".join(r["research_tags"] + [r["research_summary"] or ""]))]
    return {
        "by_university": by_org,
        "by_theme": group(records, lambda r: [r["theme"]]),
        "by_industry": group(records, lambda r: [i["name"] for i in r["industries"]] or ["(none matched)"]),
        "by_funding": group(records, lambda r: [f["name"] for f in r["funding"]] or ["unknown"]),
        "by_scrape_status": group(records, lambda r: [r["scrape_status"]]),
        "presets": {rules.PRESET_NAME: {"count": len(preset_ids), "ids": preset_ids,
                                        "rule": {"themes": rules.PRESET_THEMES, "keywords": rules.PRESET_KEYWORDS}}},
    }


def main():
    people = json.loads(DIRECTORY.read_text(encoding="utf-8"))
    scraped = json.loads(SCRAPED.read_text(encoding="utf-8")) if SCRAPED.exists() else {}
    records = [enrich(p, scraped) for p in people]
    OUT.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    groupings = build_groupings(records)
    GROUPS.write_text(json.dumps(groupings, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {len(records)} records to {OUT} and groupings to {GROUPS}")
    print("Scrape status:", dict(Counter(r["scrape_status"] for r in records)))
    print("Theme:", dict(Counter(r["theme"] for r in records).most_common()))
    print("Industry:", {k: v["count"] for k, v in groupings["by_industry"].items()})
    print("Funding:", {k: v["count"] for k, v in groupings["by_funding"].items()})
    print(f"Classes listed: {sum(1 for r in records if r['classes'])} people")
    print(f"Research summary from profile: {sum(1 for r in records if r['research_summary_source'] == 'profile')}")
    print(f"Preset '{rules.PRESET_NAME}': {groupings['presets'][rules.PRESET_NAME]['count']} people")
    few = [r["id"] for r in records if len(r["research_tags"]) < rules.MIN_TAGS]
    print(f"!! Fewer than {rules.MIN_TAGS} tags ({len(few)}): {few}")
    print(f"!! Unclassified theme: {[r['id'] for r in records if r['theme'] == 'Unclassified']}")
    known = set(rules.COLLEGE_ALIASES.values()) | rules.KNOWN_COLLEGES | set(rules.COLLEGE_IS_DEPARTMENT.values())
    odd = Counter(r["college"] for r in records if r["college"] and r["college"] not in known)
    print(f"Colleges not covered by an alias (check spelling): {dict(odd)}")


if __name__ == "__main__":
    main()
