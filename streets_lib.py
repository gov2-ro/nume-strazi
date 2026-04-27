"""Shared helpers used by build_db.py and the OSM enrichment tools.

Kept stdlib-only and side-effect-free so it's safe to import from anywhere.
"""
import unicodedata

DIACRITIC_FIX = str.maketrans({"ş": "ș", "ţ": "ț", "Ş": "Ș", "Ţ": "Ț"})


def fix_diacritics(s):
    """Normalize cedilla forms (ş, ţ) to comma-below (ș, ț). Display-safe."""
    return s.translate(DIACRITIC_FIX) if s else s


def normalize_match(s):
    """Lowercase ASCII, î≡â collapsed. For grouping/joining only — never display."""
    if not s:
        return ""
    s = s.replace("î", "â").replace("Î", "Â")
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


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
