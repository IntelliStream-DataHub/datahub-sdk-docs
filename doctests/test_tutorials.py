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
    links = plans_mod.chain(slug, lang, ALL_PLANS)
    sections = []
    for link in links:
        link_page = _page(link)
        link_blocks = link_page.of_lang(lang)
        if not link_blocks:
            pytest.fail(f"{link.page} has no {lang} blocks, but its plan declares a {lang} scenario.")
        link.lang(lang).validate_injects(link_blocks, link.page)
        link.lang(lang).validate_replacements(link_blocks, link.page)
        sections.append((link.lang(lang), link_blocks, link.page))

    # A tutorial whose prerequisites this environment cannot supply is skipped with
    # the reason, not failed: the page may be perfectly correct.
    for link in links:
        llp = link.lang(lang)
        absent = [v for v in llp.requires_env if not env.get(v)]
        if absent:
            pytest.skip(f"{link.page} needs {', '.join(absent)} in doctests/.env to be tested honestly")
        for module in llp.requires_python:
            if lang == "python" and importlib.util.find_spec(module) is None:
                pytest.skip(f"{link.page} needs the `{module}` package: pip install {module} into doctests/.venv")

    # An API-reference page's blocks are independent examples; a tutorial's are a
    # sequence. `independent` picks which, and the runs below differ only in whether
    # the page's blocks arrive as one program or several.
    if lp.independent:
        programs = [
            runners.compose(lang, sections[:-1] + [(lp, [block], plan.page)])
            for block in lp.select(sections[-1][1])
        ]
    else:
        programs = [runners.compose(lang, sections)]

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
    own_creations: set[str] = set()
    for link_lp, link_blocks, _ in sections:
        selected = link_lp.select(link_blocks)
        for ids in entities.owned("\n".join(b.body for b in selected),
                                  include_edge_refs=False).values():
            own_creations.update(ids)

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
        for kind, ids in plans_mod.merged_owns(links).items()
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

    try:
        assert result.ok, _explain(plan, lang, result)

        for fragment in plan.expect_stdout:
            assert fragment in result.stdout, (
                f"{plan.page} [{lang}] ran, but its output never contained {fragment!r}.\n"
                f"The page tells the reader to expect that. Output was:\n"
                f"{runners.tidy(result.stdout, 1500)}"
            )

        missing = backend.missing_entities(cli, plan.expect_exists, plan.settle_secs)
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
