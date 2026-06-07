# Manual QA checklist — 2026-06-07 quirky + map batch

Run `python3 build_site.py --variant default --detail --serve --port 9000`, open
`http://localhost:9000/`. Expected values are from the build used to ship the
panels; if a number is off, the wiring regressed.

## Landing page — Task 2 (lexical / anomalies)

- [ ] **#abecedar** (Abecedar · litera inițială) — 26 bars A→Z, **C** clearly the
  tallest (3,282 distinct names). Header reads **29.737 nume distincte**. Hover a
  bar → title shows `letter · N nume · M străzi`.
- [ ] **#curiozitati-lexicale** (Curiozități lexicale)
  - Palindrome chips: **Sebeș (7 str.)**, Anina (6), Salaș, Ciric, Laval, Potop,
    Seles, Somoș. No "A III-a"-style enumerators.
  - Longest list top = **„Florin Popescu - Campion Olimpic Sydnei 2000" · 44 car.**
    No "DN65A de la km…" highway rows.
  - Shortest chips: Tei, Olt, Iza, Dej, VII, CAP, Șes, Dos (all 3 chars, no single
    letters).
  - Caption: **22.687 nume (76,3%)** apar într-o singură localitate.
- [ ] **#nume-propozitii** (Nume ca propoziții) — header **517 nume · 662 străzi**.
  Top rows: Peste Vale (13), Sub Coastă (13), Pe Vale (12), După Grădini (8).
- [ ] **#nume-universale** (Nume în toate județele · mai puțin unul) — header
  **19 nume în toate 42**. Rows show name + red `− <județ>` holdout + street count:
  Trandafirilor −B 496, Morii −B 494, Lalelelor −CV 375, Crinului −CS 369.

## Landing page — Task 1 (geo-ego / lifecycle)

- [ ] **#secole-nastere** (Secolul nașterii) — **sec. 19** bar dominates (208 p /
  7.697 str.); sec. 1 present (173 str / 1 p). Caption names Decebal & Traian.
- [ ] **#geografia-gloriei** (Geografia gloriei) — two sub-sections:
  - *Profet în țara lui*: Eminescu 300 str / **7 acasă (2,3%)** n. BT; Tudor
    Vladimirescu 293 / 5; Creangă 290 / 5; Cuza 280 / 7.
  - *Județe exportatoare*: B 531 (13 onor.), IS 493 (9), **BT 490 (4 onor.)**,
    BN 437 (3). Caption mentions the Eminescu + Iorga effect.
- [ ] **#eroi-locali** (Eroi locali) — Ioan Suciu AR 75%, Ion Irimescu SV 66,7%,
  Petru I Mușat SV 62,5%, Pintea Viteazul MM 62,5%, **Ion Nistor SV 61,5% with a
  green „localnic" badge**, Orbán Balázs HR 60%. Each name links to `/persoana/…`.

## Street detail maps (Task 4)

- [ ] `/strada/trandafirilor/` — "Harta · 496 localități" section above the textual
  list; Romania outline with **~496 red dots** spread across the whole country.
- [ ] Hover a dot → dark tooltip with `Uat Name (JJ)` (and `· N` if count > 1).
- [ ] A low-footprint name (e.g. open any street present in 1 locality) → **single
  dot**, map still renders.
- [ ] A name with a few unmapped UATs → caption notes "N localități fără coordonate
  nu apar."
- [ ] View-source or network tab: page fetches `/ro-counties.geojson` (root-relative);
  d3 loaded only on pages that have a map.

## Județe map — UAT-level choropleth (added later 2026-06-07)

Open `/judete/`.

- [ ] Map header shows a **Nivel** toggle: `Județe` (active) / `Localități`, then the
  metric chips.
- [ ] Click **Localități** → after a brief load the map redraws with **~1,171 UAT
  polygons** colored; rural communes with no registry streets (and the 8 Bucharest
  sectors) stay grey. Scale label gains "· pe localități".
- [ ] Switch metric chips while in Localități mode → recolors, legend min/max update
  from the UAT value range (not the județ range).
- [ ] Click a colored UAT → right panel shows a compact card: name, județ, total
  streets, modal name, 6 metric rows (active metric bolded), and "Vezi pagina
  localității →" **only** for UATs that have a detail page (the 108 seats/municipii).
- [ ] Click a grey UAT → card says "Fără date de străzi în registru".
- [ ] Toggle back to **Județe** → original choropleth + fingerprint return; no reload.
- [ ] Network tab: `ro-uats.topojson` and `judete/uat-metrics.json` fetched **only**
  after first switching to Localități (lazy), not on page load.

## Browser filters — live counts in brackets (added later 2026-06-07)

Open `/browser/` (compact view is default).

- [ ] Open any filter dropdown (e.g. Clasificare) → each option shows a right-aligned
  count badge; "Toate" shows the total for the current other-filters context.
- [ ] Pick Clasificare = Persoană → open Profesie → counts now reflect only person
  rows (writer ~65, poet ~39…); options with 0 matches under the current context dim
  out. The Clasificare dropdown's own counts stay full (a filter's counts ignore its
  own selection so you can still see alternatives).
- [ ] Type in search → all dropdown counts update to the search-filtered context.
- [ ] Switch to Tabel view → counts still update (they read the same in-memory rows).
- [ ] Counts are name-counts (match the "N rezultate" bar), formatted ro-RO
  (thousands dot).

## Cross-cutting

- [ ] No JS console errors on the landing page or a street page.
- [ ] All 8 new panels use the same panel chrome (header label + icon + meta) as the
  existing ones; no broken icon glyphs.
- [ ] Under a subfolder deploy (`--base /nume-strazi --mount /nume-strazi`) the map
  still loads its geojson (path becomes `/nume-strazi/ro-counties.geojson`).
