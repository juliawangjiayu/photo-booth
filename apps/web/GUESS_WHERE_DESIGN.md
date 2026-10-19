# Future public Guess Where contract

The public game uses one answer flow for every challenge:

1. The player can click the map directly or type a place description.
2. Text searches Google Places and shows candidate locations.
3. If direct search finds nothing, a protected server may ask the configured language model to rewrite the search once, then retry Google Places.
4. The player inspects the resolved candidate on the map, adjusts the Pin if needed, and explicitly confirms the final Pin.
5. The server grades that Pin by distance from the private answer.

The language model is a search interpreter only. It never receives the photo's private answer, creates coordinates, or decides a score.

## Server boundary

Static Gallery JSON, challenge payloads, browser bundles, and share cards must never contain canonical coordinates, accepted radius, private author descriptions, provider credentials, or model prompts. The browser sends only the challenge identifier and the player's confirmed coordinates to an authenticated, rate-limited server endpoint.

The server loads the private answer record and grades distance deterministically. It returns the result, score, explanation, and distance:

```json
{
  "result": "correct",
  "score": 5000,
  "explanation": "The pin is 4.2 km from the answer.",
  "distanceKm": 4.2
}
```

`result` is always `correct`, `close`, or `incorrect`, and `score` is an integer from 0 to 5000. Provider failures during optional text interpretation remain separate from scoring and must let the player revise the query or place the Pin manually.

## Alignment with Photo Booth

- Photo Booth offers 1, 10, 50, and 100 km answer radii and defaults new answers to 10 km.
- Pin distance at or below the answer radius is `correct` and scores 5000.
- Pin distance above the radius and at or below three times the radius is `close`.
- Greater distance is `incorrect`, with sufficiently distant answers reaching 0 points.
- Google search candidates are never answers until the player confirms the Pin.
- The local Photo Booth Pin-grading preview is the reference behavior for the future protected website endpoint.

The public game itself belongs in the future personal-website repository. Photo Booth owns local answer authoring and the publishable configuration contract, not the public game UI.
