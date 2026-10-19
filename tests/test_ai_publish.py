from __future__ import annotations

import socket
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STUDIO_PARENT = ROOT / 'apps' / 'studio'
if str(STUDIO_PARENT) not in sys.path:
    sys.path.insert(0, str(STUDIO_PARENT))

from backend.ai_publish import AiPublishError, build_release, publish_release


@pytest.fixture
def version():
    return SimpleNamespace(
        version=7,
        provider='deepseek',
        base_url='https://api.deepseek.com',
        model='deepseek-flash',
        timeout_seconds=12,
        retry_count=1,
        prompt_text='Rewrite uncertain place text for Google Places.',
        config_hash='a' * 64,
    )


def test_release_schema_is_exact_and_ordinary_publish_excludes_secret(version):
    release = build_release(version)
    assert release == {
        'schemaVersion': 1,
        'version': 7,
        'provider': 'deepseek',
        'baseUrl': 'https://api.deepseek.com',
        'model': 'deepseek-flash',
        'timeoutSeconds': 12,
        'retryCount': 1,
        'prompt': 'Rewrite uncertain place text for Google Places.',
        'promptHash': 'a' * 64,
    }
    assert 'deepSeekApiKey' not in release


def test_explicit_key_rotation_includes_the_key_exactly_once(version):
    release = build_release(version, include_secret=True, deepseek_key='sk-rotate-once')
    assert release['deepSeekApiKey'] == 'sk-rotate-once'
    assert list(release).count('deepSeekApiKey') == 1
    with pytest.raises(AiPublishError, match='DeepSeek key'):
        build_release(version, include_secret=True, deepseek_key='')


def test_publish_requires_https_and_a_token(version):
    release = build_release(version)
    with pytest.raises(AiPublishError, match='HTTPS'):
        publish_release('http://photos.example', 'publisher-token', release)
    with pytest.raises(AiPublishError, match='publisher token'):
        publish_release('https://photos.example', '', release)


def test_publish_uses_stable_idempotency_and_validates_matching_receipt(version):
    release = build_release(version)
    calls = []
    def requester(url, payload, headers, timeout):
        calls.append((url, payload, headers, timeout))
        return ({'version': 7, 'promptHash': 'a' * 64, 'receipt': 'receipt-7'}, url)
    first = publish_release('https://photos.example/config', 'publisher-token', release, requester=requester)
    second = publish_release('https://photos.example/config/', 'publisher-token', release, requester=requester)
    assert first == second == {'version': 7, 'promptHash': 'a' * 64, 'receipt': 'receipt-7'}
    assert calls[0][0] == 'https://photos.example/config/api/admin/ai-place-config'
    assert calls[0][2] == {
        'Authorization': 'Bearer publisher-token',
        'Content-Type': 'application/json',
        'Idempotency-Key': f"ai-place-config-v7-{'a' * 64}",
    }
    assert calls[0][2]['Idempotency-Key'] == calls[1][2]['Idempotency-Key']


def test_redirect_or_different_response_host_is_rejected(version):
    release = build_release(version)
    receipt = {'version': 7, 'promptHash': 'a' * 64, 'receipt': 'bad-host'}
    with pytest.raises(AiPublishError, match='redirect'):
        publish_release(
            'https://photos.example', 'publisher-token', release,
            requester=lambda *_: (receipt, 'https://evil.example/api/admin/ai-place-config'),
        )


def test_mismatched_receipt_and_timeout_are_safe_and_never_echo_secrets(version):
    release = build_release(version, include_secret=True, deepseek_key='sk-never-echo')
    with pytest.raises(AiPublishError, match='receipt') as mismatch:
        publish_release(
            'https://photos.example', 'publisher-never-echo', release,
            requester=lambda *args: ({'version': 8, 'promptHash': 'b' * 64, 'receipt': 'wrong'}, args[0]),
        )
    assert 'sk-never-echo' not in str(mismatch.value)
    assert 'publisher-never-echo' not in str(mismatch.value)

    def timeout(*_):
        raise socket.timeout('publisher-never-echo sk-never-echo')
    with pytest.raises(AiPublishError, match='timed out') as timed_out:
        publish_release('https://photos.example', 'publisher-never-echo', release, requester=timeout)
    assert 'sk-never-echo' not in str(timed_out.value)
    assert 'publisher-never-echo' not in str(timed_out.value)


def test_boolean_version_cannot_masquerade_as_integer_one(version):
    release = build_release(version)
    release['version'] = 1
    with pytest.raises(AiPublishError, match='receipt'):
        publish_release(
            'https://photos.example', 'publisher-token', release,
            requester=lambda *args: ({
                'version': True,
                'promptHash': release['promptHash'],
                'receipt': 'boolean-is-not-version-one',
            }, args[0]),
        )
