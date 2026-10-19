# AI Places Administration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local AI & Places administration area that configures, tests, versions, activates, and optionally publishes DeepSeek-powered Google Places query rewriting without exposing private answers or secrets.

**Architecture:** SQLite stores one editable draft and immutable non-secret release versions; macOS Keychain stores DeepSeek and publisher credentials through the secret-store abstraction from the Google migration. FastAPI owns model calls, strict output validation, activation, and remote publication. React owns the three-page administration experience and composes the backend rewrite with the Google Places adapter.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLite, keyring, urllib/HTTPS, React 19, TypeScript, Vite, Google Places API (New), DeepSeek OpenAI-compatible chat completions, pytest, Node test runner.

**Spec:** `docs/superpowers/specs/2026-10-19-google-ai-places-design.md`

## Global Constraints

- The editable prompt may change model behavior, but locked schema, coordinate prohibition, correct-answer isolation, and scoring separation remain code-enforced.
- DeepSeek receives only the location text plus prompt; never send photo metadata, canonical answer, answer coordinates, radius, or grade.
- Default DeepSeek base URL is `https://api.deepseek.com`; default model is `deepseek-flash`; both are configurable.
- Model calls explicitly disable thinking mode, request JSON output, bound input/output, enforce timeout, and use at most the configured retry count.
- Saving a draft invalidates its prior successful test; only the exact tested prompt hash may be activated or published.
- A failed test or failed remote publication never replaces the active configuration.
- Website publishing remains visibly disconnected until a future personal-site backend implements the documented contract.
- Secrets never enter SQLite, logs, API responses, public exports, Git history, or frontend state beyond the restricted Google browser key already covered by the migration plan.
- Existing local Pin-grading preview remains available. The legacy direct LLM text-grading endpoint is removed because text now resolves to a Pin and the model must never receive private answer data.

## Review Focus

- Prompt injection or coordinate requests inside a location description: treat as untrusted text and reject coordinate-bearing output; pin this in Task 2 tests.
- Model returns valid JSON with unknown fields, overlong strings, NaN confidence, or an invalid status: reject it and preserve the prior active version; pin this in Task 2 and Task 3 tests.
- Draft changes after a successful test: activation/publish must fail until retested; pin this in Task 3 tests.
- Network timeout, 401, 429, or malformed DeepSeek response: return a recoverable error and leave Google/manual Pin available; pin this in Task 2 and Task 5 tests.
- Remote endpoint returns a different version/hash or redirects away from HTTPS: do not mark the release published and do not leak tokens; pin this in Task 6 tests.

---

### Task 1: Add versioned AI configuration storage

**Files:**
- Create: `apps/studio/backend/ai_config.py`
- Modify: `apps/studio/backend/db.py:13-88`
- Create: `tests/test_ai_config.py`

**Interfaces:**
- Consumes: SQLite connections from `backend.db.connect()`.
- Produces: `AiConfigDraft`, `AiConfigVersion`, `load_or_create_draft(conn)`, `save_draft(conn, changes)`, `record_test(conn, prompt_hash, summary)`, `activate_draft(conn)`, `list_versions(conn)`, and `restore_version(conn, version)`.

- [ ] **Step 1: Write failing lifecycle tests**

Add tests asserting:

```python
def test_initial_draft_uses_deepseek_flash_and_the_approved_prompt(): ...
def test_saving_draft_changes_hash_and_invalidates_prior_test(): ...
def test_only_exact_tested_hash_can_activate(): ...
def test_restore_creates_a_new_draft_without_mutating_history(): ...
def test_ai_config_tables_never_store_secret_values(): ...
```

- [ ] **Step 2: Run tests and confirm storage is absent**

Run: `python -m pytest -q tests/test_ai_config.py`

Expected: FAIL because `backend.ai_config` and its schema do not exist.

- [ ] **Step 3: Add the schema and repository functions**

Create `ai_place_draft` as a singleton row and `ai_place_versions` as immutable history. Store provider, base URL, model, timeout seconds, retry count, prompt text, SHA-256 prompt/config hash, test state/summary, lifecycle timestamps, and remote publish receipt. Do not store API keys or tokens.

- [ ] **Step 4: Seed the approved initial prompt deterministically**

Use the exact editable prompt in the design spec. Schema creation may insert the singleton draft only when absent; never overwrite a user's existing draft on startup.

- [ ] **Step 5: Run tests**

Run: `python -m pytest -q tests/test_ai_config.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/studio/backend/ai_config.py apps/studio/backend/db.py tests/test_ai_config.py
git commit -m "feat: add versioned ai place configuration"
```

### Task 2: Implement strict DeepSeek location interpretation

**Files:**
- Create: `apps/studio/backend/ai_places.py`
- Create: `tests/test_ai_places.py`

**Interfaces:**
- Consumes: `AiConfigDraft` and DeepSeek key from `SecretStore`.
- Produces: `PlaceInterpretation`, `build_location_messages(raw_text, prompt) -> list[dict[str, str]]`, and `interpret_place(raw_text, config, api_key, requester=request_model) -> PlaceInterpretation`.

- [ ] **Step 1: Write failing model-contract tests**

Cover searchable output, insufficient output, mixed Chinese/English, prompt injection, malformed JSON, unknown fields, coordinate fields, overlong query, invalid confidence, timeout, unauthorized response, and rate limiting. Assert captured request messages contain the raw description but no keys named `latitude`, `longitude`, `answer`, `radius`, or `score`.

- [ ] **Step 2: Run focused tests**

Run: `python -m pytest -q tests/test_ai_places.py`

Expected: FAIL because `backend.ai_places` does not exist.

- [ ] **Step 3: Implement the locked prompt envelope and validated output model**

Define:

```python
class PlaceInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["searchable", "insufficient"]
    normalized_query: str = Field(max_length=300)
    landmark: str = Field(max_length=160)
    locality: str = Field(max_length=160)
    region: str = Field(max_length=160)
    country: str = Field(max_length=160)
    category: str = Field(max_length=100)
    uncertainty: list[str] = Field(max_length=8)
    confidence: float = Field(ge=0, le=1)
    clarification: str = Field(max_length=300)
```

Add a post-validator enforcing empty `normalized_query` for `insufficient` and non-empty query for `searchable`. Reject any model response before returning it to the frontend if validation fails.

- [ ] **Step 4: Implement bounded DeepSeek HTTP behavior**

POST to `{base_url}/chat/completions` with bearer authentication, the configured timeout/retries, `thinking: {"type": "disabled"}`, `temperature: 0`, JSON response format, and a small maximum output. Convert 401, 429, timeout, malformed body, and validation failures into typed recoverable errors without echoing the key or full provider body.

- [ ] **Step 5: Run focused tests**

Run: `python -m pytest -q tests/test_ai_places.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/studio/backend/ai_places.py tests/test_ai_places.py
git commit -m "feat: add deepseek location interpretation"
```

### Task 3: Expose draft, test, activation, and history APIs

**Files:**
- Modify: `apps/studio/backend/main.py`
- Modify: `tests/test_api.py`
- Modify: `apps/studio/backend/secret_store.py`

**Interfaces:**
- Consumes: Task 1 repository and Task 2 interpreter.
- Produces: `/api/ai-places/config`, `/draft`, `/secrets/deepseek`, `/test`, `/activate`, `/versions`, and `/versions/{version}/restore` endpoints from the spec.

- [ ] **Step 1: Write failing API tests**

Add tests asserting masked secret state, key replacement/clear, draft save invalidation, test result and latency shape, missing-key 503, activation-before-test 409, activation-after-test success, immutable history, and restore-as-new-draft behavior.

- [ ] **Step 2: Run focused tests**

Run: `python -m pytest -q tests/test_api.py -k 'ai_places'`

Expected: FAIL with missing endpoints.

- [ ] **Step 3: Add Pydantic request/response models and endpoints**

Keep endpoint orchestration in `main.py` and business rules in `ai_config.py`/`ai_places.py`. Limit test input to 500 characters. Return provider errors as concise 503 details and validation conflicts as 409/422 without exposing secrets.

- [ ] **Step 4: Ensure editing invalidates the tested hash atomically**

`PATCH /draft` must update and invalidate in one SQLite transaction. `POST /activate` must compare the stored successful test hash to the current draft hash in the same transaction before creating the immutable active version.

- [ ] **Step 5: Run focused and complete backend suites**

Run: `python -m pytest -q tests/test_api.py -k 'ai_places'`

Expected: PASS.

Run: `python -m pytest -q tests`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/studio/backend/main.py apps/studio/backend/secret_store.py tests/test_api.py
git commit -m "feat: expose ai place configuration api"
```

### Task 4: Build the AI & Places administration section

**Files:**
- Create: `apps/studio/frontend/src/AiPlacesPage.tsx`
- Create: `apps/studio/frontend/src/aiPlacesState.ts`
- Create: `apps/studio/frontend/tests/aiPlacesState.test.ts`
- Modify: `apps/studio/frontend/src/App.tsx:1-188`
- Modify: `apps/studio/frontend/src/api.ts`
- Modify: `apps/studio/frontend/src/types.ts`
- Modify: `apps/studio/frontend/src/styles.css`

**Interfaces:**
- Consumes: Task 3 APIs and Google Places adapter from the migration plan.
- Produces: one top-level `ai-places` page with `model`, `test`, and `versions` internal tabs.

- [ ] **Step 1: Write failing state tests**

Test that dirty draft edits clear the successful-test state, test results associate with an exact hash, publish stays disabled without a matching test and endpoint, secret fields never retain returned full values, and restoring a version creates editable draft state.

- [ ] **Step 2: Run the state tests**

Run: `cd apps/studio/frontend && node --test tests/aiPlacesState.test.ts`

Expected: FAIL because `aiPlacesState.ts` does not exist.

- [ ] **Step 3: Implement API types and client methods**

Add exact `AiPlaceDraft`, `AiPlaceVersion`, `AiPlaceInterpretation`, `AiPlaceTestResult`, and masked-secret types. Add client methods matching Task 3 endpoints; no secret GET method may return a full DeepSeek key.

- [ ] **Step 4: Implement the three internal pages from the approved mockup**

Keep **AI & Places** as one left-navigation item. Model & prompt edits non-secret fields and replaces secrets explicitly. Test configuration runs DeepSeek first, then passes `normalized_query` to `searchGooglePlaces`, showing candidates and latencies. Published versions distinguishes local active, remote live, failed, and disconnected states.

- [ ] **Step 5: Preserve responsive and keyboard behavior**

Tabs are real buttons with `aria-selected`; all inputs have labels; secret replacement is explicit; status changes use an `aria-live` region; primary actions remain usable at 320 px width.

- [ ] **Step 6: Run tests and production build**

Run: `cd apps/studio/frontend && node --test tests/*.test.ts && npm run build`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/studio/frontend/src/AiPlacesPage.tsx apps/studio/frontend/src/aiPlacesState.ts apps/studio/frontend/src/App.tsx apps/studio/frontend/src/api.ts apps/studio/frontend/src/types.ts apps/studio/frontend/src/styles.css apps/studio/frontend/tests/aiPlacesState.test.ts
git commit -m "feat: add ai and places administration"
```

### Task 5: Integrate model fallback into photo location search

**Files:**
- Create: `apps/studio/frontend/src/placeSearchFlow.ts`
- Create: `apps/studio/frontend/tests/placeSearchFlow.test.ts`
- Modify: `apps/studio/frontend/src/PhotoEditor.tsx:90-144,228-241`
- Modify: `apps/studio/frontend/src/api.ts`
- Modify: `apps/studio/backend/grading.py`
- Modify: `apps/studio/backend/main.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: direct `searchGooglePlaces` and `POST /api/ai-places/test` using the locally active configuration.
- Produces: `searchWithFallback(rawQuery, searchPlaces, reinterpret, mode) -> PlaceSearchOutcome` with `mode: "automatic" | "forced"`.

- [ ] **Step 1: Write failing flow tests**

Cover direct results without model call, zero direct results causing exactly one interpretation and one retry, forced reinterpretation despite direct candidates, insufficient interpretation causing no retry, DeepSeek failure preserving direct/manual options, and no recursive retry.

- [ ] **Step 2: Run focused tests**

Run: `cd apps/studio/frontend && node --test tests/placeSearchFlow.test.ts`

Expected: FAIL because `placeSearchFlow.ts` does not exist.

- [ ] **Step 3: Implement the bounded orchestration helper**

The helper accepts injected Google/model functions for deterministic tests. It never invokes DeepSeek on keystrokes and never executes more than one model call plus one rewritten Google search per user action.

- [ ] **Step 4: Update Photo Editor interaction**

Direct **Search** uses automatic fallback only when Google returns zero candidates. When candidates exist, show **Try another interpretation**. Show rewritten query and uncertainty before candidate selection. Preserve candidate selection, map verification, draggable Pin, and explicit confirmation.

- [ ] **Step 5: Retire direct text grading while preserving Pin grading preview**

Remove `grade_text`, `TextGradeInput`, `/api/guess/{photo_id}/grade-text`, the Grade text control, and obsolete `PHOTO_BOOTH_LLM_*` grading setup. Keep `grade_pin`, `/grade-pin`, test latitude/longitude controls, and all distance/radius tests. Add an API test that the removed text-grading route is unavailable and a regression test that Pin grading still returns the expected distance score.

- [ ] **Step 6: Run frontend and backend suites**

Run: `cd apps/studio/frontend && node --test tests/*.test.ts && npm run build`

Run: `python -m pytest -q tests`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/studio/frontend/src/placeSearchFlow.ts apps/studio/frontend/src/PhotoEditor.tsx apps/studio/frontend/src/api.ts apps/studio/frontend/tests/placeSearchFlow.test.ts apps/studio/backend/grading.py apps/studio/backend/main.py tests/test_api.py
git commit -m "feat: add model fallback to place search"
```

### Task 6: Add safe future-website publication

**Files:**
- Create: `apps/studio/backend/ai_publish.py`
- Create: `tests/test_ai_publish.py`
- Modify: `apps/studio/backend/main.py`
- Modify: `apps/studio/frontend/src/AiPlacesPage.tsx`
- Modify: `apps/studio/frontend/src/api.ts`
- Modify: `apps/studio/frontend/src/types.ts`

**Interfaces:**
- Consumes: locally active `AiConfigVersion`, optional rotated DeepSeek key, HTTPS endpoint, and publisher token.
- Produces: `build_release(version, include_secret=False)`, `publish_release(endpoint, token, release, requester=request_json)`, `PUT /api/ai-places/remote`, and `POST /api/ai-places/publish`.

- [ ] **Step 1: Write failing publisher tests**

Test HTTPS-only endpoint validation, missing-token rejection, exact schema/version/hash payload, stable idempotency key, ordinary publish excluding the DeepSeek key, explicit rotation including it once, redirect/different-host rejection, mismatched receipt rejection, timeout behavior, and secret-free error strings.

- [ ] **Step 2: Run publisher tests**

Run: `python -m pytest -q tests/test_ai_publish.py`

Expected: FAIL because the publisher does not exist.

- [ ] **Step 3: Implement the remote contract**

Use the exact headers and payload fields from the design spec. Do not follow redirects automatically. Mark `remote_published_at` and store the non-secret receipt only after response version/hash match the request.

- [ ] **Step 4: Expose remote settings and publish states**

Store endpoint in SQLite and token in Keychain. API responses expose endpoint, token-configured boolean/mask, and last receipt, never the token or DeepSeek key. The frontend disables publishing while disconnected or while draft/test/active hashes differ.

- [ ] **Step 5: Run backend and frontend checks**

Run: `python -m pytest -q tests`

Run: `cd apps/studio/frontend && node --test tests/*.test.ts && npm run build`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/studio/backend/ai_publish.py apps/studio/backend/main.py apps/studio/frontend/src/AiPlacesPage.tsx apps/studio/frontend/src/api.ts apps/studio/frontend/src/types.ts tests/test_ai_publish.py
git commit -m "feat: prepare secure ai config publishing"
```

### Task 7: Document, exercise, and publish the Photo Booth repository

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Create: `docs/ai-place-publishing-contract.md`
- Verify: all tracked files and Git history

**Interfaces:**
- Consumes: completed local implementation and authenticated GitHub CLI.
- Produces: tested documentation and a public `photo-booth` GitHub repository, with no personal website code or private data.

- [ ] **Step 1: Update the operating guide**

Document Google Cloud key setup, DeepSeek key entry through Photo Booth, prompt draft/test/activate flow, disconnected remote state, Keychain behavior, failure fallback, and the fact that the personal website belongs in another repository.

- [ ] **Step 2: Document the future server contract**

Record request headers, JSON schema, receipt schema, HTTPS/auth requirements, secret-rotation behavior, idempotency, and explicit exclusions for answer coordinates and scoring data.

- [ ] **Step 3: Run the complete automated suite**

Run: `python -m pytest -q tests`

Run: `cd apps/studio/frontend && node --test tests/*.test.ts && npm run build`

Expected: all tests and build pass.

- [ ] **Step 4: Perform the macOS browser walkthrough**

Exercise AI & Places draft edit, masked key replacement, `香港 太平山顶 缆车站`, `比较老城区，可能是晋江`, and `海边`; verify direct search, automatic fallback, explicit reinterpretation, candidate selection, Pin move, radius circle, save/reload persistence, version activation, restore, disconnected remote state, and model/network failure fallback.

- [ ] **Step 5: Audit the final tracked repository**

Run: `git status --short --ignored`

Run: `git ls-files | rg '(\.local/|\.sqlite|node_modules/|dist/|originals/|thumbs/|previews/|\.(jpe?g|png|heic|tiff?|webp)$)'`

Run: `git grep -n -E '(sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{20,}|Bearer [A-Za-z0-9._-]{16,}|/Users/[A-Za-z0-9._-]+)'`

Expected: no tracked private data, binaries, credentials, or personal absolute paths.

- [ ] **Step 6: Commit the release documentation**

```bash
git add README.md .env.example docs/ai-place-publishing-contract.md
git commit -m "docs: explain ai places administration"
```

- [ ] **Step 7: Refresh GitHub authentication**

Run: `gh auth login -h github.com`

Expected: `gh auth status` reports the intended account authenticated. This interactive authorization is required because the currently configured token is invalid.

- [ ] **Step 8: Create and attach the public repository**

Run: `gh repo create photo-booth --public --source . --remote origin --push`

Expected: the new public repository contains only the audited Photo Booth history on `main`. If `photo-booth` is unavailable, stop and ask Julia for the alternative name rather than inventing one. Do not add a license unless Julia makes that separate choice.
