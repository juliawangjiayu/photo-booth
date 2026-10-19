import assert from 'node:assert/strict';
import test from 'node:test';
import {
  applyAiTestResult,
  canPublishActiveConfig,
  canActivateAiDraft,
  canPublishAiDraft,
  clearSecretInput,
  draftFromVersion,
  editAiDraft,
} from '../src/aiPlacesState.ts';
import type { AiPlaceDraft, AiPlaceVersion } from '../src/types.ts';

const draft: AiPlaceDraft = {
  provider: 'deepseek',
  base_url: 'https://api.deepseek.com',
  model: 'deepseek-flash',
  timeout_seconds: 12,
  retry_count: 1,
  prompt_text: 'Interpret the place description.',
  config_hash: 'hash-tested',
  test_state: 'passed',
  tested_hash: 'hash-tested',
  test_summary: 'Test passed',
  active_version: 2,
  created_at: '2026-10-19T10:00:00Z',
  updated_at: '2026-10-19T10:00:00Z',
};

test('editing a tested draft immediately clears its successful-test state', () => {
  const changed = editAiDraft(draft, {model: 'deepseek-chat'});
  assert.equal(changed.model, 'deepseek-chat');
  assert.equal(changed.test_state, 'untested');
  assert.equal(changed.tested_hash, null);
  assert.equal(changed.test_summary, null);
  assert.equal(canActivateAiDraft(changed), false);
});

test('a test result only unlocks the exact current configuration hash', () => {
  const matching = applyAiTestResult(draft, {
    interpretation: {
      status: 'searchable',
      normalized_query: 'Peak Tram, Hong Kong',
      landmark: 'Peak Tram',
      locality: 'Hong Kong',
      region: 'Hong Kong',
      country: 'Hong Kong',
      category: 'transit station',
      uncertainty: [],
      confidence: 0.92,
      clarification: '',
    },
    testedHash: 'hash-tested',
    modelLatencyMs: 420,
  });
  const stale = applyAiTestResult({...draft, config_hash: 'hash-new'}, {
    interpretation: matching.interpretation!,
    testedHash: 'hash-tested',
    modelLatencyMs: 420,
  });
  assert.equal(matching.testMatchesDraft, true);
  assert.equal(stale.testMatchesDraft, false);
});

test('publishing stays disabled without a matching test and an HTTPS endpoint', () => {
  assert.equal(canPublishAiDraft(draft, ''), false);
  assert.equal(canPublishAiDraft(draft, 'http://example.com/admin'), false);
  assert.equal(canPublishAiDraft({...draft, tested_hash: 'stale'}, 'https://example.com/admin'), false);
  assert.equal(canPublishAiDraft(draft, 'https://example.com/admin'), true);
});

test('remote publishing requires token, tested draft, and the same active hash', () => {
  const active = {config_hash: 'hash-tested'};
  const remote = {endpoint: 'https://photos.example/config', tokenConfigured: true};
  assert.equal(canPublishActiveConfig(draft, active, remote), true);
  assert.equal(canPublishActiveConfig(draft, {...active, config_hash: 'older'}, remote), false);
  assert.equal(canPublishActiveConfig(draft, active, {...remote, tokenConfigured: false}), false);
  assert.equal(canPublishActiveConfig({...draft, tested_hash: 'stale'}, active, remote), false);
});

test('secret inputs are cleared even if a server payload accidentally includes a value', () => {
  assert.equal(clearSecretInput({configured: true, mask: 'sk-••••••78', api_key: 'must-not-stay'}), '');
});

test('restoring an immutable version creates an editable untested draft', () => {
  const version: AiPlaceVersion = {
    version: 3,
    provider: 'deepseek',
    base_url: 'https://api.deepseek.com',
    model: 'deepseek-chat',
    timeout_seconds: 15,
    retry_count: 1,
    prompt_text: 'Version three prompt',
    config_hash: 'hash-v3',
    test_summary: 'Passed on example',
    lifecycle_state: 'superseded',
    activated_at: '2026-10-18T10:00:00Z',
    remote_published_at: null,
    remote_publish_receipt: null,
  };
  const restored = draftFromVersion(version, draft);
  assert.equal(restored.model, 'deepseek-chat');
  assert.equal(restored.prompt_text, 'Version three prompt');
  assert.equal(restored.test_state, 'untested');
  assert.equal(restored.tested_hash, null);
  assert.equal(restored.active_version, draft.active_version);
});
