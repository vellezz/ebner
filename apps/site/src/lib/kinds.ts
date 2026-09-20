/**
 * Reader-facing labels for entry kinds.
 *
 * The stored values are English identifiers, as everything in the data is; the
 * reader only ever sees Polish. This lived in two components and was missing
 * from a third place that needed it — the notification, which shipped saying
 * "Dzień 7 · new_job" and read like an unfinished placeholder. One copy now.
 *
 * The keys must stay in step with the `kind` enum in
 * content/schema/entry.schema.json, which is the source of truth for which
 * kinds exist at all.
 */
export const KIND_LABEL: Record<string, string> = {
  travel: 'podróż',
  new_job: 'nowe zlecenie',
  continuation: 'ciąg dalszy',
  resolution: 'rozstrzygnięcie',
  adventure: 'przygoda',
  quiet: 'cisza',
  note: 'notatka',
  documents: 'dokumenty',
  stopover: 'postój',
};

/** The Polish label, falling back to the raw value rather than to nothing. */
export const kindLabel = (kind: string): string => KIND_LABEL[kind] ?? kind;
