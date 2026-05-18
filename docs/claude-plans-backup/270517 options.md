Here's a brainstorm built on your two confirmed ideas (street →
  cities, category → streets). I'll group additional ideas by
  "browsing axis" and flag which I'd push first.

  A. Drill-into-entity views (your two ideas + extensions)

  A1. Street name → UATs (your idea). Click "Mihai Eminescu" → ranked
   list of UATs (by județ), e.g. "PH/Ploiești · 4 străzi". Hover
  shows alternate-name variants.

  A2. Category/theme → streets (your idea). Click 🌿 flori → all
  flower-derived names ranked; click 🚩 ideologic > unire → "Unirii
  (847)", "Marii Uniri (132)", etc.

  A3. Person → bio + map of presence. Click a person chip → side
  panel with: era, profession, nationality, Wikipedia link (we have
  wiki_ro_url), QID badge, portrait, and the full county/UAT
  distribution. This is just A1 + person metadata — natural
  extension.

  A4. UAT lookup ("my town"). Search "Sibiu" or "Comuna Cornu" → see
  its full street roster, themed breakdown (% persoană / natură /
  religios), top-5 honorees, and what makes it distinctive vs.
  national average.

  B. Cross-cutting facet browsers

  B1. Profession atlas. Click ✍️ scriitor (in the existing Profession
   panel) → top writers by streets, plus their county strongholds.

  B2. Era atlas. Click 🎩 interbelic → all interbelic-era persons,
  with a map showing where they cluster.

  B3. Saints index. Dedicated browser of all is_saint = 1 patterns:
  Sf. Maria, Sf. Nicolae, etc., with geographic spread.

  B4. Date catalog. All is_date = 1 streets: 1 Decembrie, 24
  Ianuarie, 22 Decembrie, with brief historical hooks.

  C. Discovery / serendipity

  C1. Free-text search. Single search box, fuzzy-matches across
  street names, persons, and UATs. Useful even before any of the
  above.

  C2. Random street button. "Surprise me" — pulls a random street,
  shows its theme + locations + (if person) bio.

  C3. "Did you know" tile rotator. Surfaces precomputed factoids:
  "Petöfi Sándor has 58 streets, all in Transilvania", "Only one
  street in România is named Stejarii Pădurați", etc.

  D. Comparison / pattern-hunting

  D1. Județ ↔ județ side-by-side. Pick two counties, see overlapping
  vs. distinctive name profiles.

  D2. Co-occurrence ("often appears with"). Names that frequently
  share a UAT — Eminescu + Creangă + Caragiale form a stable trio.

  D3. Multi-facet filter on the chip cloud. Combine gender × era ×
  profession × nationality (e.g., "women writers from the interwar
  period"). Builds on the existing Bărbați/Femei/Non-române split.

  E. Architectural decision lurking underneath

  All A/B require a "click → detail" pattern. Three structural
  options:

  - Inline expansion — click a chip, it expands a panel under it.
  Simplest, no routing.
  - Modal overlay — click → modal with detail; preserves scroll
  position.
  - Detail pages — /strada/eminescu, /persoana/Q184935, /judet/PH.
  Real URLs, shareable, but adds Jinja routes and breaks the
  single-page feel.
