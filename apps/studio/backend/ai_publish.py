"""Secure publisher for versioned AI place-search configuration."""
from __future__ import annotations

import json
import socket
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class AiPublishError(RuntimeError):
    def __init__(self, message: str, code: str = "publish_failed"):
        super().__init__(message)
        self.code = code


def _field(source: Any, name: str) -> Any:
    return source[name] if isinstance(source, Mapping) else getattr(source, name)


def normalize_endpoint(endpoint: str) -> str:
    value = endpoint.strip().rstrip("/")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise AiPublishError("Website endpoint must be a plain HTTPS URL", "invalid_endpoint")
    return value


def build_release(version: Any, include_secret: bool = False, deepseek_key: str = "") -> dict[str, Any]:
    release = {
        "schemaVersion": 1,
        "version": int(_field(version, "version")),
        "provider": str(_field(version, "provider")),
        "baseUrl": str(_field(version, "base_url")),
        "model": str(_field(version, "model")),
        "timeoutSeconds": int(_field(version, "timeout_seconds")),
        "retryCount": int(_field(version, "retry_count")),
        "prompt": str(_field(version, "prompt_text")),
        "promptHash": str(_field(version, "config_hash")),
    }
    if include_secret:
        secret = deepseek_key.strip()
        if not secret:
            raise AiPublishError("A DeepSeek key is required for explicit production-key rotation", "missing_key")
        release["deepSeekApiKey"] = secret
    return release


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


def request_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: int,
) -> tuple[dict[str, Any], str]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    opener = build_opener(_RejectRedirects())
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(128_001)
            if len(body) > 128_000:
                raise AiPublishError("Remote receipt was too large", "invalid_receipt")
            parsed = json.loads(body.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise AiPublishError("Remote receipt was invalid", "invalid_receipt")
            return parsed, response.geturl()
    except HTTPError as error:
        if 300 <= error.code < 400:
            raise AiPublishError("Remote endpoint redirect was rejected", "redirect") from None
        if error.code in (401, 403):
            raise AiPublishError("Remote website rejected the publisher token", "unauthorized") from None
        raise AiPublishError("Remote website rejected the configuration release", "remote_error") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise AiPublishError("Remote receipt was invalid", "invalid_receipt") from None


Requester = Callable[
    [str, dict[str, Any], dict[str, str], int],
    tuple[dict[str, Any], str] | dict[str, Any],
]


def publish_release(
    endpoint: str,
    token: str,
    release: dict[str, Any],
    requester: Requester = request_json,
    timeout: int = 15,
) -> dict[str, Any]:
    base = normalize_endpoint(endpoint)
    publisher_token = token.strip()
    if not publisher_token:
        raise AiPublishError("Configure the website publisher token first", "missing_token")
    version = release.get("version")
    prompt_hash = release.get("promptHash")
    if not isinstance(version, int) or not isinstance(prompt_hash, str) or not prompt_hash:
        raise AiPublishError("Configuration release is invalid", "invalid_release")
    target = base + "/api/admin/ai-place-config"
    headers = {
        "Authorization": f"Bearer {publisher_token}",
        "Content-Type": "application/json",
        "Idempotency-Key": f"ai-place-config-v{version}-{prompt_hash}",
    }
    try:
        response = requester(target, release, headers, timeout)
    except AiPublishError:
        raise
    except (TimeoutError, socket.timeout):
        raise AiPublishError("Remote publication timed out", "timeout") from None
    except URLError:
        raise AiPublishError("Remote website is unavailable", "unavailable") from None
    except Exception:
        raise AiPublishError("Remote publication failed", "publish_failed") from None

    if isinstance(response, tuple):
        receipt, final_url = response
    else:
        receipt, final_url = response, target
    if not isinstance(final_url, str) or urlparse(final_url).hostname != urlparse(target).hostname or final_url != target:
        raise AiPublishError("Remote endpoint redirect was rejected", "redirect")
    if not isinstance(receipt, dict):
        raise AiPublishError("Remote receipt was invalid", "invalid_receipt")
    receipt_version = receipt.get("version")
    receipt_hash = receipt.get("promptHash")
    if (
        type(receipt_version) is not int
        or type(receipt_hash) is not str
        or receipt_version != version
        or receipt_hash != prompt_hash
    ):
        raise AiPublishError("Remote receipt did not match the published version", "receipt_mismatch")
    receipt_id = receipt.get("receipt")
    if not isinstance(receipt_id, str) or not receipt_id.strip() or len(receipt_id) > 500:
        raise AiPublishError("Remote receipt was invalid", "invalid_receipt")
    return {"version": version, "promptHash": prompt_hash, "receipt": receipt_id.strip()}
