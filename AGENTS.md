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
