-- Web Push subscriptions.
--
-- The only table here that is NOT a projection of content/state/. It holds
-- browser-issued endpoints, which no replay can reconstruct — losing it means
-- everyone resubscribes, which is a nuisance rather than a loss of canon.
--
-- The endpoint is the identity: browsers reissue it when it rotates, and the
-- old one stops working, so INSERT OR REPLACE on it keeps the table honest.

CREATE TABLE push_subscriptions (
  endpoint   TEXT PRIMARY KEY,
  p256dh     TEXT NOT NULL,
  auth       TEXT NOT NULL,
  created_at TEXT NOT NULL,
  -- Set when a push service answers 404 or 410: the subscription is gone and
  -- the row should not be tried again.
  gone_at    TEXT
);

CREATE INDEX idx_push_live ON push_subscriptions(gone_at);
