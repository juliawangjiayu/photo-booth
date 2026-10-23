# Photo Booth — Local Photography Studio

A privacy-minded, local-first photo CMS for a future Next.js photography portfolio and *Guess Where?* geography game. **Mac-friendly, not deployed publicly.**

## What works in v0.1

- Import and copy multiple photos (drag-and-drop, file picker, folder picker) after choosing or creating a Collection; originals are never edited.
- SHA-256 deduplication, thumbnail/preview creation, date/GPS extraction from EXIF when available.
- Sequential, atomic review after import: a photo must have a month-or-day date, managed device and at least one Collection before the next photo opens.
- Single-column photo editor: optional description, date (month or full day), existing-or-create tags, a Homepage checkbox, and an inline Guess Where section. Photos do not use titles or separate Gallery location fields.
- One managed camera/device per photo, detected from EXIF/TIFF Make and Model when possible, with manual choices for iPhone 6, iPhone 11, iPhone 14, Sony NEX-C3, Sony a6400 and Canon G3QL.
- Guess Where place search and a world-map pin editor; EXIF GPS may seed a Pin but never confirms it automatically.
- Google Places searches first; zero results trigger at most one DeepSeek rewrite and one Google retry. Existing candidates can be reinterpreted explicitly.
- A local **AI & Places** console for masked Keychain secrets, editable prompt/model settings, live end-to-end tests, immutable active versions, and optional HTTPS publication to a future website backend.
- Collections (a photo may belong to multiple), basic bulk collection/tag edits.
- Independent Guess Where pool with confirmed coordinates, precision and difficulty; saved locally in SQLite.
- Private Guess Where answer names/descriptions and a 1/10/50/100 km radius (10 km by default), plus a local map-pin grading preview.
- Local export of optimized WebP images and **public-only** JSON for a Next.js website.
- Opt-in Git `commit` and `push` of **only managed photo export files** to an existing remote, with explicit confirmation.
- Needs Review contains only imported photos whose complete review has not yet been saved.
- Local publish checklist for unfinished review and unconfirmed game pins.

**Not yet included:** the future website-side configuration receiver, D1 remote answer synchronization, a real public Next.js Gallery, image editing, authentication, a full featured collection-order editing UI, a packaged `.app`, or cloud background sync. These require separate phases in the separate personal-website repository.

## First-run setup (macOS)

1. Install **Node.js 20+** and **Python 3.11+**. Optional but strongly recommended: `brew install exiftool` (ensures robust GPS metadata extraction). For HEIC support, native format helpers may also be needed; unsupported images receive an import error without affecting other files.
2. Extract this ZIP to a folder on your Mac. Open Terminal in that folder.
3. Run:

   ```bash
   ./start.command
   ```

4. Visit **http://127.0.0.1:5173**. Keep the Terminal window open while using Photo Booth. Ctrl+C stops it.

Manual equivalent:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r apps/studio/backend/requirements.txt
python -m uvicorn backend.main:app --app-dir apps/studio --host 127.0.0.1 --port 8000
# In another terminal:
cd apps/studio/frontend && npm install && npm run dev
```

API documentation (local only): http://127.0.0.1:8000/docs

## Organizing photos

- Every import starts by selecting an existing Collection or creating one inline. A duplicate file reuses its existing photo record and is linked to the chosen Collection without copying the original again.
- Imported draft photos open in a sequential review queue. **Save and next** is available only after the current photo is complete; **Save and exit** completes the current photo and leaves the untouched remainder in Needs Review.
- `taken_at` is required and must be `YYYY-MM` or `YYYY-MM-DD`. Photo Booth prefers the complete EXIF date when available; manual entry may stop at the month.
- A managed camera/device and at least one Collection are required. The device is filled from recognized EXIF/TIFF Make and Model when possible.
- Photos have no title or separate Gallery location fields. Homepage and Guess Where are ordinary checked/unchecked choices saved with the rest of the review.
- Tags are selected from existing values or created in the review form; they are persisted only when the complete photo review succeeds.
- If Guess Where is checked, enter a canonical place answer and **confirm the answer by placing a map pin**; a photo does not need existing EXIF GPS to join the game.
- Collections are many-to-many. Tags are independent from Collections.
- The game question pool and the Gallery share stable photo IDs (`p_<hash>`).

## Location lookup and maps

Photo Booth uses Google Maps JavaScript API for the Pin editor and answer-radius circle, and Places API (New) for place candidates. Add a browser key under **AI & Places → Model & prompt**; Photo Booth stores the full value in macOS Keychain, while SQLite keeps only the non-secret Map ID. Restrict the key in Google Cloud to the required APIs and local HTTP referrers.

Google Cloud setup:

1. Create or choose a Google Cloud project with billing enabled. Google Maps Platform requires billing even when usage remains within available credits.
2. Enable **Maps JavaScript API** and **Places API (New)** for that project.
3. Create an API key with **Websites** application restrictions. Add `http://127.0.0.1:5173/*` and `http://localhost:5173/*` as allowed referrers.
4. Restrict the key to only **Maps JavaScript API** and **Places API (New)**, then paste it into Photo Booth → **AI & Places → Model & prompt**.
5. Keep `DEMO_MAP_ID` while testing, or create a Map ID in Google Cloud and save it alongside the key. Advanced Markers require a Map ID.

The future public website should use a separate browser key restricted to its production domains. Do not reuse an unrestricted local-development key in a deployed site, and never commit either key to Git.

Guess Where search accepts Chinese, English, and mixed descriptions and returns at most five Google Places candidates. Google searches the original text first. If it returns zero candidates, Photo Booth may ask DeepSeek to produce one safer search query and retry Google exactly once. When direct candidates already exist, **Try another interpretation** is explicit rather than automatic. Choosing a candidate only positions the draft Pin: you must still inspect the map and explicitly confirm it. The Pin can always be entered as latitude/longitude even when maps, search, or DeepSeek are unavailable. These online services require Internet access.

When GPS exists, the Guess Where map may open at that position. GPS is never used as a confirmed game answer without explicit approval in the map editor.
The map displays the selected private answer radius as a shaded circle so the Pin and accepted area can be checked before saving.

## Local folder and privacy

Private data is stored under `.local/` beside the code:

```text
.local/
  studio.sqlite3      # fresh photo metadata, private game answers and settings
  originals/          # copied original images
  thumbs/             # local previews
  previews/           # local previews
```

`.local/` and any `.env` files are ignored by Git. **Back up `.local/`** (and your original photo library); reinstalling or deleting this directory loses edits and answers.

This version does not migrate metadata from an older Photo Booth database. Start with a fresh `.local/studio.sqlite3`; original image files are independent and are never rewritten by metadata editing.

## AI-assisted place search

Map-pin grading works locally without an API key. DeepSeek is used only as a bounded fallback when Google Places cannot understand a location description; it receives the typed search description and the configured prompt, but never the photo, private answer Pin, radius, canonical answer, or score.

Configure it under **AI & Places**:

1. In **Model & prompt**, keep the default DeepSeek endpoint/model or edit the non-secret fields, paste the DeepSeek API key, and save the draft. The key is stored in macOS Keychain and immediately cleared from the input.
2. In **Test configuration**, try real examples. Photo Booth calls DeepSeek with the draft, displays the normalized Google query and uncertainty, then shows live Google Places candidates and separate latencies. Ordinary photo editing uses only the locally active version and never marks a draft as tested.
3. Any draft or secret edit invalidates the previous test. Only the exact tested draft hash can be activated.
4. **Activate as new version** creates immutable local history. Restoring an old version copies it into an untested editable draft; it never rewrites history.
5. **Versions & sync** distinguishes the local active version, local website D1 synchronization, and optional production publication.

The page keeps the complete lifecycle visible: **Draft** is only an editable working copy in local SQLite; **Test** approves one exact hash; **Activate** creates the immutable version Photo Booth may use; and **Sync** is the only stage that copies an active version to a website D1 database. Saving or testing a draft never changes either website environment.

The editable prompt is wrapped in a code-enforced safety envelope. Malformed model output, timeouts, invalid keys, and vague descriptions are recoverable errors; manual Pin entry remains available. Full Google, DeepSeek, and publisher credentials are stored in macOS Keychain rather than SQLite, `.env`, or public exports.

The backend listens only on `127.0.0.1`; do not expose it publicly. Photo exports are re-encoded into WebP without EXIF or GPS, and generated JSON excludes exact coordinates. Do not commit `.local/` to Git even in a private repository.

## Publish to a Next.js website

Use a Next.js project folder that already contains `package.json` (for example a public site under `apps/web`). In Photo Booth → **Settings**, set this folder path, then **Publish** → **Export locally**. Output:

```text
<next-web-root>/
  public/photos/p_<id>.webp
  public/photos/p_<id>-thumb.webp
  src/generated/photography.json
  src/generated/collections.json
```

Photo Booth exports all reviewed photos with a valid month-or-day date and an existing original. Drafts are skipped with reasons. The JSON uses camelCase and contains only public fields: image URLs, size, date, description, device, collections, tags and featured status. Photo titles and Gallery locations are not exported.

If the website folder is an existing Git repository with an `origin` remote and you have Git credentials configured, you can then choose **Commit & push to GitHub**. The app refuses to publish if you already have staged changes, and stages only the managed output paths. **This triggers a real `git push`**, so review your repository's deployment settings first. GitHub authentication is provided by your own Git credentials, not stored inside Photo Booth.

**Game answer sync is intentionally not implemented in v0.1.** Answers remain in your local SQLite database until a secure, authenticated API for Cloudflare D1 exists; this avoids leaking the quiz answers into a public Git repo or static JSON.

### AI configuration synchronization

For local personal-website testing, start the sibling website Worker, then run `npm run sync:ai-config` from `../juliawangjiayu.github.io`. That command reads only the active row from Photo Booth SQLite and copies the non-secret version to local D1. It never reads the editable draft or macOS Keychain; the local Worker gets its DeepSeek key from its own `.dev.vars`.

For production, the **Versions & sync** tab can save the website's HTTPS base endpoint and a publisher token. The token stays in macOS Keychain; only the endpoint and non-secret receipt are stored in SQLite.

Photo Booth publishes only the exact tested and locally active version. Ordinary releases contain the provider, endpoint, model, timeout, retry count, editable prompt, version and prompt hash. They contain no photos, Guess Where answers, coordinates, radii, scores, Google key, or publisher token. **Publish + replace production key** is a separate confirmed action that adds the current DeepSeek key to that one request; ordinary releases never resend it. Redirects are rejected, releases are idempotent, and the local version is marked remote only after a matching version/hash receipt. See [the publishing contract](docs/ai-place-publishing-contract.md).

The personal website and its receiver belong in a separate repository. This repository is only the local Photo Booth application and the client-side contract.

## Tests

From the repository root, after installing the backend requirements and `pytest` / `httpx`:

```bash
python -m pytest -q tests
```

Frontend type/build check (requires npm dependencies):

```bash
cd apps/studio/frontend
node --test tests/*.test.ts
npm run build
```

## Practical limits

- Each photo upload is limited to 80MB; each batch to 100 files. Large folders can be imported in multiple passes.
- Originals are copied into the private archive, which uses extra disk space by design.
- Thumbnail generation supports JPEG/PNG/WebP/TIFF; HEIC depends on your Pillow's available codecs.
- No automatic deletion of original photos: clearing a selection or removing a Collection will never delete original image files.
- Some map services may be unavailable behind certain networks; Guess Where answer names remain editable and map coordinates can be entered manually.
- Guess Where answers are intentionally stored locally. The AI configuration publisher does not synchronize answers; authenticated answer sync remains a separate future feature.
