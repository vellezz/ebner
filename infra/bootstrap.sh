#!/usr/bin/env bash
#
# Provisions every Cloudflare resource this project needs. This is the whole of
# the infrastructure layer — there is no Terraform or OpenTofu; see CLAUDE.md,
# "Infrastructure", for why.
#
# Idempotent: every step checks before it creates, so running this twice is a
# no-op and running it against a half-built account finishes the job.
#
# Auth: a wrangler OAuth session (`wrangler login`) locally, or
# CLOUDFLARE_API_TOKEN in the environment for CI.
#
# The site Worker and the ebner.gripe binding are NOT here — they live in
# apps/site/wrangler.jsonc and are applied by the deploy workflow.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

D1_NAME="ebner"
VECTORIZE_NAME="ebner-fragments"
VECTORIZE_DIMENSIONS=1024
VECTORIZE_METRIC="cosine"
MEDIA_BUCKET="ebner-media"
BACKUP_BUCKET="ebner-backups"
MEDIA_DOMAIN="media.ebner.gripe"

# Wrangler cannot look a zone id up, and requiring one from the environment
# would defeat the point of this script — it is supposed to rebuild the account
# on its own. A zone id is an identifier, not a credential: it does nothing
# without a token. Override with CF_ZONE_ID when pointing at another zone.
CF_ZONE_ID="${CF_ZONE_ID:-376fa4ed9deb43f30e73ff15d7ead528}"

# Call the pinned binary directly rather than going through pnpm: package
# manager shims differ between Git Bash, WSL and CI runners, and the version
# that matters is the one in apps/site/package.json either way.
WRANGLER="$REPO/apps/site/node_modules/.bin/wrangler"
if [ ! -x "$WRANGLER" ]; then
  echo "wrangler not found at $WRANGLER — run 'pnpm install' in apps/site first" >&2
  exit 1
fi
wr() { "$WRANGLER" "$@"; }

step() { printf '\n\033[1m%s\033[0m\n' "$*"; }
have() { printf '  already there: %s\n' "$*"; }
made() { printf '  created: %s\n' "$*"; }
skip() { printf '  skipped: %s\n' "$*"; }

# --- R2 buckets ----------------------------------------------------------
# ebner-media is public, but only through media.ebner.gripe — never r2.dev.
# ebner-backups is private and holds the weekly D1 exports.
step "R2"
buckets="$(wr r2 bucket list 2>/dev/null || true)"
for bucket in "$MEDIA_BUCKET" "$BACKUP_BUCKET"; do
  if printf '%s' "$buckets" | grep -q "$bucket"; then
    have "$bucket"
  else
    wr r2 bucket create "$bucket" >/dev/null
    made "$bucket"
  fi
done

# --- R2 custom domain ----------------------------------------------------
# ebner-media is reachable only through this domain, never through r2.dev.
step "R2 custom domain"
domains="$(wr r2 bucket domain list "$MEDIA_BUCKET" 2>/dev/null || true)"
if printf '%s' "$domains" | grep -q "$MEDIA_DOMAIN"; then
  have "$MEDIA_DOMAIN"
else
  wr r2 bucket domain add "$MEDIA_BUCKET" \
    --domain "$MEDIA_DOMAIN" \
    --zone-id "$CF_ZONE_ID" \
    --min-tls 1.2 >/dev/null
  made "$MEDIA_DOMAIN -> $MEDIA_BUCKET"
fi

# --- D1 ------------------------------------------------------------------
# The world state, and a projection of content/state/ — nothing lives here
# that cannot be rebuilt by replaying those files.
step "D1"
if wr d1 list 2>/dev/null | grep -q "$D1_NAME"; then
  have "$D1_NAME"
else
  wr d1 create "$D1_NAME" >/dev/null
  made "$D1_NAME"
fi

# --- Vectorize -----------------------------------------------------------
# 1024 dimensions to match Workers AI @cf/baai/bge-m3. No preset covers that
# model, so the dimensions and metric are given explicitly.
step "Vectorize"
if wr vectorize list 2>/dev/null | grep -q "$VECTORIZE_NAME"; then
  have "$VECTORIZE_NAME"
else
  wr vectorize create "$VECTORIZE_NAME" \
    --dimensions="$VECTORIZE_DIMENSIONS" \
    --metric="$VECTORIZE_METRIC" >/dev/null
  made "$VECTORIZE_NAME ($VECTORIZE_DIMENSIONS dims, $VECTORIZE_METRIC)"
fi

step "Done."
printf '  Migrations are separate: wrangler d1 migrations apply %s --remote\n' "$D1_NAME"
