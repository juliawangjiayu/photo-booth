# AI place configuration publishing contract

This document defines the receiver that the future personal-website repository may implement. Photo Booth is the publishing client. The receiver does not exist in this repository, and leaving Photo Booth disconnected is a supported state.

## Transport and authentication

Photo Booth accepts a plain HTTPS base URL with no embedded credentials, query, or fragment, then sends:

```http
POST {base-url}/api/admin/ai-place-config
Authorization: Bearer <publisher-token>
Idempotency-Key: ai-place-config-v<version>-<promptHash>
Content-Type: application/json
```

The receiver must authenticate the bearer token, reject unauthorized requests, and process the idempotency key so a retry cannot create a second release. Photo Booth does not follow redirects; the final response URL must be the exact requested URL on the configured host. The publisher token is stored only in macOS Keychain and must never be returned or logged.

## Request body

An ordinary release uses this exact schema:

```json
{
  "schemaVersion": 1,
  "version": 7,
  "provider": "deepseek",
  "baseUrl": "https://api.deepseek.com",
  "model": "deepseek-flash",
  "timeoutSeconds": 12,
  "retryCount": 1,
  "prompt": "Editable place-interpretation prompt",
  "promptHash": "64-character configuration hash"
}
```

The configuration hash covers the non-secret provider, base URL, model, timeout, retry count, and editable prompt. A version is immutable after local activation.

Only the explicit **Publish + replace production key** action adds this field:

```json
{
  "deepSeekApiKey": "the-new-production-key"
}
```

The receiver should replace its stored production DeepSeek key atomically with the accepted release. It must not return, log, or persist the key in ordinary configuration/version tables. Ordinary releases omit this field and therefore leave the production key unchanged.

## Success receipt

A successful receiver returns JSON:

```json
{
  "version": 7,
  "promptHash": "the-same-64-character-configuration-hash",
  "receipt": "non-secret-receiver-generated-id"
}
```

The response should use a 2xx status. Photo Booth records `remote_published_at` and the non-secret receipt only when `version` and `promptHash` exactly match the request. A mismatched, missing, oversized, malformed, redirected, timed-out, or non-2xx response leaves the local active version unchanged and not remotely published.

## Receiver behavior

- Validate `schemaVersion`, every field type and length, the HTTPS provider base URL, and the 64-character hash before changing production state.
- Authenticate before parsing or applying secrets.
- Apply configuration and optional key replacement atomically.
- Treat the idempotency key as stable for the same version/hash and return the original successful receipt for a duplicate request.
- Keep the last known-good version active when validation, authorization, storage, or deployment fails.
- Never expose the active prompt administration route publicly without authentication and rate limiting.

## Explicit exclusions

This contract never contains original photos, thumbnails, EXIF, Gallery metadata, canonical Guess Where answers, answer descriptions, latitude/longitude, accepted radii, difficulty, player answers, distance calculations, or scores. It also excludes the Google Maps key and publisher token.

Guess Where answer synchronization requires a separate authenticated server contract and must not be added to this payload.
