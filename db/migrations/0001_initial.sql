-- World state.
--
-- Every table here is a PROJECTION of content/state/*.json. Nothing may live in
-- D1 that cannot be rebuilt by replaying those files in filename order, which
-- is what makes unpublishing an entry a complete operation rather than a
-- partial one.

-- People, places, organisations and ships. Places nest through `parent`:
-- a moon inside a planet inside a system.
CREATE TABLE entities (
  id              TEXT PRIMARY KEY,
  kind            TEXT NOT NULL CHECK (kind IN ('person', 'place', 'organisation', 'ship')),
  name            TEXT NOT NULL,
  parent          TEXT REFERENCES entities(id),
  summary         TEXT,
  first_entry     INTEGER,
  last_entry      INTEGER,
  reference_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_entities_kind ON entities(kind);
CREATE INDEX idx_entities_parent ON entities(parent);
-- Retrieval surfaces places unvisited for a while, so this is a hot path.
CREATE INDEX idx_entities_last_entry ON entities(last_entry);

-- One row per entry. `day` is Ebner's in-world day count: strictly increasing,
-- never consecutive. `location` is where the entry ENDS.
CREATE TABLE entries (
  day          INTEGER PRIMARY KEY,
  title        TEXT NOT NULL,
  location     TEXT NOT NULL REFERENCES entities(id),
  kind         TEXT NOT NULL CHECK (kind IN (
                 'travel', 'new_job', 'continuation', 'resolution',
                 'adventure', 'quiet', 'note', 'documents', 'stopover')),
  body         TEXT NOT NULL,
  published_at TEXT NOT NULL
);

CREATE INDEX idx_entries_location ON entries(location);

-- Movement, in order. Kept as its own record rather than derived from
-- consecutive entries, because a travel entry is precisely about the hops in
-- between and consecutive pairs would lose every one of them.
CREATE TABLE travel (
  entry_day   INTEGER NOT NULL REFERENCES entries(day) ON DELETE CASCADE,
  seq         INTEGER NOT NULL,
  from_entity TEXT REFERENCES entities(id),
  to_entity   TEXT NOT NULL REFERENCES entities(id),
  PRIMARY KEY (entry_day, seq)
);

-- Ongoing matters. Shown to the reader as "sprawy". Ceilings are enforced by
-- guards in code, not here: at most 5 active, at most 3 recurring.
CREATE TABLE threads (
  id               TEXT PRIMARY KEY,
  type             TEXT NOT NULL CHECK (type IN ('short', 'medium', 'long', 'recurring')),
  status           TEXT NOT NULL CHECK (status IN ('active', 'closed', 'dormant')),
  closure          TEXT CHECK (closure IN ('resolved', 'abandoned', 'merged')),
  reference_policy TEXT NOT NULL CHECK (reference_policy IN ('develop', 'mention', 'may_return', 'do_not_touch')),
  opened_day       INTEGER NOT NULL,
  last_used_day    INTEGER,
  closed_day       INTEGER,
  planned_entries  INTEGER,
  cooldown_days    INTEGER NOT NULL DEFAULT 0,
  reference_count  INTEGER NOT NULL DEFAULT 0,
  summary          TEXT
);

CREATE INDEX idx_threads_status ON threads(status);
CREATE INDEX idx_threads_last_used ON threads(last_used_day);

-- Facts are never edited. A repair, a payment or any change of circumstance
-- closes the old fact by setting valid_to and opens a new one — that is what
-- these columns are for, and it is how ship condition, money and debts are
-- modelled without tables of their own.
--
-- source_entry is NULL for the seed in 0000.json, which uses valid_from 0.
CREATE TABLE facts (
  id           TEXT PRIMARY KEY,
  kind         TEXT NOT NULL DEFAULT 'general' CHECK (kind IN ('general', 'world_rule')),
  content      TEXT NOT NULL,
  subject      TEXT REFERENCES entities(id),
  valid_from   INTEGER NOT NULL,
  valid_to     INTEGER,
  source_entry INTEGER REFERENCES entries(day) ON DELETE CASCADE
);

-- Only facts with valid_to IS NULL reach the prompt, so this is the hot path.
CREATE INDEX idx_facts_valid ON facts(valid_to);
CREATE INDEX idx_facts_subject ON facts(subject);
CREATE INDEX idx_facts_kind ON facts(kind);

-- Indexed in Vectorize, which stores only `id -> vector`. All filtering lives
-- here: thread status, reference_policy, cooldown and fact validity.
CREATE TABLE fragments (
  id        TEXT PRIMARY KEY,
  entry_day INTEGER REFERENCES entries(day) ON DELETE CASCADE,
  kind      TEXT NOT NULL CHECK (kind IN ('scene', 'document', 'punchline', 'world_description')),
  content   TEXT NOT NULL
);

CREATE INDEX idx_fragments_entry ON fragments(entry_day);

CREATE TABLE fragment_threads (
  fragment_id TEXT NOT NULL REFERENCES fragments(id) ON DELETE CASCADE,
  thread_id   TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
  PRIMARY KEY (fragment_id, thread_id)
);

CREATE INDEX idx_fragment_threads_thread ON fragment_threads(thread_id);
