/**
 * Polish plurals.
 *
 * Polish has three forms, not two. `3 wpisów` is wrong where `3 wpisy` is
 * meant, and a naive one-versus-many rule produces that error for every count
 * from 2 to 4 — which on a site whose whole point is Polish prose reads as
 * carelessness.
 *
 *   1            → one    (1 wpis)
 *   2-4          → few    (3 wpisy)
 *   0, 5+, 12-14 → many   (5 wpisów, 13 wpisów)
 *
 * The 12-14 exception is why the rule looks at the last two digits: 22 takes
 * the few form, 12 does not.
 */

export function plural(n: number, one: string, few: string, many: string): string {
  const abs = Math.abs(n);
  if (abs === 1) return one;
  const lastTwo = abs % 100;
  const last = abs % 10;
  if (last >= 2 && last <= 4 && !(lastTwo >= 12 && lastTwo <= 14)) return few;
  return many;
}

/** The count and its noun, which is what the call sites actually want. */
export function count(n: number, one: string, few: string, many: string): string {
  return `${n} ${plural(n, one, few, many)}`;
}
