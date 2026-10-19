"""Strict, bounded DeepSeek rewrite for location search only."""
from __future__ import annotations

import json
import socket
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictStr, ValidationError, model_validator


LOCKED_ENVELOPE = """Return one JSON object matching the required schema and no other text.
Never produce latitude, longitude, bounding boxes, place IDs, distances, scores, or a correct answer.
Never request or infer private answer data.
The normalized query must be at most 300 characters.
When status is insufficient, normalized_query must be empty and clarification must say what geographic context is missing."""


class PlaceInterpretationError(RuntimeError):
    def __init__(self, message: str, code: str = 'unavailable'):
        super().__init__(message)
        self.code = code


class PlaceInterpretation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    status: Literal['searchable', 'insufficient']
    normalized_query: StrictStr = Field(max_length=300)
    landmark: StrictStr = Field(max_length=160)
    locality: StrictStr = Field(max_length=160)
    region: StrictStr = Field(max_length=160)
    country: StrictStr = Field(max_length=160)
    category: StrictStr = Field(max_length=100)
    uncertainty: list[StrictStr] = Field(max_length=8)
    confidence: StrictFloat = Field(ge=0, le=1)
    clarification: StrictStr = Field(max_length=300)

    @model_validator(mode='after')
    def check_searchability(self):
        if self.status == 'searchable' and not self.normalized_query.strip():
            raise ValueError('Searchable result requires a query')
        if self.status == 'insufficient' and (self.normalized_query or not self.clarification.strip()):
            raise ValueError('Insufficient result requires clarification and no query')
        return self


def build_location_messages(raw_text: str, prompt: str) -> list[dict[str, str]]:
    return [
        {'role': 'system', 'content': prompt.strip() + '\n\n' + LOCKED_ENVELOPE},
        {'role': 'user', 'content': raw_text.strip()},
    ]


def request_model(payload: dict, api_key: str, base_url: str, timeout: int) -> dict:
    parsed = urlparse(base_url)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password:
        raise PlaceInterpretationError('Provider URL must use HTTPS', 'invalid_config')
    request = Request(
        base_url.rstrip('/') + '/chat/completions',
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        method='POST',
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read(128_000).decode('utf-8'))


def interpret_place(raw_text: str, config, api_key: str, requester=request_model) -> PlaceInterpretation:
    if not isinstance(raw_text, str) or not raw_text.strip() or len(raw_text) > 500:
        raise PlaceInterpretationError('Enter a place description of 1–500 characters', 'invalid_input')
    if not api_key.strip():
        raise PlaceInterpretationError('Configure the DeepSeek API key first', 'missing_key')
    field = lambda key: config[key] if isinstance(config, dict) else getattr(config, key)
    payload = {
        'model': field('model'), 'temperature': 0,
        'thinking': {'type': 'disabled'},
        'response_format': {'type': 'json_object'},
        'max_tokens': 400,
        'messages': build_location_messages(raw_text, field('prompt_text')),
    }
    retries = max(0, min(5, int(field('retry_count'))))
    for attempt in range(retries + 1):
        try:
            result = requester(payload, api_key, field('base_url'), int(field('timeout_seconds')))
            content = result['choices'][0]['message']['content']
            if not isinstance(content, str):
                raise ValueError('Non-text model output')
            return PlaceInterpretation.model_validate_json(content)
        except HTTPError as error:
            if error.code == 401:
                raise PlaceInterpretationError('DeepSeek rejected the API key', 'unauthorized') from None
            if error.code == 429:
                if attempt < retries: continue
                raise PlaceInterpretationError('DeepSeek is rate limited; try again later', 'rate_limited') from None
            if 500 <= error.code < 600 and attempt < retries: continue
            raise PlaceInterpretationError('DeepSeek is temporarily unavailable', 'provider_error') from None
        except (TimeoutError, socket.timeout, URLError):
            if attempt < retries: continue
            raise PlaceInterpretationError('DeepSeek timed out; try again or place a Pin manually', 'timeout') from None
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError, ValidationError):
            raise PlaceInterpretationError('DeepSeek returned an invalid location interpretation', 'invalid_response') from None
    raise PlaceInterpretationError('DeepSeek is temporarily unavailable')
