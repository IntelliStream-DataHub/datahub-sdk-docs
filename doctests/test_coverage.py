"""The gate that keeps the suite from quietly falling behind the docs.

A test suite over documentation decays in one specific way: someone adds a page,
nobody adds a test, and the suite stays green while coverage drops. So membership
is checked, not just correctness. Every page carrying runnable code must be either
planned or listed in ``plans/UNTRIAGED.toml`` with a reason. A new tutorial is red
until somebody makes a decision about it, and the decision is recorded in the repo.

``UNTRIAGED.toml`` is a backlog, not a waiver — it is meant to shrink, and these
tests refuse to let it hold stale or duplicated entries.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import docblocks
import plans as plans_mod

REPO = Path(__file__).parent.parent
PAGES = {p.slug: p for p in docblocks.all_pages(REPO)}
RUNNABLE = {slug: p for slug, p in PAGES.items() if any(p.counts().get(l) for l in docblocks.EXECUTABLE)}


def _planned_pages() -> set[str]:
    """Page slugs a plan covers — read off each plan's `page`, not its filename.

    A page can carry more than one plan (a step-by-step walk and the complete
    program are different scenarios over the same tutorial), so coverage is keyed
    by the page a plan points at.
    """
    return {docblocks.slug_for(p.page) for p in plans_mod.load_all().values()}


def test_every_runnable_page_is_accounted_for():
    known = _planned_pages() | set(plans_mod.untriaged())
    orphans = sorted(set(RUNNABLE) - known)
    assert not orphans, (
        "These pages contain runnable code but no test plan:\n"
        + "\n".join(f"  {RUNNABLE[s].rel}  ({_summary(RUNNABLE[s])})" for s in orphans)
        + "\n\nScaffold one with:\n"
        + "\n".join(f"  ./doctests/bin/newplan.py {RUNNABLE[s].rel}" for s in orphans)
        + "\n\nIf the page genuinely cannot be run end to end, add it to "
        "doctests/plans/UNTRIAGED.toml with a reason saying why."
    )


def test_no_page_is_both_planned_and_untriaged():
    both = sorted(_planned_pages() & set(plans_mod.untriaged()))
    assert not both, (
        f"Planned and listed as untriaged at the same time: {both}. "
        "Remove the UNTRIAGED.toml entry — the plan supersedes it."
    )


def test_untriaged_list_has_no_stale_entries():
    ghosts = sorted(set(plans_mod.untriaged()) - set(PAGES))
    assert not ghosts, (
        f"UNTRIAGED.toml names pages that no longer exist: {ghosts}. "
        "Delete the entries so the backlog reflects the docs."
    )


@pytest.mark.parametrize("slug", sorted(plans_mod.load_all()), ids=sorted(plans_mod.load_all()))
def test_plan_is_wellformed(slug):
    """Load and validate every plan, including ones whose scenarios are disabled.

    A plan with a typo in it would otherwise sit unnoticed until the day someone
    enables it.
    """
    plan = plans_mod.load_all()[slug]
    assert (REPO / plan.page).exists(), f"{plan.path.name}: `page` points at a file that is gone."
    if plan.disabled is not None:
        assert plan.disabled.strip(), f"{plan.path.name}: `disabled` needs a reason."
    for lang, lp in plan.langs.items():
        if lp.disabled is not None:
            assert lp.disabled.strip(), f"{plan.path.name} [{lang}]: `disabled` needs a reason."
        assert lp.timeout > 0, f"{plan.path.name} [{lang}]: timeout must be positive."


def _summary(page) -> str:
    return " ".join(f"{l}:{page.counts()[l]}" for l in docblocks.EXECUTABLE if page.counts().get(l))
