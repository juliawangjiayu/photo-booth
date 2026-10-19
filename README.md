# Photo Booth — Local Photography Studio

A privacy-minded, local-first photo CMS for a future Next.js photography portfolio and *Guess Where?* geography game. **Mac-friendly, not deployed publicly.**

## What works in v0.1

- Import and copy multiple photos (drag-and-drop, file picker, folder picker) after choosing or creating a Collection; originals are never edited.
- SHA-256 deduplication, thumbnail/preview creation, date/GPS extraction from EXIF when available.
- Sequential, atomic review after import: a photo must have a month-or-day date, managed device and at least one Collection before the next photo opens.
- Single-column photo editor: optional description, date (month or full day), existing-or-create tags, a Homepage checkbox, and an inline Guess Where section. Photos do not use titles or separate Gallery location fields.
- One managed camera/device per photo, detected from EXIF/TIFF Make and Model when possible, with manual choices for iPhone 6, iPhone 11, iPhone 14, Sony NEX-C3, Sony a6400 and Canon G3QL.
- Guess Where place search and a world-map pin editor; EXIF GPS may seed a Pin but never confirms it automatically.
- Collections (a photo may belong to multiple), basic bulk collection/tag edits.
- Independent Guess Where pool with confirmed coordinates, precision and difficulty; saved locally in SQLite.
- Private Guess Where answer names/descriptions and a 1/10/50/100 km radius (10 km by default), plus local previews for map-pin and online language-model text grading.
- Local export of optimized WebP images and **public-only** JSON for a Next.js website.
- Opt-in Git `commit` and `push` of **only managed photo export files** to an existing remote, with explicit confirmation.
- Needs Review contains only imported photos whose complete review has not yet been saved.
- Local publish checklist for unfinished review and unconfirmed game pins.

**Not yet included:** D1 remote answer synchronization, a real public Next.js Gallery, image editing, authentication, a full featured collection-order editing UI, a packaged `.app`, or cloud background sync. These require separate phases.

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

Photo Booth uses Google Maps JavaScript API for the Pin editor and answer-radius circle, and Places API (New) for place candidates. Add a browser key under Settings; Photo Booth stores the full value in macOS Keychain, while SQLite keeps only the non-secret Map ID. Restrict the key in Google Cloud to the required APIs and local HTTP referrers.

Guess Where search accepts Chinese, English, and mixed descriptions and returns at most five Google Places candidates. Choosing a candidate only positions the draft Pin: you must still inspect the map and explicitly confirm it. The Pin can always be entered as latitude/longitude even when maps or search are unavailable. These online services require Internet access.

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

## Optional text-answer grading preview

Map-pin grading works locally without an API key. Text grading sends the private canonical answer context and the player's test answer to an OpenAI-compatible chat-completions API. Configure the backend process with:

```bash
export PHOTO_BOOTH_LLM_API_KEY="your-key"
export PHOTO_BOOTH_LLM_MODEL="your-model"
# Optional, defaults to https://api.openai.com/v1
export PHOTO_BOOTH_LLM_BASE_URL="https://api.openai.com/v1"
```

The key is read only by the FastAPI process and is never stored in SQLite, returned to the frontend, or written into public exports. If these variables are absent or the provider returns malformed data, Photo Booth reports that text grading is unavailable instead of guessing a result.

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

## Tests

From the repository root, after installing the backend requirements and `pytest` / `httpx`:

```bash
python -m pytest -q tests
```

Frontend type/build check (requires npm dependencies):

```bash
cd apps/studio/frontend
node --test tests/connection.test.ts tests/reviewWorkflow.test.ts
npm run build
```

## Practical limits

- Each photo upload is limited to 80MB; each batch to 100 files. Large folders can be imported in multiple passes.
- Originals are copied into the private archive, which uses extra disk space by design.
- Thumbnail generation supports JPEG/PNG/WebP/TIFF; HEIC depends on your Pillow's available codecs.
- No automatic deletion of original photos: clearing a selection or removing a Collection will never delete original image files.
- Some map services may be unavailable behind certain networks; Guess Where answer names remain editable and map coordinates can be entered manually.
- Guess Where answers are intentionally stored locally, and remote publication awaits authenticated sync support.
