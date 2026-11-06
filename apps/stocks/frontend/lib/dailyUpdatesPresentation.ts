export interface DailyUpdateSync {
  revision: string;
  applied_revision: string | null;
  last_seen_at: string | null;
}

export function dailySyncStatus(state: DailyUpdateSync, now = Date.now()) {
  const lastSeen = state.last_seen_at ? Date.parse(state.last_seen_at) : NaN;
  const online = Number.isFinite(lastSeen) && now - lastSeen < 120_000;
  const received = state.revision === state.applied_revision;
  if (!state.last_seen_at) return { label: 'Waiting for local automation', detail: 'Your settings are saved. Your computer will receive them when its backend connects.' };
  if (!online) return { label: received ? 'Received · local automation offline' : 'Changes waiting for local automation', detail: 'Your computer will check the live settings when its backend reconnects, and before the next daily run.' };
  return received
    ? { label: 'Received by local automation', detail: 'The live site and local automation are using the same ticker settings.' }
    : { label: 'Syncing your changes', detail: 'Your settings are saved. Waiting for the local automation to acknowledge them.' };
}
