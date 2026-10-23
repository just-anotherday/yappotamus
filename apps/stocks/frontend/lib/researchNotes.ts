export const RESEARCH_NOTE_LIMIT = 10000;

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
