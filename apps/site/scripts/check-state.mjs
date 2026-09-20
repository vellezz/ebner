// Guard for content/state/*.json and the entries beside them.
//
// Provisional: the spec puts guards in the Python generator, but that does not
// exist yet and nothing else validates state files in CI. Keep this until the
// generator owns these checks, then delete it rather than maintaining two.
//
// Checks: both JSON Schemas, referential integrity across files, travel
// continuity, thread lifecycle, and chronology (monotonic, step capped at 7).

import Ajv from 'ajv/dist/2020.js';
import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
// Strip a UTF-8 BOM: files hand-edited on Windows routinely carry one and
// JSON.parse rejects it outright.
const read = (p) => JSON.parse(readFileSync(p, 'utf8').replace(/^﻿/, ''));

const ajv = new Ajv({ allErrors: true, strict: false });
const validateEntry = ajv.compile(read(join(ROOT, 'content/schema/entry.schema.json')));
const validateState = ajv.compile(read(join(ROOT, 'content/schema/state.schema.json')));

const problems = [];
let checked = 0;

// --- entry frontmatter ---------------------------------------------------
const entryDir = join(ROOT, 'content/entries');
const entries = new Map();

for (const f of readdirSync(entryDir).filter((n) => n.endsWith('.md'))) {
  const raw = readFileSync(join(entryDir, f), 'utf8');
  const m = raw.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!m) {
    problems.push(`${f}: no frontmatter block`);
    continue;
  }
  const fm = {};
  for (const line of m[1].split(/\r?\n/)) {
    const kv = line.match(/^(\w+):\s*(.*)$/);
    if (!kv) continue;
    const k = kv[1];
    const v = kv[2].trim();
    if (v === 'null') fm[k] = null;
    else if (/^\[.*\]$/.test(v))
      fm[k] = v.slice(1, -1).split(',').map((s) => s.trim()).filter(Boolean);
    else if (/^-?\d+$/.test(v)) fm[k] = Number(v);
    else fm[k] = v.replace(/^["']|["']$/g, '');
  }
  if (!validateEntry(fm)) {
    problems.push(`${f}: ${ajv.errorsText(validateEntry.errors, { separator: '; ' })}`);
  }
  entries.set(fm.day, fm);
  checked++;
}

// --- state files, replayed in filename order -----------------------------
const stateDir = join(ROOT, 'content/state');
const knownEntities = new Set();
const knownThreads = new Set();
const knownFacts = new Set();
let prevLocation = null;
let prevDay = -1;

for (const f of readdirSync(stateDir).filter((n) => n.endsWith('.json')).sort()) {
  const s = read(join(stateDir, f));
  checked++;

  if (!validateState(s)) {
    problems.push(`${f}: ${ajv.errorsText(validateState.errors, { separator: '; ' })}`);
    continue;
  }

  if (s.day <= prevDay) problems.push(`${f}: day ${s.day} does not exceed ${prevDay}`);
  if (prevDay >= 1 && s.day - prevDay > 7)
    problems.push(`${f}: day step ${s.day - prevDay} exceeds the cap of 7`);

  for (const e of s.entities ?? []) {
    if (knownEntities.has(e.id)) problems.push(`${f}: entity ${e.id} already exists`);
    knownEntities.add(e.id);
  }
  for (const e of s.entities ?? []) {
    if (e.parent === e.id) problems.push(`${f}: entity ${e.id} is its own parent`);
    else if (e.parent && !knownEntities.has(e.parent))
      problems.push(`${f}: entity ${e.id} has unknown parent ${e.parent}`);
  }
  for (const t of s.threads ?? []) {
    if (t.op === 'open') knownThreads.add(t.id);
    else if (!knownThreads.has(t.id)) problems.push(`${f}: thread ${t.id}: ${t.op} before open`);
  }
  for (const fact of s.facts ?? []) {
    if (fact.subject && !knownEntities.has(fact.subject))
      problems.push(`${f}: fact ${fact.id} has unknown subject ${fact.subject}`);

    // Closing a fact that was never opened is the quietest failure in the
    // system: the UPDATE matches no row, nothing errors, and the world keeps
    // believing something the entry just said is over.
    if (fact.op === 'open') knownFacts.add(fact.id);
    else if (!knownFacts.has(fact.id))
      problems.push(`${f}: fact ${fact.id}: close before open`);
  }
  for (const fr of s.fragments ?? []) {
    for (const t of fr.threads ?? []) {
      if (!knownThreads.has(t)) problems.push(`${f}: fragment ${fr.id} references unknown thread ${t}`);
    }
  }

  const hops = [...(s.travel ?? [])].sort((a, b) => a.seq - b.seq);
  for (const h of hops) {
    if (h.from && !knownEntities.has(h.from)) problems.push(`${f}: travel leaves unknown ${h.from}`);
    if (!knownEntities.has(h.to)) problems.push(`${f}: travel arrives at unknown ${h.to}`);
  }

  if (s.day === 0) continue;

  const entry = entries.get(s.day);
  if (!entry) {
    problems.push(`${f}: no entry file for day ${s.day}`);
  } else {
    if (!knownEntities.has(entry.location))
      problems.push(`${f}: entry location ${entry.location} is not a known entity`);
    if (hops.length > 0) {
      if (prevLocation && hops[0].from !== prevLocation)
        problems.push(
          `${f}: first hop leaves ${hops[0].from}, but the previous entry ended at ${prevLocation}`,
        );
      if (hops[hops.length - 1].to !== entry.location)
        problems.push(
          `${f}: last hop arrives at ${hops[hops.length - 1].to}, but the entry location is ${entry.location}`,
        );
    }
    for (const t of entry.threads ?? []) {
      if (!knownThreads.has(t)) problems.push(`${f}: frontmatter references unknown thread ${t}`);
    }
    prevLocation = entry.location;
  }
  prevDay = s.day;
}

// --- every entry needs its state file ------------------------------------
const stateDays = new Set(
  readdirSync(stateDir)
    .filter((n) => /^\d+\.json$/.test(n))
    .map((n) => Number(n.replace('.json', ''))),
);
for (const day of entries.keys()) {
  if (!stateDays.has(day)) problems.push(`day ${day}: entry has no state file`);
}

if (problems.length > 0) {
  console.error(`check-state: ${problems.length} problem(s) across ${checked} file(s)`);
  for (const p of problems) console.error(`  ${p}`);
  process.exit(1);
}

console.log(
  `check-state: ${checked} file(s) OK — ${knownEntities.size} entities, ${knownThreads.size} threads`,
);
