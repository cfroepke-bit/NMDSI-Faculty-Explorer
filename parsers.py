"""Profile-page parsers. Each returns a dict of sections; classify_sections() maps them to fields.

Domain patterns seen in the directory:
  uwm.edu/...                 -> <main id="content">, h2 section headings
  www.marquette.edu, mcw.*    -> <div id="facultyPage"> .bio, h3 section headings
  law.marquette.edu           -> <main>, h2 "Biography", "Courses Taught" as a <strong> label
  anything else               -> generic: strip nav/header/footer, use h1-h4 headings
"""
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

HEADING = re.compile(r"^h[1-4]$")
SKIP_HEADINGS = re.compile(r"directory categories|quick links|report a problem|problem with this webpage|contact|"
                           r"faculty & staff directory|^share", re.I)

SECTION_KINDS = {
    "courses": re.compile(r"course|teaching|classes", re.I),
    "grants": re.compile(r"grant|funding|sponsor", re.I),
    "research": re.compile(r"research|expertise|interest|speciali[sz]|areas of|focus", re.I),
    "bio": re.compile(r"^(bio|biography|about|overview|profile)\b", re.I),
}
PUBLICATIONS = re.compile(r"publication|presentation|selected works|recent papers", re.I)
# "CHEM", "MTHSTAT", "Geog", and UWM two-word subjects like "POL SCI", "BUS ADM", "ATM SCI"
SUBJECT = r"(?:[A-Z]{2,7}(?: (?:SCI|ADM|ENG|STAT))?|[A-Z][a-z]{2,5})"
# "511 Organization of Information 714 Metadata ...": UWM Information Studies lists bare course numbers
BARE_NUMBER = re.compile(r"(?:^|\s)(\d{3})\s+(?=[A-Z])")
# Notes that are not part of a course title: "(Fall 2025 & Spring 2026)", "Fall 2025", ", lecturer"
TITLE_NOTES = re.compile(
    r"\s*\(?\b(?:fall|spring|summer|winter)\s+\d{4}(?:\s*(?:&|and|,)\s*(?:(?:fall|spring|summer|winter)\s+)?\d{4})*\)?"
    r"|\s*\((?:graduate|undergraduate)\)|,\s*(?:lecturer|instructor|co-instructor|guest lecturer)\b", re.I)
COURSE_CODE = re.compile(
    rf"\b(?!(?:Fall|Spring|Summer|Winter|Room|Hall)\b)({SUBJECT})\s?(\d{{3,4}}[A-Z]?)(?:-\d{{3}})?"
    rf"((?:\s?/\s?(?:{SUBJECT}\s?)?\d{{3,4}}[A-Z]?)*)\b")
TABLE_HEADER = re.compile(r"^Course\s+(Num(ber)?|No\.?)\s+Title(\s+Syllabus)?\s*", re.I)


def clean(text):
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def element_lines(el):
    """Text of an element as lines: one per <li>/<p>, else the whole text."""
    if isinstance(el, str):
        return [clean(el)] if clean(el) else []
    items = el.find_all(["li", "p"]) or el.find_all("tr") or [el]
    return [clean(i.get_text(" ")) for i in items if clean(i.get_text(" "))]


def heading_level(tag):
    return int(tag.name[1])


def label_of(el):
    """'Professional Interests:' if el is a <p>/<div> that starts with a bold label ending in a colon."""
    if getattr(el, "name", None) not in ("p", "div"):
        return None
    lab = el.find(["strong", "b"])
    if lab is None:
        return None
    text = clean(lab.get_text(" "))
    if len(text) >= 60 or not clean(el.get_text(" ")).startswith(text):
        return None
    if text.endswith(":"):
        return text
    # "<strong>STATEMENT OF RESEARCH INTERESTS</strong><br/>...": a bold first line naming a known section
    nxt = lab.next_sibling
    while isinstance(nxt, str) and not nxt.strip():
        nxt = nxt.next_sibling
    if lab.parent is el and getattr(nxt, "name", None) == "br" and any(p.search(text) for p in SECTION_KINDS.values()):
        return text + ":"
    return None


def is_boundary(el):
    name = getattr(el, "name", None)
    return bool(name) and (HEADING.match(name) or el.find(HEADING) is not None or label_of(el) is not None)


def collect_sections(root):
    """Map section title -> content lines. Sections are headings (h1-h4) or bold "Label:" paragraphs;
    each runs until the next heading or label of any level."""
    sections = {}
    for p in root.find_all(["p", "div"]):
        label = label_of(p)
        if not label:
            continue
        lines = [clean(p.get_text(" "))[len(label):].strip()]
        for sib in p.next_siblings:
            if is_boundary(sib):
                break
            lines += element_lines(sib)
        lines = [l for l in lines if l]
        if lines and not SKIP_HEADINGS.search(label):
            sections.setdefault(label.rstrip(":"), []).extend(lines)
    for h in root.find_all(HEADING):
        title = clean(h.get_text(" ")).replace("Hide Show", "").strip()
        if not title or SKIP_HEADINGS.search(title):
            continue
        lines = []
        for sib in h.next_siblings:
            if is_boundary(sib):
                break
            lines += element_lines(sib)
        # content wrapped with the heading in its own small container
        if not lines and h.parent is not None and len(h.parent.find_all(HEADING)) == 1:
            parent_text = clean(h.parent.get_text(" "))
            rest = parent_text[len(clean(h.get_text(" "))):].strip()
            if rest:
                lines = [rest]
        if lines:
            sections.setdefault(title, []).extend(lines)
    return sections


def strip_chrome(soup):
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript", "form"]):
        tag.decompose()
    return soup


def parse_uwm(soup):
    root = soup.select_one("main#content") or soup.find("main") or soup.body
    return collect_sections(root), root


def parse_marquette(soup):
    root = soup.select_one("#facultyPage") or soup.select_one("#leftContent") or soup.body
    return collect_sections(root), root


def parse_law(soup):
    root = soup.find("main") or soup.body
    sections = collect_sections(root)
    for strong in root.find_all("strong"):
        label = clean(strong.get_text(" "))
        if re.match(r"courses taught", label, re.I):
            # "Courses Taught</strong> Property Law, International IP Law, ..." -> text after the label
            text = clean(strong.parent.get_text(" "))[len(label):].strip(" :")
            courses = [c.strip() for c in text.split(",") if c.strip()]
            if courses:
                sections["Courses Taught"] = courses
    return sections, root


def parse_generic(soup):
    root = soup.find("main") or soup.find("article") or soup.body
    return collect_sections(root), root


PARSERS = [
    (re.compile(r"(^|\.)law\.marquette\.edu$"), "law", parse_law),
    (re.compile(r"^(www\.|mcw\.)?marquette\.edu$"), "marquette", parse_marquette),
    (re.compile(r"^(www\.)?uwm\.edu$"), "uwm", parse_uwm),
]


def course_title(text):
    """Text after a course code -> title, dropping separators, 'Syllabus' links and trailing descriptions."""
    text = re.sub(r"\bSyllabus\b", "", text).lstrip(" :;,-–—")
    title = re.split(r"\s[–—|]", text)[0].strip(" :;,-")
    return strip_notes(title)[:120] or None


def strip_notes(title):
    return TITLE_NOTES.sub("", title).strip(" :;,-") if title else title


def is_title_case(text):
    words = [w for w in text.split() if w.lower() not in ("and", "of", "the", "in", "for", "to", "a", "an", "&")]
    return len(text.split()) >= 2 and all(w[0].isupper() for w in words)


def parse_courses(lines):
    courses = []
    for line in lines:
        line = TABLE_HEADER.sub("", line).strip()
        if not line or TABLE_HEADER.match(line + " "):
            continue
        matches = list(COURSE_CODE.finditer(line))
        if matches and matches[0].start() < 5:
            # one line can hold several courses: "FINA 4040 International Finance FINA 6111: Investments"
            for m, nxt in zip(matches, matches[1:] + [None]):
                title = course_title(line[m.end():nxt.start() if nxt else len(line)])
                code = clean(f"{m.group(1)} {m.group(2)}{m.group(3)}")
                courses.append({"code": code, "title": title})
        elif len(numbers := list(BARE_NUMBER.finditer(line))) >= 2 and numbers[0].start() == 0:
            for m, nxt in zip(numbers, numbers[1:] + [None]):
                title = course_title(line[m.end():nxt.start() if nxt else len(line)])
                courses.append({"code": m.group(1), "title": title})
        elif line.isupper() or re.search(r"catalog", line, re.I):
            continue
        elif "." not in line.rstrip(".") and (line.count(",") >= 2 or ";" in line):
            # "Information Systems, Business Analytics, Applied Artificial Intelligence"
            courses += [{"code": None, "title": t.strip(" .")} for t in re.split(r"[,;]", line) if t.strip(" .")]
        elif line.count(",") == 1 and all(is_title_case(p.strip(" .")) for p in line.split(",")):
            # "Introduction to Information Systems, Database Management Systems"
            courses += [{"code": None, "title": p.strip(" .")} for p in line.split(",")]
        elif len(line) <= 120:
            courses.append({"code": None, "title": strip_notes(line)})
    # the same course is often listed once per semester: keep the first of each code + title
    seen, unique = set(), []
    for c in courses:
        key = ((c["code"] or "").upper(), (c["title"] or "").lower())
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


PROSE_COURSE = re.compile(
    r"\b([A-Z]{2,5})\s?(\d{3,4})\s+((?:[A-Z][\w&'-]*|of|and|the|in|for|to|&)(?:\s+(?:[A-Z][\w&'-]*|of|and|the|in|for|to|&))*)")


def courses_from_prose(paragraphs):
    """'Dr. Bo teaches SW 662 Methods of Social Welfare Research, SW 795 ...' -> course list."""
    courses = []
    for para in paragraphs:
        for sentence in re.split(r"(?<=[.!?])\s+", para):
            if not re.search(r"\bteach|\bcourses?\b|\bclasses\b", sentence, re.I):
                continue
            for m in PROSE_COURSE.finditer(sentence):
                title = re.sub(r"\s+(of|and|the|in|for|to|&)$", "", m.group(3)).strip()
                courses.append({"code": f"{m.group(1)} {m.group(2)}", "title": title or None})
    return courses


def intro_paragraphs(root):
    """Long free-text paragraphs (bios written without a heading), stopping at any Publications section."""
    paras = []
    for el in root.find_all(["p", "h1", "h2", "h3", "h4", "div"]):
        heading_text = clean(el.get_text(" ")) if HEADING.match(el.name) else label_of(el)
        if heading_text and PUBLICATIONS.search(heading_text):
            break
        if el.name == "p" and len(clean(el.get_text(" "))) > 200 and not label_of(el):
            paras.append(clean(el.get_text(" ")))
    return paras[:4]


def decode(html_bytes):
    """Pages declare UTF-8 but some serve cp1252 punctuation; decode strictly, then fall back."""
    try:
        return html_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return html_bytes.decode("cp1252", errors="replace")


def parse_profile(html_bytes, url):
    soup = strip_chrome(BeautifulSoup(decode(html_bytes), "html.parser"))
    host = urlparse(url).netloc.lower()
    name, parser = "generic", parse_generic
    for pattern, pname, fn in PARSERS:
        if pattern.search(host):
            name, parser = pname, fn
            break
    sections, root = parser(soup)
    if not sections and not intro_paragraphs(root) and parser is not parse_generic:
        sections, root = parse_generic(soup)
        name += "+generic"

    out = {"parser": name, "page_title": clean(soup.title.get_text()) if soup.title else None,
           "courses": [], "research": [], "grants": [], "bio": [], "sections": sections}
    for heading, lines in sections.items():
        if re.search(r"interest|areas", heading, re.I) and SECTION_KINDS["research"].search(heading):
            out["research"].extend(lines)  # "Teaching and Research Interests" are interests, not classes
            continue
        for kind, pattern in SECTION_KINDS.items():
            if pattern.search(heading):
                if kind == "research" and re.search(r"publication|presentation|position|appointment|employment|"
                                                    r"experience|degree|education", heading, re.I):
                    continue  # "Research Positions" is a job history, not research topics
                out[kind].extend(lines)
                break
    if not out["bio"]:
        out["bio"] = intro_paragraphs(root)
    out["courses"] = parse_courses(out["courses"])
    if not out["courses"]:
        out["courses"] = courses_from_prose(out["bio"] + out["research"])
    out["full_text"] = clean(root.get_text(" ")) if root else ""
    return out
