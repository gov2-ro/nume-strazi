#!/usr/bin/env python3
"""Normalise name_categories.subcategory into a consistent vocabulary.

`subcategory` is free text written by whichever model classified the key, so it
drifted: 461 distinct values under only 9 categories as of 2026-08-01, with five
recurring defect classes —

  1. separator drift      "historical event"  vs "historical_event"
                          "public utility" / "public_utility" / "utility"
  2. singular vs plural   "saint"/"saints", "craftsman"/"craftsmen"
  3. adjective vs noun    "geometry"/"geometric"/"geometrical"
                          "topographic"/"topographical"/"topography"
  4. Romanian leakage     "valori", "profesii", "resurse", "codificare",
                          "tehnologie" — the prompt is English, these slipped
  5. tautology            category "abstract" with subcategory "abstract"

Two passes, deliberately separated:

  _mechanical()  lowercase, trim, collapse separators to "_". Pure syntax, no
                 judgement, safe to apply anywhere.
  SYNONYMS       hand-curated equivalences for 2-4 above. Judgement, but only
                 where the two spellings genuinely denote the same thing.

Neither pass invents a controlled vocabulary or drops detail: "sieve_maker"
stays "sieve_maker". Faceting a UI down to a browsable number of options is a
presentation concern, handled by GROUPS (see --groups) which maps the normalised
value to a coarse bucket WITHOUT overwriting it.

Idempotent (CLAUDE.md rule #6): re-running changes nothing.

Usage:
    python3 tools/normalize_taxonomy.py --dry-run     # preview every change
    python3 tools/normalize_taxonomy.py --report      # value counts after
    python3 tools/normalize_taxonomy.py
"""
import argparse, re, sqlite3, sys
from collections import Counter

# ── pass 1: syntax ────────────────────────────────────────────────────────────

def _mechanical(s: str | None) -> str | None:
    """lowercase, trim, and collapse any run of separators into a single "_"."""
    if s is None:
        return None
    s = s.strip().lower()
    s = re.sub(r"[\s/\-]+", "_", s)
    s = re.sub(r"_{2,}", "_", s).strip("_")
    return s or None


# ── pass 2: meaning ───────────────────────────────────────────────────────────
# Applied AFTER _mechanical, so keys here are already underscore-joined and
# lowercase. Left side → right side. Only genuine equivalences.

SYNONYMS = {
    # -- Romanian leakage (defect class 4) --
    "valori": "value", "profesii": "profession", "resurse": "resource",
    "codificare": "numeric", "tehnologie": "technology",

    # -- plural → singular (defect class 2) --
    "saints": "saint", "crafts": "craft", "craftsmen": "craftsman",
    "farmers": "farmer", "millers": "miller", "hunters": "hunter",
    "foresters": "forester", "builders": "builder", "blacksmiths": "blacksmith",
    "barrel_makers": "barrel_maker", "musicians": "musician",
    "outlaws": "outlaw", "tools": "tool", "oil_wells": "oil_well",
    "musical_instruments": "musical_instrument", "textiles": "textile",
    "creatures": "creature", "masons": "mason", "carpenters": "carpenter",
    "gardeners": "gardener", "fishermen": "fisherman", "potters": "potter",
    "merchants": "merchant", "furriers": "furrier", "athletes": "athlete",
    "veterans": "veteran", "heroes": "hero", "aviators": "aviator",
    "archers": "archer", "partisans": "partisan", "romans": "roman",
    "dacians": "dacian", "pandurs": "pandur", "dorobanti": "dorobant",
    "householders": "householder", "operators": "operator",
    "railway_workers": "railway_worker", "oil_workers": "oil_worker",
    "beekeepers": "beekeeping", "values": "value", "objects": "object",
    "ideals": "ideal", "border_guards": "border_guard",
    "historical_figures": "historical_figure",
    # Second wave, 2026-08-01: plurals arriving from the full-backlog run. The
    # vocabulary keeps growing as classification proceeds, which is expected —
    # import_csv.py canonicalises on the way in, so these only need adding once.
    "artists": "artist", "goldsmiths": "goldsmith", "tailors": "tailor",
    "vessels": "vessel", "angels": "angel", "goatherds": "goatherd",
    "pigeon_fanciers": "pigeon_fancier",

    # -- adjective/noun/verb variants of one concept (defect class 3) --
    "geometric": "geometry", "geometrical": "geometry",
    "topographical": "topographic", "topography": "topographic",
    "geographical": "geography", "geographical_feature": "geography",
    "geographic": "geography",
    "philosophical": "philosophy",
    "scientific": "science",
    "literary": "literature",
    "cultural": "culture",
    "industrial": "industry", "manufacturing": "industry",
    "production": "industry", "factory": "industry",
    "artistic": "art", "arts": "art",
    "administrative": "administration",
    "technological": "technology", "technical": "technology",
    "agricultural": "agriculture", "farming": "agriculture", "farm": "agriculture",
    "commercial": "commerce",
    "mine": "mining",
    "sport": "sports",
    "academy": "academic",
    "ethnic": "ethnic_group", "ethnicity": "ethnic_group",
    "demonym": "ethnic_group",
    "architectural": "architecture",
    "astronomical": "astronomy",
    "public_administration": "administration",
    "cooperative_movement": "cooperative",
    "religious_service": "religious",
    "blacksmith_shop": "blacksmith",
    "literary_work": "literature",
    "innkeeping": "inn",
    "press": "media",

    # -- separator-only survivors that also differ in wording (class 1) --
    "public_utility": "utility",
    "urban_development": "urban_planning",
    "place_of_worship": "church",
    "social_class": "social_status",
    "historical_rank": "social_status", "boyar_rank": "social_status",
    "military_logistics": "military",

    # -- numbering family: one concept, six spellings --
    "numerical": "numeric", "numbering": "numeric",
    "numbered_street": "numeric", "ordinal": "numeric",
    "ordinal_number": "numeric", "street_naming": "numeric",

    # -- mythology pantheon markers --
    "greek_goddess": "greek", "roman_deity": "roman",
    "roman_mythology": "roman", "classical_mythology": "classical",
    "goddess": "deity",
}

# Category name repeated as its own subcategory carries no information.
TAUTOLOGY = "general"


def canonical(category: str, subcategory: str | None) -> str | None:
    s = _mechanical(subcategory)
    if s is None:
        return None
    s = SYNONYMS.get(s, s)
    if s == _mechanical(category):
        return TAUTOLOGY
    return s


# ── presentation buckets ──────────────────────────────────────────────────────
# For UI faceting only. A long tail of one-off values is inherent to free-text
# generation and is worth keeping for analysis; a filter dropdown is not. This
# maps the normalised subcategory to a coarse bucket, and is applied by the
# --groups report rather than written back over the data.

GROUPS = {
    "road":        {"county_road", "national_road", "communal_road",
                    "exploitation_road", "road", "ring_road", "street", "bridge",
                    "ramp", "dead_end", "railway", "maritime", "transport"},
    "utilities":   {"utility", "electrical", "water_management", "dam", "canal",
                    "embankment", "relay", "telecommunications", "communication"},
    "numbering":   {"numeric"},
    "military":    {"military", "fortification", "barracks", "border_guard",
                    "veteran", "partisan", "archer", "dorobant", "pandur",
                    "aviation"},
    "religion":    {"religious", "church", "monastery", "chapel", "hermitage",
                    "saint", "clergy", "clerical", "parish", "biblical",
                    "christian_feast", "easter", "annunciation", "cross",
                    "wayside_shrine", "theological", "islamic", "protestant",
                    "cult", "holiday", "coronation"},
    "craft_trade": {"craft", "craftsman", "trade", "blacksmith", "miller",
                    "potter", "carpenter", "mason", "furrier", "barrel_maker",
                    "tailor", "stonecutter", "sieve_maker", "barber_shaver",
                    "merchant", "market", "commerce", "retail", "bakery",
                    "workshop", "brickyard", "dairy", "winery", "wine",
                    "occupational", "tool", "agricultural_tool", "textile",
                    "builder", "fishmonger"},
    "land_work":   {"agriculture", "farmer", "shepherd", "pastoral", "forestry",
                    "forester", "woodcutting", "hunting", "hunter", "fisherman",
                    "beekeeping", "apiary", "gardener", "harvest", "cereals",
                    "poultry", "animal_husbandry", "plantation", "nursery",
                    "greenhouse", "silo", "mill"},
    "industry":    {"industry", "mining", "miner", "metallurgy", "petroleum",
                    "oil_well", "oil_worker", "quarry", "construction",
                    "warehouse", "storage", "container", "depot", "resource"},
    "people":      {"profession", "social_status", "nobility", "operator",
                    "householder", "labor", "athlete", "musician", "poet",
                    "painter", "hero", "aviator", "outlaw", "personal_name",
                    "given_name", "family_name", "historical_figure",
                    "ethnic_group", "dacian", "roman", "moti_people",
                    "railway_worker"},
    "civic":       {"administration", "institutional", "public_service",
                    "public_space", "city_hall", "police", "firefighters",
                    "fire_station", "justice", "legal", "post_office", "bank",
                    "association", "community", "communal_property",
                    "international_organization", "postal_worker"},
    "education":   {"education", "school", "kindergarten", "academic",
                    "science", "museum", "library", "cultural_center"},
    "health":      {"medical", "health", "hospital", "polyclinic", "dispensary",
                    "pharmacy", "spa_baths"},
    "culture":     {"culture", "art", "literature", "music", "folklore",
                    "folk_culture", "folk_music", "folk_tradition",
                    "folk_figure", "tradition", "cultural_tradition", "legend",
                    "epic_literature", "literary_work", "musical_instrument",
                    "writing", "printing", "media"},
    "leisure":     {"sports", "stadium", "arena", "pool", "park", "gazebo",
                    "tourism", "resort", "recreation", "leisure", "camp",
                    "cabin", "hospitality"},
    "built_form":  {"architecture", "architectural", "building", "housing",
                    "residential", "urban", "urban_planning", "urban_feature",
                    "urban_furniture", "settlement", "monument", "tower",
                    "castle", "manor", "complex", "cemetery", "port", "airport",
                    "train_station", "barrier", "land_division", "land",
                    "religious_object", "infrastructure"},
    "ideology":    {"ideological", "communist", "communist_propaganda",
                    "communist_press", "communist_enterprise", "political",
                    "political_event", "socialist_solidarity", "solidarity",
                    "cooperative", "cooperative_movement", "workers", "youth",
                    "revolution", "liberation", "independence", "unification",
                    "republic", "democracy", "emancipation", "equality",
                    "fraternity", "brotherhood", "patriotic", "homeland",
                    "national_day", "national_identity", "national", "monarchy",
                    "dynasty", "progress", "rebirth", "modernity"},
    "history":     {"historical", "historical_event", "national_event", "event",
                    "battle_site", "military_victory", "ancient_history",
                    "archaeology", "historical_monument", "historical_weapon",
                    "historical_social", "historical_group", "commemorative",
                    "regional", "regional_identity", "international", "heroic"},
    "myth":        {"mythology", "classical", "greek", "roman_history",
                    "deity", "creature", "astrology", "astronomy", "ancient"},
    "place":       {"toponymic", "geography", "topographic", "spatial",
                    "direction", "geographical_direction", "boundary",
                    "landmark", "scenic_view", "mound", "furrow", "courtyard",
                    "cul_de_sac", "ascent", "central", "geopolitical"},
    "quality":     {"virtue", "value", "ideal", "moral", "justice", "peace",
                    "freedom", "glory", "triumph", "victory", "honorific",
                    "gratitude", "harmony", "happiness", "hope", "joy",
                    "longing", "emotion", "beauty", "aesthetic", "decorative",
                    "poetic", "quality", "resolve", "abundance", "dignity",
                    "identity", "enlightenment", "philosophy", "symbolic"},
    "descriptive": {"descriptive", "small", "short", "long", "large", "narrow",
                    "main", "main_line", "new", "old", "crooked", "round",
                    "green", "labyrinth", "geometry", "generic", "material",
                    "object", "jewel", "precious_stone", "precious_metals"},
    "nature":      {"natural_phenomena", "light", "flame", "echo", "energy",
                    "flight", "impetus", "morning", "zenith", "horizon",
                    "celestial", "astronomical", "meteorology", "time",
                    "future", "eternity"},
    "social":      {"social", "social_value", "social_group", "human",
                    "human_activity", "civic", "economic", "economy",
                    "technology", "science_tech", "concept", "abstract",
                    "general", "other"},
}
_GROUP_OF = {v: g for g, vs in GROUPS.items() for v in vs}


def group_of(sub: str | None) -> str:
    return _GROUP_OF.get(sub or "", "other")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/streets.db")
    ap.add_argument("--dry-run", action="store_true", help="show changes, write nothing")
    ap.add_argument("--report", action="store_true", help="value counts after normalising")
    ap.add_argument("--groups", action="store_true", help="show the UI bucket rollup")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    rows = con.execute(
        "SELECT core_name_norm, category, subcategory FROM name_categories"
    ).fetchall()

    changes, updates = [], []
    for key, cat, sub in rows:
        new = canonical(cat, sub)
        if new != sub:
            changes.append((key, cat, sub, new))
            updates.append((new, key))

    before = len({s for _, _, s in rows if s})
    after = len({canonical(c, s) for _, c, s in rows if canonical(c, s)})
    print(f"{len(rows)} rows · distinct subcategory {before} → {after} "
          f"({before - after} merged) · {len(changes)} rows change")

    if args.dry_run:
        for key, cat, old, new in sorted(changes, key=lambda r: (r[1], str(r[2]))):
            print(f"  {cat:<15} {str(old):<28} → {new:<28} ({key})")
        return 0

    if updates:
        con.executemany(
            "UPDATE name_categories SET subcategory = ? WHERE core_name_norm = ?",
            updates)
        con.commit()
        print(f"Updated {len(updates)} rows.")
    else:
        print("Nothing to change.")

    if args.report:
        print("\n── subcategory counts by category ──")
        cur = con.execute(
            "SELECT category, subcategory, COUNT(*) FROM name_categories "
            "GROUP BY category, subcategory ORDER BY category, COUNT(*) DESC")
        cat_now = None
        for cat, sub, n in cur:
            if cat != cat_now:
                cat_now = cat
                print(f"\n{cat}")
            print(f"    {str(sub):<28} {n}")

    if args.groups:
        print("\n── UI buckets (presentation only, not written back) ──")
        counts, unmapped = Counter(), Counter()
        for _, cat, sub in con.execute(
                "SELECT core_name_norm, category, subcategory FROM name_categories"):
            g = group_of(sub)
            counts[g] += 1
            if g == "other" and sub:
                unmapped[sub] += 1
        for g, n in counts.most_common():
            print(f"    {g:<14} {n}")
        if unmapped:
            print(f"\n  unbucketed values ({len(unmapped)} distinct, "
                  f"{sum(unmapped.values())} rows):")
            for s, n in unmapped.most_common(40):
                print(f"    {s:<28} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
