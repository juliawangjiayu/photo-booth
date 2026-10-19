# Photo Device and Text Guess Design

## Goal

Extend Photo Booth without changing or deleting original photos or migrating the existing database:

1. Every photo may have exactly one managed camera/device value. Import should detect it from EXIF/TIFF metadata when possible, and the editor should provide the six user-approved choices when detection is absent or unsupported.
2. A Guess Where entry may include a private canonical place answer and an author description in addition to its confirmed coordinates. Players may answer either with a map pin or text. Text grading uses a configurable online language-model API while returning the same `correct`, `close`, or `incorrect` outcome categories used by coordinate grading.

This phase implements the local Photo Booth authoring system. The public photography website is not implemented in this repository; its data contract and future Guess Where interaction design are updated so it can support both answer modes later.

## Managed devices

The only stored non-empty device values are:

- `iPhone 6`
- `iPhone 11`
- `iPhone 14`
- `Sony NEX-C3`
- `Sony a6400`
- `Canon G3QL`

Each photo has a nullable `device` column in the new database schema.

Import reads EXIF/TIFF `Make` and `Model` tags. ExifTool requests `Make` and `Model`; Pillow falls back to TIFF/EXIF tags 271 and 272. A normalization function maps known spelling and manufacturer variations to the managed values. Unsupported or missing values remain empty and never guess a device.

The photo editor shows a single-select device field with an empty option and the six managed values. A user may change or clear it. Device is included in public photo metadata because it is not a location secret.

## Private Guess Where answer model

`guess_where_entries` retains the confirmed `latitude` and `longitude` as the canonical spatial truth and adds:

- `answer_name`: a concise standard place name, such as a city, district, or county.
- `answer_description`: an optional natural-language description supplied by the author.
- `answer_radius_km`: the distance threshold for a fully correct map answer.

The existing `precision` value supplies the default radius: exact answers default to 10 km and approximate answers default to 40 km. The author can adjust the radius between 1 and 500 km.

These fields remain private and are excluded from the Gallery JSON together with coordinates. The public photography export may include `device`, but no Guess Where answer data.

## Authoring flow

When enabling Guess Where, the author can enter a standard place or a vague description and run the existing location search. Search results provide named candidate coordinates. Selecting a result fills the canonical answer name and provisional coordinates, then opens or updates the map so the author can confirm or adjust the pin. A vague description is preserved as `answer_description`; it is not treated as a reliable coordinate until the author confirms a search result or map pin.

A playable entry requires all of:

- enabled;
- confirmed coordinates;
- a non-empty canonical answer name;
- a valid answer radius.

Saving ordinary Gallery metadata does not require a Guess Where answer.

## Grading model

The backend owns grading; secrets are never sent to the browser.

Map grading computes the haversine distance between the submitted pin and canonical coordinates:

- `correct`: distance is at most `answer_radius_km`;
- `close`: distance is greater than the radius and at most three times the radius;
- `incorrect`: distance is greater than three times the radius.

Text grading calls an OpenAI-compatible chat-completions endpoint configured through environment variables:

- `PHOTO_BOOTH_LLM_API_KEY`
- `PHOTO_BOOTH_LLM_MODEL`
- `PHOTO_BOOTH_LLM_BASE_URL` (optional; defaults to the OpenAI API base URL)

The prompt receives the private canonical place name, author description, canonical coordinates, answer radius, and the player's text. It must return structured JSON containing `result` (`correct`, `close`, or `incorrect`), `confidence` from 0 to 1, and a short explanation. The backend validates this JSON and rejects malformed or unavailable responses with a clear service-unavailable error. It does not silently invent a grade.

The model is instructed to judge geographic equivalence, aliases, administrative hierarchy, and reasonable specificity. The distance thresholds are supplied as the semantic reference so text and map grading use the same tolerance. Text answers and grading responses are not persisted in the local database in this phase.

## API and UI

Photo read/update APIs add `device`.

Guess entry read/update APIs add `answer_name`, `answer_description`, and `answer_radius_km`.

Two local/private grading-preview endpoints are added:

- `POST /api/guess/{photo_id}/grade-pin`
- `POST /api/guess/{photo_id}/grade-text`

The local Photo Booth UI adds device selection to Photo details and answer-name, description, location-search, radius, and map confirmation controls to Guess Where. It also exposes a small local grading preview for both answer modes so the author can test the configured rules before publishing a future public game.

The future public website design uses the same three-result grading contract for map and text answers. The website sends only a player's answer to a protected server endpoint; canonical names, descriptions, coordinates, radius, model credentials, and grading prompts are never shipped in static files or browser bundles. Implementing that protected public endpoint and player UI is outside this phase.

## Fresh database and privacy

The previous `.local/studio.sqlite3` may be deleted before first launch. The revised application creates a fresh `.local/studio.sqlite3` with the complete new schema and performs no legacy-data migration. Existing original, thumbnail, and preview files remain untouched; newly imported images continue using the established content-addressed file layout.

The README explains that this version starts with fresh metadata and does not import legacy database rows.

Public export tests must assert that latitude, longitude, answer name, answer description, and radius never appear in generated JSON. Original-file hashes must remain unchanged across metadata editing, Guess Where authoring, and export.

## Testing

Backend tests cover:

- EXIF/TIFF Make/Model normalization and unknown-device behavior;
- device validation, persistence, and public export;
- creation and reuse of a fresh database without any migration path;
- Guess Where answer persistence and game-ready counting;
- deterministic pin grading at threshold boundaries;
- text-grading success, malformed response, missing configuration, and upstream failure;
- public-export exclusion of all private answer fields;
- unchanged original bytes after every metadata operation.

Frontend verification covers TypeScript production build plus manual authoring checks for device selection, place-search-to-pin synchronization, radius editing, and grading preview states.
