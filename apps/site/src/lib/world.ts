/**
 * World state, projected at build time.
 *
 * The site never talks to D1. It does not have to: D1 is itself a projection
 * of content/state/, so the site computes the same projection from the same
 * files. The replay rules here mirror apps/generator/ebner/apply.py — if one
 * changes, the other has to.
 */

import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..');
const STATE_DIR = join(ROOT, 'content', 'state');

export type EntityKind = 'person' | 'place' | 'organisation' | 'ship';
export type ThreadStatus = 'active' | 'closed' | 'dormant';

export interface Entity {
  id: string;
  kind: EntityKind;
  name: string;
  parent: string | null;
  summary?: string;
  firstEntry: number | null;
  lastEntry: number | null;
}

export interface Thread {
  id: string;
  type: string;
  status: ThreadStatus;
  closure?: string;
  summary?: string;
  openedDay: number;
  closedDay: number | null;
  days: number[];
}

export interface Fact {
  id: string;
  kind: string;
  content: string;
  subject: string | null;
  validFrom: number;
  validTo: number | null;
}

export interface Hop {
  day: number;
  seq: number;
  from: string | null;
  to: string;
}

export interface World {
  entities: Map<string, Entity>;
  threads: Map<string, Thread>;
  facts: Map<string, Fact>;
  travel: Hop[];
}

const read = (path: string) => JSON.parse(readFileSync(path, 'utf8').replace(/^﻿/, ''));

let cached: World | null = null;

export function loadWorld(): World {
  if (cached) return cached;

  const entities = new Map<string, Entity>();
  const threads = new Map<string, Thread>();
  const facts = new Map<string, Fact>();
  const travel: Hop[] = [];

  // Filename order is replay order — the same property that makes unpublishing
  // an entry a complete operation rather than a partial one.
  const files = readdirSync(STATE_DIR)
    .filter((n) => n.endsWith('.json'))
    .sort();

  for (const file of files) {
    const state = read(join(STATE_DIR, file));
    const day: number = state.day;
    const entryDay = day === 0 ? null : day;

    for (const e of state.entities ?? []) {
      const existing = entities.get(e.id);
      entities.set(e.id, {
        id: e.id,
        kind: e.kind,
        name: e.name,
        parent: e.parent ?? null,
        summary: e.summary,
        firstEntry: existing?.firstEntry ?? entryDay,
        lastEntry: existing?.lastEntry ?? null,
      });
    }

    for (const t of state.threads ?? []) {
      if (t.op === 'open') {
        threads.set(t.id, {
          id: t.id,
          type: t.type ?? 'medium',
          status: t.status ?? 'active',
          summary: t.summary,
          openedDay: day,
          closedDay: null,
          days: [],
        });
      } else {
        const thread = threads.get(t.id);
        if (!thread) continue;
        if (t.summary) thread.summary = t.summary;
        if (t.status) thread.status = t.status;
        if (t.op === 'close') {
          thread.status = t.status ?? 'closed';
          thread.closure = t.closure;
          thread.closedDay = day;
        }
      }
    }

    for (const f of state.facts_opened ?? []) {
      facts.set(f.id, {
        id: f.id,
        kind: f.kind ?? 'general',
        content: f.content,
        subject: f.subject ?? null,
        validFrom: f.valid_from ?? day,
        validTo: null,
      });
    }
    for (const f of state.facts_closed ?? []) {
      const fact = facts.get(f.id);
      if (fact) fact.validTo = f.valid_to ?? day;
    }

    for (const hop of [...(state.travel ?? [])].sort((a, b) => a.seq - b.seq)) {
      travel.push({ day, seq: hop.seq, from: hop.from ?? null, to: hop.to });
    }
  }

  cached = { entities, threads, facts, travel };
  return cached;
}

/** Being somewhere means being inside everything that contains it. */
export function containmentChain(world: World, id: string): Entity[] {
  const chain: Entity[] = [];
  let current = world.entities.get(id);
  while (current) {
    chain.push(current);
    current = current.parent ? world.entities.get(current.parent) : undefined;
  }
  return chain;
}

export const STATUS_LABEL: Record<string, string> = {
  active: 'w toku',
  closed: 'zamknięta',
  dormant: 'uśpiona',
};

export const CLOSURE_LABEL: Record<string, string> = {
  resolved: 'rozstrzygnięta',
  abandoned: 'porzucona',
  merged: 'scalona',
};
