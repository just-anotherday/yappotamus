export const RESEARCH_NOTE_LIMIT = 10000;

export function confirmResearchNoteClose(ticker?: string): boolean {
  const event = new CustomEvent('research-note-close', {cancelable: true, detail: {ticker, confirmed: false}});
  return window.dispatchEvent(event);
}

export function researchNoteKey(ticker: string): string {
  return `yapvibes:research-notes:${ticker.trim().toUpperCase()}`;
}

export function saveResearchNote(
  storage: Pick<Storage, 'setItem' | 'removeItem'>,
  ticker: string,
  text: string,
): void {
  if (text.length > RESEARCH_NOTE_LIMIT) throw new Error('Note is too long.');
  const key = researchNoteKey(ticker);
  if (text.trim()) storage.setItem(key, text);
  else storage.removeItem(key);
}
