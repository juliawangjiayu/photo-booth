import {useMemo, useRef, useState} from 'react';
import {FolderOpen, Images, LoaderCircle, Plus, UploadCloud, X} from 'lucide-react';
import {api} from './api';
import {canStartImport, supportedPhotoFiles} from './reviewWorkflow';
import type {Collection, ImportResult} from './types';

type Props = {
  collections: Collection[];
  initialFiles?: File[];
  initialMode?: 'files' | 'folder';
  onCollectionCreated: (collection: Collection) => void;
  onImported: (result: ImportResult) => void;
  onClose: () => void;
  toast: (message: string, isError?: boolean) => void;
};

const emptyResult = (): ImportResult => ({added: [], duplicates: [], errors: [], reviewIds: []});

export default function ImportDialog({
  collections,
  initialFiles = [],
  initialMode = 'files',
  onCollectionCreated,
  onImported,
  onClose,
  toast,
}: Props) {
  const [collectionId, setCollectionId] = useState('');
  const [newTitle, setNewTitle] = useState('');
  const [creating, setCreating] = useState(false);
  const [files, setFiles] = useState<File[]>(() => supportedPhotoFiles(initialFiles));
  const [importing, setImporting] = useState(false);
  const [progress, setProgress] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);
  const selectedNames = useMemo(() => files.slice(0, 5).map(file => file.name), [files]);

  const chooseFiles = (selected: FileList | null) => {
    if (!selected) return;
    const supported = supportedPhotoFiles(Array.from(selected));
    setFiles(supported);
    if (!supported.length) toast('No supported image files selected.', true);
  };

  const createCollection = async () => {
    const title = newTitle.trim();
    if (!title) return;
    setCreating(true);
    try {
      const created = await api.createCollection(title);
      const collection = {...created, count: created.count ?? 0};
      onCollectionCreated(collection);
      setCollectionId(collection.id);
      setNewTitle('');
      toast(`Collection “${collection.title}” created.`);
    } catch (error) {
      toast(String(error), true);
    } finally {
      setCreating(false);
    }
  };

  const startImport = async () => {
    if (!canStartImport(collectionId, files.length)) return;
    setImporting(true);
    const merged = emptyResult();
    const reviewIds = new Set<string>();
    try {
      for (let index = 0; index < files.length; index += 25) {
        const chunk = files.slice(index, index + 25);
        setProgress(`Importing ${index + 1}–${Math.min(index + chunk.length, files.length)} of ${files.length}`);
        const result = await api.import(chunk, collectionId);
        merged.added.push(...result.added);
        merged.duplicates.push(...result.duplicates);
        merged.errors.push(...result.errors);
        for (const id of result.reviewIds) reviewIds.add(id);
      }
      merged.reviewIds = [...reviewIds];
      const summary = [
        `${merged.added.length} new`,
        `${merged.duplicates.length} duplicate${merged.duplicates.length === 1 ? '' : 's'}`,
        merged.errors.length ? `${merged.errors.length} failed` : '',
      ].filter(Boolean).join(' · ');
      toast(`Import complete: ${summary}.`, merged.errors.length > 0);
      onImported(merged);
    } catch (error) {
      toast(String(error), true);
    } finally {
      setImporting(false);
      setProgress('');
    }
  };

  return <div className="modal-backdrop" onMouseDown={event => {
    if (event.target === event.currentTarget && !importing) onClose();
  }}>
    <section className="dialog-card import-dialog" role="dialog" aria-modal="true" aria-label="Import photos">
      <div className="modal-head">
        <div><p className="eyebrow">COLLECTION-FIRST IMPORT</p><h2>Import photos</h2><span>Choose where these photos belong before importing.</span></div>
        <button className="icon-btn" onClick={onClose} disabled={importing} aria-label="Close import"><X size={18}/></button>
      </div>

      <label className="field">Collection <span className="required">*</span>
        <select value={collectionId} onChange={event => setCollectionId(event.target.value)}>
          <option value="">Choose a Collection…</option>
          {collections.map(collection => <option key={collection.id} value={collection.id}>{collection.title}</option>)}
        </select>
      </label>
      <div className="inline-collection-create">
        <input aria-label="New Collection title" value={newTitle} onChange={event => setNewTitle(event.target.value)} placeholder="Or create a new Collection" onKeyDown={event => {
          if (event.key === 'Enter') { event.preventDefault(); void createCollection(); }
        }}/>
        <button className="outline-btn" disabled={!newTitle.trim() || creating || importing} onClick={() => void createCollection()}>
          {creating ? <LoaderCircle className="spin" size={15}/> : <Plus size={15}/>} Create
        </button>
      </div>

      <div className="import-file-box">
        <div className="import-file-summary"><Images size={20}/><div><strong>{files.length ? `${files.length} supported photo${files.length === 1 ? '' : 's'}` : 'No photos selected'}</strong><span>{selectedNames.join(' · ')}{files.length > selectedNames.length ? ` · +${files.length - selectedNames.length} more` : ''}</span></div></div>
        <div className="import-file-actions">
          <input ref={fileRef} type="file" multiple hidden accept="image/jpeg,image/png,image/webp,image/tiff,image/heic,image/heif" onChange={event => chooseFiles(event.target.files)}/>
          <input ref={folderRef} type="file" multiple hidden onChange={event => chooseFiles(event.target.files)}/>
          <button className={initialMode === 'files' ? 'subtle-btn preferred' : 'subtle-btn'} onClick={() => fileRef.current?.click()} disabled={importing}><UploadCloud size={15}/> Select photos</button>
          <button className={initialMode === 'folder' ? 'subtle-btn preferred' : 'subtle-btn'} onClick={() => {
            folderRef.current?.setAttribute('webkitdirectory', '');
            folderRef.current?.click();
          }} disabled={importing}><FolderOpen size={15}/> Select folder</button>
        </div>
      </div>

      <div className="import-dialog-footer">
        <span>{progress || (!collectionId ? 'Choose a Collection to continue.' : !files.length ? 'Select one or more photos.' : 'Ready to import and review.')}</span>
        <button className="primary-btn" disabled={!canStartImport(collectionId, files.length) || importing} onClick={() => void startImport()}>
          {importing ? <LoaderCircle className="spin" size={16}/> : <UploadCloud size={16}/>} {importing ? 'Importing…' : 'Import & review'}
        </button>
      </div>
    </section>
  </div>;
}
