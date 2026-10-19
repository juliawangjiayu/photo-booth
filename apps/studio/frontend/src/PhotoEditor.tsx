import {useEffect, useState} from 'react';
import {Compass, LoaderCircle, MapPin, Save, Search, Settings2, Sparkles, Trash2, X} from 'lucide-react';
import {api} from './api';
import {loadGoogleMaps, searchGooglePlaces} from './googleMaps';
import MapPicker from './MapPicker';
import {searchWithFallback, type PlaceSearchOutcome} from './placeSearchFlow';
import TagPicker from './TagPicker';
import {ANSWER_RADIUS_OPTIONS, completionLabel, normalizeAnswerRadius, reviewProblems} from './reviewWorkflow';
import type {AnswerRadius, Collection, Difficulty, GradeResult, Photo, PhotoReviewInput, Place, Precision} from './types';

type FormFields = Pick<Photo,
  'taken_at'|'description'|'device'|'featured'|'collectionIds'
>;

type EditorDraft = {
  form: FormFields;
  tags: string[];
  gameEnabled: boolean;
  coords: {latitude: number; longitude: number} | null;
  confirmed: boolean;
  precision: Precision;
  difficulty: Difficulty;
  answerName: string;
  answerDescription: string;
  answerRadius: AnswerRadius;
};

type ReviewContext = {
  index: number;
  total: number;
  onSavedAndNext: (photo: Photo) => void;
  onSavedAndExit: (photo: Photo) => void;
};

type Props = {
  photo: Photo;
  collections: Collection[];
  review?: ReviewContext;
  allTags: string[];
  onTagsChange: (tags: string[]) => void;
  onSaved: (photo: Photo) => void;
  onDeleted: (photoId: string) => void | Promise<void>;
  onClose: () => void;
  onConfigureMaps: () => void;
  toast: (message: string, isError?: boolean) => void;
};

const createDraft = (photo: Photo): EditorDraft => ({
  form: {
    taken_at: photo.taken_at,
    description: photo.description,
    device: photo.device,
    featured: photo.featured,
    collectionIds: [...photo.collectionIds],
  },
  tags: [...photo.tags],
  gameEnabled: Boolean(photo.guess),
  coords: photo.guess ? {latitude: photo.guess.latitude, longitude: photo.guess.longitude} : null,
  confirmed: Boolean(photo.guess?.confirmed),
  precision: photo.guess?.precision ?? 'exact',
  difficulty: photo.guess?.difficulty ?? 'medium',
  answerName: photo.guess?.answer_name ?? '',
  answerDescription: photo.guess?.answer_description ?? '',
  answerRadius: normalizeAnswerRadius(photo.guess?.answer_radius_km ?? 10),
});

export default function PhotoEditor({
  photo,
  collections,
  review,
  allTags,
  onTagsChange,
  onSaved,
  onDeleted,
  onClose,
  onConfigureMaps,
  toast,
}: Props) {
  const [draft, setDraft] = useState<EditorDraft>(() => createDraft(photo));
  const [baseline, setBaseline] = useState(() => JSON.stringify(createDraft(photo)));
  const [tagOptions, setTagOptions] = useState(allTags);
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [query, setQuery] = useState(photo.guess?.answer_name ?? '');
  const [places, setPlaces] = useState<Place[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchMessage, setSearchMessage] = useState('');
  const [mapsNeedConfiguration, setMapsNeedConfiguration] = useState(false);
  const [mapOpen, setMapOpen] = useState(false);
  const [searchOutcome, setSearchOutcome] = useState<PlaceSearchOutcome | null>(null);
  const [previewLat, setPreviewLat] = useState('');
  const [previewLng, setPreviewLng] = useState('');
  const [gradeResult, setGradeResult] = useState<GradeResult|null>(null);

  useEffect(() => {
    setTagOptions(current => {
      const merged = [...current];
      for (const tag of allTags) {
        if (!merged.some(value => value.toLocaleLowerCase() === tag.toLocaleLowerCase())) merged.push(tag);
      }
      return merged;
    });
  }, [allTags]);

  const dirty = JSON.stringify(draft) !== baseline;
  const edit = <K extends keyof FormFields>(field: K, value: FormFields[K]) => {
    setDraft(current => ({...current, form: {...current.form, [field]: value}}));
  };
  const editDraft = <K extends keyof EditorDraft>(field: K, value: EditorDraft[K]) => {
    setDraft(current => ({...current, [field]: value}));
  };

  const searchPlaces = async (mode: 'automatic' | 'forced' = 'automatic') => {
    const normalizedQuery = query.trim();
    if (normalizedQuery.length < 3) {
      setSearchMessage('Enter at least 3 characters.');
      return;
    }
    setSearching(true);
    setPlaces([]);
    setSearchOutcome(null);
    setSearchMessage('');
    setMapsNeedConfiguration(false);
    try {
      const config = await api.googleMapsBootstrap();
      if (!config.apiKey.trim()) {
        setMapsNeedConfiguration(true);
        setSearchMessage('Add a restricted Google Maps browser key before searching places. You can still enter coordinates manually.');
        return;
      }
      await loadGoogleMaps(config);
      const outcome = await searchWithFallback(
        normalizedQuery,
        searchGooglePlaces,
        async rawText => (await api.testAiPlace(rawText)).interpretation,
        mode,
      );
      setSearchOutcome(outcome);
      setPlaces(outcome.places);
      if (outcome.modelError) {
        setMapsNeedConfiguration(true);
        setSearchMessage(`Google found no direct match. AI interpretation is unavailable: ${outcome.modelError}. You can shorten the search or place the Pin manually.`);
      } else if (outcome.source === 'insufficient') {
        setSearchMessage(outcome.clarification);
      } else if (outcome.source === 'interpreted') {
        setSearchMessage(outcome.places.length
          ? `${outcome.places.length} candidate place${outcome.places.length === 1 ? '' : 's'} found from the interpreted query. Check the explanation, then select and confirm a Pin.`
          : `No Google Places candidates were found for “${outcome.queryUsed}”. Try adding a city or place the Pin manually.`);
      } else {
        setSearchMessage(`${outcome.places.length} candidate place${outcome.places.length === 1 ? '' : 's'} found. Select one, then confirm its Pin on the map.`);
      }
    } catch (error) {
      setMapsNeedConfiguration(true);
      setSearchMessage('Google Places is unavailable. Check the browser key and enabled APIs; manual coordinates still work.');
      toast(String(error), true);
    } finally {
      setSearching(false);
    }
  };

  const choosePlace = (place: Place) => {
    setDraft(current => ({
      ...current,
      answerName: place.name,
      coords: {latitude: place.latitude, longitude: place.longitude},
      confirmed: false,
    }));
    setQuery(place.name);
    setPlaces([]);
    setSearchMessage('Place selected. Open the map to check and confirm the Pin.');
  };

  const guess = draft.gameEnabled && draft.coords ? {
    ...draft.coords,
    precision: draft.precision,
    difficulty: draft.difficulty,
    answer_name: draft.answerName.trim(),
    answer_description: draft.answerDescription.trim(),
    answer_radius_km: draft.answerRadius,
    enabled: true,
    confirmed: draft.confirmed,
  } : null;
  const problems = reviewProblems({
    taken_at: draft.form.taken_at,
    device: draft.form.device,
    collectionIds: draft.form.collectionIds,
    featured: draft.form.featured,
    guess_enabled: draft.gameEnabled,
    guess,
  });

  const save = async (action: 'single'|'next'|'exit') => {
    if (problems.length) {
      toast(problems[0], true);
      return;
    }
    const device = draft.form.device;
    if (!device) {
      toast('Choose a camera/device', true);
      return;
    }
    const payload: PhotoReviewInput = {
      ...draft.form,
      device,
      tags: draft.tags,
      guess_enabled: draft.gameEnabled,
      guess,
    };
    setSaving(true);
    try {
      const updated = await api.reviewPhoto(photo.id, payload);
      const nextDraft = createDraft(updated);
      setDraft(nextDraft);
      setBaseline(JSON.stringify(nextDraft));
      const mergedTags = [...tagOptions];
      for (const tag of updated.tags) {
        if (!mergedTags.some(value => value.toLocaleLowerCase() === tag.toLocaleLowerCase())) mergedTags.push(tag);
      }
      onTagsChange(mergedTags);
      onSaved(updated);
      if (action === 'next') review?.onSavedAndNext(updated);
      else if (action === 'exit') review?.onSavedAndExit(updated);
      else toast('Saved photo details');
    } catch (error) {
      toast(String(error), true);
    } finally {
      setSaving(false);
    }
  };

  const close = () => {
    if (dirty && !window.confirm('Discard unsaved changes?')) return;
    onClose();
  };
  const configureMaps = () => {
    if (dirty && !window.confirm('Discard unsaved changes and open map settings?')) return;
    setMapOpen(false);
    onClose();
    onConfigureMaps();
  };
  const remove = async () => {
    if (!window.confirm(
      'Remove this photo from Photo Booth? Its metadata, Collection links, tags, Guess Where answer, and local previews will be removed. The archived original photo will be kept.',
    )) return;
    setRemoving(true);
    try {
      await api.deletePhoto(photo.id);
      await onDeleted(photo.id);
    } catch (error) {
      toast(String(error), true);
    } finally {
      setRemoving(false);
    }
  };
  const openMap = () => {
    if (!draft.coords && photo.exif_lat !== null && photo.exif_lng !== null) {
      editDraft('coords', {latitude: photo.exif_lat, longitude: photo.exif_lng});
    }
    setMapOpen(true);
  };
  const changeGame = (enabled: boolean) => {
    setDraft(current => ({
      ...current,
      gameEnabled: enabled,
      coords: enabled && !current.coords && photo.exif_lat !== null && photo.exif_lng !== null
        ? {latitude: photo.exif_lat, longitude: photo.exif_lng}
        : current.coords,
    }));
  };

  return <aside className="inspector">
    <div className="inspector-heading"><div><p className="eyebrow">{review ? `REVIEW PHOTO ${review.index + 1} OF ${review.total}` : 'PHOTO EDITOR'}</p><h3>Details & metadata</h3></div><button className="icon-btn" onClick={close} aria-label="Close editor"><X size={18}/></button></div>
    <div className="inspector-scroll">
      <img src={photo.previewUrl} className="inspector-photo" alt={photo.original_name}/>
      <p className="filename">{photo.original_name}</p>
      <div className="editor-fields">
        <label className="field">Date taken <span className="required">*</span><input value={draft.form.taken_at} onChange={event => edit('taken_at', event.target.value)} placeholder="YYYY-MM or YYYY-MM-DD"/><small>At least a month is required. EXIF date is kept when available.</small></label>
        <label className="field">Description <span className="optional">optional</span><textarea rows={3} value={draft.form.description} onChange={event => edit('description', event.target.value)} placeholder="A story behind this photo…"/></label>
        <label className="field">Camera / device <span className="required">*</span><select value={draft.form.device} onChange={event => edit('device', event.target.value as Photo['device'])}><option value="">Choose a device…</option><option>iPhone 6</option><option>iPhone 11</option><option>iPhone 14</option><option>Sony NEX-C3</option><option>Sony a6400</option><option>Canon G3QL</option></select><small>Filled from EXIF/TIFF when recognized.</small></label>
        <div className="field"><span>Collections <span className="required">*</span></span><div className="choice-list">{collections.length ? collections.map(collection => <label key={collection.id} className="choice"><input type="checkbox" checked={draft.form.collectionIds.includes(collection.id)} onChange={event => edit('collectionIds', event.target.checked ? [...draft.form.collectionIds, collection.id] : draft.form.collectionIds.filter(id => id !== collection.id))}/>{collection.title}</label>) : <span className="muted small">Create a Collection first.</span>}</div></div>
        <div className="field"><span>Tags <span className="optional">optional</span></span><TagPicker options={tagOptions} selected={draft.tags} onOptionsChange={setTagOptions} onChange={tags => editDraft('tags', tags)}/></div>
        <label className="toggle-row"><span>Feature on home page</span><input type="checkbox" checked={draft.form.featured} onChange={event => edit('featured', event.target.checked)}/></label>
        <div className="editor-section-divider"/>
        <div className="game-intro"><Compass size={20}/><div><strong>Add this photo to Guess Where?</strong><p>A checked photo needs a named, confirmed map Pin.</p></div></div>
        <label className="toggle-row"><span>Include in Guess Where</span><input type="checkbox" checked={draft.gameEnabled} onChange={event => changeGame(event.target.checked)}/></label>
        {draft.gameEnabled && <><div className="coord-display"><div><span>ANSWER COORDINATES</span><strong>{draft.coords ? `${draft.coords.latitude.toFixed(5)}, ${draft.coords.longitude.toFixed(5)}` : 'Not set'}</strong></div><span className={`status-pill ${draft.confirmed ? 'positive' : 'warning'}`}>{draft.confirmed ? 'Confirmed' : 'Needs confirmation'}</span></div>
          <label className="field">Canonical place name <span className="required">*</span><input value={draft.answerName} onChange={event => editDraft('answerName', event.target.value)} placeholder="Tokyo / Chaoyang District"/></label>
          <label className="field">Place description <span className="optional">optional</span><textarea rows={3} value={draft.answerDescription} onChange={event => editDraft('answerDescription', event.target.value)} placeholder="Near Tokyo Bay, exact district uncertain"/></label>
          <div className="field"><span>Find coordinates from a place description</span><small>Google Places searches first. When it finds nothing, DeepSeek may rewrite the description once; no result is accepted until you confirm the Pin.</small><div className="search-row"><input value={query} placeholder="Search city, district or landmark" onChange={event => {setQuery(event.target.value); setPlaces([]); setSearchOutcome(null); setSearchMessage(''); setMapsNeedConfiguration(false);}} onKeyDown={event => {if (event.key === 'Enter') {event.preventDefault(); void searchPlaces();}}}/><button className="subtle-btn" onClick={() => void searchPlaces()} disabled={searching || query.trim().length < 3} title="Search answer place">{searching ? <LoaderCircle className="spin" size={16}/> : <Search size={16}/>}<span>Search</span></button></div>{searchOutcome?.source === 'interpreted' && <div className="place-interpretation"><span><Sparkles size={13}/> Searched as</span><strong>{searchOutcome.queryUsed}</strong>{searchOutcome.interpretation && searchOutcome.interpretation.uncertainty.length > 0 && <small>Uncertainty preserved: {searchOutcome.interpretation.uncertainty.join(' · ')}</small>}</div>}{searchMessage && <small className="place-search-message" aria-live="polite">{searchMessage}</small>}{mapsNeedConfiguration && <button className="inline-action" onClick={configureMaps}><Settings2 size={13}/> Open AI & Places settings</button>}{places.length > 0 && searchOutcome?.source === 'direct' && <button className="inline-action reinterpret-action" disabled={searching} onClick={() => void searchPlaces('forced')}><Sparkles size={13}/> Try another interpretation</button>}{places.length > 0 && <div className="place-results">{places.map(place => <button key={place.id || `${place.latitude}:${place.longitude}`} onClick={() => choosePlace(place)}><MapPin size={14}/><span><b>{place.name}</b>{place.formattedAddress && <small>{place.formattedAddress}</small>}</span></button>)}</div>}</div>
          <button className="outline-btn full" onClick={openMap}><MapPin size={16}/> {draft.confirmed ? 'Edit confirmed Pin' : 'Open map & confirm Pin'}</button>
          <label className="field">Position precision<select value={draft.precision} onChange={event => editDraft('precision', event.target.value as Precision)}><option value="exact">Exact GPS</option><option value="approximate">Approximate location</option></select></label>
          <label className="field">Accepted answer radius<select value={draft.answerRadius} onChange={event => editDraft('answerRadius', Number(event.target.value) as AnswerRadius)}>{ANSWER_RADIUS_OPTIONS.map(radius => <option value={radius} key={radius}>{radius} km</option>)}</select><small>The map shows this private area so you can check whether the Pin and tolerance match the photo.</small></label>
          <label className="field">Difficulty<select value={draft.difficulty} onChange={event => editDraft('difficulty', event.target.value as Difficulty)}><option value="easy">Easy — obvious landmarks</option><option value="medium">Medium — some clues</option><option value="hard">Hard — few clues</option></select></label>
          {photo.guess?.confirmed && <div className="hint-card"><strong>Test the Pin grading rules</strong><p className="small muted">This local preview uses the same distance and answer-radius rules as the game.</p><div className="two-col"><label className="field">Test latitude<input type="number" step="any" value={previewLat} onChange={event => setPreviewLat(event.target.value)}/></label><label className="field">Test longitude<input type="number" step="any" value={previewLng} onChange={event => setPreviewLng(event.target.value)}/></label></div><button className="subtle-btn" disabled={!previewLat || !previewLng} onClick={async () => {try {setGradeResult(await api.gradePin(photo.id, Number(previewLat), Number(previewLng)));} catch (error) {toast(String(error), true);}}}><MapPin size={13}/> Grade Pin</button>{gradeResult && <p><b>{gradeResult.result.toUpperCase()} · {gradeResult.score.toLocaleString()} / 5,000</b><br/>{gradeResult.explanation}</p>}</div>}
          <div className="hint-card">True coordinates remain in your private local SQLite database and are never included in the public export.</div>
        </>}
      </div>
    </div>
    <div className={`inspector-footer editor-footer ${review ? 'review-actions' : ''}`}>
      <span className={`save-tip ${problems.length ? 'has-problem' : ''}`}>{problems[0] ?? 'All required fields are complete.'}</span>
      <div className="editor-footer-actions">
        <button className="outline-btn danger" onClick={() => void remove()} disabled={saving || removing}><Trash2 size={15}/>{removing ? 'Removing…' : 'Remove photo'}</button>
        {!review && <button className="primary-btn" onClick={() => void save('single')} disabled={saving || removing}><Save size={15}/>{saving && <LoaderCircle className="spin" size={15}/>} Save changes</button>}
      </div>
      {review && <div className="review-buttons"><button className="outline-btn" onClick={() => void save('exit')} disabled={saving || removing}>{completionLabel('exit', review.index, review.total)}</button><button className="primary-btn" onClick={() => void save('next')} disabled={saving || removing}><Save size={15}/>{saving && <LoaderCircle className="spin" size={15}/>} {completionLabel('next', review.index, review.total)}</button></div>}
    </div>
    {mapOpen && <MapPicker initial={draft.coords ?? (photo.exif_lat !== null && photo.exif_lng !== null ? {latitude: photo.exif_lat, longitude: photo.exif_lng} : null)} radiusKm={draft.answerRadius} onClose={() => setMapOpen(false)} onConfigure={configureMaps} onConfirm={point => {setDraft(current => ({...current, coords: point, confirmed: true})); setMapOpen(false); toast('Answer Pin confirmed. Save this photo to persist it.');}}/>}
  </aside>;
}
