# NMDSI Affiliated Faculty Explorer

A searchable, enriched directory of the Northwestern Mutual Data Science Institute affiliated faculty
(Marquette University + UW-Milwaukee), built from `nmdsi_directory.pdf` (updated 1 October 2025).

## Setup

```
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Before fetching profiles, set a contact email so site owners know who is crawling:
`$env:NMDSI_CONTACT_EMAIL = "you@example.com"` (PowerShell) or `export NMDSI_CONTACT_EMAIL=you@example.com`.
`scrape.py --offline` doesn't need it.

**What's in the repo:** the code, the dashboard, and the generated data (`faculty.json`, `data/*.json`,
`scrape_log.csv`), so the site runs as-is. Not included: the source PDF (`nmdsi_directory.pdf`, put your copy in the
project root to rerun `extract.py`) and `cache/` (saved profile pages; `scrape.py` re-creates it).

**Live site:** deployed on Vercel as a static site. `vercel.json` sends `/` to `/dashboard/`; there is no build step.

## Run, in order

| Step | Command | Output |
|---|---|---|
| 1. Extract the PDF | `python extract.py` | `data/directory_raw.json` + a parse report |
| 2. Scrape profiles | `python scrape.py --limit 5` (trial), then `python scrape.py` | `cache/<id>.html`, `scrape_log.csv`, `data/scraped.json` |
| 3–4. Enrich + group | `python enrich.py` | `faculty.json`, `data/groupings.json` + a report |
| 5. Dashboard | `python -m http.server 8000`, then open <http://localhost:8000/dashboard/> | |

Run the server from the project root: the dashboard fetches `../faculty.json` and `../data/groupings.json`,
and `fetch()` does not work from `file://`.

## Dashboard

Four tabs, all running in the browser (no server-side code, no paid APIs):

| Tab | What it does | Code |
|---|---|---|
| **Search** | Opens on a search page; results appear after 2+ characters, a theme/quick view, or "See all faculty". Smart search ranks by topic relevance and adds related terms ("fraud" also matches "forensic accounting"; "AI" also matches "machine learning"). Each card shows why it matched. Untick "Include related terms" for exact matching. | `js/app.js` |
| **Find an Expert** | Paste a project description in plain language. Faculty are ranked with a match strength and reasons (matching tags, classes they teach, words in their research). A **suggested team** of up to 3 people covers the most of the request, preferring both universities. | `js/match.js` |
| **Collaboration Map** | Network of faculty linked by shared research, grouped by theme. Gold lines connect UWM and Marquette. Click anyone to see their connections; the side panel lists the top cross-campus opportunities. | `js/network.js` |
| **Shortlist** | Star people anywhere. Add notes, export a spreadsheet (CSV), print or save a one-page PDF, or copy a share link. Saved in the browser. | `js/shortlist.js` |

How matching works (`js/textindex.js`): text is split into stemmed words and two-word phrases, weighted by field
(tags ×3, NMDSI blurb ×2, class titles ×1.5, research summary ×1, department ×1), and ranked with BM25. Results that
cover more of the query's distinct ideas rank higher, with rare words counting more. Related terms come from
`js/synonyms.js`; edit that list freely, no pipeline rerun needed. The map compares people with TF-IDF cosine
similarity and keeps each person's 3 closest matches (similarity ≥ 0.12), plus any pair ≥ 0.3.

Shareable links: a search (`/dashboard/?q=supply%20chain`), an expert query (`/dashboard/?tab=match&mq=fraud%20detection`),
a shortlist (`/dashboard/?tab=shortlist&ids=joseph-wall,layth-alwan`), or a profile (`/dashboard/#satya-aditya-akundi`).

Tests: with the server running, open <http://localhost:8000/dashboard/tests/ui-test.html>. It clicks through every tab
and prints PASS/FAIL for 18 checks. Your own shortlist is restored afterwards.

Libraries load from a CDN: Fuse.js (typo-tolerant name search) and d3 (the map), so the map needs an internet connection.

Logos live in `dashboard/assets/`: `nmdsi-mark.svg` (redrawn from the NMDSI logo; colors navy #0d497a, gold #fdb81b,
sky #81d3f1, gray #bababa), `uwm-logo.svg` (Wikimedia Commons, UWM-logo-2024.svg) and `marquette-logo.png`
(Marquette news-center media kit). The school logos are used unaltered on white backgrounds, per brand guidelines.

## Scraping politely

- `robots.txt` is checked per host, and pages it disallows are skipped and logged. A site's `Crawl-delay` is honored
  (sites.uwm.edu asks for 30 s).
- There is a random 3–6 s delay between requests, and a descriptive User-Agent with contact details
  (`CONTACT_EMAIL` / `CONTACT_URL` at the top of `scrape.py`).
- Raw HTML is cached in `cache/`. Cached pages are never refetched, so the scraper can be interrupted
  (Ctrl+C saves progress) and rerun. Delete a cache file to force a refetch.
- `python scrape.py --offline` re-parses the cached pages without touching the network (use after editing `parsers.py`).
  `python scrape.py --only <id> [<id> ...]` processes just those people.
- `URL_OVERRIDES` in `scrape.py` replaces a person's directory link with a better page. Changing a URL there
  discards that person's cached page on the next run.
- Timeouts, 429s and 5xx responses get 2 retries with backoff. Every URL is logged to `scrape_log.csv`
  (`id, url, status_code, result, notes`).
- A full run is about 170 pages × ~4.5 s, roughly 13–15 minutes.

## Profile parsers (`parsers.py`)

| Domain | Structure |
|---|---|
| `uwm.edu` | `<main id="content">`, h2 sections (Areas of Expertise, Research Interests…) or bold `Label:` paragraphs; prose bios |
| `www.marquette.edu`, `mcw.marquette.edu` | `#facultyPage .bio`, h3 sections (Courses Taught, Research Interests, Recent Grants…) |
| `law.marquette.edu` | h2 Biography; "Courses Taught" as a bold label with a comma-separated list |
| anything else | generic: h1–h4 headings and bold labels, matched against Courses/Teaching/Classes, Research/Interests/Expertise, Grants/Funding, Bio/About |

Course lists also handle two-word UWM subjects (`POL SCI 390`), bare course numbers run together on one line
(`511 Organization of Information 714 Metadata`, used by Information Studies), and two titles joined by one comma.
Semester and role notes ("(Fall 2025 & Spring 2026)", ", lecturer") are removed from titles.

Course codes are also picked out of bio prose ("teaches SW 662 Methods of Social Welfare Research…").

## Enrichment rules (`rules.py`)

All tagging is keyword-based and lives in `rules.py`. Edit it and rerun `python enrich.py`. No re-scraping is needed.

- **theme**: one per person. Research-text keyword hits are added to 2× the department/college hits, and the
  highest score wins. `theme_evidence` lists the keywords that matched, so a wrong theme can be traced to its rule.
- **industries**: zero or more, from the fixed list of 8.
- **funding**: only sponsors named on the profile, in a Grants/Funding section or in a sentence that also
  says funded/grant/award/supported. A sentence about an honor ("Excellence in Research Award") that only says
  "award" does not count. Each sponsor carries the `evidence` text it was found in. If none is named,
  `funding` is `[]` and `funding_status` is `"unknown"`.
- **research_tags**: 3–8 tags. Short research-interest list items from the profile come first, then from the
  directory, then vocabulary matches from prose. Lead-ins ("Her research interests include…", "Research on…")
  are stripped, PDF line wraps inside comma/semicolon lists are rejoined, a blurb that reads as a sentence is
  not chopped into tags, and a filler tag is skipped when a longer tag starts with it ("robotic" after "robotics").
  Profile headings about jobs or degrees ("Research Positions") are not treated as research.
- **college**: inconsistent spellings in the PDF are normalized via `COLLEGE_ALIASES`; the original is in `college_raw`.
  A school listed as a college (School of Information Studies) moves to `department` under its college
  (`COLLEGE_IS_DEPARTMENT`), and a missing college is filled in from the department where it is unambiguous
  (`COLLEGE_FROM_DEPARTMENT`). Both set `college_source` to `inferred`. Names that are not topics (College of
  Community Engagement and Professions) are left out of theme scoring (`NON_TOPICAL_COLLEGES`). The enrich report
  flags any college that is neither an alias target nor in `KNOWN_COLLEGES`.

Every derived field says where it came from: `research_summary_source`, `research_tags_source`,
`theme_source`, and `source` on each industry, class and funding item. Values are `profile` (read off the profile page),
`directory` (from the PDF) or `inferred` (keyword rules). The dashboard's profile panel marks non-profile values as "auto-generated" or "from NMDSI directory".

## Known data quirks in the PDF

- Mehdi Maadooliat is listed twice (pages 17 and 18). The duplicate is merged.
- No profile link: Jacob Rice, Deepak Babu, Mumin Cebe, Laira Anne Stark.
- No title: Thomas Holbrook, Xiaohan Yan, Laira Anne Stark (who also has no college or department).
- Satish Puri's link is a Marquette news article, not a profile, so the generic parser handles it.
- 34 directory links returned 404 (checked Nov 2026). 16 were found at new addresses in the current department
  listings and are in `URL_OVERRIDES` (incl. Henry Duah, whose PDF link said `henry-dual.php`). The other 18
  are not in their department's current listing and have probably left: Chudamani Poudyal, David Krause,
  Giorgo Sertsios, Hunter Sandidge, Jangsu Yoon, Joseph Wall, Keith Dookeran, Kevin Trainor, Laura Roehl,
  Lei Fan, Lillian Campbell, Lu He, Lynne Knobloch-Fedders, Min Sook Park, Samantha Majhor, Tanya Joosten,
  Thomas Schwarz, Thomas Kaczmarek (emeritus, no profile page). Their data comes from the PDF only.
- Courses listed once per semester are de-duplicated (same code + title).
- Swapnil Tripathi's link redirects to a Waukesha campus closure notice. Any redirect whose last URL segment
  differs from the original's is marked `redirected_away`, and nothing from that page is kept.
- Rina Ghose's link is a contact-only lab home page; `URL_OVERRIDES` points to her research statement instead.
  Research summaries longer than 3,000 characters are cut at a sentence end (tags and theme use the full text).
- Nadiyah Johnson, Taly Gilat-Schmidt and Xiaohan Yan's profiles are contact cards with no research, courses
  or bio (`parsed_empty`). Their research comes from the PDF.
- Mohammad Habibur Rahman is listed under "Department of Business Statistics" in the College of Engineering.
