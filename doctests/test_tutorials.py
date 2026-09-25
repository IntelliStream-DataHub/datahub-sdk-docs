"""Run every planned tutorial end to end and check it did what the page claims.

One test per (page, language). The test does what a reader does: take the page's
code from the top, run it against a real backend, and see whether the thing the
page promised exists afterwards.

Failures are formatted to point at the *documentation*, not at the harness — the
whole value of this suite is that a red build names the doc line to go fix.
"""

from __future__ import annotations

import fnmatch
import importlib.util
import re
from pathlib import Path

import pytest

import backend
import docblocks
import entities
import plans as plans_mod
import runners
import scenario
from runners import ToolchainMissing

REPO = Path(__file__).parent.parent
ALL_PLANS = plans_mod.load_all()

# Plans other plans depend on for data. These are tested like any other page, but
# their teardown must not run: a data-seeding page that tidies up after itself
# leaves every recipe that depends on it reading an empty backend. The session
# fixture in conftest owns their cleanup instead.
FIXTURE_SLUGS = {
    dep
    for plan in ALL_PLANS.values()
    for lp in plan.langs.values()
    for dep in lp.requires_once
}

# Traceback frames pointing at the composed program, so its line can be translated
# back into the doc line the reader would be looking at.
_PY_FRAME = re.compile(r'File "[^"]*tutorial\.py", line (\d+)')

# The api answers a tripped quota with RFC 9457 and a 429.
_RATE_LIMITED = re.compile(r"rate-limit-exceeded|429 Too Many Requests")


def _cases():
    """(slug, lang) for every language a plan actually declares a scenario for."""
    out = []
    for slug, plan in sorted(ALL_PLANS.items()):
        if plan.disabled:
            continue
        for lang in docblocks.EXECUTABLE:
            lp = plan.langs.get(lang)
            if lp is not None and not lp.disabled:
                out.append(pytest.param(slug, lang, id=f"{slug}[{lang}]"))
    return out


def _page(plan) -> docblocks.Page:
    path = REPO / plan.page
    if not path.exists():
        pytest.fail(
            f"{plan.path.name} points at {plan.page}, which does not exist. "
            "The page was renamed or deleted — move or delete its plan to match."
        )
    return docblocks.load(path, REPO)


def _explain(plan, lang, result: runners.RunResult) -> str:
    """A failure report that names the doc, the block, and the likely line."""
    lines = [
        f"The {lang} tutorial on {plan.page} did not run cleanly.",
        "",
        f"  exit code : {'timed out after %ss' % result.duration if result.timed_out else result.exit_code}",
        f"  duration  : {result.duration:.1f}s",
    ]

    blamed = {int(m.group(1)) for m in _PY_FRAME.finditer(result.stderr)}
    if blamed:
        where = sorted({result.blame(n) for n in blamed})
        lines += ["", "  failing block(s):"] + [f"    {w}" for w in where]

    if result.stderr.strip():
        lines += ["", "  stderr:", *(f"    {ln}" for ln in runners.tidy(result.stderr).splitlines())]
    if result.stdout.strip():
        lines += ["", "  stdout:", *(f"    {ln}" for ln in runners.tidy(result.stdout, 1500).splitlines())]

    lines += [
        "",
        "  This is a documentation failure until proven otherwise: the code on the page,",
        "  run in the order the page presents it, did not work. Fix the page. Only change",
        f"  doctests/plans/{plan.path.name} if the *plan's* assumptions (prologue, bounded-run",
        "  replacements, owned ids) are what went stale.",
        "",
        "  To reproduce the exact program that ran:",
        f"    ./doctests/run.sh --langs {lang} -k '{plan.slug}' --keep -s",
    ]
    return "\n".join(lines)


@pytest.mark.parametrize("slug,lang", _cases())
def test_tutorial_runs_end_to_end(slug, lang, langs, cli, env, seed, pytestconfig, tmp_path):
    if lang not in langs:
        pytest.skip(f"{lang} not selected (--langs={','.join(sorted(langs))})")

    plan = ALL_PLANS[slug]
    lp = plan.lang(lang)

    # Data-generating prerequisites run once per session; unlike `requires`, they are
    # not composed into this program — the page just needs their data to be there.
    for fixture_slug in lp.requires_once:
        seed(fixture_slug, lang)

    # A guide that opens "you already have a client" is only meaningful when the page
    # it continues from actually ran, so the whole chain is composed into one program:
    # quickstart first, this page last.
    try:
        run = scenario.build(slug, lang, ALL_PLANS, REPO)
    except scenario.MissingBlocks as exc:
        pytest.fail(str(exc))

    # A tutorial whose prerequisites this environment cannot supply is skipped with
    # the reason, not failed: the page may be perfectly correct.
    for link in run.links:
        llp = link.lang(lang)
        absent = [v for v in llp.requires_env if not env.get(v)]
        if absent:
            pytest.skip(f"{link.page} needs {', '.join(absent)} in doctests/.env to be tested honestly")
        for module in llp.requires_python:
            if lang == "python" and importlib.util.find_spec(module) is None:
                pytest.skip(f"{link.page} needs the `{module}` package: pip install {module} into doctests/.venv")

    programs = run.programs()

    # A page's sweep must never reclaim what a session fixture planted: these recipes
    # read series that `generate-sample-data` seeded, and they legitimately name those
    # series in `owns` for the ids they add themselves. Deleting the seed before the
    # run would leave the recipe with nothing to read and blame the doc for it.
    seeded: list[str] = []
    for fixture_slug in lp.requires_once:
        for ids in plans_mod.merged_owns(plans_mod.chain(fixture_slug, lang, ALL_PLANS)).values():
            seeded.extend(ids)

    # What this page builds for itself. A fixture may seed a stand-in under the same
    # id — `generate-sample-data` seeds a placeholder for the anomaly score that
    # predictive-maintenance computes for real — and in that case the page must still
    # be allowed to clear it, or its own create fails as a duplicate.
    own_creations = run.creates()

    def _is_seeded(external_id: str) -> bool:
        # A fixture declares whole families by pattern (`pump_07_*`), while a recipe
        # names the individual series it reads. Comparing the two as plain strings
        # protects nothing, and the sweep then deletes the very data the recipe was
        # about to read — which surfaces as an empty result deep inside the page.
        if external_id in own_creations:
            return False
        return any(fnmatch.fnmatch(external_id, pattern) for pattern in seeded)

    owns = {
        kind: [i for i in ids if not _is_seeded(i)]
        for kind, ids in run.owns().items()
    }

    # Start from a known-empty backend so the page's fixed external ids create
    # cleanly. Without this, a second run of the suite fails on 409s that say
    # nothing about whether the tutorial is correct.
    backend.sweep(cli, owns)

    def _run_all():
        out = []
        for src, lmap in programs:
            # Independent examples are independent: each assumes a clean slate, the
            # way a reader meets it. Without a sweep between them, one example's
            # `create` collides with the next example's, which says nothing about
            # whether either is correct.
            if lp.independent and len(programs) > 1:
                backend.sweep(cli, owns)
            out.append(runners.RUNNERS[lang](src, lmap, tmp_path, env, lp))
        return out

    try:
        results = _run_all()
    except ToolchainMissing as exc:
        pytest.skip(str(exc))
    # Report the first program that failed; the rest still ran, so a page with two
    # broken examples is not hidden behind the first one.
    result = next((r for r in results if not r.ok), results[0])
    source, line_map = next(((s_, l_) for (s_, l_), r in zip(programs, results) if not r.ok),
                            programs[0])

    # A quota is the stack's policy, not the page's mistake. The seeding pages alone make
    # hundreds of requests, so a suite run against a stack someone else is also using can trip
    # the per-user limit, and every page after it would be reported as broken documentation.
    # Both streams: the bindings echo every response body to stdout, so a page that *swallows*
    # the 429 — an empty `items` list, then `[0]` — raises `IndexError: list index out of range`
    # on stderr and leaves the only evidence of the quota on stdout. Reading stderr alone
    # reported five rate-limited pages as broken documentation.
    if not result.ok and _RATE_LIMITED.search(result.stderr + result.stdout):
        pytest.skip(f"{plan.page} [{lang}]: the stack rate-limited this run "
                    "(429, datahub.limits rate-limit-exceeded), so nothing here is a statement "
                    "about the page. Re-run when the window resets, or raise the tenant's limit.")

    try:
        assert result.ok, _explain(plan, lang, result)

        for fragment in plan.expect_stdout:
            assert fragment in result.stdout, (
                f"{plan.page} [{lang}] ran, but its output never contained {fragment!r}.\n"
                f"The page tells the reader to expect that. Output was:\n"
                f"{runners.tidy(result.stdout, 1500)}"
            )

        missing = backend.missing_entities(cli, plan.expect_exists, plan.settle_secs)
        # The same quota, one step later. A page whose writes were refused can still exit 0 —
        # the SDK reports the 429 in the body it echoes, the page never looks — and then the
        # only symptom is that the backend does not hold what the page promised. That is the
        # stack's policy showing up as a missing entity, not the page being wrong.
        if missing and _RATE_LIMITED.search(result.stdout + result.stderr):
            pytest.skip(f"{plan.page} [{lang}]: the stack rate-limited this run, and what the page "
                        f"promises to create is absent ({', '.join(missing)}). The page exited 0, so "
                        "this is about the quota, not the documentation. Re-run when the window resets.")
        # A lookup that errored is not an entity that is missing. The page ran and exited 0;
        # what failed is the harness asking the backend about it — typically an SDK newer
        # than the stack it talks to. Still a failure, because nothing was verified, but
        # one that must not send anyone to edit the page.
        unverifiable = [m for m in missing if "(lookup failed:" in m]
        assert not unverifiable, (
            f"{plan.page} [{lang}] exited 0, but the harness could not check what it left behind: "
            f"{', '.join(unverifiable)}.\n"
            "This says nothing about the page. The harness's own lookup failed, which usually means "
            "the SDK and the stack disagree about an endpoint: compare the API image's date with "
            "the SDK's."
        )
        assert not missing, (
            f"{plan.page} [{lang}] exited 0, but the backend does not hold what the page "
            f"promises it creates: {', '.join(missing)}.\n"
            "An exit code of 0 is not proof a tutorial worked — this check is why."
        )

        short = backend.datapoint_shortfall(cli, plan.expect_datapoints, plan.settle_secs)
        assert not short, (
            f"{plan.page} [{lang}] created its series but the data is not there: "
            f"{'; '.join(short)}."
        )
    finally:
        if not pytestconfig.getoption("--keep") and slug not in FIXTURE_SLUGS:
            backend.sweep(cli, owns)


@pytest.mark.parametrize("slug", sorted(ALL_PLANS), ids=sorted(ALL_PLANS))
def test_plan_still_matches_the_page(slug):
    """Fail when a page gains or loses code blocks under a plan that selects by index.

    This is the guard that keeps the suite honest. Plans address blocks by their
    position among their language's blocks, so an inserted snippet silently shifts
    what every later selection points at — a test that keeps passing while testing
    the wrong code. Pinning the counts turns that into a loud, cheap failure.
    """
    plan = ALL_PLANS[slug]
    page = _page(plan)
    counts = page.counts()

    for lang in docblocks.EXECUTABLE:
        if counts.get(lang) and lang not in plan.blocks:
            pytest.fail(
                f"{plan.page} has {counts[lang]} {lang} block(s) but {plan.path.name} does not "
                f"declare a count for {lang}.\nAdd `{lang} = {counts[lang]}` under [blocks]."
            )

    for lang, declared in plan.blocks.items():
        actual = counts.get(lang, 0)
        if actual != declared:
            pytest.fail(
                f"{plan.page} now has {actual} {lang} block(s); {plan.path.name} was written "
                f"against {declared}.\n"
                "Re-read the page: block numbering has shifted, so the plan's `only`/`exclude` "
                "selections may now point at different code. Update the plan and the count together."
            )


@pytest.mark.parametrize("slug", sorted(ALL_PLANS), ids=sorted(ALL_PLANS))
def test_plan_still_composes(slug):
    """Build every program a plan describes, without running it. No backend needed.

    The checks that a bounded-run `replace` still matches, that an `inject` still has a
    block to land on, and that `only`/`exclude` still name blocks the page has all live in
    `scenario.build` — which, before this test, only ran inside the live tutorial test. With
    no stack configured that test skips first, so a rewritten `while True:` sailed through
    the structure tier and was discovered as a hang the next time someone had a backend.
    Composing here makes those guards hold everywhere, CI included.

    Sections that do not run (`disabled`) are still checked for their block selection:
    the compile tier reads it.
    """
    plan = ALL_PLANS[slug]
    page = _page(plan)
    problems = []
    for lang in docblocks.EXECUTABLE:
        lp = plan.langs.get(lang)
        if lp is None:
            continue
        try:
            if lp.disabled or plan.disabled:
                lp.select(page.of_lang(lang))
            else:
                scenario.build(slug, lang, ALL_PLANS, REPO).programs()
        except (plans_mod.PlanError, scenario.MissingBlocks) as exc:
            problems.append(f"[{lang}] {exc}")
    assert not problems, (
        f"{plan.path.name} no longer lines up with {plan.page}:\n  " + "\n  ".join(problems)
        + "\nThe page changed under the plan. Re-read it and update the plan; do not delete a "
        "`replace` just to get green, it exists to bound a run."
    )


@pytest.mark.parametrize("slug", sorted(ALL_PLANS), ids=sorted(ALL_PLANS))
def test_plan_owns_what_its_page_creates(slug):
    """Every entity a scenario creates must be in some `owns`, or the sweep leaves it behind.

    A leftover does not fail the run that made it. It fails the *next* run, on a duplicate
    create that reads exactly like a broken page — which is how `press_07_oil_temp`,
    `pump_p101_discharge_bar` and the production page's cooling graph each sent a
    reader to fix documentation that was fine. Checked statically, from the same entity
    reader the sweep's assertions use, so it needs no backend.
    """
    plan = ALL_PLANS[slug]
    missing: dict[str, set[str]] = {}
    for lang in ("python",):
        lp = plan.langs.get(lang)
        if lp is None or lp.disabled or plan.disabled:
            continue
        run = scenario.build(slug, lang, ALL_PLANS, REPO)
        owns = run.owns()
        seeded = [p for dep in lp.requires_once
                  for ids in plans_mod.merged_owns(plans_mod.chain(dep, lang, ALL_PLANS)).values() for p in ids]
        for link_lp, blocks, _ in run.sections:
            source = "\n".join([link_lp.prologue, *(i.code for i in link_lp.inject),
                                *(b.body for b in link_lp.select(blocks))])
            for kind, ids in entities.owned(source, include_edge_refs=False).items():
                for external_id in ids:
                    covered = any(external_id == p or fnmatch.fnmatch(external_id, p) or fnmatch.fnmatch(p, external_id)
                                  for p in [*owns.get(kind, []), *seeded])
                    if not covered:
                        missing.setdefault(kind, set()).add(external_id)
    assert not missing, (
        f"{plan.page} creates entities {plan.path.name} does not own, so the sweep leaves them behind "
        f"and the next run fails on a duplicate create:\n  "
        + "\n  ".join(f"{kind}: {', '.join(sorted(ids))}" for kind, ids in sorted(missing.items()))
        + "\nAdd them under [owns] (a `prefix_*` pattern for ids minted at run time)."
    )
