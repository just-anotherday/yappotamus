'use client';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { RESEARCH_NOTE_LIMIT, researchNoteKey } from '@/lib/researchNotes';
import { researchRequest } from '@/lib/researchApi';
interface Note { text: string; version: number }
export default function TickerResearchNotes({ ticker }: { ticker: string }) {
  return <NoteEditor key={ticker.trim().toUpperCase()} ticker={ticker.trim().toUpperCase()} />;
}
function NoteEditor({ ticker }: { ticker: string }) {
  const id = useId();
  const [text, setText] = useState('');
  const [saved, setSaved] = useState('');
  const [version, setVersion] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [browserNote, setBrowserNote] = useState('');
  const busy = useRef(false);
  const alive = useRef(true);
  const dirty = loaded && text !== saved;
  useEffect(() => {
    alive.current = true;
    let active = true;
    researchRequest<Note>(`/notes/${encodeURIComponent(ticker)}`).then(note => {
      if (!active) return;
      setText(note.text); setSaved(note.text); setVersion(note.version); setLoaded(true);
      try { setBrowserNote(localStorage.getItem(researchNoteKey(ticker)) ?? ''); } catch { /* Account storage is independent. */ }
    }).catch(failure => { if (active) setError(failure.message); });
    return () => { active = false; alive.current = false; };
  }, [ticker]);
  const save = useCallback(async () => {
    if (!loaded || busy.current || text === saved) return;
    busy.current = true; setSaving(true); setError('');
    try {
      const note = await researchRequest<Note>(`/notes/${encodeURIComponent(ticker)}`, { method: 'PUT', headers: {'Content-Type':'application/json'}, body: JSON.stringify({text, version}) });
      if (alive.current) { setSaved(note.text); setVersion(note.version); }
    } catch (failure) {
      if (alive.current) setError(failure instanceof Error ? failure.message : 'Save failed. Keep a copy of your draft.');
    } finally {
      busy.current = false; if (alive.current) setSaving(false);
    }
  }, [loaded, text, saved, ticker, version]);
  useEffect(() => {
    if (!dirty || saving || error) return;
    const timer = setTimeout(() => { void save(); }, 900);
    return () => clearTimeout(timer);
  }, [dirty, saving, error, save]);
  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    const beforeLink = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target.closest('a') : null;
      if (target && target.getAttribute('href')?.startsWith('/') && !window.confirm('Your note has unsaved changes. Leave without saving?')) { event.preventDefault(); event.stopPropagation(); }
    };
    const beforeCollapse = (event: Event) => {
      const close = event as CustomEvent<{ticker?:string;confirmed:boolean}>;
      if (close.defaultPrevented || close.detail.confirmed || (close.detail.ticker && close.detail.ticker !== ticker)) return;
      if (window.confirm('Your note has unsaved changes. Close without saving?')) close.detail.confirmed = true;
      else close.preventDefault();
    };
    window.addEventListener('beforeunload', beforeUnload);
    window.addEventListener('research-note-close', beforeCollapse);
    document.addEventListener('click', beforeLink, true);
    return () => { window.removeEventListener('beforeunload', beforeUnload); window.removeEventListener('research-note-close', beforeCollapse); document.removeEventListener('click', beforeLink, true); };
  }, [dirty, ticker]);
  return (
    <details className="my-5 min-w-0 whitespace-normal rounded-xl border border-divider bg-card p-4">
      <summary className="cursor-pointer font-semibold text-primary">Research notes · {ticker}</summary>
      <p id={`${id}-help`} className="mt-3 text-xs text-muted">Saved to your account and available on your other devices. Clearing browser data will not remove account-saved notes. Autosaves after you pause typing.</p>
      {browserNote && browserNote !== saved && <div className="my-3 rounded border border-divider p-3 text-sm"><p>A note from this browser is available. Importing replaces the editor draft; your browser copy is kept.</p><button type="button" disabled={!loaded || saving} onClick={() => { if (!text.trim() || window.confirm('Replace this editor draft with your browser note?')) { setText(browserNote); setBrowserNote(''); } }} className="mt-2 underline">Import browser note</button></div>}
      <label htmlFor={id} className="mt-3 block text-sm font-medium text-primary">Your notes for {ticker}</label>
      <textarea id={id} aria-describedby={`${id}-help`} value={text} disabled={!loaded} maxLength={RESEARCH_NOTE_LIMIT} onChange={event => setText(event.target.value)} rows={5} placeholder={'My thesis…\nQuestions to research…\nWhat would change my mind…'} className="mt-2 w-full resize-y rounded-lg border border-divider bg-transparent p-3 text-sm text-primary focus:ring-2 focus:ring-accent disabled:opacity-50" />
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <button type="button" onClick={() => { void save(); }} disabled={!loaded || !dirty || saving} className="rounded-lg bg-action px-4 py-2 text-sm text-white disabled:opacity-50">{saving ? 'Saving…' : 'Save note'}</button>
        <span role="status" className="text-xs text-muted">{!loaded ? 'Loading account note…' : saving ? 'Saving to your account…' : dirty ? 'Unsaved changes' : 'Saved to your account'}</span>
        <span className="ml-auto text-xs text-muted">{text.length.toLocaleString()} / {RESEARCH_NOTE_LIMIT.toLocaleString()}</span>
      </div>
      {error && <p role="alert" className="mt-2 text-sm text-negative">{error} {loaded ? 'Your draft remains in the editor. Save note retries.' : <button className="underline" onClick={() => location.reload()}>Reload to retry</button>}</p>}
    </details>
  );
}
