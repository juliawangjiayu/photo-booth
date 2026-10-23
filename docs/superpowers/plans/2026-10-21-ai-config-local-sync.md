# AI Configuration Local Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe local command that copies only Photo Booth's active AI configuration to the personal website's local D1 runtime, and make the four-stage lifecycle unmistakable in Photo Booth.

**Architecture:** Photo Booth SQLite remains the authoring source while each website Worker environment owns a small D1 runtime replica. A website-side command reads one immutable active row, publishes the existing versioned contract to a loopback Worker, and never reads Keychain secrets; Photo Booth presents Draft, Test, Activate, and Sync as separate stages.

**Tech Stack:** Node.js 24, TypeScript, node:sqlite, React, Vite, Python/FastAPI tests already present in the repositories.

**Spec:** `docs/superpowers/specs/2026-10-19-google-ai-places-design.md`

## Global Constraints

- Drafts are never synchronized.
- The local sync command accepts loopback Worker endpoints only.
- The DeepSeek key remains in website `.dev.vars` locally and Cloudflare Secrets online.
- The command must not print the prompt, API key, publisher token, coordinates, or private photo data.
- Existing Photo Booth publishing and personal-site Guess Where behavior must remain compatible.

## Review Focus

- Missing active version must fail without sending a request.
- A non-loopback endpoint must be rejected by the local-only command.
- The payload must exactly match the existing website receiver contract and idempotency key.
- A saved or tested draft whose hash differs from the active version must never be selected.
- UI lifecycle state must distinguish unsaved, untested, tested, active, and active-with-new-draft conditions.

---

### Task 1: Personal website local AI configuration sync

**Files:**
- Create: `../juliawangjiayu.github.io/scripts/ai-config-sync.ts`
- Create: `../juliawangjiayu.github.io/scripts/sync-ai-config.mjs`
- Create: `../juliawangjiayu.github.io/tests/aiConfigSync.test.ts`
- Modify: `../juliawangjiayu.github.io/package.json`
- Modify: `../juliawangjiayu.github.io/tsconfig.node.json`
- Modify: `../juliawangjiayu.github.io/README.md`

**Interfaces:**
- Consumes: Photo Booth `ai_place_versions` active row and the existing `POST /api/admin/ai-place-config` contract.
- Produces: `readActiveAiConfig(databasePath)`, `normalizeLocalWorkerEndpoint(endpoint)`, `publishActiveAiConfig(options)`, and `npm run sync:ai-config`.

- [x] **Step 1: Write failing behavior tests**

Test a temporary SQLite database containing both active and newer draft data; assert the active row becomes the exact release payload, no active row fails, a public endpoint is rejected, and the authenticated request uses the stable idempotency key without a secret field.

- [x] **Step 2: Run the focused test and verify RED**

Run: `node --test tests/aiConfigSync.test.ts`

Expected: FAIL because `scripts/ai-config-sync.ts` does not exist.

- [x] **Step 3: Implement the minimal sync module and command**

The command defaults to `../photo-booth/.local/studio.sqlite3`, `http://127.0.0.1:8787`, and the admin token in the website `.dev.vars`, with environment variables and CLI flags available as overrides.

- [x] **Step 4: Run focused and complete website verification**

Run: `node --test tests/aiConfigSync.test.ts`, then `npm test`, `npm run typecheck`, and `npm run build`.

Expected: all commands pass.

### Task 2: Photo Booth lifecycle guidance

**Files:**
- Modify: `apps/studio/frontend/tests/aiPlacesState.test.ts`
- Modify: `apps/studio/frontend/src/aiPlacesState.ts`
- Modify: `apps/studio/frontend/src/AiPlacesPage.tsx`
- Modify: `apps/studio/frontend/src/styles.css`
- Modify: `README.md`

**Interfaces:**
- Consumes: `AiPlaceDraft`, `AiPlaceVersion`, unsaved-draft state, and existing local/remote publication state.
- Produces: `aiConfigLifecycle(...)` and a visible four-stage lifecycle guide plus local/online data-source explanation.

- [x] **Step 1: Write failing lifecycle-state tests**

Assert that an edited draft is Draft-current, an exact tested hash enables Test, activation is complete only when the active hash matches, and a later draft edit keeps the active version syncable while clearly marking it as different from the working draft.

- [x] **Step 2: Run the focused test and verify RED**

Run: `npm test -- --test-name-pattern=\"configuration lifecycle\"`

Expected: FAIL because `aiConfigLifecycle` does not exist.

- [x] **Step 3: Add lifecycle derivation and visible UI**

Show Draft → Test → Activate → Sync above every AI & Places tab, define each term in plain language, rename the versions tab to Versions & sync, and show `npm run sync:ai-config` as the local website action while retaining the authenticated production publish controls.

- [x] **Step 4: Run focused and complete Photo Booth verification**

Run frontend tests and build, then run backend `pytest` to confirm the publishing contract remains unchanged.

Expected: all commands pass.
