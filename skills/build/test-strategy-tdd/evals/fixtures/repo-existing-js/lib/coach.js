// FICTIONAL example lib module.
const THIRTY_DAYS = 30 * 24 * 60 * 60 * 1000;

export function isFresh(nudge, now = Date.now()) {
  return now - nudge.createdAt <= THIRTY_DAYS;
}

export async function pendingNudges(patientId, store = { list: async () => [] }) {
  const all = await store.list(patientId);
  return all.filter((n) => !n.readAt && isFresh(n));
}
