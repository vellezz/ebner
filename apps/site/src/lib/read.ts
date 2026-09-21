/**
 * Which entries this browser has read.
 *
 * Per-browser and nowhere else. There are no accounts here, so the phone and
 * the desktop keep separate counts and always will — that is a real limitation
 * and the reason this marks what is unread rather than deciding what to show.
 * A mechanism that picked the next entry for you would be wrong on the second
 * device, and wrong quietly.
 *
 * Every access is wrapped: private windows and blocked site data both throw,
 * and losing the marks must never take the page with them.
 */
const KEY = 'ebner-read';

export function readDays(): Set<number> {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return new Set();
    const days = JSON.parse(raw);
    return new Set(Array.isArray(days) ? days.filter((d) => Number.isInteger(d)) : []);
  } catch {
    return new Set();
  }
}

export function markRead(day: number): void {
  if (!Number.isInteger(day)) return;
  try {
    const days = readDays();
    if (days.has(day)) return;
    days.add(day);
    localStorage.setItem(KEY, JSON.stringify([...days].sort((a, b) => a - b)));
  } catch {
    // Nothing to do and nothing worth saying: the page reads fine unmarked.
  }
}

/** The unread days among `all`, oldest first. */
export function unread(all: number[]): number[] {
  const seen = readDays();
  return all.filter((day) => !seen.has(day)).sort((a, b) => a - b);
}
