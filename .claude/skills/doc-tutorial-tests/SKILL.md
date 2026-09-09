---
name: doc-tutorial-tests
description: Run, write and repair the end-to-end tests that prove every tutorial in these docs still works against a live DataHub backend. Use when a doc-tutorial test fails, when adding or editing a page that contains runnable code, when a page needs a test plan, after an SDK upgrade, or when asked whether the documentation still works. Triggers on "doctest", "doc tests", "tutorial test", "does this tutorial still work", "the docs are broken", "add a test for this page", "UNTRIAGED.toml", "test plan for a doc page", "doctests/plans".
---

# Documentation tutorial tests

Proves one thing and proves it properly: **the code on a doc page, run in the order
the page presents it, against a real backend, does what the page says it does.**

Not that snippets parse. Not that method names look plausible. That a reader who
follows the page gets the result the page promises.

## The shape of it

```
docs/quickstart.mdx ──┐
                      ├─► compose ─► one program ─► run live ─► assert on the backend
doctests/plans/…toml ─┘
```

The code always comes from the page, never from a copy. A plan supplies only what
a reader has that the page does not restate, and declares what must be true
afterwards. The consequence worth internalising: **there is nowhere to "fix" a
failing test except the documentation.** That is deliberate.

## Run it

```bash
./doctests/setup.sh                        # once — venv + SDK built from source
./doctests/run.sh                          # every planned tutorial, Python
./doctests/run.sh doctests/test_harness.py doctests/test_api_surface.py   # no stack needed
./doctests/run.sh -k quickstart            # one page
./doctests/run.sh --langs all              # Java and Rust too
./doctests/run.sh --keep -s -k tutorial    # leave the data behind and watch it run
```

Needs a reachable stack in `doctests/.env` (see `.env.example`). **Never point it at
production** — it creates and deletes entities under the docs' own external ids.
No backend configured means skips, not failures: 165 structural checks still run, and
the API-surface checks run whenever the SDK is installed. That is what makes the suite
useful in CI without a stack, and what `.github/workflows/doc-tutorials.yml` leans on.

## Reading a failure

The report names the doc line. Work the causes in this order — the first one that
fits is almost always right.

| What you see | What it means | Where to fix |
| --- | --- | --- |
| `ImportError` / `AttributeError` on an SDK name | The SDK renamed or removed it; the page is behind. | The page. |
| HTTP 400 with a field name | The page's payload is wrong (a missing `unit`, a bad `value_type`). | The page. |
| `NameError` on a variable | The page uses something no block defines. Either the page has a gap, or the plan's prologue should supply what the prose establishes. | Usually the page. |
| A blamed line inside `doctests/plans (prologue …)` | The plan's fixture broke, not the tutorial. | The plan. |
| `replacement '…' no longer matches` | A bounded-run substitution went stale because the page changed. | Re-read the page, then the plan. |
| `now has N blocks; plan was written against M` | Someone added or removed a fence. Block numbering has shifted, so the plan may now select different code. | Re-read, update plan and count together. |
| HTTP 500 or 409 on a `create` | Almost always the entity is still there — the plan's `owns` is missing an id, so the sweep left it behind. Check `owns` before believing the server is broken. | The plan's `owns`. |
| `PanicException` | An SDK bug: the bindings panicked instead of raising. | File it. Leave the test red; it is telling the truth. |
| Backend does not hold what the page promises | The program exited 0 without doing the job. Common where a tutorial catches its own exceptions. | The page. |

### The rule

**A red test is a claim about the documentation, so verify it before believing it.**
Reproduce the failure with plain SDK calls, outside the harness, before filing it as a
doc bug. Several failures that looked like documentation defects turned out to be
harness bugs — a retrieve limit above the API's cap, an assertion about a file the page
deliberately deletes, a `[expect]` naming a branch the page only takes sometimes. The
suite is not evidence until its own claim has been checked.

**Never make a test pass by weakening what it checks.** Deleting an `expect`,
dropping a `replace`, or handing the doc code a working import in a prologue all
produce green — over code that is still broken for every reader. If a check is
wrong, say why in the plan comment. If a tutorial is genuinely broken, leave it red
until the page is fixed.

## Adding a plan for a page

```bash
./doctests/bin/triage.py docs/guides/my-page.mdx    # what the page needs to run
./doctests/bin/newplan.py docs/guides/my-page.mdx   # scaffold, pre-filled from the page
```

`triage.py` walks the page's AST and reports the mechanical half: names it uses but
never defines, packages it needs, calls that never return, and the external ids it
creates (including ones minted at run time, which become `prefix_*` patterns). The
judgement half is yours. Read the page as a reader would, and fill in:

- **`requires`** — the page(s) this one continues from, by plan slug. A guide that
  opens "you already have a client" should `requires = ["quickstart"]`, so the
  quickstart genuinely runs first. Never hand-write that setup in a prologue: it
  would keep passing after the quickstart breaks.
- **`prologue`** — only what the prose establishes but no block shows: a `handle`
  callback the page describes, a local file the page says you have, the fixture
  world the page's premise assumes. If you find yourself importing the SDK here to
  make doc code work, stop — you are hiding the bug you were hired to find.
- **`only` / `exclude`** — by default every block of the language runs, concatenated,
  which is what makes it end-to-end. Narrow it when a page carries alternatives
  (sync *and* async) or a complete listing that repeats the steps above it.
- **`[[replace]]`** — bound anything that would never terminate. Every one must still
  match the page, so a rewritten loop fails loudly instead of hanging CI.
- **Leaving a language uncovered** — just omit its section. A plan with no `[java]`
  table already means "no Java scenario"; writing `disabled = "not written yet"` says
  the same thing in three more lines and buries the `disabled` reasons that are
  actually specific. `[blocks]` still pins the language's fence count either way.
- **`requires_env` / `requires_python`** — prerequisites the environment may not have.
  Missing ones skip with a reason; an unconfigurable environment is not a broken doc.
- **`[owns]`** — every external id the page creates, so the run is swept clean before
  and after. Ids minted at run time can be given as `prefix_*` patterns. **Anything a
  prologue or inject creates belongs here too** — a fixture the sweep does not know
  about survives the run, and the next one fails on a duplicate create that reads like
  a documentation bug.
- **`[expect]`** — the point of the whole exercise. Exit code 0 only proves nothing
  threw. State what must exist, how many datapoints must be readable, what the page
  tells the reader they will see on stdout.
- **`requires_once`** — for a page whose job is to *populate* the backend rather than
  teach (`advanced/generate-sample-data` seeds every series the ML recipes read). It
  runs once per session and is not composed in. Such a page keeps its data for the
  rest of the session; the session fixture cleans up at the end.
- **`independent`** — run each block as its own program, with a sweep between them.
  Right for an API reference, where the fences are separate examples and one of them
  deletes what another needs. Wrong for a tutorial, whose steps only mean anything in
  sequence — which is why concatenation is the default.
- **`inject`** — code spliced before one block, for what a reader has only part way
  down the page (step 2 using the arrays step 1 just built under other names).

Test programs may `from tutorial_support import ...` for the things pages leave open:
`Recorder` (a placeholder that remembers what it was handed and returns something
usable), `take` (bound a listener by count and wall clock), `feed` (write datapoints in
the background so a subscription actually receives traffic), `wait_for_datapoints`
(let an eventually-consistent write land before the page reads it back).

A page can carry more than one plan when it makes more than one promise — see
`tutorial.toml` (the step-by-step path) beside `tutorial-complete.toml` (the finished
program). Coverage is keyed by the page a plan points at, not the plan's filename.

## Coverage

Every page containing runnable code must be either planned or listed in
`doctests/plans/UNTRIAGED.toml` with a reason. A new tutorial is **red until someone
decides**, which is what stops coverage from quietly decaying.

`UNTRIAGED.toml` is currently **empty**: every page with runnable code has a plan.
Keep it that way — it is a backlog, not a waiver, and an entry added there is a
tutorial nobody is checking.

```bash
./doctests/bin/newplan.py --untriaged "needs a populated asset model" docs/industries/x.mdx
```

## Known traps in this codebase

- **A series created without `value_type` becomes a long column.** Inserting a float
  into it fails with 422 `Could not parse value: 11.4 to long`. Verified directly:
  `value_type="float"` accepts the same insert. So `value_type` is effectively
  required for any float series — `review/API-SURFACE.md` says otherwise and is wrong.
- **`unit` is required on timeseries create** — omitting it is HTTP 400
  `timeseries.unit.not.blank`. The single most common bug in these docs.
- **Aggregates are asymmetric** — request `"avg"`, read back `.average`. There is no
  `count` aggregate; asking for one is silently dropped.
- **`retrieve` is named differently per language** — Java `retrieve`, Python and Rust
  `retrieve_datapoints`.
- **Java `.unit(x)` is a trap** — it aliases `setUnitExternalId` and leaves the required
  `unit` blank. Use `.setUnit(x)`.
- **Rust aggregates need `Some(vec![...])`** — a bare `vec![...]` does not compile.
- **Reads are eventually consistent, and the graph lags most.** `fetch_related` returns
  nothing for a second or two after the edges are written. Never assert — or build a
  fixture — immediately after a write; the harness polls (`settle_secs`) and so should
  any check you add.
- **`delete` and `by_ids` take bare external-id strings on every service.** Some also
  accept an `IdCollection`; `resources`, `events` and `files` raise `TypeError` for it.
  This one is worth knowing because the sweep swallows exceptions by design, so the
  wrong shape does not fail — it silently leaves entities behind, and the *next* run
  fails on a duplicate create that looks exactly like a documentation bug. If a page
  fails with HTTP 500 on a create, check for leftovers before believing the page.
- **Duplicate creates answer differently per service.** Timeseries gives a clean 409;
  `resources.create` gives **500** with an empty body; `datasets.create` returns an
  **empty list** and the page then fails on `[0]`. A 500 on create usually means the
  entity is already there, not that the server is broken.
- **A deleted file keeps its path.** Delete moves a file to trash and nothing purges
  it, so re-uploading to the same path fails permanently. Pages that upload can be run
  once per stack; see the note in `plans/reference__files.toml`.

`review/API-SURFACE.md` holds the fuller per-language method inventory. Verify against
the SDK source before trusting either — both drift.
