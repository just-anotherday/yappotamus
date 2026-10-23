'use client';

import { useEffect, useId, useState } from 'react';
import { RESEARCH_NOTE_LIMIT, researchNoteKey, saveResearchNote } from '@/lib/researchNotes';

export default function TickerResearchNotes({ ticker }: { ticker: string }) {
  return <NoteEditor key={ticker.trim().toUpperCase()} ticker={ticker.trim().toUpperCase()} />;
}

function NoteEditor({ ticker }: { ticker: string }) {
  const id = useId();
  const [text, setText] = useState('');
  const [saved, setSaved] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    const timer = setTimeout(() => {
      try {
        const note = localStorage.getItem(researchNoteKey(ticker)) ?? '';
        setText(note);
        setSaved(note);
        setLoaded(true);
      } catch {
        setError('Notes could not be loaded. Allow browser storage and reload to try again.');
      }
    }, 0);
    return () => clearTimeout(timer);
  }, [ticker]);

  function save() {
    try {
      saveResearchNote(localStorage, ticker, text);
      setSaved(text);
      setMessage(text.trim() ? 'Saved in this browser.' : 'Note cleared.');
      setError('');
    } catch {
      setError('Your note could not be saved. Keep a copy and check browser storage.');
    }
  }

  return (
    <details className="my-5 min-w-0 whitespace-normal rounded-xl border border-divider bg-card p-4 dark:border-slate-700 dark:bg-slate-800">
      <summary className="cursor-pointer font-semibold text-primary dark:text-white">Research notes · {ticker}</summary>
      <p id={`${id}-help`} className="mt-3 text-xs text-muted dark:text-slate-400">
        Saved only in this browser. Clearing browser data removes these notes. Notes are not synced to other devices or included in AI reports.
      </p>
      <label htmlFor={id} className="mt-3 block text-sm font-medium text-primary dark:text-white">Your notes for {ticker}</label>
      <textarea id={id} aria-describedby={`${id}-help`} value={text} disabled={!loaded} maxLength={RESEARCH_NOTE_LIMIT}
        onChange={event => { setText(event.target.value); setMessage(''); }} rows={5}
        placeholder={'My thesis…\nQuestions to research…\nWhat would change my mind…'}
        className="mt-2 w-full resize-y rounded-lg border border-divider bg-transparent p-3 text-sm text-primary focus:outline-none focus:ring-2 focus:ring-accent disabled:opacity-50 dark:border-slate-600 dark:text-white" />
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <button type="button" onClick={save} disabled={!loaded || text === saved}
          className="rounded-lg bg-action px-4 py-2 text-sm font-medium text-white disabled:opacity-50">Save note</button>
        <span role="status" className="text-xs text-muted dark:text-slate-400">{message || (text !== saved ? 'Unsaved changes' : '')}</span>
        <span className="ml-auto text-xs text-muted dark:text-slate-400">{text.length.toLocaleString()} / {RESEARCH_NOTE_LIMIT.toLocaleString()}</span>
      </div>
      {error && <p role="alert" className="mt-2 text-sm text-negative dark:text-negative">{error}</p>}
    </details>
  );
}
