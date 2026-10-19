# Future public Guess Where contract

The public website should offer two answer modes for the same photo challenge:

1. A player places a map pin.
2. A player enters a natural-language place answer.

Both modes return the same server response:

```json
{
  "result": "correct",
  "score": 5000,
  "confidence": 1.0,
  "explanation": "The pin is 4.2 km from the answer.",
  "distanceKm": 4.2
}
```

`result` is always `correct`, `close`, or `incorrect`, and `score` is an integer from 0 to 5000. `distanceKm` is present for pin answers and omitted for text answers.

## Server boundary

Static Gallery JSON and browser bundles must never contain canonical coordinates, answer names, author descriptions, accepted radius, model credentials, or grading prompts. The browser sends only the challenge identifier and player's answer to an authenticated/rate-limited server endpoint.

The server loads the private answer record, grades pins deterministically using the configured radius, and grades text with the configured language model. It returns only the result, confidence, explanation, and optional distance. Provider failures return an unavailable response; the client must not treat a failure as an incorrect answer.

## Alignment between answer modes

- Photo Booth offers 1, 10, 50 and 100 km answer radii and defaults new answers to 10 km.
- Pin distance at or below the answer radius is `correct` and scores 5000.
- Pin distance above the radius and at or below three times the radius is `close`.
- Greater distance is `incorrect`.
- The text-grading prompt receives those same thresholds and judges aliases, translations, administrative hierarchy, and specificity against them.

The local Photo Booth grading preview is the reference behavior for the future protected website endpoint.
