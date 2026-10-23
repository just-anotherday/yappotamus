import assert from 'node:assert/strict';
import test from 'node:test';
import { articleLink, isPublisherHost } from './articleEvidence.ts';
import { RESEARCH_NOTE_LIMIT, researchNoteKey, saveResearchNote } from './researchNotes.ts';

test('research notes survive storage reads and stay isolated by ticker', () => {
  const values = new Map();
  const storage = { setItem: (key, text) => values.set(key, text), removeItem: key => values.delete(key) };
  saveResearchNote(storage, ' amd ', 'My thesis\nQuestions to revisit');
  saveResearchNote(storage, 'NVDA', 'Separate research');
  assert.equal(values.get(researchNoteKey('AMD')), 'My thesis\nQuestions to revisit');
  saveResearchNote(storage, 'AMD', '   ');
  assert.equal(values.has(researchNoteKey('AMD')), false);
  assert.equal(values.get(researchNoteKey('nvda')), 'Separate research');
  assert.throws(() => saveResearchNote(storage, 'AMD', 'x'.repeat(RESEARCH_NOTE_LIMIT + 1)));
});

test('storage failures propagate so the editor cannot claim a note was saved', () => {
  const storage = { setItem: () => { throw new Error('Quota exceeded'); } };
  assert.throws(() => saveResearchNote(storage, 'AMD', 'Important question'), /Quota exceeded/);
});

test('source links show the destination and reject unusable or executable URLs', () => {
  assert.deepEqual(articleLink(' https://www.example.com/story?a=1 '), { href: 'https://www.example.com/story?a=1', publisher: 'example.com' });
  for (const url of [null, '', 'not a url', '#', '/story', 'javascript:alert(1)', 'data:text/html,hello', 'https://user:password@example.com']) {
    assert.equal(articleLink(url), null);
  }
});

test('publisher domains reject lookalike hosts while allowing real subdomains', () => {
  for (const host of ['yahoo.com', 'finance.yahoo.com', 'WWW.YAHOO.COM']) {
    assert.equal(isPublisherHost(host, 'yahoo.com'), true);
  }
  for (const host of ['evilyahoo.com', 'yahoo.com.attacker.example', 'fake-yahoo.com']) {
    assert.equal(isPublisherHost(host, 'yahoo.com'), false);
  }
});
