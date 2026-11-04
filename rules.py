"""Keyword rules used by enrich.py. Edit freely, then rerun `python enrich.py`.

Matching is case-insensitive on whole words/phrases. A keyword ending in "*" matches as a prefix
("optimi*" matches optimize and optimization, but not optimal).
All-caps keywords ("AI", "GIS", "NSF") are matched case-sensitively so "AI" does not match "ai".
"""

# --- College name cleanup (regex -> canonical name) -------------------------------------------
# The PDF spells several colleges inconsistently; groupings use the canonical name.
COLLEGE_ALIASES = {
    r"^Kling?l?er College of Arts and Sciences?$": "Klingler College of Arts and Sciences",
    r"^College of Letters? (and|&) Sciences?\b.*$": "College of Letters & Science",
    r"^College of Engineering (and|&) Applied Sciences?,?$": "College of Engineering & Applied Science",
    r"^Helen Ba(d|da)r School of Social Welfare$": "Helen Bader School of Social Welfare",
    r"^(Joseph J\.? )?Zilber (College|School) of Public Health$": "Zilber College of Public Health",
    r"^Lubar (School|College) of Business$": "Lubar College of Business",
    r"^(Marquette University )?School of Dentistry$": "School of Dentistry",
    r"^Marquette University Law School$": "Law School",
    r"^School of Rehabilitation (Sciences )?and Technology$": "School of Rehabilitation Sciences and Technology",
    # only Marquette has an Arts and Sciences college: Klingler (Karen Andeen, Samantha Majhor)
    r"^(College|School) of Arts and Sciences?$": "Klingler College of Arts and Sciences",
    # Odai Khasawneh, IT Management: that department is in the Lubar College of Business
    r"^Lubar College of Engineering$": "Lubar College of Business",
    # UWM's nursing unit is the College of Nursing (groupings are per university, so Marquette's stays separate)
    r"^School of Nursing$": "College of Nursing",
}

# Units the PDF lists as a college that are really a school inside one. When the person has no department,
# the unit becomes their department.
COLLEGE_IS_DEPARTMENT = {
    "School of Information Studies": "College of Community Engagement and Professions",
}

# College for people the PDF lists without one, inferred from (university, department regex).
COLLEGE_FROM_DEPARTMENT = [
    ("UW-Milwaukee", r"Helen Bader School of Social Welfare", "Helen Bader School of Social Welfare"),
    ("UW-Milwaukee", r"^Department of Computer Science$", "College of Engineering & Applied Science"),
]

# College names that say nothing about research topics, left out of theme/industry scoring
# ("Community" in this name was pushing everyone in it toward Social Science & Policy).
NON_TOPICAL_COLLEGES = {"College of Community Engagement and Professions", "College of General Studies", "Academic Affairs"}

# Correctly spelled colleges that need no alias. A college that is neither here nor an alias target is flagged.
KNOWN_COLLEGES = {
    "College of Business Administration", "College of Education", "College of Health Sciences", "College of Nursing",
    "Diederich College of Communication", "Opus College of Engineering", "Raynor Library",
    "College of Community Engagement and Professions", "College of General Studies", "Academic Affairs",
    "Peck School of the Arts", "School of Freshwater Sciences",
}

# --- Themes: one primary theme per person ------------------------------------------------------
# Score = keyword hits in research text + DEPARTMENT_WEIGHT x hits in department/college text.
# Highest score wins; ties go to the theme listed first. No hits at all -> "Unclassified".
DEPARTMENT_WEIGHT = 2
THEMES = {
    "AI/ML & NLP": [
        "artificial intelligence", "AI", "machine learning", "deep learning", "neural network*", "NLP",
        "natural language", "large language model*", "LLM*", "generative AI", "agentic", "computer vision",
        "reinforcement learning", "data mining", "data science", "robot*", "autonomous", "image processing",
        "pattern recognition", "recommender", "text mining", "computer science",
    ],
    "Health Informatics": [
        "health informatics", "informatics", "clinical", "patient*", "electronic health record*", "EHR",
        "public health", "nursing", "health care", "healthcare", "medical", "dental", "dentistry",
        "population health", "health outcomes", "opioid", "substance use", "mental health", "epidemiolog*",
        "health sciences", "physical therapy", "exercise science", "rehabilitation",
    ],
    "Statistics & Mathematics": [
        "statistic*", "mathematic*", "probability", "stochastic", "bayesian", "time series", "regression",
        "inference", "extreme value", "random network*", "integral equations", "numerical", "applied math*",
        "biostatistic*", "survival analysis", "high-dimensional", "spatial statistics", "uncertainty quantification",
        "hypothes*", "functional data", "simulation*",
        # physical sciences have no theme of their own; they land here (consider adding a theme)
        "physics", "astrophysic*", "cosmology", "relativity", "astronomy",
    ],
    "Operations & Supply Chain": [
        "supply chain", "operations management", "operations research", "logistics", "inventory",
        "scheduling", "queueing", "optimi*", "decision making under uncertainty", "manufacturing",
        "production", "statistical process control", "quality control", "forecasting", "sustainable operations",
        "revenue management", "dynamic pricing", "transportation",
    ],
    "Finance & Economics": [
        "financ*", "economic*", "accounting", "insurance", "actuarial", "risk management", "banking",
        "investment*", "asset pricing", "corporate disclosure", "audit*", "tax", "taxation", "market*", "e-commerce",
        "advertising", "consumer*", "business analytics", "fintech",
    ],
    "Climate & Environment": [
        "climate", "environment*", "water", "hydrolog*", "freshwater", "ecolog*", "sustainab*", "energy",
        "pollution", "weather", "atmospher*", "geospatial", "GIS", "remote sensing", "agricultur*", "urban",
        "geograph*", "earth science*", "meteorolog*", "watershed", "geoscience",
        # combustion / thermal-fluid engineering grouped with energy
        "combustion", "fluid*", "thermal", "heat transfer",
    ],
    "Security & Systems": [
        "security", "cybersecurity", "privacy", "cryptograph*", "computer network*", "network security", "internet of things", "IoT",
        "distributed systems", "cloud", "information technology", "information systems", "programming languages", "type systems", "static analysis", "high performance computing", "HPC", "parallel computing",
        "critical infrastructure", "blockchain", "embedded", "power systems", "signal processing",
        "wireless", "software engineering", "databases", "electrical engineering", "computer engineering", "ICT",
    ],
    "Social Science & Policy": [
        "social", "sociolog*", "criminolog*", "crime", "criminal justice", "political", "policy", "elections",
        "survey*", "psycholog*", "behavior*", "education", "learning analytics", "organizations",
        "inequality", "community", "social work", "public administration", "urban planning", "gerontolog*",
        "workplace", "technostress", "human behavior*", "misinformation", "disinformation", "fake news",
    ],
    "Biology & Biomedical": [
        "biolog*", "bioinformatics", "genom*", "genetic*", "microbio*", "molecular", "protein*", "cell*",
        "neuroscience", "biomedical", "biophysic*", "evolution*", "phage", "chemistry", "chemical",
        "imaging", "optical", "biomechanic*", "physiolog*", "cancer", "drug", "musculoskeletal", "biomimetic",
        "rehabilitation engineering", "biomaterial*",
    ],
    "Humanities & Communication": [
        "communication", "journalism", "media", "rhetoric", "history", "historical", "philosophy",
        "theology", "religio*", "literature", "language*", "linguistic*", "digital humanities", "arts",
        "music", "law", "legal", "intellectual property", "ethics", "library", "archiv*", "fiction", "english",
        "writing", "syriac", "early christianity",
    ],
}

# --- Industries: zero or more per person -------------------------------------------------------
INDUSTRIES = {
    "Healthcare": [
        "health*", "clinical", "patient*", "medical", "medicine", "hospital*", "nursing", "dental",
        "disease*", "cancer", "opioid", "substance use", "mental health", "rehabilitation", "biomedical",
        "pharma*", "drug",
    ],
    "Finance & Insurance": [
        "financ*", "insurance", "actuarial", "banking", "investment*", "accounting", "audit*",
        "credit", "risk management", "fintech", "asset pricing", "corporate disclosure",
    ],
    "Manufacturing & Supply Chain": [
        "manufacturing", "supply chain", "logistics", "inventory", "production", "operations management",
        "quality control", "statistical process control", "robot*", "industrial", "assembly", "materials",
    ],
    "Energy & Environment": [
        "energy", "climate", "environment*", "water", "freshwater", "pollution", "sustainab*",
        "power systems", "renewable", "ecolog*", "agricultur*", "hydrolog*",
    ],
    "Technology & Cybersecurity": [
        "cybersecurity", "security", "privacy", "software", "cloud", "internet of things", "IoT",
        "computing", "computer network*", "artificial intelligence", "machine learning", "AI", "information technology",
        "digital transformation", "blockchain", "data science",
    ],
    "Public Sector & Policy": [
        "policy", "public administration", "government", "crime", "criminal justice", "criminolog*",
        "political", "elections", "public health", "social welfare", "social work", "urban planning",
        "law", "legal",
    ],
    "Education": [
        "education", "educational", "teaching", "learning analytics", "students", "online learning",
        "higher education", "curriculum", "STEM education",
    ],
    "Marketing & Retail": [
        "marketing", "advertising", "retail", "consumer*", "e-commerce", "customer*", "brand*",
        "promotion", "pricing", "shopping",
    ],
}

# --- Funding: sponsors must be explicitly named on the profile page --------------------------
# Checked in order; the first matching sponsor type claims the text it matched.
FUNDING_SPONSORS = {
    "NSF": [r"\bNSF\b", r"National Science Foundation"],
    "NIH": [r"\bNIH\b", r"National Institutes? of Health", r"\b(NCI|NIMH|NIDA|NIAAA|NHLBI|NICHD|NIGMS|NINDS|"
            r"NIDDK|NIEHS|NIBIB|NINR|NIDCR|NLM|NIA)\b"],
    "DoD": [r"\bDoD\b", r"Department of Defense", r"\bDARPA\b", r"Office of Naval Research", r"\bONR\b",
            r"Army Research", r"\bAFOSR\b", r"Air Force Research"],
    "DOE": [r"\bDOE\b", r"Department of Energy", r"\bARPA-E\b"],
    "Other federal": [r"\bUSDA\b", r"\bNASA\b", r"\bNOAA\b", r"\bEPA\b", r"\bNEH\b", r"\bCDC\b", r"\bHRSA\b",
                      r"\bAHRQ\b", r"\bIES\b", r"Department of Education", r"\bUSGS\b", r"Department of Transportation"],
    "internal": [r"Way Klingler", r"Regular Research Grant", r"Research Growth Initiative", r"\bRGI\b",
                 r"UWM Research Foundation", r"Northwestern Mutual Data Science Institute", r"\bNMDSI\b",
                 r"seed grant", r"internal(ly)? fund", r"Marquette University (Strategic|Research|Summer)"],
    "industry partner": [r"industry[- ](sponsored|partner|funded)", r"Northwestern Mutual", r"Johnson Controls",
                         r"Rockwell", r"GE Healthcare", r"Advocate Aurora", r"Froedtert", r"Microsoft", r"Google",
                         r"Amazon", r"\bIBM\b", r"Kohl's", r"Harley-Davidson", r"A\.O\. Smith", r"Badger Meter"],
    "foundation": [r"\b[A-Z][\w.&' -]{2,60} Foundation\b", r"\bFoundation for\b"],
}
# A sentence must mention one of these for a sponsor name in prose to count as funding.
# Lines inside a "Grants" / "Funding" section always count.
FUNDING_CONTEXT = r"\b(fund(ed|ing|s)?|grants?|awards?|awarded|supported by|sponsor(ed|s)?|fellowship|CAREER)\b"
# "award" alone in a sentence about an honor ("Excellence in Research Award") is recognition, not funding,
# unless the sentence also uses one of the stronger words above.
HONOR_CONTEXT = r"\b(excellence|outstanding|distinguished|recognition|recogni[sz]ed|honou?r(ed|s)?|best paper|teaching award)\b"
STRONG_FUNDING_CONTEXT = r"\b(fund(ed|ing|s)?|grants?|supported by|sponsor(ed|s)?)\b"

# --- Research tags -------------------------------------------------------------------------------
# Short research-interest list items from the profile (or directory) become tags directly.
# Prose is scanned for these phrases (keyword -> tag) to reach at least MIN_TAGS.
MIN_TAGS, MAX_TAGS = 3, 8
MAX_TAG_LENGTH = 60
# Lead-ins removed before a research blurb is split into list items:
# "Her research interests include social tagging, metadata, ..." -> "social tagging, metadata, ..."
TAG_LEADIN = (r"^(?:(?:dr\.?\s+)?[\w-]+[’']s|her|his|my|their|our)\s+(?:current\s+)?research(?:\s+interests?)?"
              r"\s+(?:include|includes|are|is|focus(?:es)?\s+on|centers?\s+on)\s+")
# Prefixes removed from single items: "Research on intellectual property" -> "intellectual property"
TAG_ITEM_PREFIX = r"^(?:research\s+on|specialization\s+in|studies\s+of|with\s+(?:special\s+)?interests?\s+in)\s+"
# An item starting like this is a clause from a sentence ("As a scholar trained in writing", "predominantly situated
# in sub-Saharan Africa"). Short clauses are dropped; a clause over 6 words means the blurb is prose, not a list.
PROSE_ITEM_START = (r"^(?:as|in|of|to|with|by|from|my|our|his|her|their|which|that|where|while|how|what|why|whether|"
                    r"predominantly|primarily|particularly|especially|mainly|mostly|specifically)\b")
TAG_VOCAB = {
    "ICTs": "ICT", "information and communication technolog*": "ICT", "africa*": "Africa",
    "rhetoric*": "rhetoric", "reproductive": "reproductive health", "infertility": "infertility",
    "health advocacy": "health advocacy", "lived experience": "lived experience",
    "machine learning": "machine learning", "deep learning": "deep learning",
    "artificial intelligence": "artificial intelligence", "natural language processing": "NLP",
    "large language model*": "large language models", "computer vision": "computer vision",
    "reinforcement learning": "reinforcement learning", "data science": "data science",
    "data mining": "data mining", "big data": "big data", "neural network*": "neural networks",
    "supply chain*": "supply chain", "operations management": "operations management",
    "inventory": "inventory control", "scheduling": "scheduling", "queueing": "queueing theory",
    "optimization": "optimization", "forecasting": "forecasting", "logistics": "logistics",
    "statistical process control": "statistical process control", "dynamic pricing": "dynamic pricing",
    "statistic*": "statistics", "bayesian": "Bayesian methods", "time series": "time series",
    "stochastic": "stochastic models", "probability": "probability", "spatial": "spatial analysis",
    "GIS": "GIS", "remote sensing": "remote sensing", "crime": "crime", "criminolog*": "criminology",
    "public health": "public health", "health informatics": "health informatics",
    "informatics": "informatics", "clinical": "clinical research", "mental health": "mental health",
    "substance use": "substance use", "opioid*": "opioids", "epidemiolog*": "epidemiology",
    "bioinformatics": "bioinformatics", "genom*": "genomics", "microbio*": "microbiology",
    "evolution*": "evolution", "imaging": "imaging", "cancer": "cancer", "neuroscience": "neuroscience",
    "climate": "climate", "water": "water resources", "hydrolog*": "hydrology", "energy": "energy",
    "sustainab*": "sustainability", "environment*": "environment", "pollution": "pollution",
    "cybersecurity": "cybersecurity", "security": "security", "privacy": "privacy",
    "internet of things": "IoT", "IoT": "IoT", "cloud": "cloud computing",
    "high performance computing": "HPC", "parallel": "parallel computing", "robot*": "robotics",
    "economic*": "economics", "financ*": "finance", "accounting": "accounting", "insurance": "insurance",
    "marketing": "marketing", "advertising": "advertising", "e-commerce": "e-commerce",
    "consumer*": "consumer behavior", "policy": "policy", "political": "politics",
    "elections": "elections", "survey*": "survey research", "education": "education",
    "communication": "communication", "media": "media", "social media": "social media",
    "ethics": "ethics", "law": "law", "intellectual property": "intellectual property",
    "meta-analysis": "meta-analysis", "quantitative methods": "quantitative methods",
    "mixed methods": "mixed methods", "visualization": "visualization", "networks": "networks",
    "manufacturing": "manufacturing", "materials": "materials", "mechanics": "mechanics",
    "signal processing": "signal processing", "image processing": "image processing",
    "digital transformation": "digital transformation", "aging": "aging", "gerontolog*": "gerontology",
    "biomechanic*": "biomechanics", "rehabilitation": "rehabilitation", "musculoskeletal": "musculoskeletal health",
    "meteorolog*": "meteorology", "weather": "weather", "combustion": "combustion", "fluid*": "fluid dynamics",
    "physics": "physics", "astrophysic*": "astrophysics", "material*": "materials", "surface*": "surfaces",
    "science fiction": "science fiction", "literature": "literature", "information technology": "information technology",
    "technostress": "technostress", "workplace": "workplace", "type systems": "type systems",
    "programming": "programming languages", "distributed system*": "distributed systems",
    "international trade": "international trade", "trade": "trade", "industrial organization": "industrial organization",
    "uncertainty quantification": "uncertainty quantification", "simulation*": "simulation", "modeling": "modeling",
    "hypothes*": "hypothesis testing", "gene expression": "gene expression", "watershed": "watersheds",
    "urban": "urban studies", "decision making": "decision making", "algorithm*": "algorithms",
    "health": "health", "social": "social science", "quantitative": "quantitative methods", "qualitative": "qualitative methods",
    "psycholog*": "psychology", "sociolog*": "sociology", "data": "data analysis",
    "educat*": "education", "identity": "identity", "exercise": "exercise science", "textual": "text analysis",
    "video": "video", "visual*": "visual content", "executive compensation": "executive compensation",
    "mixed-method*": "mixed methods", "linear models": "linear models", "dominance analysis": "dominance analysis",
}

# --- Dashboard preset ----------------------------------------------------------------------------
# "Ops/Supply Chain + AI": theme in PRESET_THEMES, OR any tag/research text matching PRESET_KEYWORDS.
PRESET_NAME = "Ops/Supply Chain + AI"
PRESET_THEMES = ["Operations & Supply Chain", "AI/ML & NLP"]
PRESET_KEYWORDS = ["supply chain", "operations management", "operations research", "logistics",
                   "inventory", "scheduling", "queueing", "manufacturing", "production planning"]
