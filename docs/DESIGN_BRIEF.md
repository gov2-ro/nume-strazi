# Romanian Street Names — Design Brief

A design brief for an interactive Romanian-language publication about how Romania names its streets. Audience: Claude Design (or any designer picking this up). The technical/data layer is specified separately in `CODE_SPEC.md`.

---

## 1. The project in one paragraph

Romania has roughly 100,000–150,000 named streets. Who and what gets honored on those streets is a portrait of national memory — biased, layered, sometimes funny. This is an interactive, Romanian-language publication that lets readers explore that portrait: the most-named people, the gender gap, the communist-era ghosts hiding in plain sight, the village that gave up on names altogether and just used numbers. It begins as a personal exploration tool and ships as a public artifact.

## 2. Audience & voice

**Reader.** Romanian-speaking, civic-curious, history-aware. Reads *Dilema Veche*, *Scena9*, *Recorder*. Not a data scientist; appreciates rigor without needing it explained. Will share findings on social media if a single view rewards a screenshot.

**Voice.** Two registers, blended:

- **Insightful.** First-person plural where appropriate ("Cum ne numim străzile"), but mostly the editorial voice of a curious researcher. Plain Romanian; no academic jargon; no Anglicisms unless unavoidable. Diacritics correct, post-1993 orthography (`ș`, `ț`, `â` mid-word, `î` at boundaries).
- **Funny.** Dry, observational, occasionally deadpan. The CIORANI commune with 218 numbered streets is funny because the data is funny — let it speak. No memes, no emoji, no "wait what 🤯" energy.

**What the voice is not:** corporate-data-storytelling ("Did you know..."), cynical, didactic, nationalist, or precious about Romania. The work is curious, not reverent.

## 3. Hero findings (the lead stories)

These earn top billing. Each is a candidate for the dashboard's opening hero, a featured callout, or a shareable card.

### A. The gender gap
Romanian streets honor men. Overwhelmingly. The exact number is the deliverable; the prototype already shows a ~99:1 split among curated person-named streets. **Display as: a single brutal stat, then a comparative bar of the most-honored women vs. the top men.**

### B. The communist ghost catalogue
Streets renamed after 1989 — some completely (`Lucian Blaga` ← `Bulevardul Uzinei`), some only nominally (`CAP-ului` ← `Strada Ceapeului`, where the new name still phonetically references the communist agricultural cooperative). **Display as: a before/after timeline gallery, sortable by the kind of substitution.**

### C. Geographers replaced ideologues
A specific pattern in Bucharest Sector 6: streets named for academic figures, mostly geographers, replaced communist-era utilitarian street names ("Veneer St", "Hungry St", "Prow Lane"). **Display as: a single annotated micro-map of one neighborhood, with hover.**

### D. The CIORANI phenomenon
A commune in Prahova where 218 of 219 streets are anonymous numbers (1, 2, 3, ..., 218). One street has a name. We don't know which one yet — that's part of the joke. **Display as: a single hero card. Possibly the funniest thing in the whole project.**

### E. Regional naming fingerprints
Maramureș doesn't sound like Dobrogea. The top-distinctive names per județ (TF-IDF) reveal regional cultural memory: Hungarian-rooted names in Harghita/Covasna, Saxon traces in Sibiu, voievozi in Moldova. **Display as: an interactive choropleth where each județ surfaces its 5 most distinctive name tokens.**

### F. The Eminescu effect
Mihai Eminescu is the most-honored Romanian by streets. The exact rank order — and how far behind everyone else lags — is a data-point on national canon. **Display as: a tower-chart of the top 20 honorees with brief bios.**

### G. Saints and the regional shape of Romanian Orthodoxy
Saint streets aren't uniformly distributed. The map of saint-prefixed streets is also a map of religious tradition. **Display as: a small choropleth, secondary view.**

### H. Holidays as fossils
`1 Decembrie` (national day) vs. `1 Mai` (worker holiday, communist resonance) vs. `9 Mai` (multivalent: Independence 1877 + WWII victory + Europe Day). The geography of which date a place chose tells a political story. **Display as: a small-multiples map, one per date.**

### I. The longest names
Title-stacking produces poetry: `Profesor Universitar Doctor Ion Tudorache`, `Învățător Constanța Teodoru`. The honorific tradition lives on in micro-history. **Display as: typographic showpiece — let the names breathe at large size.**

### J. The locally-honored
People honored in exactly one UAT — usually a teacher, priest, or military officer from that village. **Display as: a "long tail" gallery with UAT and brief context.**

## 4. Information architecture

Flat, single-page-application style with deep-linkable sections. Top nav scrolls/jumps between views.

| Section | Lead | Supporting |
|---|---|---|
| 1. Acasă (intro hero) | One brutal headline stat (gender gap). Scroll cue. | Subtitle, project tagline. |
| 2. Cele mai întâlnite nume | Top 50 names list, deduplicated nationally. | Filter: by judet, by street type. Search. |
| 3. Pe cine onorăm | Hero: most-honored people; the gender gap chart. | Profession breakdown, era distribution, foreign honorees. |
| 4. Tematică | Donut/sunburst of theme composition (person, nature, place, religious, abstract, ideological). | Drill: nature subtypes ranking, ideological tokens. |
| 5. Harta României | Choropleth, switchable metrics. | Hover tooltips per județ; click to drill into the județ panel. |
| 6. Identitate regională | Per-județ "fingerprint": top distinctive names. | Side-by-side compare two județe. |
| 7. Renumiri | Before/after gallery of renamings; communist-token highlight. | Filter by substitution type. |
| 8. Curiozități | CIORANI card, longest names, locally-honored, animal popularity contest. | Self-contained shareable cards. |
| 9. Despre date | Source, methodology caveats, curation strategy in plain Romanian. | Acknowledgments, data download. |

Sections 1–3 form the editorial spine. 4–6 are exploratory. 7–8 are the curiosity payoffs. 9 is the rigor.

## 5. Visual style direction

The aim is **editorial, magazine-feel** — closer to *The Pudding* or *Bloomberg Graphics* than to a corporate BI dashboard. Specifically:

- **Not a dashboard.** No filter sidebars, no "rendered by Tableau" vibe. The reader scrolls a story, encounters charts and maps embedded in flowing layout.
- **Romanian without kitsch.** Avoid the blue-yellow-red flag palette. Avoid folk patterns (covor oltenesc, etc.) unless used with deliberate irony in one specific section. Restraint reads as confident.
- **Typography is half the design.** A Romanian-friendly serif for editorial copy and headlines (candidates: *Source Serif 4*, *EB Garamond*, *Lora*, *Tinos*). A clean sans for chart labels and UI (*Inter*, *IBM Plex Sans*). Diacritics must render flawlessly — test `ț ș ă â î Ț Ș Ă Â Î` early.
- **Color palette.** Editorial earth tones suggested — terracotta, old paper, deep ink, muted olive — but final palette is the designer's call. One single accent color used sparingly for highlighting.
- **Charts.** Minimal. Direct labeling over legends. Annotated, not decorated. Numbers always with thousands separator (Romanian: dot, not comma: `12.847`). Use visual hierarchy to tell the reader what to look at — a single highlighted bar in red against muted greys.
- **Maps.** Muted base layer. The accent color encodes the chosen metric. Județ borders thin; UAT borders thinner where shown. Bucharest treated as its own zoomed inset (the six sectors deserve room).
- **Photography or illustration?** Optional. If illustrated: hand-drawn or risograph-feel street signs as section dividers could work. Avoid stock vector illustration of "people walking in a city."

## 6. Map specs

- Source: județ-level TopoJSON owned by the user.
- Default view: full Romania with județe outlined, no UAT detail.
- Switchable metrics on the main map:
  - `% female-named streets`
  - `% saint-named streets`
  - `% anonymous (numeric) streets`
  - Modal name in județ
- Hover tooltip: județ name, total streets, top 3 most common names, the active metric value.
- Click: drills to a județ panel showing its naming fingerprint.
- Bucharest detail: separate inset with six sectors. Worth its own treatment because of size and renaming density.
- Future (Phase 3): per-street dot map. Design should leave room for this without committing to it now.

## 7. Interactivity

Restrained. The reader is reading, not querying. Specifically:

- **Search bar (always visible)** — type any street name, see all UATs that have it. Romanian fuzzy match (handles `î/â`, `ș/s`, capitalization).
- **Filters on Section 3 only** — gender, era, profession, nationality. Use chip-style toggles, not dropdown menus.
- **Județ comparison (Section 6)** — pick two județe, see fingerprints side-by-side.
- **All visualizations are linked-but-not-coordinated** — choosing a județ on the map doesn't filter the other charts. The reader scrolls; views are independent stories.

What we explicitly avoid:
- Multi-filter cross-tab dashboards. The data is rich; the interaction should be focused.
- Pop-up modals. Use side-panels or in-place expansion.
- "Click to drill into 47 levels of detail." Two levels max.

## 8. Romanian copy samples

These are tonal references, not finals. The designer should iterate.

**Hero (Section 1)**

> **99 din 100 de români onorați pe străzi sunt bărbați.**
>
> Asta arată registrul electoral al țării — peste 140.000 de străzi, în 41 de județe. Cine sunt acei bărbați, ce profesii au, în ce epoci au trăit? Și cine sunt cele 100 de femei? Să vedem.

**Section 2 intro**

> **Cele mai întâlnite nume de străzi**
>
> În aproape orice sat, un drum se cheamă "Principală". În aproape orice oraș, una "Eminescu". Românilor le plac florile, școlile, bisericile și un anumit poet din Botoșani.

**CIORANI card (Section 8)**

> **Comuna care a renunțat la nume**
>
> În Cioranii din Prahova, 218 din 219 străzi se cheamă pur și simplu printr-un număr. *Strada 1*, *Strada 2*, *Strada 218*. Una singură are nume. Cei care locuiesc acolo știu de ce.

**Methodology blurb (Section 9)**

> **De unde vin datele**
>
> Datele provin din Registrul Secțiilor de Vot al Autorității Electorale Permanente. Ele descriu străzile pe care locuiesc alegători înregistrați — adică aproape toate, dar nu chiar toate. Detaliile metodologice sunt mai jos.

These should be revised by a Romanian-native editorial pass before publication.

## 9. Editorial features (the "funny" delivery vehicles)

Discrete moments where the playful register shows through. Use sparingly — one per section, max.

- **"Onorat doar aici"** — locally-honored figures with one-line context. Often: a village teacher, a parish priest, a fallen soldier.
- **"Concursul animalelor"** — top 10 animal street names. Pure rank chart. Title is the joke.
- **"Cea mai poetică"** — featured longest name in typography-showpiece treatment.
- **"Reciclare semantică"** — renamings where the new name phonetically echoes the old. CAP-ului ← Ceapeului is the canonical example.
- **"Sfinții cei mai populari"** — saint ranking, possibly with a tiny halo glyph each. Restrained. Don't make it cute.

These are the moments where readers screenshot for social. Each should be self-contained at one screen height, with the title carrying enough wit to stand alone.

## 10. Constraints

- **Romanian only.** All UI copy, chart labels, tooltips, methodology, microcopy. No English fallbacks.
- **Diacritics must render perfectly.** Test the full alphabet (`ăâîșțĂÂÎȘȚ`) at every type size. Pay attention to font fallbacks for `ș`/`ț` (some fonts only have cedilla forms — these are wrong).
- **Mobile must work, but desktop is primary.** Charts and maps are designed at desktop and gracefully degrade. Long-form scrolling is fine on mobile; complex multi-axis charts collapse to simpler forms.
- **Each section should screenshot well.** Not optimized for social *over* the reading experience, but a reader sharing a single section should get a coherent rectangular crop with headline, viz, and source.
- **Performance.** Initial load <2s on broadband. Large data lazy-loaded as the reader scrolls. Map should not block first paint.

## 11. Non-goals

- Not a tool for searching addresses. Not Google Maps.
- Not a comprehensive list of Romanian streets. The dataset has known gaps; we own them in methodology.
- Not multilingual. English/Russian/Hungarian translations are out of scope (notwithstanding the Romanian linguistic heritage of those communities).
- Not a real-time service. The data refreshes when we re-ingest, manually.
- Not advocacy. The findings speak for themselves — they're allowed to feel like an indictment of certain patterns, but the project doesn't editorialize about them.

## 12. Mood references

(Designer's call to interpret; these are starting points.)

- *The Pudding* — for editorial scrolling format with embedded interactives.
- *Bloomberg Graphics* — for restrained chart aesthetic, annotated-not-decorated.
- *Le Monde infographics* — for European editorial typography.
- *Scena9* (Romanian online cultural magazine) — for tone in Romanian.
- *Lapham's Quarterly* — for the "let the data speak through layout" approach to history.

Avoid: *Tableau Public* dashboards, *Power BI* templates, generic "data storytelling" Medium posts, anything with a hero illustration of a stylized city.

## 13. What to deliver from this brief

For Claude Design specifically, the next deliverable is a **visual direction document** containing:
1. Color palette (3–6 colors with named usage).
2. Typography system (display, body, UI, with Romanian-glyph confirmation).
3. Three key view mockups: the hero (Section 1), the map (Section 5), one curiosity card (CIORANI).
4. Component library starter: chart types, card patterns, section dividers.
5. Microcopy/tone samples for 3–5 different moments in the reader journey.

Mockups can be high-fidelity static images or HTML/React (designer's choice). Editorial copy in mockups should be in Romanian but is placeholder-quality at this stage.
