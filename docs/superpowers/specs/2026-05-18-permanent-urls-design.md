# Permanent URLs for Filter State

**Date:** 2026-05-18  
**Status:** approved  
**Scope:** `templates/index.html.j2` only — JS changes, ~15 lines

---

## Problem

Selecting a județ or municipiu in the landing-page filter is ephemeral. Refreshing the page resets to the national view. The filtered view cannot be bookmarked or shared as a link.

## URL Scheme

| State | URL |
|---|---|
| National (no filter) | `/` |
| Județ selected | `/?judet=CJ` |
| Municipiu selected | `/?judet=CJ&siruta=54984` |

Parameters: `judet` = two-letter județ code (matching keys in `DATA_S2.by_judet`); `siruta` = numeric SIRUTA code (matching `m.s` values in `DATA_MUNICIPII.by_judet[code]`).

## Writing State

A `updateUrl(code, siruta)` helper is called from both event listeners (after calling `render`). It:

1. Constructs a `URLSearchParams` — adds `judet` if `code !== 'all'`, adds `siruta` if `siruta` is truthy and not `'all'`
2. Calls `history.replaceState({}, '', qs ? '?' + qs : location.pathname)` — updates the address bar without creating a history entry and without triggering a page reload

When returning to national view, the URL clears to `/`.

## Reading State (Page Load)

Replace the unconditional `render('all', null)` at the end of the IIFE with:

1. `new URLSearchParams(window.location.search)` to read params
2. Validate `judet`: must be a key in `DATA_S2.by_judet`; otherwise fall back to `'all'`
3. If valid județ: set `select.value`, call `syncUatSelect(judet)` (this populates the municipiu dropdown)
4. Validate `siruta`: must appear as an `m.s` value in the municipiu list for that județ; otherwise ignore
5. If valid siruta: set `uatSelect.value`
6. Call `render(judet, siruta || null)`

Invalid or missing params silently fall back to the national view — no error UI needed.

## Changes

- **`templates/index.html.j2`** — only file touched
  - Add `updateUrl(code, siruta)` helper (~6 lines)
  - Call `updateUrl` in both event listeners
  - Replace final `render('all', null)` with URL-reading init block (~12 lines)

## Out of Scope

- Deep-linking from the județe overview map (`/judete/`) to `/?judet=XX` — natural follow-up
- `<link rel="canonical">` tag — data is client-side rendered, moot for SEO
- Back-button navigation between filter states — explicitly not wanted; `replaceState` (not `pushState`) is used throughout
