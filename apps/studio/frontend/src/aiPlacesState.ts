import type {
  AiDraftInput,
  AiPlaceDraft,
  AiPlaceInterpretation,
  AiPlaceTestResult,
  AiPlaceVersion,
} from './types';

export type AiPlaceTestView = {
  interpretation: AiPlaceInterpretation | null;
  modelLatencyMs: number | null;
  testedHash: string | null;
  testMatchesDraft: boolean;
};

export function editAiDraft(draft: AiPlaceDraft, changes: AiDraftInput): AiPlaceDraft {
  return {
    ...draft,
    ...changes,
    test_state: 'untested',
    tested_hash: null,
    test_summary: null,
  };
}

export function applyAiTestResult(
  draft: AiPlaceDraft,
  result: AiPlaceTestResult,
): AiPlaceTestView {
  return {
    interpretation: result.interpretation,
    modelLatencyMs: result.modelLatencyMs,
    testedHash: result.testedHash,
    testMatchesDraft: result.testedHash === draft.config_hash,
  };
}

export function canActivateAiDraft(draft: AiPlaceDraft): boolean {
  return draft.test_state === 'passed' && draft.tested_hash === draft.config_hash;
}

export function canPublishAiDraft(draft: AiPlaceDraft, endpoint: string): boolean {
  if (!canActivateAiDraft(draft)) return false;
  try {
    return new URL(endpoint).protocol === 'https:';
  } catch {
    return false;
  }
}

export function canPublishActiveConfig(
  draft: AiPlaceDraft,
  active: Pick<AiPlaceVersion, 'config_hash'> | null,
  remote: {endpoint: string; tokenConfigured: boolean},
): boolean {
  return Boolean(
    active
    && remote.tokenConfigured
    && active.config_hash === draft.config_hash
    && canPublishAiDraft(draft, remote.endpoint),
  );
}

export function clearSecretInput(_response?: unknown): string {
  return '';
}

export function draftFromVersion(
  version: AiPlaceVersion,
  current: AiPlaceDraft,
): AiPlaceDraft {
  return {
    ...current,
    provider: version.provider,
    base_url: version.base_url,
    model: version.model,
    timeout_seconds: version.timeout_seconds,
    retry_count: version.retry_count,
    prompt_text: version.prompt_text,
    config_hash: version.config_hash,
    test_state: 'untested',
    tested_hash: null,
    test_summary: null,
  };
}
