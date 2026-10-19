import {useMemo, useState} from 'react';
import {Plus, Search, X} from 'lucide-react';
import {addTag} from './reviewWorkflow';

type Props = {
  options: string[];
  selected: string[];
  onOptionsChange: (options: string[]) => void;
  onChange: (selected: string[]) => void;
};

export default function TagPicker({options, selected, onOptionsChange, onChange}: Props) {
  const [query, setQuery] = useState('');
  const normalized = query.trim().toLocaleLowerCase();
  const filtered = useMemo(
    () => options.filter(option => option.toLocaleLowerCase().includes(normalized)),
    [normalized, options],
  );
  const exact = options.some(option => option.toLocaleLowerCase() === normalized);

  const create = () => {
    const next = addTag(options, selected, query);
    onOptionsChange(next.options);
    onChange(next.selected);
    setQuery('');
  };

  const toggle = (tag: string, checked: boolean) => {
    onChange(checked ? [...selected, tag] : selected.filter(value => value !== tag));
  };

  return <div className="tag-picker">
    {selected.length > 0 && <div className="tag-chips">{selected.map(tag => <span key={tag}>{tag}<button type="button" aria-label={`Remove ${tag}`} onClick={() => toggle(tag, false)}><X size={11}/></button></span>)}</div>}
    <div className="tag-search"><Search size={14}/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search or create a tag" onKeyDown={event => {
      if (event.key === 'Enter' && normalized && !exact) { event.preventDefault(); create(); }
    }}/></div>
    <div className="tag-options">
      {filtered.map(tag => <label key={tag}><input type="checkbox" checked={selected.includes(tag)} onChange={event => toggle(tag, event.target.checked)}/><span>{tag}</span></label>)}
      {normalized && !exact && <button type="button" className="create-tag" onClick={create}><Plus size={13}/> Create “{query.trim()}”</button>}
      {!filtered.length && (!normalized || exact) && <span className="tag-empty">No matching tags</span>}
    </div>
  </div>;
}
