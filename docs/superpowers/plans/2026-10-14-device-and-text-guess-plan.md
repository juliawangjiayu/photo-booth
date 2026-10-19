# Device and Text Guess Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add managed camera metadata and private, coordinate-aligned text-answer authoring and grading previews to the local Photo Booth.

**Architecture:** Extend the fresh SQLite schema and existing photo/Guess Where APIs, isolate device normalization and grading in focused backend modules, then wire the existing React inspector to those contracts. The future public site receives a design/data-contract document only; private answer data remains backend-only.

**Tech Stack:** Python 3.13, FastAPI, SQLite, Pillow/ExifTool, pytest, React 19, TypeScript, Vite, MapLibre.

**Spec:** `docs/superpowers/specs/2026-10-14-device-and-text-guess-design.md`

## Global Constraints

- Do not edit, move, or delete original photo files.
- Start from a fresh `.local/studio.sqlite3`; implement no legacy migration.
- Store only one of the six approved device names or an empty value.
- Never put coordinates or Guess Where answer fields in public static JSON.
- Keep model API credentials on the backend in environment variables.
- Map and text grading must return `correct`, `close`, or `incorrect`.

## Review Focus

- Mixed-case and manufacturer-prefixed EXIF model names normalize to the correct managed device; unknown models remain empty.
- Empty/invalid managed device writes return validation errors rather than arbitrary stored values.
- Exact radius boundaries grade deterministically and invalid coordinates are rejected.
- Missing/malformed/upstream-failing language-model responses produce clear 503 errors and no invented grade.
- Public export contains `device` but no canonical answer, description, radius, latitude, or longitude.

---

### Task 1: Managed device metadata

**Files:**
- Create: `apps/studio/backend/devices.py`
- Modify: `apps/studio/backend/db.py`
- Modify: `apps/studio/backend/images.py`
- Modify: `apps/studio/backend/main.py`
- Modify: `apps/studio/backend/publish.py`
- Modify: `apps/studio/frontend/src/types.ts`
- Modify: `apps/studio/frontend/src/PhotoEditor.tsx`
- Test: `tests/test_api.py`

**Interfaces:**
- Produces: `MANAGED_DEVICES`, `normalize_device(make, model) -> str`, `Photo.device`, PATCH `/api/photos/{id}` device validation, and public `device` metadata.
- Consumes: existing import, edit, and export flows.

- [x] Add failing tests asserting known model normalization, unknown fallback, API persistence/validation, and public export behavior.
- [x] Run `.venv313/bin/python -m pytest -q tests` and confirm failures are caused by the absent device feature.
- [x] Implement device normalization, schema/API fields, EXIF/TIFF Make/Model extraction, editor dropdown, and export field.
- [x] Run `.venv313/bin/python -m pytest -q tests` and confirm the complete backend suite passes.
- [x] Run `npm run build` in `apps/studio/frontend` and confirm TypeScript and Vite succeed.

### Task 2: Private Guess Where answer model

**Files:**
- Modify: `apps/studio/backend/db.py`
- Modify: `apps/studio/backend/main.py`
- Modify: `apps/studio/frontend/src/types.ts`
- Modify: `apps/studio/frontend/src/api.ts`
- Modify: `apps/studio/frontend/src/PhotoEditor.tsx`
- Test: `tests/test_api.py`

**Interfaces:**
- Produces: `Guess.answer_name`, `Guess.answer_description`, `Guess.answer_radius_km`; game-ready counting that requires all canonical answer fields.
- Consumes: confirmed coordinates and precision from the existing Guess Where flow.

- [x] Add failing tests for answer persistence, radius validation, and game-ready counting.
- [x] Run the focused tests and confirm they fail because the answer fields are absent.
- [x] Extend the fresh schema, Pydantic model, upsert, editor fields, place-result synchronization, and save rules.
- [x] Run the full backend suite and frontend production build.

### Task 3: Unified grading preview

**Files:**
- Create: `apps/studio/backend/grading.py`
- Modify: `apps/studio/backend/main.py`
- Modify: `apps/studio/backend/requirements.txt`
- Modify: `apps/studio/frontend/src/types.ts`
- Modify: `apps/studio/frontend/src/api.ts`
- Modify: `apps/studio/frontend/src/PhotoEditor.tsx`
- Test: `tests/test_api.py`

**Interfaces:**
- Produces: `grade_pin`, `grade_text`, POST `/api/guess/{photo_id}/grade-pin`, POST `/api/guess/{photo_id}/grade-text`, and `GradeResult`.
- Consumes: canonical answer data from Task 2 and `PHOTO_BOOTH_LLM_*` environment variables.

- [x] Add failing tests with hand-derived distances for correct/close/incorrect and API validation boundaries.
- [x] Add failing text-grading tests using an injected local HTTP transport for success, malformed JSON, missing config, and upstream failure.
- [x] Implement haversine grading and a narrow OpenAI-compatible HTTP client with strict structured-response validation.
- [x] Add local UI preview inputs and result display for map and text modes.
- [x] Run the full backend suite and frontend production build.

### Task 4: Privacy, documentation, and final verification

**Files:**
- Modify: `tests/test_api.py`
- Modify: `README.md`
- Create: `apps/web/GUESS_WHERE_DESIGN.md`

**Interfaces:**
- Produces: verified privacy regression coverage and the future website contract.
- Consumes: all API and storage contracts from Tasks 1–3.

- [x] Add a regression test hashing an imported original before and after device editing, Guess Where authoring, grading, and export.
- [x] Extend export assertions to reject every private answer field while accepting the public device field.
- [x] Document fresh-database behavior, model environment variables, authoring flow, and local grading preview.
- [x] Document the future public website request/response contract and server-only secret requirements.
- [x] Run `.venv313/bin/python -m pytest -q tests` and `npm run build`.
- [x] Verify `/api/health`, `/api/stats`, and the Vite proxy over the running local services.
