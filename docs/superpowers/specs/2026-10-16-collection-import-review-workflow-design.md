# Collection-first Import and Photo Review Workflow

**Date:** 2026-10-16

## Context

Photo Booth currently imports selected files immediately and returns to the Library. Metadata is then edited photo by photo through a general-purpose side panel. This does not match the primary workflow: import a group of photographs into one Collection, then review every new photograph in sequence before moving on.

The revised workflow must preserve the existing independent Collection and Guess Where management panels. It must also preserve original files, the Collection many-to-many relationship, and the rule that private Guess Where answers are never included in the public export.

## Goals

- Require an existing or newly created Collection before an import begins.
- Add every selected photo to that Collection without creating duplicate photo records.
- Open a sequential review queue after import.
- Prevent moving to the next photo until the current photo is complete.
- Allow the user to finish the current photo and exit; unreviewed photos remain in Needs Review.
- Keep Needs Review limited to photos that have not completed the review workflow.
- Prefer EXIF metadata for date and device while allowing manual correction.
- Replace comma-separated tag entry with an existing-or-create multi-select.

## Non-goals

- No persistent import-batch history or new import-batches table.
- No partial drafts for a photo that has entered the review form.
- No change to the public Guess Where player implementation.
- No deletion or modification of original photo files.
- No replacement of the existing Collection or Guess Where management panels.

## Import Flow

The Add Photos and Import Folder actions open an import dialog instead of uploading immediately.

1. The user selects one existing Collection or creates a Collection inline.
2. The user selects files or a folder.
3. Photo Booth imports supported images and associates each result with the selected Collection.
4. Newly imported photos are placed in `draft` status.
5. If a file is a duplicate, Photo Booth reuses the existing photo record and adds the selected Collection relationship if it is missing.
6. Completed duplicate photos do not enter the review queue. Duplicate photos still in `draft` do enter the queue.
7. The frontend opens the first draft photo returned by the import operation.

The queue follows selected-file order where possible. Failures and unsupported files are reported without preventing successfully processed photos from entering the queue.

## Sequential Review Experience

Review mode reuses the photo editor's fields but presents a clear queue context, including progress such as `3 / 18`.

The available completion actions are:

- **Save and next:** atomically saves the current photo, then opens the next queue item.
- **Save and exit:** atomically saves the current photo, then leaves review mode.
- **Save and finish:** replaces Save and next on the final item.

The user cannot navigate to the next photo while the current form is incomplete. Form changes remain local until one of the save actions succeeds. Closing an incomplete or dirty form warns that current changes will be discarded. After discarding, that photo remains `draft` and no partial metadata is persisted.

Exiting after a successful save leaves all remaining, unreviewed queue items in Needs Review. Opening Needs Review later can start another sequential queue from the remaining draft photos.

## Review Form Rules

### Required

- **Date taken:** initialized from EXIF when available. A saved value must be either `YYYY-MM` or `YYYY-MM-DD`. A year without a month is insufficient.
- **Camera/device:** initialized from normalized EXIF Make/Model when possible. Otherwise the user chooses one of the managed devices.
- **At least one Collection:** the import Collection is selected by default; additional Collections may be added.

### Required decisions represented by checkboxes

- **Homepage:** checked means the photo is featured; unchecked means it is not featured.
- **Guess Where:** checked means the photo belongs to the game; unchecked means it does not.

No additional “decision made” columns are needed. The checkbox values become intentional only when the entire form is atomically saved and the photo leaves `draft` status.

If Guess Where is checked, the following become required before save:

- canonical place answer;
- confirmed latitude and longitude from the MapLibre picker;
- answer radius, precision, and difficulty using their valid defaults or edited values.

The optional descriptive answer remains available for text-answer grading.

### Optional

- Title
- Public Gallery location
- Description
- Tags

The title may remain empty and must not block review or publishing. Public consumers must tolerate an empty title and may choose an image-appropriate fallback in presentation code.

## Tags

The free-form comma-separated tag input is replaced by a searchable multi-select.

- `GET /api/tags` returns all existing tag names in a stable, case-insensitive order.
- The user can select any number of existing tags.
- Entering a non-existing tag offers a create-and-select action.
- New tags are created as part of the atomic photo save.
- Existing case-insensitive uniqueness and photo-to-tag many-to-many storage are retained.

## Backend API and Transactions

### Collection-first import

`POST /api/photos/import` remains multipart but also requires `collection_id`.

The backend validates the Collection before processing files. For each successful file it either creates a new photo or resolves the existing photo by SHA-256, then inserts the Collection relationship with `INSERT OR IGNORE` semantics.

The response includes:

- newly added photo IDs;
- duplicate filenames and their resolved photo IDs;
- per-file errors;
- ordered `reviewIds` containing only draft photos associated during this operation.

### Atomic review save

A dedicated review endpoint, `PUT /api/photos/{photo_id}/review`, accepts all form state in one request:

- photo metadata;
- Collection IDs;
- tag names;
- Homepage checkbox value;
- Guess Where checkbox value and, when enabled, its private answer payload.

The backend validates the complete request before committing. On success it:

1. updates photo metadata and Homepage state;
2. replaces Collection and tag relationships;
3. creates missing tags and reuses existing tags;
4. upserts the private Guess Where entry when enabled, or removes it when disabled;
5. changes the photo status from `draft` to `modified`;
6. commits once.

Any validation or database failure rolls the whole operation back. A photo can therefore be either unreviewed or completely saved, never partially reviewed.

General patch and bulk-edit APIs must not move a draft photo out of Needs Review. Draft photos are completed only through the atomic review endpoint. Bulk metadata editing remains available for already reviewed photos.

## Status, Needs Review, and Publishing

The existing `photos.status` field remains the source of review state:

- `draft`: imported but not successfully reviewed;
- `modified`: reviewed and locally saved;
- `published`: reviewed and included in a successful export.

Needs Review is exactly the set of photos with `status = 'draft'`. EXIF-derived defaults and the initial Collection link do not count as user review.

Publishing excludes draft photos. For reviewed photos, publishing requires a valid month-or-day date and an existing original file. An empty title is allowed. Public export still includes the Homepage boolean, public location fields, Collections, and tags, while excluding EXIF GPS and every private Guess Where answer field.

## Compatibility

No new database table or decision columns are required. Existing `modified` and `published` photos are treated as reviewed. Existing `draft` photos appear in Needs Review and can be completed through the new queue.

The managed device list and existing EXIF normalization remain unchanged. Existing Collection and tag many-to-many tables remain unchanged.

## Error Handling

- Import is blocked until a Collection is selected or successfully created.
- A deleted or unknown Collection produces a validation error before file processing.
- Individual file failures do not discard other successful imports.
- Review validation reports field-specific problems and leaves the database unchanged.
- Closing a dirty review form requires confirmation because unsaved changes will be discarded.
- Online place search and map failures continue to allow retry; Guess Where cannot be completed until a valid Pin has been confirmed.

## Verification

Backend tests must cover:

- import rejection without a Collection;
- new-photo Collection association;
- duplicate reuse and Collection association without a second photo row;
- correct `reviewIds` behavior for draft and already reviewed duplicates;
- date rejection for `YYYY` and acceptance for `YYYY-MM` and `YYYY-MM-DD`;
- required managed device validation;
- atomic rollback when required fields or Guess Where data are incomplete;
- Homepage checked and unchecked persistence;
- Guess Where upsert and removal through review save;
- selecting existing tags and creating new tags;
- draft-only Needs Review statistics and filtering;
- optional title publishing;
- unchanged original-file hashes and private-coordinate export exclusion.

Frontend tests should isolate queue progression and review-form validation from rendering where practical. A browser verification pass must exercise:

1. selecting or creating a Collection before import;
2. importing multiple files;
3. completing one photo and advancing;
4. saving and exiting with remaining photos in Needs Review;
5. selecting and creating tags;
6. both Homepage checkbox states;
7. both Guess Where checkbox states, including map confirmation;
8. resuming remaining draft photos from Needs Review.

