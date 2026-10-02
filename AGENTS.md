# AGENTS.md

Guidance for working in this repo (the DataHub SDK documentation site, built with
Docusaurus).

## Running the docs

The dev server is started with:

```bash
npm start          # runs `docusaurus start`, serves http://localhost:3000
```

`npm install` is needed the first time. To preview on the LAN, add
`-- --host 0.0.0.0 --port 8001`.

## Fonts are self-hosted

Manrope and JetBrains Mono are served from our own origin, not from Google Fonts.
They come from the `@fontsource-variable/*` packages via `src/css/fonts.css`, which
webpack rewrites into hashed files under `build/assets/fonts/`, so the baseUrl is
handled for you. Do not reintroduce an `@import` of a `fonts.googleapis.com` URL.
If you add a weight or style, check the variable axis covers it (Manrope 200 to 800,
JetBrains Mono 100 to 800) rather than reaching for the CDN. The sibling
`../datahub-docs` site is set up the same way; keep the two in step.

## Node version gotcha (system Node is too old)

This project requires **Node.js ≥ 20** (see `engines` in `package.json`), but the
system Node on this host is **v18.19.1**. Running `npm start` with system Node fails
with:

```
[ERROR] Minimum Node.js version not met :(
[INFO] You are using Node.js v18.19.1, Requirement: Node.js >=20.0.
```

### Workaround: use a standalone Node 22.17.0

When you can't (or don't want to) change the system Node, download a standalone
Node 22.17.0 build and put it first on `PATH` for the command. This needs no root
and doesn't touch the system install:

```bash
# Download + extract once (pick any durable dir; ~/.local/node keeps it across sessions)
NODE_DIR=~/.local/node/node-v22.17.0-linux-x64
mkdir -p "$(dirname "$NODE_DIR")"
curl -fsSL https://nodejs.org/dist/v22.17.0/node-v22.17.0-linux-x64.tar.xz \
  | tar -xJ -C "$(dirname "$NODE_DIR")"

# Use it for this shell
export PATH="$NODE_DIR/bin:$PATH"
node --version    # -> v22.17.0
npm start
```

Verify the running dev server is on the standalone Node (not system Node):

```bash
readlink -f /proc/$(pgrep -f "docusaurus start" | tail -1)/exe   # -> .../node-v22.17.0-linux-x64/bin/node
```

Note: if you extract into a temporary/session scratchpad instead of a durable
directory, that copy disappears when the session is cleaned up — re-download it
(or extract to `~/.local`) for a lasting setup.

### Durable fix (preferred long-term)

Install Node 20+ via a version manager so `npm start` just works:

```bash
nvm install 22 && nvm use 22       # or fnm, or a NodeSource apt package
```


## Versions: which SDK these pages describe

The Python and Rust SDKs are pre-1.0 and still change their interfaces between versions (the
platform's `FAQ.md` says so), so one page cannot be right for every release. These are the rules for
that. Nothing like them was written down before 2026-09-17, and by then the examples matched no
SDK version at all: some calls only the released 0.2.0 had, some only `main`.

**`master` describes the development versions, not the latest release.**

| SDK | What `master` describes | How it is released |
| --- | --- | --- |
| Python and Rust | `main` of [dataplatform-rust-sdk](https://github.com/IntelliStream-DataHub/dataplatform-rust-sdk) | `intellistream-datahub-sdk` on PyPI and crates.io, from a `vX.Y.Z` tag |
| Java | the default branch of [datahub-platform](https://github.com/IntelliStream-DataHub/datahub-platform) | `ai.intellistream:datahub-sdk` on Maven Central, from a `vX.Y.Z` GitHub Release of that repo; its version is `version` in that repo's `gradle.properties` |

The platform already works this way: its `docs-check` skill sends a user-visible change here,
"changed API or SDK contracts" included, when the change merges, not when it is released. The
SDK repository's `AGENTS.md` asks the same of SDK changes.

**Every example works in all three languages.** The intro promises it: "every example on the
site gives you a working guide in your language of choice". Where a client lacks a feature, the
reference page says so in its "What each client covers" table. A tab is never left out without
a word.

**Install lines name the latest release, and the quick start says what that means.** A page can
use a call newer than the latest release, so the `:::note` under "1. Install" in
`quickstart.mdx` names the latest release per language. When an SDK is released, update in the
same change: that note's table, and the versions in the install lines of `quickstart.mdx` and
`tutorial.mdx` (the `Cargo.toml` snippets and the Java `implementation(...)` line).

**A release gets a frozen snapshot of the docs**, one per minor version, since in 0.x the minor
version is where breaking changes go. When the SDK tags `vX.Y.0`:

1. `npm run docusaurus docs:version X.Y`. It copies `docs/` into `versioned_docs/version-X.Y/`
   and writes `versioned_sidebars/` and `versions.json`. Cut it from an up-to-date `master`, as
   the last step before the pull request: every merge into `docs/` makes an uncut snapshot stale,
   and there is no refresh command, only delete and cut again.
2. In the docs preset in `docusaurus.config.js`, add `versions: { current: { label: 'Next
   (unreleased)' } }`. Do **not** set `lastVersion`: it defaults to the newest name in
   `versions.json`, so each later cut moves readers on its own. With `routeBasePath: '/'` the
   release is then served at `/` and `master` at `/next/`, both by default.
3. Replace the hardcoded `v1.0` navbar badge with `{ type: 'docsVersionDropdown', position: 'right' }`.
   Not before the first snapshot: with none, the dropdown renders as a lone link labelled after
   the development version, which reads as a release.
4. Rewrite the quick start note in `docs/`: from the first snapshot on, `master` is the "Next"
   version and the note says so. Give the snapshot's own copy of the note the versions that
   shipped, and the same for the install lines it froze.
5. Build, and check that search and the `/next/` pages both work before `sync-docs` publishes it.
   Each version gets its own index (`build/search-index.json`, `build/next/search-index.json`);
   search from a `/next/` page and confirm the hit stays under `/next/`.

Snapshots are cut for released versions only. A version the SDK has not tagged never gets one,
so the version a reader picks in the navbar is always one they can install.

A snapshot is changed only where it was wrong for its own release, a patch release that changes
behaviour included. A new feature goes into `docs/`, never back into a snapshot.

**Where this stands.** No snapshot exists yet, so the published site describes `main`, and a
reader on 0.2.0 can meet calls their version lacks; the quick start note warns them. The steps
above are all that is left to run, and `editCurrentVersion` is already set so a snapshot's "Edit
this page" will point at `docs/`. The first cut waits on the first tagged release; the SDK has
tagged only `v0.2.0`, and bumped `main` past it without releasing, so no number in between gets a
snapshot. Nothing checks these rules automatically yet. The doc tests being added under
`doctests/` are meant to, by building against pinned SDK and platform commits.

## Every example has to be runnable

An example that reads `engine_temperature` is not documentation until something creates
`engine_temperature`. The convention, in three parts:

1. **Seed it.** Guides read the sandbox built by
   [`docs/guides/seed-a-sandbox.mdx`](docs/guides/seed-a-sandbox.mdx); the advanced
   scenarios read the generators in
   [`docs/advanced/generate-sample-data.mdx`](docs/advanced/generate-sample-data.mdx).
   A new page that reads data adds its generator to one of those two, keyed by a letter,
   rather than inventing a third place.
2. **Point at the seed.** A page that reads data it does not create opens with the
   `:::info Needs a sandbox` banner linking to the seed page. A page that creates what it
   reads says so, so a reader knows the difference.
3. **Verify it.** The example ends with a check that can be run and read: a count, a query
   for what was written, or an `assert`. `docs/advanced/sustained-alarm-window.mdx` is the
   reference shape, seed, replay, verify, then run it live.

The seeded signal has to actually exercise the rule the page teaches. The engine series in
the guides sandbox end in a stretch above 110 °C because
`docs/guides/detect-events.mdx` fires above 110, and generator **L** puts four short
transients and one long excursion into the same series because the sliding-window page is
about the difference between them. A generator that produces a plausible signal the example
never reacts to is the failure mode worth watching for.

**The industry pages already follow this**, and were audited page by page on 2026-08-14:
all 40 carry a `## Set up demo data` block and a `## See the result` check, their seeds
create what their bodies read, and the seeded shapes are chosen to make each page's rule
fire (a pressure that sags past the anomaly line, a p99 that breaches the SLO, CO₂ that
leaves the comfort band). The audit found one defect, since fixed: `oil-and-gas/production`
walked outward from two temperature sensors and a `cooling_system` that nothing created, so
its correlation step returned nothing.

Worth knowing if you audit them again: a regex comparing quoted identifiers in the seed
against those in the body reports about thirty false positives, because event types,
metadata keys and f-string-built series names all look like identifiers. Compare only ids
used in *read* calls (`ts=`, `by_ids`, `fetch_related`, `listen`) against everything created
anywhere on the page, and read the survivors by hand.
