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
