import {useCallback, useEffect, useMemo, useState} from 'react';
import {
  Check,
  CheckCircle2,
  Clock3,
  CloudOff,
  ExternalLink,
  KeyRound,
  LoaderCircle,
  MapPinned,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import {api} from './api';
import {canActivateAiDraft, canPublishActiveConfig, clearSecretInput, editAiDraft} from './aiPlacesState';
import {loadGoogleMaps, searchGooglePlaces} from './googleMaps';
import type {
  AiDraftInput,
  AiPlaceConfig,
  AiPlaceInterpretation,
  AiPlaceVersion,
  GoogleMapsConfig,
  Place,
} from './types';

type Tab = 'model' | 'test' | 'versions';
type Props = {notify: (message: string, error?: boolean) => void};

const blankMaps: GoogleMapsConfig = {
  apiKeyConfigured: false,
  apiKeyMask: '',
  mapId: 'DEMO_MAP_ID',
};

function dateLabel(value: string | null): string {
  if (!value) return 'Not published';
  const parsed = new Date(value.endsWith('Z') ? value : `${value}Z`);
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleString();
}

export default function AiPlacesPage({notify}: Props) {
  const [tab, setTab] = useState<Tab>('model');
  const [config, setConfig] = useState<AiPlaceConfig | null>(null);
  const [maps, setMaps] = useState<GoogleMapsConfig>(blankMaps);
  const [versions, setVersions] = useState<AiPlaceVersion[]>([]);
  const [deepSeekKey, setDeepSeekKey] = useState('');
  const [googleKey, setGoogleKey] = useState('');
  const [publisherToken, setPublisherToken] = useState('');
  const [remoteEndpoint, setRemoteEndpoint] = useState('');
  const [remoteDirty, setRemoteDirty] = useState(false);
  const [remoteError, setRemoteError] = useState('');
  const [draftDirty, setDraftDirty] = useState(false);
  const [mapsDirty, setMapsDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [example, setExample] = useState('香港 太平山顶 缆车站');
  const [interpretation, setInterpretation] = useState<AiPlaceInterpretation | null>(null);
  const [modelLatency, setModelLatency] = useState<number | null>(null);
  const [placesLatency, setPlacesLatency] = useState<number | null>(null);
  const [places, setPlaces] = useState<Place[]>([]);
  const [placesError, setPlacesError] = useState('');

  const reload = useCallback(async () => {
    const [nextConfig, nextMaps, nextVersions] = await Promise.all([
      api.aiPlacesConfig(),
      api.googleMapsConfig(),
      api.aiPlaceVersions(),
    ]);
    setConfig(nextConfig);
    setRemoteEndpoint(nextConfig.remote.endpoint);
    setMaps(nextMaps);
    setVersions(nextVersions);
    setDraftDirty(false);
    setMapsDirty(false);
    setRemoteDirty(false);
  }, []);

  useEffect(() => {
    void reload().catch(error => notify(String(error), true));
  }, [notify, reload]);

  const editDraft = (changes: AiDraftInput) => {
    setConfig(current => current ? {...current, draft: editAiDraft(current.draft, changes)} : current);
    setDraftDirty(true);
    setInterpretation(null);
    setPlaces([]);
    setStatus('Draft changed. Save and test this exact configuration before activating it.');
  };

  const saveDraft = async () => {
    if (!config) return;
    setBusy(true);
    try {
      const draft = await api.updateAiPlacesDraft({
        provider: config.draft.provider,
        base_url: config.draft.base_url,
        model: config.draft.model,
        timeout_seconds: config.draft.timeout_seconds,
        retry_count: config.draft.retry_count,
        prompt_text: config.draft.prompt_text,
      });
      setConfig(current => current ? {...current, draft} : current);
      setDraftDirty(false);
      setStatus('Draft saved locally. Run a test before activating.');
      notify('AI place draft saved.');
    } catch (error) {
      notify(String(error), true);
    } finally {
      setBusy(false);
    }
  };

  const replaceDeepSeekKey = async () => {
    if (!deepSeekKey.trim()) {
      notify('Paste a replacement DeepSeek API key first.', true);
      return;
    }
    setBusy(true);
    try {
      const secret = await api.updateDeepSeekSecret({api_key: deepSeekKey.trim()});
      setDeepSeekKey(clearSecretInput(secret));
      await reload();
      setStatus('DeepSeek key replaced in macOS Keychain. Test the configuration again.');
      notify('DeepSeek key saved in macOS Keychain.');
    } catch (error) {
      setDeepSeekKey('');
      notify(String(error), true);
    } finally {
      setBusy(false);
    }
  };

  const clearDeepSeekKey = async () => {
    if (!window.confirm('Remove the DeepSeek API key from macOS Keychain?')) return;
    setBusy(true);
    try {
      await api.updateDeepSeekSecret({clear: true});
      setDeepSeekKey('');
      await reload();
      setStatus('DeepSeek key removed.');
      notify('DeepSeek key removed.');
    } catch (error) {
      notify(String(error), true);
    } finally {
      setBusy(false);
    }
  };

  const saveMaps = async () => {
    setBusy(true);
    try {
      const saved = await api.updateGoogleMapsConfig({
        map_id: maps.mapId,
        api_key: googleKey.trim() || undefined,
      });
      setMaps(saved);
      setGoogleKey('');
      setMapsDirty(false);
      setStatus('Google Maps configuration saved. Reload Photo Booth after replacing the browser key.');
      notify('Google Maps configuration saved.');
    } catch (error) {
      setGoogleKey('');
      notify(String(error), true);
    } finally {
      setBusy(false);
    }
  };

  const clearGoogleKey = async () => {
    if (!window.confirm('Remove the Google Maps browser key from macOS Keychain?')) return;
    setBusy(true);
    try {
      const saved = await api.updateGoogleMapsConfig({map_id: maps.mapId, clear_api_key: true});
      setMaps(saved);
      setGoogleKey('');
      setMapsDirty(false);
      setStatus('Google Maps key removed.');
      notify('Google Maps key removed.');
    } catch (error) {
      notify(String(error), true);
    } finally {
      setBusy(false);
    }
  };

  const runTest = async () => {
    if (!example.trim() || draftDirty) return;
    setBusy(true);
    setPlaces([]);
    setPlacesError('');
    setInterpretation(null);
    setStatus('Asking DeepSeek to interpret the location…');
    try {
      const result = await api.testAiPlace(example.trim());
      setInterpretation(result.interpretation);
      setModelLatency(result.modelLatencyMs);
      const refreshed = await api.aiPlacesConfig();
      setConfig(refreshed);
      if (result.interpretation.status === 'insufficient' || !result.interpretation.normalized_query) {
        setPlacesLatency(null);
        setStatus('DeepSeek needs a more specific description. No Places request was sent.');
        return;
      }
      setStatus('Interpretation complete. Searching Google Places…');
      const bootstrap = await api.googleMapsBootstrap();
      await loadGoogleMaps(bootstrap);
      const started = performance.now();
      const candidates = await searchGooglePlaces(result.interpretation.normalized_query);
      setPlacesLatency(Math.round(performance.now() - started));
      setPlaces(candidates);
      setStatus(candidates.length
        ? `Test passed. Google returned ${candidates.length} candidate${candidates.length === 1 ? '' : 's'}.`
        : 'DeepSeek test passed, but Google Places returned no candidates.');
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (interpretation) setPlacesError(message);
      setStatus(message);
      notify(message, true);
    } finally {
      setBusy(false);
    }
  };

  const activate = async () => {
    setBusy(true);
    try {
      const activated = await api.activateAiPlaces();
      await reload();
      setStatus(`Version ${activated.version} is now the local active configuration.`);
      notify(`AI place configuration v${activated.version} activated.`);
    } catch (error) {
      notify(String(error), true);
    } finally {
      setBusy(false);
    }
  };

  const restore = async (version: number) => {
    setBusy(true);
    try {
      const draft = await api.restoreAiPlaceVersion(version);
      setConfig(current => current ? {...current, draft} : current);
      setDraftDirty(false);
      setTab('model');
      setStatus(`Version ${version} was copied into the editable draft. Test it before activating.`);
      notify(`Version ${version} restored as a draft.`);
    } catch (error) {
      notify(String(error), true);
    } finally {
      setBusy(false);
    }
  };

  const saveRemote = async () => {
    setBusy(true);
    try {
      const remote = await api.updateAiPlacesRemote({
        endpoint: remoteEndpoint,
        publisher_token: publisherToken.trim() || undefined,
      });
      setConfig(current => current ? {...current, remote} : current);
      setRemoteEndpoint(remote.endpoint);
      setPublisherToken('');
      setRemoteDirty(false);
      setRemoteError('');
      setStatus(remote.endpoint && remote.tokenConfigured
        ? 'Website publishing connection saved.'
        : 'Remote publishing remains disconnected. Local activation still works.');
      notify('Remote publishing settings saved.');
    } catch (error) {
      setPublisherToken('');
      notify(String(error), true);
    } finally {
      setBusy(false);
    }
  };

  const clearPublisherToken = async () => {
    if (!window.confirm('Remove the website publisher token from macOS Keychain?')) return;
    setBusy(true);
    try {
      const remote = await api.updateAiPlacesRemote({clear_token: true});
      setConfig(current => current ? {...current, remote} : current);
      setRemoteEndpoint(remote.endpoint);
      setPublisherToken('');
      setRemoteDirty(false);
      setStatus('Website publisher token removed.');
      notify('Publisher token removed.');
    } catch (error) {
      notify(String(error), true);
    } finally {
      setBusy(false);
    }
  };

  const publishRemote = async (rotateDeepSeekKey: boolean) => {
    if (rotateDeepSeekKey && !window.confirm('Replace the production DeepSeek key as part of this release? Ordinary releases do not resend it.')) return;
    setBusy(true);
    setRemoteError('');
    try {
      const receipt = await api.publishAiPlaces(rotateDeepSeekKey);
      await reload();
      setStatus(`Version ${receipt.version} published to the website. Receipt ${receipt.receipt}.`);
      notify(`AI place configuration v${receipt.version} published.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setRemoteError(message);
      setStatus(`Remote publication failed: ${message}`);
      notify(message, true);
    } finally {
      setBusy(false);
    }
  };

  const testReady = Boolean(config && !draftDirty && example.trim() && config.secret.configured);
  const activationReady = Boolean(config && !draftDirty && canActivateAiDraft(config.draft));
  const activeVersion = config?.active ?? versions.find(item => item.lifecycle_state === 'active') ?? null;
  const publishReady = Boolean(config && !draftDirty && canPublishActiveConfig(config.draft, activeVersion, config.remote));
  const remoteConnected = Boolean(config?.remote.endpoint && config.remote.tokenConfigured);
  const remoteLive = Boolean(activeVersion && config?.remote.lastPublishedVersion === activeVersion.version);
  const draftHash = useMemo(() => config?.draft.config_hash.slice(0, 10) ?? '—', [config]);

  if (!config) {
    return <section className="ai-loading" aria-live="polite"><LoaderCircle className="spin" size={20}/> Loading local configuration…</section>;
  }

  return <section className="ai-places-page">
    <div className="ai-tabs" role="tablist" aria-label="AI & Places sections">
      <button role="tab" aria-selected={tab === 'model'} className={tab === 'model' ? 'active' : ''} onClick={() => setTab('model')}><Sparkles size={16}/> Model & prompt</button>
      <button role="tab" aria-selected={tab === 'test'} className={tab === 'test' ? 'active' : ''} onClick={() => setTab('test')}><Search size={16}/> Test configuration</button>
      <button role="tab" aria-selected={tab === 'versions'} className={tab === 'versions' ? 'active' : ''} onClick={() => setTab('versions')}><Clock3 size={16}/> Published versions</button>
    </div>
    <p className="ai-live-status" aria-live="polite">{status || 'Secrets stay in macOS Keychain; only non-secret configuration is versioned.'}</p>

    {tab === 'model' && <div className="ai-config-layout">
      <div className="ai-card ai-main-card">
        <div className="ai-card-head"><div><span className="ai-kicker">PLACE INTERPRETER</span><h2>DeepSeek model & prompt</h2></div><span className={`status-pill ${canActivateAiDraft(config.draft) ? 'positive' : 'warning'}`}>{canActivateAiDraft(config.draft) ? <CheckCircle2 size={14}/> : <RefreshCw size={14}/>} {canActivateAiDraft(config.draft) ? 'Tested' : 'Needs test'}</span></div>
        <div className="ai-form-grid">
          <label className="field">Provider<input value={config.draft.provider} onChange={event => editDraft({provider: event.target.value})}/></label>
          <label className="field">Model<input value={config.draft.model} onChange={event => editDraft({model: event.target.value})}/></label>
          <label className="field ai-span-two">API base URL<input inputMode="url" value={config.draft.base_url} onChange={event => editDraft({base_url: event.target.value})}/><small>HTTPS is enforced by the backend.</small></label>
          <label className="field">Timeout (seconds)<input type="number" min="1" max="120" value={config.draft.timeout_seconds} onChange={event => editDraft({timeout_seconds: Number(event.target.value)})}/></label>
          <label className="field">Retry count<input type="number" min="0" max="5" value={config.draft.retry_count} onChange={event => editDraft({retry_count: Number(event.target.value)})}/></label>
          <label className="field ai-span-two">Place interpretation prompt<textarea rows={10} value={config.draft.prompt_text} onChange={event => editDraft({prompt_text: event.target.value})}/><small>A locked safety envelope is added by Photo Booth. The model never receives the private answer Pin, radius, or score.</small></label>
        </div>
        <div className="ai-action-row"><button className="primary-btn" disabled={busy || !draftDirty} onClick={() => void saveDraft()}><Save size={15}/> Save draft</button><span>Draft hash <code>{draftHash}</code></span></div>
      </div>

      <aside className="ai-side-stack">
        <div className="ai-card">
          <div className="ai-card-head compact"><div><span className="ai-kicker">PRIVATE SECRET</span><h3>DeepSeek API key</h3></div><KeyRound size={19}/></div>
          <p>{config.secret.configured ? `Configured · ${config.secret.mask}` : 'No key configured'}. The full value is never returned to the browser.</p>
          <label className="field">Replace key<input type="password" autoComplete="new-password" value={deepSeekKey} onChange={event => setDeepSeekKey(event.target.value)} placeholder={config.secret.configured ? 'Paste only to replace' : 'Paste DeepSeek API key'}/></label>
          <div className="ai-action-row"><button className="outline-btn" disabled={busy || !deepSeekKey.trim()} onClick={() => void replaceDeepSeekKey()}>Save key</button>{config.secret.configured && <button className="text-danger" onClick={() => void clearDeepSeekKey()}>Remove</button>}</div>
        </div>
        <div className="ai-card">
          <div className="ai-card-head compact"><div><span className="ai-kicker">MAP & SEARCH</span><h3>Google Maps Platform</h3></div><MapPinned size={19}/></div>
          <p>{maps.apiKeyConfigured ? `Browser key configured · ${maps.apiKeyMask}` : 'No browser key configured'}.</p>
          <label className="field">Replace browser key<input type="password" autoComplete="new-password" value={googleKey} onChange={event => {setGoogleKey(event.target.value); setMapsDirty(true);}} placeholder={maps.apiKeyConfigured ? 'Leave blank to keep current key' : 'Paste restricted browser key'}/></label>
          <label className="field">Google Map ID<input value={maps.mapId} onChange={event => {setMaps(current => ({...current, mapId: event.target.value})); setMapsDirty(true);}}/></label>
          <div className="ai-action-row"><button className="outline-btn" disabled={busy || !mapsDirty} onClick={() => void saveMaps()}>Save Maps</button>{maps.apiKeyConfigured && <button className="text-danger" onClick={() => void clearGoogleKey()}>Remove key</button>}</div>
        </div>
      </aside>
    </div>}

    {tab === 'test' && <div className="ai-test-layout">
      <div className="ai-card ai-test-controls">
        <span className="ai-kicker">END-TO-END CHECK</span><h2>Try a real place description</h2>
        <p>Photo Booth asks DeepSeek for a search query, then sends only that query to Google Places. Testing marks this exact draft hash as eligible for activation.</p>
        <label className="field">Location description<textarea rows={4} value={example} onChange={event => setExample(event.target.value)} placeholder="例如：香港 太平山顶 缆车站"/></label>
        {draftDirty && <div className="ai-warning">Save the edited draft before testing.</div>}
        {!config.secret.configured && <div className="ai-warning">Configure a DeepSeek API key on Model & prompt first.</div>}
        <button className="primary-btn" disabled={busy || !testReady} onClick={() => void runTest()}>{busy ? <LoaderCircle className="spin" size={16}/> : <Sparkles size={16}/>} Run DeepSeek + Google test</button>
      </div>
      <div className="ai-test-results">
        <div className="ai-card">
          <div className="ai-card-head compact"><div><span className="ai-kicker">STEP 1</span><h3>DeepSeek interpretation</h3></div>{modelLatency !== null && <span className="latency">{modelLatency} ms</span>}</div>
          {interpretation ? <div className="interpretation-grid"><div><span>Status</span><strong>{interpretation.status}</strong></div><div><span>Confidence</span><strong>{Math.round(interpretation.confidence * 100)}%</strong></div><div className="wide"><span>Google query</span><strong>{interpretation.normalized_query || 'No query sent'}</strong></div>{interpretation.clarification && <div className="wide"><span>Clarification</span><strong>{interpretation.clarification}</strong></div>}{interpretation.uncertainty.length > 0 && <div className="wide"><span>Uncertainty kept</span><strong>{interpretation.uncertainty.join(' · ')}</strong></div>}</div> : <p className="ai-empty">Run a test to inspect the structured interpretation.</p>}
        </div>
        <div className="ai-card">
          <div className="ai-card-head compact"><div><span className="ai-kicker">STEP 2</span><h3>Google Places candidates</h3></div>{placesLatency !== null && <span className="latency">{placesLatency} ms</span>}</div>
          {placesError && <div className="ai-warning">{placesError}</div>}
          {places.length ? <div className="candidate-list">{places.map(place => <div key={place.id || `${place.latitude}-${place.longitude}`}><MapPinned size={17}/><span><strong>{place.name}</strong><small>{place.formattedAddress || [place.city, place.region, place.country].filter(Boolean).join(', ')}</small></span><code>{place.latitude.toFixed(4)}, {place.longitude.toFixed(4)}</code></div>)}</div> : <p className="ai-empty">No candidates to show yet.</p>}
        </div>
        <div className="ai-card ai-activation-card"><div><ShieldCheck size={20}/><span><strong>Local activation</strong><small>{activationReady ? 'This exact draft has passed a live test.' : 'A successful test of the exact current draft is required.'}</small></span></div><button className="primary-btn" disabled={busy || !activationReady} onClick={() => void activate()}><Check size={15}/> Activate as new version</button></div>
      </div>
    </div>}

    {tab === 'versions' && <div className="ai-version-layout">
      <div className="ai-status-grid">
        <div className="ai-card status-card"><span className="status-icon good"><CheckCircle2 size={18}/></span><div><span>LOCAL ACTIVE</span><strong>{activeVersion ? `Version ${activeVersion.version}` : 'No active version'}</strong><small>{activeVersion ? `${activeVersion.model} · ${dateLabel(activeVersion.activated_at)}` : 'Test and activate a draft first.'}</small></div></div>
        <div className="ai-card status-card"><span className={`status-icon ${remoteLive ? 'good' : remoteError ? 'error-icon' : 'muted-icon'}`}>{remoteLive ? <CheckCircle2 size={18}/> : <CloudOff size={18}/>}</span><div><span>REMOTE WEBSITE</span><strong>{remoteLive ? `Version ${config.remote.lastPublishedVersion} live` : remoteError ? 'Publish failed' : remoteConnected ? 'Connected · not current' : 'Disconnected'}</strong><small>{remoteLive ? `${dateLabel(config.remote.lastPublishedAt)} · receipt ${config.remote.lastReceipt}` : remoteError || (remoteConnected ? 'Publish the tested local active version when ready.' : 'Add an HTTPS endpoint and publisher token below.')}</small></div></div>
      </div>
      <div className="ai-card version-card"><div className="ai-card-head"><div><span className="ai-kicker">IMMUTABLE HISTORY</span><h2>Local activated versions</h2></div><button className="outline-btn" disabled={busy} onClick={() => void reload()}><RefreshCw size={14}/> Refresh</button></div>
        {versions.length ? <div className="version-list">{versions.map(version => <article key={version.version}><div className="version-number">v{version.version}</div><div className="version-details"><div><strong>{version.model}</strong><span className={`status-pill ${version.lifecycle_state === 'active' ? 'positive' : ''}`}>{version.lifecycle_state}</span></div><p>{version.test_summary || 'Test passed'}</p><small>{dateLabel(version.activated_at)} · <code>{version.config_hash.slice(0, 10)}</code></small></div><button className="outline-btn" disabled={busy} onClick={() => void restore(version.version)}><RotateCcw size={14}/> Restore as draft</button></article>)}</div> : <p className="ai-empty">No versions have been activated yet.</p>}
      </div>
      <div className="ai-card remote-config-card"><div className="ai-card-head"><div><span className="ai-kicker">SECURE CONNECTION</span><h2>Website publishing endpoint</h2></div><ExternalLink size={19}/></div><p>The public website receiver is optional. The endpoint is stored in SQLite; the publisher token stays in macOS Keychain and is never shown again.</p><div className="remote-form"><label className="field">HTTPS website endpoint<input inputMode="url" value={remoteEndpoint} onChange={event => {setRemoteEndpoint(event.target.value); setRemoteDirty(true);}} placeholder="https://photos.example.com"/><small>Photo Booth appends <code>/api/admin/ai-place-config</code>.</small></label><label className="field">Replace publisher token <span className="optional">{config.remote.tokenConfigured ? `configured · ${config.remote.tokenMask}` : 'not configured'}</span><input type="password" autoComplete="new-password" value={publisherToken} onChange={event => {setPublisherToken(event.target.value); setRemoteDirty(true);}} placeholder={config.remote.tokenConfigured ? 'Paste only to replace' : 'Paste publisher token'}/></label></div><div className="ai-action-row"><button className="outline-btn" disabled={busy || !remoteDirty} onClick={() => void saveRemote()}><Save size={14}/> Save connection</button>{config.remote.tokenConfigured && <button className="text-danger" onClick={() => void clearPublisherToken()}>Remove token</button>}</div></div>
      <div className="ai-card future-publish"><div><ExternalLink size={19}/><span><strong>{publishReady ? `Version ${activeVersion?.version} is ready to publish` : 'Remote release is locked'}</strong><small>{publishReady ? 'Only versioned model and prompt settings are sent. Private photo answers and scoring data are excluded.' : 'Connect the website, then test and activate the exact current draft.'}</small></span></div><div className="publish-button-stack"><button className="primary-btn" disabled={busy || !publishReady} onClick={() => void publishRemote(false)}>Publish to website</button><button className="outline-btn" disabled={busy || !publishReady || !config.secret.configured} onClick={() => void publishRemote(true)}>Publish + replace production key</button></div></div>
    </div>}
  </section>;
}
