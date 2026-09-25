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

**Your SDK checkouts have to be on upstream `main`.** The docs describe the default branch
of each SDK repository, so that is the only thing a result here means anything against. Every
tier refuses to run from a checkout behind it, names the commit and the distance, and says so
rather than reporting the pages as broken — which is what it used to do, silently, for eight
reference pages whose Java examples were correct all along. The checkouts are matched to
upstream by repository URL, not by remote name: a fork whose default branch is an old `master`
would otherwise look current. To test an SDK change that is not merged yet, say so with
`DOCTEST_ALLOW_SDK_DRIFT=1`. The Python bindings are checked the same way, through the
checkout their editable install records, because a venv keeps what was compiled into it long
after that checkout has moved on.

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
| `test_api_surface.py` | Checks every SDK name and service method the docs use against the built SDK. Needs the SDK, not a backend. |
| `compile_check.py` | Composes each page's Java and Rust blocks into one file per page and compiles them all in one `javac` and one `cargo check`. |
| `test_compile.py` | One test per (language, page): the examples compile against the SDK, errors reported at the doc line. Plus controls: synthetic pages with a known result, compiled beside the docs, that fail if a compiler upgrade changes what the tier can see. Needs the SDKs and toolchains, not a backend. |
| `test_harness.py` | Tests the guards themselves. Needs neither. |
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

## How the tests themselves were checked

A suite that blames the wrong thing is worse than none, so each tier was checked against
known answers on 2026-09-16, and the checks that can run unattended now do:

- **Compile tier.** A hand-fixed page compiles clean; a missing method, type or import
  fails at exactly its line; a reader-supplied name passes and does not hide an error on
  the next line. Every passing page was then broken on purpose (a method renamed, a type
  renamed): all 66 caught, after two blind spots in the Java classifier were found this way
  and fixed. The controls in `test_compile.py` keep those answers pinned.
- **Structure tier.** A fence added, a page added, a `replace` gone stale and an `only`
  pointing past the page each fail. The last two did not until `test_plan_still_composes`
  moved those guards out of the live test, which skips without a stack.
- **API surface.** A missing name, a missing service method and a missing module each fail;
  a page fixed to the current SDK passes.
- **Live tier.** On the quickstart: removing the insert, raising in block 2, writing a
  different series than promised and promising unprinted output each fail with the right
  message; running twice passes. Every live failure was then traced to its cause. The
  harness faults found (plans not owning what their page creates, a lookup failure
  reported as a missing entity) are fixed, and `test_plan_owns_what_its_page_creates`
  keeps the first from coming back.

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

Every Java and Rust example is **compiled** against the SDK on every run, by
`test_compile.py`: seventy pages carry each, and a compiler catches most of what goes
wrong with them (a removed method, a field that became an `Option`, a constructor that
grew arguments) without a stack. Unresolved *values and functions* are allowed, because
pages leave `shiftStart` or `latest(...)` to the reader; an unresolved *type*, a missing
method or a wrong argument is a failure. `compile_check.py` explains why the line is
there. It needs:

| | Toolchain | SDK |
| --- | --- | --- |
| Rust | `cargo` | `DOCTEST_RUST_SDK_PATH`, default `../dataplatform-rust-sdk` |
| Java | `javac` (JDK 25) | `DOCTEST_JAVA_CLASSPATH`, or built from `DOCTEST_JAVA_REPO`, default `../datahub-platform` |

A missing one skips with the reason. `--compile-langs none` turns the tier off. Which
blocks compile together comes from the plan: `only`, `exclude`, `independent` and
`imports` under `[java]` or `[rust]` apply to compiling even when that section is
`disabled` for running.

**Running** is a different matter. Python runs by default: its toolchain is the one this
repo can assume, so it is the one that can be held green. Java and Rust runners are wired
(`--langs all`, or `DOCTEST_LANGS=rust`), but only the quickstart has a live scenario in
those languages so far.

## What runs where

The suite is in four tiers, because they need very different things:

| Tier | Needs | Catches |
| --- | --- | --- |
| Structure (under 1s) | nothing | a fence added or removed under a plan, a new page with no plan, a stale bounded-run substitution, a malformed plan, a regression in the harness itself |
| API surface (Python) | the SDK built | a renamed or removed SDK symbol, a service method the docs call that no longer exists, a page importing a package that is not installed |
| Compile (Java, Rust, ~15s warm) | the SDKs and a JDK and cargo | every Java and Rust example that no longer compiles against the SDK, at the doc line |
| Tutorials | a live stack | everything else — whether the page actually works |

Two workflows run them:

- `.github/workflows/doc-tutorials.yml`, here, on every docs pull request. The first
  three tiers need no infrastructure. The fourth runs when a `DOCTEST_BASE_URL` secret
  points at a stack, and posts a notice instead of failing when it does not.
- `.github/workflows/e2e.yml` in **datahub-platform**, on every platform pull request. It
  boots the stack from that pull request's code, compiles the Java examples against that
  pull request's Java SDK, and runs every Python tutorial against the stack, so a change to
  the application that breaks a tutorial shows up in the pull request that made it. This
  is the run that answers "do the docs still work after this update". Both steps are
  non-blocking until the docs are green; the job summary lists the failing pages.

**Never point it at production.** Each run creates and deletes entities under the docs'
own external ids.

The API-surface tier is the one worth running from the **SDK** side: it needs only a
build, so an SDK change that removes something the docs use can fail in the pull request
that removes it, rather than being discovered here months later.

## Working on it

See `.claude/skills/doc-tutorial-tests/SKILL.md` for how to write a plan, how to read a
failure, and the known traps in this API.
