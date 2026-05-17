# Permanent URLs for Filter State — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the landing-page județ/municipiu filter state bookmarkable and shareable via query string (`/?judet=CJ` or `/?judet=CJ&siruta=54984`).

**Architecture:** Pure client-side JS change in `templates/index.html.j2`. Add a `updateUrl()` helper that writes `history.replaceState` on every filter change. On page load, read `URLSearchParams` and restore the filter state before calling `render()`. No Python, no build-system changes.

**Tech Stack:** Vanilla JS (`URLSearchParams`, `history.replaceState`), Jinja2 template

---

## File Map

| File | Change |
|---|---|
| `templates/index.html.j2` | Only file touched — add `updateUrl`, update two event listeners, replace init `render` call |

No new files. No Python changes. No `build_site.py` changes.

---

## Task 1: Add `updateUrl` and wire to event listeners

**Files:**
- Modify: `templates/index.html.j2:1737-1744`

The two event listeners currently call `render()` but never update the URL. This task adds the `updateUrl` helper and calls it from both listeners.

- [ ] **Step 1.1: Add `updateUrl` function before the event listeners**

Find the line `select.addEventListener('change', e => {` (around line 1737) and insert the helper immediately before it:

```js
  function updateUrl(code, siruta) {
    const p = new URLSearchParams();
    if (code && code !== 'all') p.set('judet', code);
    if (siruta && siruta !== 'all') p.set('siruta', String(siruta));
    const qs = p.toString();
    history.replaceState({}, '', qs ? '?' + qs : location.pathname);
  }
```

- [ ] **Step 1.2: Update the județ event listener to call `updateUrl`**

Replace:
```js
  select.addEventListener('change', e => {
    syncUatSelect(e.target.value);
    uatSelect.value = 'all';
    render(e.target.value, null);
  });
```

With:
```js
  select.addEventListener('change', e => {
    syncUatSelect(e.target.value);
    uatSelect.value = 'all';
    render(e.target.value, null);
    updateUrl(e.target.value, null);
  });
```

- [ ] **Step 1.3: Update the municipiu event listener to call `updateUrl`**

Replace:
```js
  uatSelect.addEventListener('change', e => {
    render(select.value, e.target.value);
  });
```

With:
```js
  uatSelect.addEventListener('change', e => {
    render(select.value, e.target.value);
    updateUrl(select.value, e.target.value);
  });
```

- [ ] **Step 1.4: Commit**

```bash
git add templates/index.html.j2
git commit -m "feat(url): write filter state to query string on change"
```

---

## Task 2: Restore filter state from URL on page load

**Files:**
- Modify: `templates/index.html.j2:1745` (the `render('all', null)` line)

On page load the IIFE currently calls `render('all', null)` unconditionally. Replace this with a block that reads `URLSearchParams` and restores whatever state the URL describes, falling back to national view for missing or invalid params.

- [ ] **Step 2.1: Replace `render('all', null)` with URL-reading init block**

Replace:
```js
  render('all', null);
```

With:
```js
  (function initFromUrl() {
    const p      = new URLSearchParams(window.location.search);
    const judet  = p.get('judet');
    const siruta = p.get('siruta');
    if (judet && (DATA_S2.by_judet || {})[judet] !== undefined) {
      select.value = judet;
      syncUatSelect(judet);
      const validSirute = ((DATA_MUNICIPII.by_judet || {})[judet] || []).map(m => String(m.s));
      if (siruta && validSirute.includes(siruta)) {
        uatSelect.value = siruta;
        render(judet, siruta);
      } else {
        render(judet, null);
      }
    } else {
      render('all', null);
    }
  })();
```

**What this does:**
- Reads `?judet=` and `?siruta=` from the URL
- Validates `judet` against `DATA_S2.by_judet` keys (the real județ codes, e.g. `'CJ'`)
- If valid: sets the select, calls `syncUatSelect` to populate the municipiu dropdown, then validates `siruta` against that județ's municipii list
- If siruta is valid: sets the municipiu select and renders at municipiu level
- If siruta is missing/invalid: renders at județ level
- If judet is missing/invalid: falls back to `render('all', null)` (national view)
- Invalid params are silently ignored — no error UI needed

- [ ] **Step 2.2: Commit**

```bash
git add templates/index.html.j2
git commit -m "feat(url): restore filter state from query string on page load"
```

---

## Task 3: Rebuild site and verify

**Files:** none (read-only verification)

- [ ] **Step 3.1: Activate venv and rebuild the site**

```bash
source ~/devbox/envs/240826/bin/activate
python3 build_site.py
```

Expected: build completes without errors, `dist/index.html` is updated.

- [ ] **Step 3.2: Start the dev server**

```bash
cd dist && python3 -m http.server 8000
```

- [ ] **Step 3.3: Verify — national → județ → URL updates**

Open `http://localhost:8000/` in a browser. Select a județ (e.g. Cluj). Confirm the address bar changes to `/?judet=CJ` without a page reload and the panels update correctly.

- [ ] **Step 3.4: Verify — județ → municipiu → URL updates**

With a județ selected, pick a municipiu. Confirm the address bar changes to `/?judet=CJ&siruta=54984` (SIRUTA will differ) and the panels update.

- [ ] **Step 3.5: Verify — URL is restored on page load (județ)**

Navigate directly to `http://localhost:8000/?judet=CJ`. Confirm: the page loads with the județ selector already set to Cluj and all panels showing Cluj data.

- [ ] **Step 3.6: Verify — URL is restored on page load (municipiu)**

Navigate directly to `http://localhost:8000/?judet=CJ&siruta=54984`. Confirm: the page loads with both selectors set and panels showing municipiu data.

- [ ] **Step 3.7: Verify — invalid params fall back gracefully**

Navigate to `http://localhost:8000/?judet=ZZ`. Confirm the page loads showing the national view with no error.

- [ ] **Step 3.8: Verify — resetting filter clears URL**

On a filtered view, reset the județ selector to "Toate județele". Confirm the address bar returns to `/` (no query string).

- [ ] **Step 3.9: Update backlog and activity log**

In `docs/BACKLOG.md`, mark the `lading page, permanent urls for selected judet / municipiu` misc item as `[x]`.

In `docs/activity-history.md`, add an entry under today's date:

```markdown
## 2026-05-18 — Permanent URLs for Landing-Page Filter

Added query-string state persistence to the two-level județ/municipiu filter on the landing page. Selecting a județ updates the URL to `/?judet=CJ`; selecting a municipiu appends `?siruta=54984`. On page load, `URLSearchParams` is read and the filter is restored before the first `render()` call. `history.replaceState` (not `pushState`) is used — Back button is intentionally not wired to filter navigation. All changes in `templates/index.html.j2`.
```

- [ ] **Step 3.10: Commit**

```bash
git add docs/BACKLOG.md docs/activity-history.md
git commit -m "docs: mark permanent URLs done; activity log"
```
