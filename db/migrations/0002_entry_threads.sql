-- Which threads an entry touches.
--
-- The frontmatter carries this and it is authoritative: an entry may touch a
-- thread without producing a fragment for it, so fragment_threads is not a
-- substitute. Thread reference counts and cooldowns are computed from here.

CREATE TABLE entry_threads (
  entry_day INTEGER NOT NULL REFERENCES entries(day) ON DELETE CASCADE,
  thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
  PRIMARY KEY (entry_day, thread_id)
);

CREATE INDEX idx_entry_threads_thread ON entry_threads(thread_id);
