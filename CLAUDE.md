# CLAUDE.md — Ebner

## What this project is

An experimental, for-fun project: every day an AI writes one entry in the work diary of **Ebner Gripe**, a self-employed repairman who travels between star systems fixing the infrastructure of alien civilizations. The domain is his name: `ebner.gripe`. Entries are grotesque, absurd science fiction written in Polish, published on a static website at **https://ebner.gripe**.

This is not a production system. The owner reads every entry; a missing entry is the only alert needed.

**Fully autonomous.** Nothing in the daily loop waits on a person. Entries publish without review, and no asset — sketch, document or anything else — is ever supplied by hand. A step that needs a human is the wrong step.

The whole stack is **serverless and free-tier**: GitHub (repo, Actions) + Cloudflare (Workers, D1, Vectorize, Workers AI, R2). The only paid items are LLM API usage and the domain.

## Language rules (strict)

- **English:** all code, identifiers, comments, commit messages, branch names, config keys, JSON keys, database tables and columns, enum values, CLI output, logs, docs in the repo (including this file).
- **Polish:** literary content only — diary entries, fact texts, thread summaries, world descriptions, and the writing prompts (they instruct the model to write Polish prose).
- Never translate Polish literary content into English and never use Polish identifiers in code.

## Non-goals

Do not add any of these unless explicitly asked:
- servers, VPS, containers in production, Kubernetes, Coolify or any PaaS layer,
- uptime monitoring, alerting, failure notifications of any kind,
- a search server (search is static, built with Pagefind),
- local or duplicated copies of media (R2 is the single source of truth for media),
- SQLite files moved around between jobs (state lives in `content/state/`, projected into D1).

## Stack

| Area | Decision |
|---|---|
| Source of truth for content and code | Public GitHub monorepo |
| Scheduler and pipeline runtime | GitHub Actions (Python) |
| Site | Astro + MDX, deployed as a static assets-only Cloudflare Worker at `ebner.gripe` |
| Search | Pagefind index generated at build time, runs in the browser |
| World state | Cloudflare D1 (managed SQLite), accessed via Cloudflare API. A **projection** of `content/state/`, never a source of truth |
| Vector search | Cloudflare Vectorize, index `ebner-fragments`, 1024 dims, cosine |
| Embeddings | Workers AI `@cf/baai/bge-m3` via REST API |
| Media | R2 bucket `ebner-media`, native custom domain `media.ebner.gripe` |
| Backups | R2 bucket `ebner-backups` (private): weekly D1 exports. Convenience only — the real backup is git |
| Domain and DNS | `ebner.gripe`, Cloudflare Registrar, DNS in Cloudflare |
| Provisioning | `infra/bootstrap.sh` — idempotent wrangler commands. No Terraform or OpenTofu layer, deliberately; see below |
| LLM gateway | LiteLLM used as a Python library (no proxy server); per-step model routing from one config file |
| Secrets | GitHub Actions secrets (Cloudflare API token scoped to this account's resources, Anthropic key, OpenRouter key) |
| Logs | GitHub Actions run logs |

## Infrastructure

**One tool: wrangler.** There is no Terraform or OpenTofu layer, and that is a decision rather than an omission.

The account holds six resources — two R2 buckets, a D1 database, a Vectorize index, the site Worker and the media custom domain. They are created once and essentially never change. A declarative IaC layer earns its keep across dozens of resources, several environments, or a team; here it would buy drift detection in exchange for a second API token, a state file with nowhere to live (its natural backend is the R2 bucket it is supposed to create), a provider that already cannot manage Vectorize, and two tools able to change the same state — which would need a written boundary to stop them fighting over the `ebner.gripe` DNS record.

Provisioning is therefore `infra/bootstrap.sh`: wrangler commands, idempotent, safe to re-run. `wrangler r2 bucket create` fails on a bucket that exists, so each step checks before it creates. The site Worker and its custom domain are declared in `apps/site/wrangler.jsonc` and applied by CI on every deploy.

What this gives up, stated plainly: **nothing detects drift.** Change a resource by hand in the dashboard and no plan will tell you. At six static resources that is worth the simplicity. Revisit it if the account ever grows a second environment.

## Model routing (`apps/generator/config/models.yaml`)

| Step | Default model | Provider |
|---|---|---|
| Write entry | Claude Opus 5 | Anthropic API directly |
| Logic and consistency check | Claude Sonnet 5 | Anthropic |
| Language edit | Claude Sonnet 5 | Anthropic |
| State extraction (JSON) | Claude Haiku 4.5 | Anthropic |
| Sketch images | configurable (e.g. Gemini image models) | OpenRouter |

Changing a model must be a one-line config change. Pin exact model IDs — `claude-opus-5`, `claude-sonnet-5`, `claude-haiku-4-5` — and never append date suffixes.

**No prompt caching.** The pipeline makes one Opus call per day and caches are scoped per model, so the three later steps cannot read what the first one wrote. A cache write costs 1.25× the input price and breaks even only on a second read of the same prefix; the next run starts 24 hours later, long after the entry expires (5 minutes by default, 1 hour at most). Caching here is a 25% surcharge for nothing. Revisit only if the consistency check ever loops back into a rewrite — a second Opus call on a warm prefix would change the arithmetic.

**Set `effort` deliberately.** Opus 5 runs adaptive thinking by default at `effort: high`, and thinking tokens bill as output. That one inherited default is the largest line in the bill, roughly two thirds of it. Choose the level on purpose in `models.yaml`.

**Budget.** At the assumed context sizes the four-call pipeline costs about **$0.23 per entry — ~$7/month, ~$85/year**; long entries and deep thinking push the ceiling nearer $140/year. Sketches through OpenRouter are a separate, unpriced item. These are estimates from assumed token counts, not measurements — re-check with `count_tokens` once `prompts/diary_pl.md` exists.

## Repository layout

```
ebner/
├── .github/workflows/
│   ├── generate.yml       # daily: write entry, commit to main
│   ├── apply-state.yml    # on merge to main: apply state to D1 + Vectorize
│   ├── review-threads.yml # weekly: thread review PR
│   ├── backup.yml         # weekly: D1 export to R2
│   └── rebuild-state.yml  # manual: replay content/state/ into D1 + Vectorize
├── apps/
│   ├── generator/         # Python: pipeline, RAG, thread logic, images
│   └── site/              # Astro + MDX + Pagefind
├── content/
│   ├── entries/           # one Markdown file per entry, e.g. 0231.md
│   ├── state/             # 0000.json (seed), 0231.json (per entry), 0231_review.json (thread review)
│   └── schema/            # entry.schema.json, state.schema.json — the two sources of truth
├── prompts/
│   ├── diary_pl.md        # step 2: writing (Polish)
│   ├── check_pl.md        # step 3: logic and consistency, and the merge gate
│   ├── edit_pl.md         # step 4: language edit
│   ├── state_pl.md        # step 5: state extraction
│   ├── style_samples/     # approved style samples
│   └── edit_pairs/        # before/after pairs from human edits in PRs
├── samples/               # reference sample weeks
├── db/
│   ├── migrations/        # plain SQL migrations for D1 (applied with wrangler)
│   └── wrangler.jsonc     # D1 binding for migrations only — the site never uses it
├── infra/
│   └── bootstrap.sh       # wrangler: R2 buckets, media domain, D1, Vectorize
└── CLAUDE.md
```

## Entry format

Each entry is a Markdown file with frontmatter (English keys). The schema lives in exactly one place — `content/schema/entry.schema.json`. The generator validates against it as a guard *before opening the PR*, and the Astro content collection builds its schema from the same file. Neither side hand-maintains a second copy of the `kind` enum: a drifted enum would otherwise pass unnoticed, land in `main`, and only then break the site build, with the entry already in the canon.

```yaml
---
day: 231
title: "Dzień 231. Orbita Hoonu"
location: orbita-hoonu   # entity id, not free text
kind: travel            # travel | new_job | continuation | resolution | adventure | quiet | note | documents | stopover
threads: [vell-archive, flower]
image: null             # R2 object key of the sketch, or null
---
```

MDX components available in entries: `<Sketch>` (renders `srcset` from R2 variants) and `<Document>` (in-world documents: invoices, protocols, letters).

The state change for each entry lives next to it in `content/state/NNNN.json`, validated against `content/schema/state.schema.json` — a file, for the same reason the frontmatter schema is one. The generator emits against it and `apply-state.yml` reads against it; the writing prompt describes the shape but does not define it.

A state file carries only the **delta**: entities introduced, hops travelled, thread operations, facts opened or closed, fragments to index. The entry row itself is derived from the Markdown file and never restated. It is committed together with the text, so the two never drift apart and a single revert takes both.

## Cold start

Day 1 is the first entry, not the first job. Ebner is an experienced repairman with a ship, debts and a long-standing grudge against the competition — he has simply never kept a diary before. The world is defined; the chronicle is empty.

The seed is `content/state/0000.json`: an ordinary state file in the ordinary schema, applied down the ordinary path. It carries

- **entities** — Ebner, his ship Hanna, Holdmark Serwis, his home port, and wherever he happens to start;
- **facts** with `source_entry` NULL and `valid_from` 0 — who Ebner is, what Hanna is, what Holdmark Serwis is, where the debts come from;
- a handful of **`world_description` fragments**, so retrieval has something to ground on from the first entry instead of returning nothing for the first dozen.

It carries no entries, no threads and no closed history. Threads open organically from entry 1 onward.

Because the seed is a state file and every entry has a state file, **D1 is fully rebuildable from `content/state/`** — replay the files in filename order from `0000.json` upward. That is what makes D1 a projection rather than a second source of truth, and why the weekly D1 export is a convenience rather than a safety net.

## Workflows

### `generate.yml` (daily, cron)

`concurrency: group: ebner-state` shared with `apply-state.yml`, so state is never read and written by two runs at once.

**One entry in flight at a time**, enforced by the shared concurrency group rather than by looking for open work. `apply-state.yml` queues behind this run instead of cancelling it: a half-applied state is worse than a late one.

**Publication is daily and unattended. Chronology is not.** Exactly one entry file is published per real day, automatically, with no human in the loop. What varies is the *in-world* date: `day` is strictly increasing but **not consecutive**.

A gap is not a missing entry — Ebner kept no diary that week, or nothing was worth writing down. The randomiser picks the step from a weighted distribution in `apps/generator/config/rhythm.yaml`: heavily weighted to +1, occasionally a few days, **hard-capped at 7**, with the larger steps reserved for `travel` and `stopover`. A week-long gap is often its own explanation: the journey *was* the week.

The cap is not cosmetic. At one entry per real day, the *mean* step decides how fast the world ages — a mean near 2 makes a year of publishing roughly two years of Ebner's life, and keeps this a working diary rather than the chronicle of an era. The hard cap stops a single bad roll; the mean stops slow drift, which is the more dangerous of the two because no single entry looks wrong.

Because no unmerged entry can exist when a run starts, the previous entry is always the highest `day` in D1 — no reservation, no collision.

1. **Assemble context:** current world state from D1 (active threads, closure pressure, valid facts, current location with its `parent` chain, recently visited places), RAG results, randomized parameters (entry kind, length, in-world day step, optional hint).
2. **Write** the entry (prompt: `prompts/diary_pl.md`).
3. **Logic and consistency check** against state, facts and related entries.
4. **Language edit** (Polish prose only; keeps colloquial register where intended).
5. **Extract state** into `content/state/NNNN.json`.
6. **Sketch** (optional): if the state defines `sketch`, generate the image, create WebP/AVIF variants in several widths, upload to `ebner-media` with content-hash names, set `image` in frontmatter.
7. **Guard, then commit** the entry and its state file to `main` as the bot. Nothing is written to D1 or Vectorize at this point — the push triggers `apply-state.yml`, which does that.

**No pull request.** The guards run inside the generator — `save` writes both files, runs the state guard across the whole corpus, and deletes both again if it refuses — so by the time anything could be proposed for merge it has already passed. A pull request would add a gate with nothing left to gate.

Worse, it would add a gate that only looked like one. A PR opened with `GITHUB_TOKEN` does not trigger other workflows, by GitHub's own design against recursion, so its checks would never run and auto-merge would merge it unexamined. A bogus gate is more dangerous than none, because it reads as protection.

The bot therefore commits straight to `main`, which triggers the deploy and `apply-state.yml` exactly as any other push does.

**What a missing entry means.** Something is wrong — the run failed, the model declined, or the guards rejected the entry — and the workflow run says which. There is no innocent explanation for a missing entry, which makes the signal sharp: nothing is ever waiting on a person.

`prompts/edit_pairs/` was meant to collect the differences between generated and merged text, to feed later prompts with examples of the owner's corrections. With no review step there are no such differences, so it stays empty until someone edits an entry by hand after the fact.

### `apply-state.yml` (on push to `main` touching `content/state/`)

Same concurrency group. Applies the merged state file to D1 in one transaction, splits the entry into fragments, embeds them with Workers AI and upserts them into Vectorize. Idempotent: re-running for the same day must not duplicate anything.

A state file with no matching entry is a supported case, not an error — `0000.json` (the seed) and `NNNN_review.json` (thread reviews) both take this path. Only fragment-splitting is skipped; everything else applies unchanged.

### Site deploy (`wrangler deploy` from Actions)

Cloudflare Pages was absorbed into Cloudflare Workers, and the Git integration went with it — `wrangler pages project create` now delegates to the Workers implementation. The site is therefore a **static assets-only Worker**: no `main`, no server code, just the Astro output from `apps/site/dist`.

Configuration lives in `apps/site/wrangler.jsonc`, including the `ebner.gripe` custom domain binding. GitHub Actions builds the site and runs `wrangler deploy`, so the Node version, pnpm, the Pagefind index and the map build all stay under our control instead of Cloudflare's build image. Runs on Node 24 (`.node-version`); wrangler 4 requires at least 22.

The site never talks to D1 or Vectorize: it builds everything it needs from `content/`.

### `review-threads.yml` (weekly)

Runs the thread review pass and opens a PR with proposed thread changes (close, merge, put to sleep) as a state file named `NNNN_review.json`, where `NNNN` is the latest entry day at review time. It merges automatically like any other PR, subject to the same guards.

The underscore is load-bearing. D1 is rebuilt by replaying state files in filename order, so the name must sort *after* the entry it follows and *before* the next one. `0231_review.json` does — `_` is 0x5F, above `.`. The more natural `0231-review.json` sorts *before* `0231.json`, because `-` is 0x2D, below `.`, and would silently apply the review ahead of the entry that triggered it.

### `backup.yml` (weekly)

Exports D1 (`wrangler d1 export`) to `ebner-backups` with a date in the key. D1 Time Travel covers short-term recovery. Vectorize is not backed up: it can be rebuilt from D1 fragments by re-embedding.

This is convenience, not insurance. The real backup is git — D1 replays from `content/state/`, and Vectorize re-embeds from the result.

### `rebuild-state.yml` (manual)

Same concurrency group. Drops D1, replays every `content/state/*.json` in filename order, then re-creates the Vectorize index and re-embeds the fragments. It is the only workflow here that is not unattended — deliberately, because it is the escape hatch. See *Unpublishing*.

## Unpublishing

Publication is automatic and unattended, so the ability to take something down afterwards is what makes that safe. Here it is a real operation rather than a hope, and the reason is the projection rule: D1 holds nothing that is not derived from `content/state/`.

To remove entry `NNNN`:

1. Delete `content/entries/NNNN.md` and `content/state/NNNN.json` on `main`. The next deploy rebuilds without it and the entry leaves the site.
2. Run `rebuild-state.yml`. D1 and Vectorize are rebuilt from what remains, so world state no longer holds anything that entry introduced — threads it opened, facts it recorded, places it named.

**The rebuild is self-checking.** If a later entry depends on what was removed — it continues a thread that no longer opens, or departs from a place that no longer exists — replay fails that entry's guards and names it. A silent half-removal is not possible, which is the property that makes this trustworthy enough to rely on.

**What it does not do is rewrite prose.** Later entries that *mention* the removed events still mention them. When replay names a dependent entry, the choice is to remove that one too or to amend its text and state. This is the one part of unpublishing that is a judgement call, and it stays with the owner.

## World state (D1)

D1 is a **projection of `content/state/`**, rebuilt by replaying those files in filename order. Nothing may live in D1 that cannot be reconstructed that way.

Tables (English names, SQLite types):

- `entities` — `id` (slug), `kind` (person | place | organisation | ship), `name` (Polish), `parent` (self-reference, nullable — geographic nesting: moon → planet → system), `summary` (Polish), `first_entry`, `last_entry`, `reference_count`.
- `travel` — `entry_day`, `seq`, `from_entity` (nullable), `to_entity`. One day may hold several hops; `seq` orders them.
- `entries` — `day`, `title`, `location` (FK to `entities`), `kind`, `body`, `published_at`.
- `threads` — `name`, `type` (short | medium | long | recurring), `status` (active | closed | dormant), `closure` (resolved | abandoned | merged), `reference_policy` (develop | mention | may_return | do_not_touch), `opened_day`, `last_used_day`, `closed_day`, `planned_entries`, `cooldown_days`, `reference_count`, `summary`.
- `facts` — `content` (Polish), `subject` (FK to `entities`), `valid_from`, `valid_to` (NULL = still valid), `source_entry` (nullable: NULL for seed facts from `0000.json`, which use `valid_from` 0).
- `fragments` — `id`, `entry_day`, `kind` (scene | document | punchline | world_description), `content`.
- `fragment_threads` — many-to-many between fragments and threads.

`entities` deliberately has no `status` column. A destroyed planet or a dead character is not a state of the entity — it is a fact that stopped being true, and `facts.valid_to` already says exactly that. Two places describing the same change would drift apart.

## Geography, travel and technicalities

Ebner is a traveller, so position is world state, not decoration.

**Where he is.** `entries.location` is where the entry *ends*. Context assembly feeds the prompt his current location, its `parent` chain, and the places he visited recently. Without it, an entry is written with no idea where the previous one left him — he lands two systems away with no journey in between, or returns to a planet he has just left.

**How he got there.** `travel` rows are the record of movement, not a derivation from consecutive entries: a `kind: travel` entry is precisely about the hops in between, and reading movement off consecutive pairs would lose every one of them. The two representations must agree, which is a guard, not a hope.

**The world keeps growing, and some of it recurs.** This is a travelogue: new worlds must keep arriving, roughly one new destination every four to six entries. The randomiser schedules that rather than leaving it to chance (`new_world` in `rhythm.yaml`), because growth left to emergence either stops or floods.

There is no cap on entity rows. A new destination usually brings its containment chain — system, planet, station are three rows for one place — and counting rows would block the most ordinary entry in the cycle: arriving somewhere new for a job. What is limited instead is what *becomes* an entity at all: places Ebner works at, stops at, or will return to. Scenery passed on the way stays in the prose and needs no id.

The failure this guards against is narrower than it first appears: not many places, but **many places and no returns** — a world that is a list of single-use names where nothing accumulates. So the pressure runs both ways. Context carries recently visited places *and* places not seen for a while, and the writer is pushed to revisit as often as to discover.

**The map is topological, never spatial.** No coordinates — nobody can assign them consistently, and hard astronomy is tonally wrong for a grotesque diary. The site draws a graph from `travel` edges and lays it out client-side. It shows route and sequence and deliberately shows **no durations**: a map that states no times cannot contradict the prose. It is built from `content/`, never from D1 — D1 is a projection of `content/state/`, so the site computes the same projection at build time.

**Technicalities: vague on purpose.** Travel times, ship parameters, obstacles and upgrades are where a long-running diary quietly builds itself a prison — every figure that enters the canon binds every later entry. `prompts/diary_pl.md` therefore steers away from hard numbers. "The flight dragged on and Hanna shed a compressor somewhere over Vell" commits to nothing; "three days and four hours" commits forever. Grotesque with *internal* logic, not physical logic.

When the prose does commit to a figure — and it will — that figure becomes a **fact** with `valid_from`, its subject the ship or the route. A later upgrade does not contradict it: the upgrade closes the old fact with `valid_to` and opens a new one. That is what those columns are for, and no new machinery is needed. An obstacle on a route has the same shape: a fact about a route, with a validity range.

**This class of consistency is not guardable, and this document says so rather than pretending otherwise.** Every guard here is binary and machine-checkable. "Is three days plausible for this route with the current drive" is not, and a guard with a tolerance threshold would only kill entries at the margins. Two softer layers cover it instead, both already in the pipeline: retrieval surfaces what has previously been said about this route and this ship (prevention), and the **logic and consistency check** step is an LLM judging fuzzy consistency, which is the right tool for the job (detection).

Because publication is unattended, that check is also *enforcement*. A hard contradiction against recorded state — a fact already closed with `valid_to`, a `do_not_touch` thread, a geographic impossibility — blocks the merge. Softer doubts about phrasing or tone are recorded on the PR and do not block: a false positive there costs an entry and buys no safety.

## Retrieval

- Vectorize stores only `fragment id → vector`. All filtering logic lives in D1.
- Query flow: embed the query → Vectorize top 50 → D1 filters candidates by thread status, `reference_policy`, cooldown and fact validity → take the best few.
- Never return fragments of `do_not_touch` threads; penalize recently referenced threads.
- Only facts with `valid_to IS NULL` go into the prompt.
- Each retrieved fragment is labeled in the prompt with its thread status and policy, e.g. `[closed, mention only]`.
- When an entry involves travel, retrieval also surfaces what has previously been stated about that route and about Hanna — the prevention layer for technicalities.
- **Index sparingly** to stay within the Vectorize free tier: at most ~5 fragments per entry (scenes, world descriptions, punchlines), not every paragraph.

## Thread discipline (enforced in code, not only in the prompt)

- At most 5 active threads (recurring jokes counted separately, at most 3).
- A new thread may be opened only if there is room.
- Threads past their planned length or unused for too long get a "close or abandon soon" instruction in the next prompt.
- Weekly review proposes closing, merging or putting threads to sleep, and applies its own proposal unattended. The owner can revise any of it afterwards, by editing the review state file and letting it re-apply.
- Weekly balance: at least as many threads closed as opened.

## Guards (there is no test suite)

This project has no automated tests, by decision, and no human reviewing entries before they publish. Guards are therefore not one layer of defence — they are the **only** one. Nothing else stands between a bad state change and the canon.

Failures here are silent, which is what makes them dangerous: the owner reads entries, not the database. A retrieval filter that leaks a `do_not_touch` fragment, a thread duplicated by a re-run, an expired fact reaching the prompt — none of these raise anything. They produce an entry that is merely *slightly* wrong. And because entries become source material for later entries, **a state error bakes itself into the canon** and within days there is nothing left to undo.

Two rules make guards workable as the only layer:

- **Guard at write time, not read time.** Check the invariant immediately before state is written to D1, so corruption never enters. The same check on the read path only reports damage already done.
- **Fail the run, never warn.** A warning in Actions logs is a warning nobody reads. A broken invariant must kill the workflow — which turns it into a missing entry, which is exactly the alert this project already relies on.

What to guard: `apply-state` idempotency, `day` strictly greater than every existing day (chronology is monotonic, not consecutive), the day step within the cap from `rhythm.yaml`, the thread ceilings (5 active, 3 recurring), the weekly closed-vs-opened balance, cooldowns, `reference_policy` filtering, fact validity, and frontmatter against `content/schema/entry.schema.json` before the PR is opened.

Geography adds four more:

- a new entity whose normalised name is close to an existing one is rejected — name drift is how a world dies quietly;
- `from_entity` of an entry's first hop must equal the `location` of the **previous entry** — the previous entry, not the previous day: days are not consecutive;
- `location` of an entry must equal `to_entity` of its last hop — the net under keeping `travel` as its own record;
- `parent` must not form a cycle.

Where they live: in the generator, alongside the code that writes the state. One exception is provisional — `apps/site/scripts/check-state.mjs` runs the state guards in CI today because the generator does not exist yet. Delete it when the generator takes them over; two implementations of one invariant is the drift this document exists to prevent.

What guards explicitly do **not** cover: travel times, ship parameters and other technicalities. See *Geography, travel and technicalities* for why, and for the two layers that handle them instead.

## Media

- `ebner-media` is public only through `media.ebner.gripe` (R2 custom domain, Cloudflare CDN).
- Objects are immutable and named by content hash; served with long-lived immutable caching.
- Only the generator writes to the bucket (scoped API token).

## Build order

0. World canon: `content/state/0000.json` (seed entities, facts and world fragments) and `prompts/diary_pl.md`.
1. Repository skeleton, `bootstrap.sh` (R2, D1, Vectorize), D1 migrations.
2. Generator runs locally and writes an entry + state file.
3. `generate.yml` with bot PRs; Astro site deployed as a Worker from Actions.
4. `apply-state.yml`: state into D1, fragments into Vectorize; retrieval, thread discipline, geography and travel continuity. `rebuild-state.yml` is the same machinery run across every state file, so it arrives with it.
5. Pagefind search on the site.
6. Travel map on the site: a graph of `travel` edges laid out client-side, with no durations.
7. Sketches, media pipeline, MDX components.
8. `review-threads.yml` and `backup.yml`.

## Visual direction (reference only)

The look lives in the `claude.ai/design` project *Trzy kierunki wpisu Ebner* — `Ebner - projekt.dc.html`, built on direction 8. It is a **visualisation, not a specification**. Take colour, type and texture from it; never take functional requirements. Where it implies data, workflows or views this document does not have, this document wins.

- Metaphor: Hanna's worn workshop terminal — gauge scales, readouts in recessed fields, stencil lettering, document plates with a riveted strip, label tape instead of stamps.
- Type: Archivo (body), Archivo Narrow 700 (titles), DM Mono (readouts and in-world documents).
- Palette: muted greys `#4B4944`, `#9C998F`, `#1E1D1A`, with one rust accent `#8F4520`. Day and night modes.
- Breakpoints: desktop 1060, mobile 390.
- Polish UI vocabulary: threads appear to the reader as **sprawy**. The identifier stays `threads`.

## Creative direction (summary; the prompt is authoritative)

- Form: Ebner's personal work diary, first person, dated headers ("Dzień N. Miejsce").
- Science fiction first: space travel, adventure and concrete alien worlds are central.
- **Most entries should be funny.** Grotesque and absurd is the foundation of the cycle, not a seasoning on top of it.
- **Absurd must have logic**: a rule, custom or trait taken literally and followed to its end — never random oddity. Be bold with scale, and collide the cosmic with the clerical: courts, invoices, stamps, queues, instalments. It works best in dialogue, where someone answers something preposterous entirely seriously. Recurring absurdities should be allowed to grow.
- **Travel is a source of events, not an interlude**: breakdowns in vacuum, strange signals, customs, detours, wrecks, stowaways, places that are not on any map.
- **Aliens are not humans in costume.** Give a world its physics, climate, gravity, day length, biology. Each civilisation lives by one rule that follows from a rational premise and is carried to its end — revealed through events and detail, never explained in a lecture.
- **Danger is real.** Ebner can be afraid, hurt, lost, or out of money and equipment.
- **A resolution never arrives by chance or from outside.** It follows from what Ebner did, or from the logic of the world.
- Three registers, mixed freely: dry report, a tradesman's colloquial yarn, and — rarely — quiet melancholy. At most every fifth entry carries the third, and never as a punchline. Quiet is not melancholy: most quiet entries are simply uneventful, not sad.
- Entries vary in kind and length; many are short; stories may span several days and need not resolve.
- **Not every entry is an event.** `kind: quiet` exists for the days when nothing happened: a valve fixed, a meal, Hanna still knocking. That is the texture of an actual working life, and it is what makes the adventures land.
- **Days are not consecutive.** The diary skips. A gap needs no apology and is frequently explanation enough by itself.
- No Stanisław Lem characters, names, plots or frames (no "star diaries", no numbered voyages).
- Recurring elements: Ebner's ship Hanna, the competitor Holdmark Serwis, unpaid debts.
- Vague about technicalities on purpose: travel times, ship specifications and distances stay impressionistic. Every figure the prose commits to becomes a permanent constraint on every entry that follows.
- Places recur. Returning to somewhere known is usually better than inventing somewhere new.

See `prompts/diary_pl.md` for the full writing prompt and `samples/` for approved sample entries.
