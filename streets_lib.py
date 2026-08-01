"""Shared helpers used by build_db.py and the OSM enrichment tools.

Kept stdlib-only and side-effect-free so it's safe to import from anywhere.
"""
import re
import unicodedata

DIACRITIC_FIX = str.maketrans({"ş": "ș", "ţ": "ț", "Ş": "Ș", "Ţ": "Ț"})


def fix_diacritics(s):
    """Normalize cedilla forms (ş, ţ) to comma-below (ș, ț). Display-safe."""
    return s.translate(DIACRITIC_FIX) if s else s


_ABBR_EXPANSIONS = [
    # G-ral / G.ral → general. Must run before diacritic stripping so case is intact.
    (re.compile(r'\bG[-.]ral\b', re.IGNORECASE), 'General'),
]


def normalize_match(s):
    """Lowercase ASCII, î≡â collapsed. For grouping/joining only — never display."""
    if not s:
        return ""
    for pattern, replacement in _ABBR_EXPANSIONS:
        s = pattern.sub(replacement, s)
    s = s.replace("î", "â").replace("Î", "Â")
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


_SLUG_NONALNUM = re.compile(r"[^a-z0-9]+")


def slugify(s):
    """URL-safe slug: ASCII-lowered, î≡â folded, runs of non-alphanumerics → '-'.

    Empty / None / whitespace-only input returns "".
    Trailing/leading hyphens are trimmed. Used for street/person/uat/theme URLs.
    """
    base = normalize_match(s)
    if not base:
        return ""
    return _SLUG_NONALNUM.sub("-", base).strip("-")


# Street-type prefixes used both during ingest (build_db) and when normalizing OSM
# `name` tags before joining to the registry. Sorted longest-first so greedy
# stripping doesn't match "Strada" inside "Stradela".
STREET_TYPES = sorted([
    "Bulevardul", "Fundătura", "Cartierul", "Prelungirea", "Strada", "Aleea",
    "Intrarea", "Calea", "Drumul", "Piața", "Șoseaua", "Ulița", "Splaiul",
    "Pasajul", "Cheiul", "Trecerea", "Cărarea", "Stradela", "Rampa",
], key=len, reverse=True)


def strip_street_type(name):
    """Return (street_type, rest) — best-effort match against the known prefix list.

    For OSM names where the type may be abbreviated (`Str.`, `Bd.`, `Sos.`, `Cal.`),
    we expand a small set first so the prefix list matches.
    """
    if not name:
        return None, name
    s = fix_diacritics(name).strip()
    abbr_map = [
        ("Bd-ul ", "Bulevardul "),
        ("Bd. ",   "Bulevardul "),
        ("B-dul ", "Bulevardul "),
        ("Bul. ",  "Bulevardul "),
        ("Str. ",  "Strada "),
        ("Sos. ",  "Șoseaua "),
        ("Șos. ",  "Șoseaua "),
        ("Cal. ",  "Calea "),
        ("Pța. ",  "Piața "),
        ("Pța ",   "Piața "),
        ("Al. ",   "Aleea "),
        ("Int. ",  "Intrarea "),
        ("Dr. ",   "Drumul "),  # ambiguous with the title "Dr." — only at start of OSM names
    ]
    for old, new in abbr_map:
        if s.startswith(old):
            s = new + s[len(old):]
            break
    for st in STREET_TYPES:
        if s.startswith(st + " "):
            return st, s[len(st):].strip()
    return None, s


# ---------- title / rank / saint / date feature extraction ----------
# Shared by build_db.py (registry) and tools/osm_ingest.py, tools/postal_ingest.py
# (external sources) so all three produce comparable core_name/core_name_norm.
TITLES = sorted([
    "Profesor Universitar Doctor","Profesor Universitar",
    "Profesor Doctor","Profesor","Prof. Univ. Dr.","Prof. Dr.","Prof.",
    "Academician","Acad.","Doctor","Dr.","Ing.","Inginer","Arh.","Arhitect",
    "Învățătorul","Învățător","Înv.",
    "Pictorul","Pictor","Sculptorul","Sculptor",
    "Compozitorul","Compozitor","Poetul","Poet","Poetă",
    "Scriitorul","Scriitor","Dramaturgul","Dramaturg","Filozoful","Filozof",
    "Părintele","Preotul","Preot","Episcopul","Episcop",
    "Mitropolitul","Mitropolit","Patriarhul","Patriarh","Protopop",
    "Ziarist","Actor","Avocat","Medic","Regizor","Fizician",
], key=len, reverse=True)

RANKS = sorted([
    "Locotenent-colonel","General-locotenent","Sublocotenent",
    "General","Colonel","Maior","Major","Căpitan","Locotenent","Sergent","Caporal","Soldat",
    "Mareșal","Amiral","Comandor","Aviator","Plutonier","Spătar",
    "Voievodul","Voievod","Domnitorul","Domnitor",
    "Regele","Regina","Împăratul","Împărăteasa","Prințul","Prinț","Prințesa",
    "Eroii","Eroul","Erou","Martirii","Martirul","Martir",
    "Haiducul",
], key=len, reverse=True)

SAINTS = sorted([
    "Sfinții Apostoli","Sfinții","Sfântul","Sfânta","Sfântu","Sfânt",
    "Sf-a","Sfta.","Sf.",
], key=len, reverse=True)

MONTHS_RO = ["ianuarie","februarie","martie","aprilie","mai","iunie",
             "iulie","august","septembrie","octombrie","noiembrie","decembrie"]
DATE_RE = re.compile(r"^(\d{1,2})\s+(" + "|".join(MONTHS_RO) + r")$", re.IGNORECASE)
# Unnamed numbered streets. The bare form ("23", "23A") and the "Nr."-prefixed
# form ("Nr. 23", "Nr.7", "Nr 11") are the same thing; only the bare one was
# matched until 2026-08-01, leaving 198 "nr. N" keys looking like real names and
# sitting in the LLM classifier's candidate pool as guaranteed skips.
# The trailing-text guard matters: "Nr. 1 Principala Mierea" is a real name and
# must NOT match.
NUMERIC_RE = re.compile(r"^(?:nr\.?\s*)?\d+[A-Za-z]?$", re.IGNORECASE)


def parse_artery(raw):
    """Split a raw 'Arteră' cell into (street_type, name, aliases).

    Fixes diacritics, extracts parenthetical alias candidates, then matches
    the remaining text against STREET_TYPES as a leading prefix.
    """
    if not raw:
        return None, None, []
    s = fix_diacritics(raw).strip()
    aliases_raw = re.findall(r"\(([^)]+)\)", s)
    main = re.sub(r"\s*\([^)]+\)", "", s).strip()
    aliases = [a.strip() for a in aliases_raw if len(a.strip()) > 2]
    for st in STREET_TYPES:
        if main.startswith(st + " "):
            return st, main[len(st):].strip(), aliases
    return None, main, aliases


def extract_features(name):
    """Peel numeric/date/saint/title/rank prefixes off a (type-stripped) name.

    Returns a dict with title, rank, is_saint, is_date, is_numeric, core_name.
    Greedy multi-pass peeling handles chains like "Colonel Dr. Ion X".
    """
    f = {"title": None, "rank": None, "is_saint": 0, "is_date": 0, "is_numeric": 0, "core_name": name}
    if not name:
        return f
    if NUMERIC_RE.match(name):
        f["is_numeric"] = 1
        f["core_name"] = None
        return f
    if DATE_RE.match(name):
        f["is_date"] = 1
        f["core_name"] = name
        return f

    remaining = name
    progress = True
    while progress:
        progress = False
        for s in SAINTS:
            if remaining == s or remaining.startswith(s + " "):
                f["is_saint"] = 1
                remaining = remaining[len(s):].strip()
                progress = True
                break
        if progress:
            continue
        for t in TITLES:
            if remaining == t or remaining.startswith(t + " "):
                f["title"] = (f["title"] + " " + t) if f["title"] else t
                remaining = remaining[len(t):].strip()
                progress = True
                break
        if progress:
            continue
        for r in RANKS:
            if remaining == r or remaining.startswith(r + " "):
                f["rank"] = (f["rank"] + " " + r) if f["rank"] else r
                remaining = remaining[len(r):].strip()
                progress = True
                break
    f["core_name"] = remaining if remaining else None
    return f


# County-name lookup for sources that give a full județ name (e.g. postal
# registries) rather than the registry's 2-letter code. Keys are the
# normalize_match()-ed full name; kept here (not site_queries.py, which is
# presentation-layer) so ETL tools can use it without a heavy import.
_JUDET_COD_TO_NAME = {
    "AB": "Alba", "AG": "Argeș", "AR": "Arad", "B": "București", "BC": "Bacău",
    "BH": "Bihor", "BN": "Bistrița-Năsăud", "BR": "Brăila", "BT": "Botoșani",
    "BV": "Brașov", "BZ": "Buzău", "CJ": "Cluj", "CL": "Călărași",
    "CS": "Caraș-Severin", "CT": "Constanța", "CV": "Covasna", "DB": "Dâmbovița",
    "DJ": "Dolj", "GJ": "Gorj", "GL": "Galați", "GR": "Giurgiu", "HD": "Hunedoara",
    "HR": "Harghita", "IF": "Ilfov", "IL": "Ialomița", "IS": "Iași",
    "MH": "Mehedinți", "MM": "Maramureș", "MS": "Mureș", "NT": "Neamț",
    "OT": "Olt", "PH": "Prahova", "SB": "Sibiu", "SJ": "Sălaj", "SM": "Satu Mare",
    "SV": "Suceava", "TL": "Tulcea", "TM": "Timiș", "TR": "Teleorman",
    "VL": "Vâlcea", "VN": "Vrancea", "VS": "Vaslui",
}
JUDET_NAME_TO_COD = {normalize_match(v): k for k, v in _JUDET_COD_TO_NAME.items()}
