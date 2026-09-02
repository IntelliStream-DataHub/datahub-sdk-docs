# Documentation tutorial tests

These tests run the tutorials in `docs/` end to end against a live DataHub backend and
check that each one does what its page says it does.

The distinction that matters: they do not lint snippets or compare method names against
a list. They take the code a reader would copy, in the order the page presents it, run
it, and then ask the backend whether the promised thing exists.

```
docs/quickstart.mdx ──┐
                      ├─► compose ─► one program ─► run live ─► assert on the backend
doctests/plans/*.toml ┘
```

## Quick start

```bash
./doctests/setup.sh          # once: venv + the SDK compiled from source
$EDITOR doctests/.env        # point it at a stack (see .env.example)
./doctests/run.sh            # run every planned tutorial
```

`setup.sh` builds the PyO3 bindings from a local `dataplatform-rust-sdk` checkout
(override with `DOCTEST_RUST_SDK_PATH`), so the docs are tested against the SDK you
actually have — re-run it after an SDK change to see what that change did to the docs.

**Never point `BASE_URL` at production.** Each run creates and deletes entities under
the docs' own external ids (`engine_temperature`, `plant_oslo`, …). With no backend
configured the suite skips rather than fails.

## What each part is

| Path | Role |
| --- | --- |
| `docblocks.py` | Pulls fenced blocks out of `.mdx`, with heading, tab and line number. |
| `plans/*.toml` | Per-page declarations: which blocks, what setup, what must be true after. |
| `plans/UNTRIAGED.toml` | Pages with runnable code and no plan yet — the backlog. |
| `runners.py` | Composes blocks into one program and runs it (Python, Java, Rust). |
| `backend.py` | Config, cleanup sweeps, and the outcome checks. |
| `test_tutorials.py` | One test per (page, language), plus the block-count drift guard. |
| `test_coverage.py` | Refuses to let a page with runnable code go unaccounted for. |
| `entities.py` | Reads which entities a page creates, so a plan can own and assert them. |
| `tutorial_support.py` | Helpers a test program may import: bounded listen, traffic feed, placeholder stubs. |
| `bin/newplan.py` | Scaffolds a plan from a page. |
| `bin/triage.py` | Reports what a page needs before it can run: free names, packages, blocking calls, ids. |

## Writing a plan

`./doctests/bin/triage.py <page>` says what the page needs; `./doctests/bin/newplan.py <page>`
writes the scaffold. The knobs, in rough order of how often they are needed:

| Key | For |
| --- | --- |
| `requires` | Pages this one continues from. Their blocks are prepended, so the guide is tested the way a reader arrives at it. |
| `requires_once` | A page whose job is to *populate* the backend. Runs once per session, not composed in. |
| `prologue` | What the prose establishes but no block shows. |
| `inject` | Code spliced before one block — for what a reader has only part way down the page. |
| `replace` | Bounded-run substitutions. Must keep matching, so a rewritten loop fails loudly instead of hanging. |
| `only` / `exclude` | Narrow the blocks. Needed where a page shows two ways to do one thing. |
| `independent` | Run each block as its own program. Right for API reference, wrong for a tutorial. |
| `requires_env` / `requires_python` | Prerequisites the environment may lack — these skip, not fail. |
| `owns` | Every external id the page creates, so the run is repeatable. `prefix_*` for ids minted at run time. |
| `expect` | What must be true on the backend afterwards. |

## Three design choices worth knowing

**Code is never copied into a test.** Every program is assembled from the page at run
time, so there is no second copy to drift. It also means a failing test cannot be fixed
here — only in the documentation.

**Prerequisites are real runs, not fixtures.** A guide that opens "you already have a
client" declares `requires = ["quickstart"]`, and the quickstart's own blocks are
prepended. Writing that setup by hand would keep the guide green after the quickstart
broke, which is the failure mode this suite exists to prevent.

**Exit code 0 is not a pass.** Several tutorials catch their own exceptions by design —
the memory-ingest daemon must survive a bad tick — so their exit code says nothing about
whether data landed. `[expect]` goes to the backend and checks.

## Languages

Python runs by default: its toolchain is the one this repo can assume, so it is the one
that can be held green. Java and Rust runners are implemented and wired — `--langs all`,
or `DOCTEST_LANGS=rust` — but need `DOCTEST_JAVA_REPO` (a `datahub-platform` checkout,
for the SDK jar) and a Rust toolchain respectively, and their per-page scenarios are
mostly still to be written. A missing toolchain skips with the reason.

## Wiring it into CI

Not configured here, because it needs an infrastructure decision this repo cannot make
on its own: the suite requires a running DataHub stack. Once there is one CI can reach,
a job is small — `setup.sh`, then `run.sh` with `BASE_URL` and credentials from secrets.
Until then, run it locally before merging a change to any page with code on it.

The suite is also worth running from the **SDK** side: an SDK change that breaks a
documented call should fail there, where the change is being made, rather than being
discovered later here.

## Working on it

See `.claude/skills/doc-tutorial-tests/SKILL.md` for how to write a plan, how to read a
failure, and the known traps in this API.
