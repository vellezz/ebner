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
# Wrangler cannot look a zone id up, so it has to be supplied. Find it on the
# zone's overview page in the Cloudflare dashboard, right-hand column.
step "R2 custom domain"
if [ -z "${CF_ZONE_ID:-}" ]; then
  skip "$MEDIA_DOMAIN — set CF_ZONE_ID to attach it"
else
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
