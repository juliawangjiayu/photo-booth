import { useCallback, useEffect, useRef, useState } from 'react';
import { Album, ArrowDownUp, ArrowRight, Check, CheckCircle2, CloudUpload, Compass, FolderHeart, Github, Grid2X2, Image, Images, Info, LayoutGrid, MapPinned, Pencil, Plus, Search, Settings2, ShieldCheck, SlidersHorizontal, Sparkles, Trash2, UploadCloud, X } from 'lucide-react';
import { api } from './api';
import AiPlacesPage from './AiPlacesPage';
import { startConnectionMonitor } from './connection';
import ImportDialog from './ImportDialog';
import { filterLibraryPhotos } from './libraryFilters';
import PhotoEditor from './PhotoEditor';
import TagPicker from './TagPicker';
import { advanceReviewProgress, normalizeReviewQueue, reconcileReviewProgress, reviewQueueFrom } from './reviewWorkflow';
import type { Collection, ImportResult, Photo, PublishPreview, Settings, Stats } from './types';

type Page = 'library'|'collections'|'game'|'ai-places'|'publish'|'settings';
const apiOrigin = '';
function resolveImage(uri:string){return apiOrigin+uri;}
const emptyStats: Stats={photos:0,ready:0,needReview:0,gamePool:0,collections:0};
const emptySettings:Settings={web_root:''};

export default function App(){
  const [page,setPage]=useState<Page>('library');
  const [photos,setPhotos]=useState<Photo[]>([]);
  const [collections,setCollections]=useState<Collection[]>([]);
  const [stats,setStats]=useState<Stats>(emptyStats);
  const [settings,setSettings]=useState<Settings>(emptySettings);
  const [allTags,setAllTags]=useState<string[]>([]);
  const [activeId,setActiveId]=useState<string|null>(null);
  const [selected,setSelected]=useState<string[]>([]);
  const [search,setSearch]=useState('');
  const [filter,setFilter]=useState('all');
  const [sort,setSort]=useState<'new'|'date'>('new');
  const [busy,setBusy]=useState(false);
  const [dragging,setDragging]=useState(false);
  const [toast,setToast]=useState<{message:string;error:boolean}|null>(null);
  const [connected,setConnected]=useState(true);
  const [collectionTitle,setCollectionTitle]=useState('');
  const [collectionDesc,setCollectionDesc]=useState('');
  const [newCollection,setNewCollection]=useState(false);
  const [editingCollection,setEditingCollection]=useState<string|null>(null);
  const [bulkCollection,setBulkCollection]=useState('');
  const [bulkTags,setBulkTags]=useState<string[]>([]);
  const [preview,setPreview]=useState<PublishPreview|null>(null);
  const [commitMessage,setCommitMessage]=useState('Update photography collection');
  const [exported,setExported]=useState(false);
  const [importOpen,setImportOpen]=useState(false);
  const [importMode,setImportMode]=useState<'files'|'folder'>('files');
  const [droppedFiles,setDroppedFiles]=useState<File[]>([]);
  const [reviewQueue,setReviewQueue]=useState<string[]>([]);
  const [reviewIndex,setReviewIndex]=useState(0);
  const reviewQueueRef=useRef(reviewQueue);
  const reviewIndexRef=useRef(reviewIndex);
  reviewQueueRef.current=reviewQueue;
  reviewIndexRef.current=reviewIndex;

  const notify=useCallback((message:string,error=false)=>{setToast({message,error});setTimeout(()=>setToast(null),5500);},[]);
  const resetReview=()=>{reviewQueueRef.current=[];reviewIndexRef.current=0;setReviewQueue([]);setReviewIndex(0);setActiveId(null);};
  const refresh=useCallback(async(quiet=false)=>{
    try{
      const [p,c,s,t]=await Promise.all([api.photos(),api.collections(),api.stats(),api.tags()]);
      setPhotos(p);setCollections(c);setStats(s);setAllTags(t.tags);setConnected(true);
      if(reviewQueueRef.current.length){
        const progress=reconcileReviewProgress(reviewQueueRef.current,reviewIndexRef.current,p);
        reviewQueueRef.current=progress.ids;reviewIndexRef.current=progress.index;
        setReviewQueue(progress.ids);setReviewIndex(progress.index);setActiveId(progress.ids[progress.index]??null);
      }
    }catch(e){setConnected(false);if(!quiet)notify('Local backend unavailable. Retrying automatically…',true);}
  },[notify]);
  useEffect(()=>{const stop=startConnectionMonitor(refresh);void api.settings().then(setSettings).catch(()=>{});return stop;},[refresh]);
  useEffect(()=>{if(page==='publish')void api.publishPreview().then(setPreview).catch(e=>notify(String(e),true));},[page,photos,notify]);
  const active=photos.find(p=>p.id===(reviewQueue[reviewIndex]??activeId))||null;
  const visible=filterLibraryPhotos(photos,filter).filter(p=>{
    const text=[p.original_name,p.description,p.device,...p.tags].join(' ').toLowerCase();
    if(search&& !text.includes(search.toLowerCase()))return false;
    if(filter==='game'&&!p.guess)return false;
    if(filter==='needs-review'&&p.status!=='draft')return false;
    if(filter.startsWith('collection:')&&!p.collectionIds.includes(filter.slice(11)))return false;
    if(page==='game'&&!p.guess)return false;
    return true;
  }).sort((a,b)=>sort==='date'?b.taken_at.localeCompare(a.taken_at):b.created_at.localeCompare(a.created_at)||b.id.localeCompare(a.id));

  const openImport=(mode:'files'|'folder',files:File[]=[] )=>{setImportMode(mode);setDroppedFiles(files);setImportOpen(true);};
  const finishImport=async(result:ImportResult)=>{
    setImportOpen(false);setPage('library');setFilter('all');
    try{
      const current=await api.photos();
      setPhotos(current);
      const queue=normalizeReviewQueue(result.reviewIds,current);
      reviewQueueRef.current=queue;reviewIndexRef.current=0;
      setReviewQueue(queue);setReviewIndex(0);setActiveId(queue[0]??null);
      await refresh(true);
      if(!queue.length)notify('Import finished. No unreviewed photos were added to the queue.');
    }catch(e){notify(String(e),true);}
  };
  const onSaved=(p:Photo)=>{setPhotos(old=>old.map(x=>x.id===p.id?p:x));};
  const onDeleted=async(photoId:string)=>{
    const remainingPhotos=photos.filter(photo=>photo.id!==photoId);
    setPhotos(remainingPhotos);
    setSelected(current=>current.filter(id=>id!==photoId));
    if(reviewQueueRef.current.length){
      const progress=reconcileReviewProgress(reviewQueueRef.current,reviewIndexRef.current,remainingPhotos);
      reviewQueueRef.current=progress.ids;reviewIndexRef.current=progress.index;
      setReviewQueue(progress.ids);setReviewIndex(progress.index);setActiveId(progress.ids[progress.index]??null);
    }else{
      setActiveId(null);
    }
    notify('Photo removed from Photo Booth. Archived original kept.');
    await refresh(true);
  };
  const savedAndNext=async()=>{
    try{
      const [current,c,s,t]=await Promise.all([api.photos(),api.collections(),api.stats(),api.tags()]);
      setPhotos(current);setCollections(c);setStats(s);setAllTags(t.tags);
      const progress=advanceReviewProgress(reviewQueue,reviewIndex,current);
      reviewQueueRef.current=progress.ids;reviewIndexRef.current=progress.index;
      setReviewQueue(progress.ids);setReviewIndex(progress.index);setActiveId(progress.nextId);
      if(!progress.nextId)notify('Review complete. All photos in this queue are saved.');
    }catch(e){notify(String(e),true);}
  };
  const savedAndExit=async()=>{
    const remaining=Math.max(0,reviewQueue.length-reviewIndex-1);
    resetReview();
    await refresh(true);
    notify(remaining?`Photo saved. ${remaining} unreviewed photo${remaining===1?' remains':'s remain'} in Needs Review.`:'Photo saved.');
  };
  const startReview=(startId?:string)=>{
    const queue=reviewQueueFrom(visible.map(photo=>photo.id),photos,startId);
    if(!queue.length){notify('No unreviewed photos in this view.');return;}
    reviewQueueRef.current=queue;reviewIndexRef.current=0;
    setReviewQueue(queue);setReviewIndex(0);setActiveId(queue[0]);
  };
  const openPhoto=(photo:Photo)=>{
    if(photo.status==='draft'){startReview(photo.id);return;}
    resetReview();setActiveId(photo.id);
  };
  const switchPage=(next:Page)=>{setPage(next);resetReview();setSelected([]);setSearch('');setFilter('all');};
  const createCollection=async()=>{
    if(!collectionTitle.trim())return;
    try{if(editingCollection)await api.editCollection(editingCollection,collectionTitle,collectionDesc);else await api.createCollection(collectionTitle,collectionDesc);setCollectionTitle('');setCollectionDesc('');setNewCollection(false);setEditingCollection(null);await refresh();notify(editingCollection?'Collection updated':'Collection created');}
    catch(e){notify(String(e),true);}
  };
  const doBulk=async()=>{
    if(!bulkCollection&&!bulkTags.length){notify('Choose a collection or tags.',true);return;}
    try{await api.bulk({ids:selected,addCollectionIds:bulkCollection?[bulkCollection]:[],addTags:bulkTags});setSelected([]);setBulkCollection('');setBulkTags([]);await refresh();notify('Batch metadata updated');}
    catch(e){notify(String(e),true);}
  };
  const openNewCollection=()=>{setCollectionTitle('');setCollectionDesc('');setEditingCollection(null);setNewCollection(true);};
  const openEditCollection=(c:Collection)=>{setCollectionTitle(c.title);setCollectionDesc(c.description);setEditingCollection(c.id);setNewCollection(true);};
  const removeCollection=async()=>{if(!editingCollection)return;if(!window.confirm('Delete this Collection? Photos will be kept.'))return;try{await api.deleteCollection(editingCollection);setNewCollection(false);setEditingCollection(null);await refresh();notify('Collection deleted; original photos kept.');}catch(e){notify(String(e),true);}};
  const saveStudioSettings=async()=>{try{const saved=await api.updateSettings(settings);setSettings(saved);notify('Studio preferences saved.');}catch(e){notify(String(e),true);}};
  const nav:( {id:Page;icon:typeof Grid2X2;label:string;count?:number})[]=[
    {id:'library',icon:LayoutGrid,label:'Library',count:stats.photos},
    {id:'collections',icon:Album,label:'Collections',count:stats.collections},
    {id:'game',icon:Compass,label:'Guess Where',count:stats.gamePool},
    {id:'ai-places',icon:Sparkles,label:'AI & Places'},
    {id:'publish',icon:CloudUpload,label:'Publish'},
  ];
  const pageTitle:Record<Page,string>={library:'Your photo library',collections:'Curated collections',game:'Guess Where pool','ai-places':'AI & Places',publish:'Publish your work',settings:'Studio settings'};
  const pageDescription:Record<Page,string>={library:'A home for the moments you want to keep.',collections:'Create stories by grouping photos into thoughtful series.',game:'Select the photos that become a geography challenge.','ai-places':'Configure, test, and version the place-search intelligence.',publish:'Prepare your Gallery for the public website.',settings:'Configure local publishing preferences.'};
  return <div className="app-shell">
    <aside className="sidebar">
      <button className="brand" onClick={()=>switchPage('library')}><span className="brand-mark"><span className="brand-dot"/></span><span><strong>PHOTO BOOTH</strong><small>the personal archive</small></span></button>
      <div className="sidebar-rule"/>
      <p className="side-label">WORKSPACE</p>
      <nav className="nav-list">{nav.map(({id,icon:Icon,label,count})=><button key={id} className={`nav-item ${page===id?'selected':''}`} onClick={()=>switchPage(id)}><Icon size={17} strokeWidth={1.9}/><span>{label}</span>{count!==undefined&&<span className="nav-count">{count}</span>}</button>)}</nav>
      <div className="sidebar-rule space"/>
      <div className="sidebar-section-head"><p className="side-label">YOUR COLLECTIONS</p><button className="side-add" title="New Collection" aria-label="New Collection" onClick={()=>{switchPage('collections');openNewCollection();}}><Plus size={15}/></button></div>
      <div className="collection-mini">{collections.slice(0,8).map(c=><button key={c.id} className={page==='library'&&filter===`collection:${c.id}`?'active':''} onClick={()=>{setPage('library');setFilter(`collection:${c.id}`);resetReview();}}><span className="mini-dot"/>{c.title}<span>{c.count}</span></button>)}{!collections.length&&<span className="side-empty">No collections yet</span>}</div>
      <div className="sidebar-bottom"><div className="sync-card"><span className="sync-pulse"/> <strong>Local workspace</strong><p>Your originals and private GPS never leave your computer during editing.</p></div><button className={`nav-item settings-link ${page==='settings'?'selected':''}`} onClick={()=>switchPage('settings')}><Settings2 size={17}/><span>Settings</span></button><div className="version">PHOTO BOOTH <span>v0.1</span></div></div>
    </aside>
    <main className="main-area" onDragEnter={e=>{e.preventDefault();if(e.dataTransfer.types.includes('Files'))setDragging(true);}} onDragOver={e=>e.preventDefault()} onDragLeave={e=>{e.preventDefault();if(!e.currentTarget.contains(e.relatedTarget as Node))setDragging(false);}} onDrop={e=>{e.preventDefault();setDragging(false);if(e.dataTransfer.files.length)openImport('files',Array.from(e.dataTransfer.files));}}>
      <header className="topbar"><div className="breadcrumbs">MY STUDIO <span>/</span> {page.toUpperCase()}</div><div className="top-right"><span className={`connection ${connected?'':'error'}`}><span/>{connected?'Local server connected':'Server offline'}</span><button className="user-avatar" aria-label="Local studio">PB</button></div></header>
      <div className="main-body"><div className="page-head"><div><p className="eyebrow">YOUR CREATIVE WORKSPACE <span className="eyebrow-line"/></p><h1>{pageTitle[page]}</h1><p>{pageDescription[page]}</p></div>{page!=='settings'&&page!=='publish'&&page!=='ai-places'&&<div className="head-actions"><button className="outline-btn folder-button" onClick={()=>openImport('folder')}><FolderHeart size={16}/> Import folder</button><button className="primary-btn" onClick={()=>openImport('files')}><Plus size={16}/> Add photos</button></div>}</div>
      {(page==='library'||page==='game')&&<>
        <section className="stat-row"><Stat icon={<Images size={18}/>} value={stats.photos} title="Total photos"/><Stat icon={<CheckCircle2 size={18}/>} value={stats.ready} title="Ready to publish"/><Stat icon={<Compass size={18}/>} value={stats.gamePool} title="Game-ready photos"/><Stat icon={<SlidersHorizontal size={18}/>} value={stats.needReview} title="Needs review"/></section>
        <div className="toolbar"><div className="search-input"><Search size={17}/><input placeholder="Search filenames, descriptions, tags..." value={search} onChange={e=>setSearch(e.target.value)}/></div><div className="toolbar-right"><select aria-label="Filter photos" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">All photos</option><option value="featured">Featured on homepage</option><option value="needs-review">Needs review</option><option value="game">Guess Where entries</option>{collections.map(c=><option key={c.id} value={`collection:${c.id}`}>{c.title}</option>)}</select><div className="select-wrap"><ArrowDownUp size={15}/><select aria-label="Sort photos" value={sort} onChange={e=>setSort(e.target.value as 'new'|'date')}><option value="new">Recently imported</option><option value="date">Date taken</option></select></div><button className="icon-btn grid-toggle" aria-label="Grid view"><Grid2X2 size={18}/></button></div></div>
        {filter==='needs-review'&&visible.length>0&&<div className="needs-review-banner"><div><strong>{visible.length} photo{visible.length===1?'':'s'} waiting for review</strong><span>Each photo must be completed before the next one opens.</span></div><button className="primary-btn" onClick={()=>startReview()}><CheckCircle2 size={16}/> Review remaining photos</button></div>}
        {selected.length>0&&<div className="bulk-strip"><span><Check size={15}/> {selected.length} selected</span><select aria-label="Add selected photos to Collection" value={bulkCollection} onChange={e=>setBulkCollection(e.target.value)}><option value="">Add to collection...</option>{collections.map(c=><option key={c.id} value={c.id}>{c.title}</option>)}</select><div className="bulk-tag-field"><TagPicker options={allTags} selected={bulkTags} onOptionsChange={setAllTags} onChange={setBulkTags}/></div><button className="small-primary" onClick={()=>void doBulk()}>Apply</button><button className="icon-btn" title="Clear selection" onClick={()=>setSelected([])}><X size={16}/></button></div>}
        {visible.length>0?<div className="photo-grid">{visible.map(p=><article key={p.id} className={`photo-card ${active?.id===p.id?'active':''}`}><button className="photo-hit" onClick={()=>openPhoto(p)} aria-label={`Edit ${p.original_name}`}><img loading="lazy" src={resolveImage(p.thumbnailUrl)} alt=""/></button><label className="select-bubble" title="Select for batch edit"><input type="checkbox" checked={selected.includes(p.id)} onChange={e=>setSelected(prev=>e.target.checked?[...prev,p.id]:prev.filter(id=>id!==p.id))}/><span><Check size={11}/></span></label>{p.guess&&<span className="card-game-tag" title="Guess Where entry"><Compass size={13}/></span>}<div className="photo-card-info"><div><strong>{p.original_name}</strong><span>{p.device||'Camera not set'}</span></div><span className="card-date">{p.taken_at||'No date'}</span></div></article>)}</div>:<div className="empty-library"><div className="empty-icon">{page==='game'?<Compass size={29}/>:<Image size={29}/>}</div><h3>{photos.length?'No matching photos yet':'Your photo story starts here'}</h3><p>{page==='game'?'Open a photo from Library, check Include in Guess Where, and confirm a map pin.':'Drop photos here or select files to build your first collection.'}</p>{photos.length===0&&<button className="primary-btn" onClick={()=>openImport('files')}><UploadCloud size={16}/> Import first photos</button>}</div>}
        {page==='game'&&<div className="bottom-guidance"><Compass size={16}/> <span>Only confirmed answers will be usable in the game. GPS metadata is never included in the public export.</span></div>}
      </>}
      {page==='collections'&&<section className="collection-page"><div className="section-heading"><div><h2>All collections</h2><p>A photo can belong to more than one collection.</p></div><button className="outline-btn" onClick={openNewCollection}><Plus size={15}/> New collection</button></div>{collections.length?<div className="collections-grid">{collections.map(c=>{const first=photos.find(p=>p.collectionIds.includes(c.id));return <div className="collection-card-shell" key={c.id}><button className="collection-card" onClick={()=>{setPage('library');setFilter(`collection:${c.id}`);resetReview();}}><div className="collection-cover">{first?<img src={first.thumbnailUrl} alt=""/>:<Album size={32}/>}</div><div><strong>{c.title}</strong><span>{c.count} photos</span></div><ArrowRight size={18}/></button><button className="collection-edit" title="Edit collection" aria-label={`Edit ${c.title}`} onClick={()=>openEditCollection(c)}><Pencil size={15}/></button></div>})}</div>:<div className="empty-library"><div className="empty-icon"><Album size={28}/></div><h3>No collections yet</h3><p>Collect your images by a place, a feeling, or a visual story.</p><button className="primary-btn" onClick={openNewCollection}><Plus size={16}/> Create collection</button></div>}</section>}
      {page==='publish'&&<section className="publish-page"><div className="section-heading"><div><h2>Export & deploy</h2><p>Only safe, public-facing photo data is exported.</p></div><span className="status-pill positive"><ShieldCheck size={14}/> GPS protected</span></div><div className="publish-summary"><Stat icon={<CheckCircle2 size={18}/>} value={preview?.ready??0} title="Publishable"/><Stat icon={<Info size={18}/>} value={preview?.issues.length??0} title="Need metadata"/><Stat icon={<MapPinned size={18}/>} value={preview?.unconfirmedGameEntries??0} title="Game pins to confirm"/></div><div className="publish-layout"><div className="publish-main-card"><h3>1. Export website assets</h3><p>Generate optimized WebP photos, thumbnails and JSON data in your Next.js website folder. Original photos never move.</p><label className="field">Path to your Next.js project folder<input placeholder="/path/to/personal-website/apps/web" value={settings.web_root} onChange={e=>{setSettings(s=>({...s,web_root:e.target.value}));setExported(false);}}/></label><div className="inline-actions"><button className="primary-btn" disabled={busy||!settings.web_root.trim()} onClick={async()=>{setBusy(true);try{await api.updateSettings({web_root:settings.web_root});const result=await api.export(settings.web_root);setExported(true);notify(`Exported ${result.count} photos${result.skipped.length?`; skipped ${result.skipped.length} incomplete`:''}.`);await refresh();}catch(e){notify(String(e),true);}finally{setBusy(false);}}}><CloudUpload size={16}/> Export locally</button><span className="hint-inline">Only images + public metadata</span></div><div className="publish-separator"/><h3>2. Publish to GitHub</h3><p>After exporting, commit and push only the generated photo files. The Git repository needs an existing <code>origin</code> remote and working credentials.</p><label className="field">Commit message<input value={commitMessage} onChange={e=>setCommitMessage(e.target.value)} /></label><button className="outline-btn" disabled={busy||!settings.web_root.trim()||!exported} onClick={async()=>{if(!window.confirm('Push only Photo Booth generated files to the remote GitHub repository?'))return;setBusy(true);try{const result=await api.github(settings.web_root,commitMessage);notify(result.pushed?`Pushed to ${result.branch}`:(result.message||'Nothing new to push'));}catch(e){notify(String(e),true);}finally{setBusy(false);}}}><Github size={17}/> Commit & push to GitHub <ArrowRight size={16}/></button>{!exported&&<p className="small muted">Export locally in this session to enable GitHub publishing.</p>}</div><div className="publish-side"><h3>Pre-publish checks</h3><div className="checklist"><div><CheckCircle2 size={16}/> Originals retained in local archive</div><div><CheckCircle2 size={16}/> EXIF / GPS stripped on export</div><div><CheckCircle2 size={16}/> Game answers excluded from public files</div><div><CheckCircle2 size={16}/> Existing staged Git changes are protected</div></div><div className="issues"><h4>Photos needing attention ({preview?.issues.length||0})</h4>{preview?.issues.slice(0,12).map(p=><button key={p.id} onClick={()=>{setPage('library');setActiveId(p.id);}}><span>{p.name}</span><small>{p.problems.join(' · ')}</small></button>)}{!preview?.issues.length&&<p className="muted small">All photo metadata looks ready.</p>}</div><p className="fine-print">Guess Where D1 synchronization is intentionally not part of V1: secure admin authentication is required before enabling remote answer uploads.</p></div></div></section>}
      {page==='ai-places'&&<AiPlacesPage notify={notify}/>}
      {page==='settings'&&<section className="settings-page"><div className="settings-card"><h2>Studio preferences</h2><p>Publishing preferences stay in local SQLite. Map and model configuration now live together under AI & Places.</p><label className="field">Next.js project path<input value={settings.web_root} onChange={e=>setSettings(s=>({...s,web_root:e.target.value}))} placeholder="/path/to/personal-website/apps/web"/></label><div className="inline-actions"><button className="primary-btn" onClick={()=>void saveStudioSettings()}><Check size={15}/> Save settings</button><button className="outline-btn" onClick={()=>setPage('ai-places')}><Sparkles size={15}/> Open AI & Places</button></div></div><div className="settings-card subtle"><h3>Privacy by design</h3><p>Photo Booth stores original images, private Guess Where answers, drafts and the SQLite file under <code>.local/</code>. This folder is ignored by Git.</p><p>API keys are stored only in macOS Keychain. Public exports contain neither Gallery location fields nor private game-answer coordinates.</p></div></section>}
      </div>
      {dragging&&<div className="drop-overlay"><UploadCloud size={42}/><h2>Drop to import photos</h2><p>JPEG, PNG, WebP, TIFF and supported HEIC files</p></div>}
    </main>
    {active&&<PhotoEditor key={active.id} photo={active} collections={collections} review={reviewQueue.length?{index:reviewIndex,total:reviewQueue.length,onSavedAndNext:()=>void savedAndNext(),onSavedAndExit:()=>void savedAndExit()}:undefined} allTags={allTags} onTagsChange={setAllTags} onSaved={onSaved} onDeleted={onDeleted} onClose={resetReview} onConfigureMaps={()=>setPage('ai-places')} toast={notify}/>}
    {importOpen&&<ImportDialog collections={collections} initialFiles={droppedFiles} initialMode={importMode} onCollectionCreated={collection=>setCollections(current=>[collection,...current.filter(item=>item.id!==collection.id)])} onImported={result=>void finishImport(result)} onClose={()=>setImportOpen(false)} toast={notify}/>} 
    {newCollection&&<div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)setNewCollection(false);}}><section className="dialog-card" role="dialog" aria-modal="true" aria-label="Create collection"><div className="modal-head"><div><p className="eyebrow">CURATE A STORY</p><h2>{editingCollection?'Edit collection':'New collection'}</h2></div><button className="icon-btn" onClick={()=>setNewCollection(false)}><X size={18}/></button></div><label className="field">Collection title<input autoFocus placeholder="Tokyo After Dark" value={collectionTitle} onChange={e=>setCollectionTitle(e.target.value)}/></label><label className="field">Description <span className="optional">optional</span><textarea rows={3} placeholder="A few words about this series" value={collectionDesc} onChange={e=>setCollectionDesc(e.target.value)}/></label><div className="collection-dialog-actions">{editingCollection&&<button className="outline-btn danger" onClick={()=>void removeCollection()}><Trash2 size={15}/> Delete</button>}<button className="primary-btn" disabled={!collectionTitle.trim()} onClick={()=>void createCollection()}><Plus size={16}/> {editingCollection?'Save changes':'Create collection'}</button></div></section></div>}
    {toast&&<div className={`toast ${toast.error?'error':''}`} role="status"><span>{toast.error?<Info size={17}/>:<CheckCircle2 size={17}/>}</span>{toast.message}<button onClick={()=>setToast(null)} aria-label="Dismiss"><X size={14}/></button></div>}
  </div>;
}
function Stat({icon,value,title}:{icon:React.ReactNode;value:number;title:string}){return <div className="stat"><div className="stat-icon">{icon}</div><div><span>{title}</span><strong>{value.toLocaleString()}</strong></div></div>}
