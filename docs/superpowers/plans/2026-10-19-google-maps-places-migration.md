# Google Maps and Places Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Photo Booth's MapLibre/OpenStreetMap location stack with configurable Google Maps JavaScript API and Places API (New) while preserving manual Pin confirmation and private answer circles.

**Architecture:** FastAPI stores non-secret map settings in SQLite and browser-key material in a credential-store abstraction backed by macOS Keychain. React loads Google Maps once, searches Places through a focused adapter, and renders the existing answer Pin and radius with Google overlays. Legacy OSM endpoints and dependencies are removed only after the Google path is covered by tests and the production build.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, keyring, React 19, TypeScript, Vite, `@googlemaps/js-api-loader`, Google Maps JavaScript API, Places API (New), Node test runner, pytest.

**Spec:** `docs/superpowers/specs/2026-10-19-google-ai-places-design.md`

## Global Constraints

- Photo Booth remains bound to localhost and its mutation-origin guard remains active.
- Original images, `.local/`, SQLite, previews, thumbnails, API keys, and tokens must never be staged or committed.
- The Google browser key is expected to be visible to the local browser and must be restricted by API and referrer; configuration APIs otherwise return only a mask.
- A separate Google browser key will be used by the future public website.
- Manual latitude/longitude entry and Pin confirmation must remain usable when Google fails.
- Existing import, review, Collections, deletion, grading preview, and export privacy behavior must not regress.
- Use Places API (New), not legacy Places widgets or services.
- Use `AdvancedMarkerElement` with a configured map ID; allow Google's documented `DEMO_MAP_ID` only as a clearly labeled local fallback.

## Review Focus

- Missing, cleared, or invalid Google key: map/search show an actionable configuration state while manual coordinates still work; pin this in Task 2 API tests and Task 4 browser verification.
- Two map components opening in one session: the loader reuses one promise and never inserts duplicate scripts; pin this in Task 3 unit tests.
- Chinese, English, and mixed-script Places results with missing address fields: normalization returns a stable display name and valid coordinates; pin this in Task 3 unit tests.
- Changing answer radius while reopening the map: the circle uses the latest 1/10/50/100 km value and remains centered on the Pin; pin this in Task 4 tests and browser verification.
- Maps network failure after initial render: an error appears without deleting typed coordinates or disabling confirmation; pin this in Task 4 browser verification.

---

### Task 1: Establish a safe Git baseline

**Files:**
- Modify: `.gitignore`
- Create: `.env.example`
- Verify: repository root and ignored working data

**Interfaces:**
- Consumes: the current unversioned Photo Booth directory.
- Produces: a local `main` Git repository whose first commit contains code and documentation but no private data.

- [ ] **Step 1: Extend the ignore contract before initializing Git**

Add explicit ignores for `.local/`, `*.sqlite*`, all image archive/preview directories, `.env*` except `.env.example`, `node_modules/`, `dist/`, caches, and macOS metadata. Document only variable names in `.env.example`; do not add values.

- [ ] **Step 2: Audit the candidate file set**

Run: `find . -type f -not -path './.local/*' -not -path '*/node_modules/*' -not -path '*/dist/*' | sort`

Expected: source, tests, README, lock files, and `docs/`; no photo, database, credential, or generated build files.

- [ ] **Step 3: Initialize the local repository and inspect the exact staged set**

Run: `git init -b main && git add . && git status --short`

Expected: only reviewed public source/documentation files are staged.

- [ ] **Step 4: Scan staged text for likely secrets and private absolute paths**

Run: `git diff --cached --check`

Run: `git grep --cached -n -E '(sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{20,}|Bearer [A-Za-z0-9._-]{16,}|/Users/[A-Za-z0-9._-]+)'`

Expected: no matches other than intentionally fake placeholders; fix any match before continuing.

- [ ] **Step 5: Commit the reviewed baseline**

```bash
git commit -m "chore: establish photo booth source baseline"
```

### Task 2: Add credential-backed Google Maps settings

**Files:**
- Create: `apps/studio/backend/secret_store.py`
- Modify: `apps/studio/backend/db.py:1-102`
- Modify: `apps/studio/backend/main.py:1-138,415-425`
- Modify: `apps/studio/backend/requirements.txt`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: `settings(key, value)` for non-secret SQLite values.
- Produces: `SecretStore.get(name) -> str`, `SecretStore.set(name, value) -> None`, `SecretStore.delete(name) -> None`, `get_secret_store() -> SecretStore`, `GET/PUT /api/maps/config`, and `GET /api/maps/bootstrap`.

- [ ] **Step 1: Write failing credential-store and map-configuration tests**

Add tests asserting:

```python
def test_google_map_config_masks_key_and_bootstrap_returns_it_only_for_local_ui(client, secret_store): ...
def test_google_map_key_can_be_replaced_and_cleared_without_entering_sqlite(client, secret_store): ...
def test_google_map_config_rejects_non_local_mutation_origin(client): ...
```

The tests must check that SQLite contains `google_maps_map_id` but not the full key and that `GET /api/maps/config` returns `apiKeyConfigured` plus a mask, never the key.

- [ ] **Step 2: Run the focused tests and confirm missing endpoints fail**

Run: `python -m pytest -q tests/test_api.py -k 'google_map_config'`

Expected: FAIL with 404 or missing `backend.secret_store`.

- [ ] **Step 3: Implement the secret-store abstraction**

Create:

```python
class SecretStore(Protocol):
    def get(self, name: str) -> str: ...
    def set(self, name: str, value: str) -> None: ...
    def delete(self, name: str) -> None: ...

class KeyringSecretStore:
    service_name = "photo-booth"
```

Use `keyring` on macOS and a test-only `MemorySecretStore`. Never silently fall back to plaintext storage.

- [ ] **Step 4: Add validated map configuration endpoints**

Add `GoogleMapsConfigInput` with `api_key: str | None`, `clear_api_key: bool = False`, and `map_id: str`. Use the credential store for `google-maps-browser-key`, SQLite for `google_maps_map_id`, and return the actual key only from `/api/maps/bootstrap` for the local frontend.

- [ ] **Step 5: Run focused and full backend tests**

Run: `python -m pytest -q tests/test_api.py -k 'google_map_config'`

Expected: PASS.

Run: `python -m pytest -q tests`

Expected: existing suite remains green.

- [ ] **Step 6: Commit**

```bash
git add apps/studio/backend/secret_store.py apps/studio/backend/db.py apps/studio/backend/main.py apps/studio/backend/requirements.txt tests/test_api.py
git commit -m "feat: store google maps configuration securely"
```

### Task 3: Build the Google Maps loader and Places adapter

**Files:**
- Create: `apps/studio/frontend/src/googleMaps.ts`
- Create: `apps/studio/frontend/tests/googleMaps.test.ts`
- Modify: `apps/studio/frontend/package.json`
- Modify: `apps/studio/frontend/package-lock.json`
- Modify: `apps/studio/frontend/src/api.ts`
- Modify: `apps/studio/frontend/src/types.ts`

**Interfaces:**
- Consumes: `GET /api/maps/bootstrap` from Task 2.
- Produces: `loadGoogleMaps(config: GoogleMapsBootstrap): Promise<GoogleLibraries>`, `searchGooglePlaces(query: string, options?: PlaceSearchOptions): Promise<Place[]>`, and `normalizeGooglePlace(place: GooglePlaceLike): Place`.

- [ ] **Step 1: Write failing frontend adapter tests**

Add tests for:

```typescript
test('normalizes a mixed-script place with partial address data', () => { ... });
test('drops places without finite coordinates', () => { ... });
test('loader returns the same promise for the same browser key', async () => { ... });
test('search passes an intentional viewport only as location bias', async () => { ... });
```

- [ ] **Step 2: Run tests to verify the module is missing**

Run: `cd apps/studio/frontend && node --test tests/googleMaps.test.ts`

Expected: FAIL because `src/googleMaps.ts` does not exist.

- [ ] **Step 3: Add Google dependencies and remove MapLibre dependencies**

Install `@googlemaps/js-api-loader` and `@types/google.maps`; remove `maplibre-gl`. Keep the lock file synchronized.

- [ ] **Step 4: Implement a single-load adapter around Maps and Places (New)**

Use dynamic library import for `maps`, `marker`, and `places`. `searchGooglePlaces` must use `Place.searchByText`, request only ID/display name/formatted address/location/address components, limit UI output to five candidates, and never apply a hidden location bias.

- [ ] **Step 5: Run frontend tests and type/build checks**

Run: `cd apps/studio/frontend && node --test tests/connection.test.ts tests/reviewWorkflow.test.ts tests/googleMaps.test.ts`

Expected: PASS.

Run: `cd apps/studio/frontend && npm run build`

Expected: TypeScript and Vite build succeed.

- [ ] **Step 6: Commit**

```bash
git add apps/studio/frontend/package.json apps/studio/frontend/package-lock.json apps/studio/frontend/src/googleMaps.ts apps/studio/frontend/src/api.ts apps/studio/frontend/src/types.ts apps/studio/frontend/tests/googleMaps.test.ts
git commit -m "feat: add google places adapter"
```

### Task 4: Migrate the Pin editor and place search

**Files:**
- Modify: `apps/studio/frontend/src/MapPicker.tsx:1-94`
- Modify: `apps/studio/frontend/src/PhotoEditor.tsx:1-274`
- Modify: `apps/studio/frontend/src/App.tsx:11-178`
- Modify: `apps/studio/frontend/src/styles.css`
- Modify: `apps/studio/frontend/src/reviewWorkflow.ts:1-41`
- Modify: `apps/studio/frontend/tests/reviewWorkflow.test.ts`
- Modify: `apps/studio/backend/main.py:447-465`
- Delete: `apps/studio/backend/geocode.py`
- Delete: `tests/test_geocode.py`

**Interfaces:**
- Consumes: Task 2 map bootstrap and Task 3 loader/search adapter.
- Produces: `MapPicker` backed by Google Map, draggable `AdvancedMarkerElement`, and `google.maps.Circle`; Photo Editor direct Google candidate search.

- [ ] **Step 1: Update failing workflow expectations before implementation**

Replace the MapLibre polygon-specific test with a pure `validCoordinates(latitude, longitude)` test used by `MapPicker`. Keep radius-choice tests unchanged.

- [ ] **Step 2: Run the frontend tests and observe the missing helper failure**

Run: `cd apps/studio/frontend && node --test tests/reviewWorkflow.test.ts`

Expected: FAIL because `validCoordinates` is not implemented.

- [ ] **Step 3: Replace MapLibre with Google Map, marker, and circle**

`MapPicker` must load bootstrap configuration, preserve the existing initial-position behavior, support map click and marker drag, center a `google.maps.Circle` on the current Pin, update its radius in metres, retain manual numeric inputs, and expose an actionable error without clearing coordinates.

- [ ] **Step 4: Replace Photo Editor's backend geocode call with direct Places search**

Use `searchGooglePlaces(query)` and keep the existing select-candidate-then-confirm-Pin sequence. Show a configure-key action when bootstrap is unavailable. Do not invoke a language model in this plan.

- [ ] **Step 5: Remove legacy map/geocode settings and backend endpoints**

Remove MapTiler fields and copy from `Settings`, Studio Settings, and README. Delete `/api/geocode`, `/api/reverse`, `backend/geocode.py`, and OSM-specific tests after the Google path compiles.

- [ ] **Step 6: Run all automated checks**

Run: `python -m pytest -q tests`

Expected: PASS.

Run: `cd apps/studio/frontend && node --test tests/connection.test.ts tests/reviewWorkflow.test.ts tests/googleMaps.test.ts && npm run build`

Expected: PASS.

- [ ] **Step 7: Browser walkthrough on macOS**

Start Photo Booth, configure a restricted local Google key, open a Guess Where photo, search `香港 太平山顶 缆车站` and `台中市 美术馆`, choose a candidate, drag the Pin, click elsewhere, change 1/10/50/100 km radius, confirm, save, reload, and verify persistence. Then simulate an invalid key and verify manual coordinate entry still works.

- [ ] **Step 8: Commit**

```bash
git add -A apps/studio/frontend apps/studio/backend tests README.md
git commit -m "feat: migrate photo booth maps to google"
```

### Task 5: Update setup documentation and verify migration residue

**Files:**
- Modify: `README.md`
- Modify: `apps/web/GUESS_WHERE_DESIGN.md`
- Verify: dependency manifests and source tree

**Interfaces:**
- Consumes: completed Google migration.
- Produces: accurate setup instructions and no remaining runtime dependency on MapLibre, MapTiler, OpenFreeMap, Nominatim, or Photon.

- [ ] **Step 1: Document Google Cloud setup and key restrictions**

Document enabling Maps JavaScript API and Places API (New), creating a localhost-restricted browser key, optional map ID, billing requirement, and the separate future production-domain key.

- [ ] **Step 2: Search for obsolete provider references**

Run: `rg -n 'MapLibre|MapTiler|OpenFreeMap|Nominatim|Photon|maplibre-gl' README.md apps tests package.json apps/studio/frontend/package.json`

Expected: no live implementation or setup reference remains; historical design notes may be explicitly marked superseded.

- [ ] **Step 3: Run the complete verification set**

Run: `python -m pytest -q tests`

Run: `cd apps/studio/frontend && node --test tests/*.test.ts && npm run build`

Expected: all checks pass.

- [ ] **Step 4: Commit**

```bash
git add README.md apps/web/GUESS_WHERE_DESIGN.md
git commit -m "docs: document google maps setup"
```
