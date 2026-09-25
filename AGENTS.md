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

The SDKs are pre-1.0 and still change their interfaces between versions (the platform's
`FAQ.md` says so), so one page cannot be right for every release. These are the rules for
that. Nothing like them was written down before 2026-09-17, and by then the examples matched no
SDK version at all: some calls only the released 0.2.0 had, some only `main`.

**`master` describes the development versions, not the latest release.**

| SDK | What `master` describes | How it is released |
| --- | --- | --- |
| Python and Rust | `main` of [dataplatform-rust-sdk](https://github.com/IntelliStream-DataHub/dataplatform-rust-sdk) | `intellistream-datahub-sdk` on PyPI and crates.io, from a `vX.Y.Z` tag |
| Java | the default branch of [datahub-platform](https://github.com/IntelliStream-DataHub/datahub-platform) | not released; its version is `javaSdkVersion` in that repo's `gradle.properties` |

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
   and writes `versioned_sidebars/` and `versions.json`.
2. In the docs preset in `docusaurus.config.js`, set `lastVersion: 'X.Y'` so readers land on the
   release, and label `versions.current` as `Next (unreleased)`. With `routeBasePath: '/'` the
   release is served at `/` and `master` at `/next/`.
3. Replace the hardcoded `v1.0` navbar badge with `{ type: 'docsVersionDropdown', position: 'right' }`.
4. Rewrite the quick start note in `docs/`: from the first snapshot on, `master` is the "Next"
   version and the note says so.
5. Build, and check that search and the `/next/` pages both work before `sync-docs` publishes it.

A snapshot is changed only where it was wrong for its own release, a patch release that changes
behaviour included. A new feature goes into `docs/`, never back into a snapshot.

**Where this stands.** No snapshot exists yet, so the published site describes `main`, and a
reader on 0.2.0 can meet calls their version lacks; the quick start note warns them. The doc
tests under `doctests/` hold the first of these rules: each tier refuses to run against an SDK
checkout behind the branch the table above says it describes, and names the commit it compiled
against in every failure. Until that guard existed the suite tested whatever a contributor had
checked out — on one machine a platform branch 445 commits behind, which reported eight correct
reference pages as broken and passed edits written against an SDK nobody ships. **The stack the
live tier runs against is not covered**: compare the API image's build date against the SDK's
commit yourself before trusting a live failure. The release rules below are still unchecked.

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
