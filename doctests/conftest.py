"""Shared fixtures: one backend connection and one language selection per session.

Both are session-scoped because both are expensive in the way that matters — a
token mint per test would dominate the run, and re-deciding the language set per
test would make a partial run's report inconsistent with itself.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import backend
import plans as plans_mod
import runners
import scenario
from docblocks import EXECUTABLE

REPO = Path(__file__).parent.parent


def pytest_addoption(parser):
    parser.addoption(
        "--langs",
        default=os.environ.get("DOCTEST_LANGS", "python"),
        help=("Comma-separated languages to execute (python,java,rust) or 'all'. "
              "Defaults to python: it is the only one whose toolchain this repo can "
              "assume, so it is the one CI can hold green."),
    )
    parser.addoption(
        "--keep",
        action="store_true",
        help="Leave the entities a tutorial created on the backend, for inspection.",
    )


@pytest.fixture(scope="session")
def langs(pytestconfig) -> set[str]:
    raw = pytestconfig.getoption("--langs").strip().lower()
    if raw == "all":
        return set(EXECUTABLE)
    chosen = {p.strip() for p in raw.split(",") if p.strip()}
    unknown = chosen - set(EXECUTABLE)
    if unknown:
        raise pytest.UsageError(f"--langs: unknown language(s) {sorted(unknown)}; pick from {EXECUTABLE}")
    return chosen


@pytest.fixture(scope="session")
def env() -> dict[str, str]:
    try:
        return backend.config()
    except backend.BackendUnavailable as exc:
        pytest.skip(f"backend not configured: {exc}", allow_module_level=True)


@pytest.fixture(scope="session")
def cli(env):
    try:
        return backend.client(env)
    except backend.BackendUnavailable as exc:
        pytest.skip(f"backend not reachable: {exc}", allow_module_level=True)



@pytest.fixture(scope="session")
def seed(env, cli, tmp_path_factory):
    """Run a data-generating page once per session, and remember that it ran.

    `advanced/generate-sample-data` seeds the series every ML recipe reads. Composing
    it into all thirteen recipes would mean generating a fortnight of minute-resolution
    data thirteen times over; running it once and letting the recipes find the data is
    both faster and closer to what the docs actually tell a reader to do.

    A failure here is reported against the seeding page, not the recipe that asked for
    it — otherwise thirteen tests all blame their own doc for one broken fixture.
    """
    done: dict[tuple[str, str], str | None] = {}
    planted: list[dict] = []

    def ensure(slug: str, lang: str) -> None:
        key = (slug, lang)
        if key in done:
            if done[key]:
                pytest.fail(done[key])
            return

        all_plans = plans_mod.load_all()
        run = scenario.build(slug, lang, all_plans, REPO)
        source, line_map = run.programs()[0]
        owns = run.owns()

        backend.sweep(cli, owns)
        workdir = tmp_path_factory.mktemp(f"seed-{slug}")
        result = runners.RUNNERS[lang](source, line_map, workdir, env, run.lang_plan)

        if not result.ok:
            done[key] = (
                f"The data-seeding page {run.plan.page} [{lang}] failed, so every "
                f"tutorial that depends on it cannot be tested.\n"
                f"Fix that page first — run: ./doctests/run.sh -k '{slug}'\n\n"
                f"{runners.tidy(result.stderr, 2000)}"
            )
            pytest.fail(done[key])

        # Exiting 0 only means the writes were accepted. The recipes that depend on
        # this read the data immediately, and reads are eventually consistent — so
        # hand over only once the fixture is actually visible. Skipping this makes the
        # suite pass on a warm backend and fail on a cold one, which is the worst kind
        # of flake: it looks like the recipes are broken.
        unmet = backend.unmet_expectations(cli, run.plan)
        if unmet:
            done[key] = (
                f"The data-seeding page {run.plan.page} [{lang}] ran, but its data never "
                f"became readable: {', '.join(unmet)}.\n"
                "Every tutorial that depends on it would fail for a reason that is not its own."
            )
            pytest.fail(done[key])

        done[key] = None
        planted.append(owns)

    yield ensure

    # Cleanup for the seeding pages happens here, once, rather than after each of
    # their own tests — those keep their data alive for the recipes that need it.
    all_plans = plans_mod.load_all()
    fixtures = {dep for plan in all_plans.values()
                for lp in plan.langs.values() for dep in lp.requires_once}
    for slug in sorted(fixtures):
        for lang in ("python",):
            try:
                planted.append(plans_mod.merged_owns(plans_mod.chain(slug, lang, all_plans)))
            except plans_mod.PlanError:
                pass
    for owns in planted:
        backend.sweep(cli, owns)
