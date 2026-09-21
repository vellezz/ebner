-- Reader verdicts on an entry: it worked, or it did not.
--
-- The second table here that is NOT a projection of content/state/, and it
-- must be excluded from `rebuild` alongside push_subscriptions for the same
-- reason: nothing in the repository could put these back. See WORLD_TABLES in
-- apps/generator/ebner/apply.py, which lists what a rebuild may clear.
--
-- `voter` is a random id the browser keeps in localStorage. It is not identity
-- and not an account — it exists so that changing your mind replaces a verdict
-- instead of adding a second one. Anyone determined to vote twice can clear
-- their storage, which at this readership is a problem worth not solving.

CREATE TABLE opinions (
  entry_day  INTEGER NOT NULL,
  voter      TEXT NOT NULL,
  -- 'ok' or 'nok'. Two values on purpose: a scale invites a model to optimise
  -- for the middle, and there is nothing in the middle worth writing.
  verdict    TEXT NOT NULL CHECK (verdict IN ('ok', 'nok')),
  created_at TEXT NOT NULL,
  PRIMARY KEY (entry_day, voter)
);

CREATE INDEX idx_opinions_day ON opinions(entry_day);
