"""Talking to the live backend: config, a cleanup client, and outcome checks.

The doc programs build their own clients, exactly as a reader would. This module
is the *harness'* own connection, used for the two things around a run: making the
backend clean before and after, and asking it afterwards whether the tutorial
actually did what the page claims.

Configuration follows the SDK's own contract (``BASE_URL`` plus either ``TOKEN`` or
the OAuth2 client-credentials trio), read from ``doctests/.env`` if present so a
developer configures this once. One addition, ``DOCTEST_TOKEN_CMD``, covers the
local-stack case where a token comes from a mint script rather than a client
secret; its output is cached briefly so a full suite run mints once, not per test.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).parent
ENV_FILE = HERE / ".env"
_TOKEN_CACHE = HERE / ".token"
_TOKEN_TTL = 240  # seconds; tokens outlive a suite run but not a coffee break


class BackendUnavailable(Exception):
    """No usable configuration or no reachable backend — the suite skips, not fails.

    A missing backend is not a broken tutorial, and reporting it as one trains
    people to ignore red. It is reported as a skip with the reason attached.
    """


@contextlib.contextmanager
def quiet():
    """Silence the SDK's response-body chatter.

    The bindings print every response body from Rust, so it lands on fd 1 directly
    and ``redirect_stdout`` cannot see it. Cleanup would otherwise bury the actual
    test output under kilobytes of JSON, so the redirect happens at the fd level.
    """
    saved = os.dup(1)
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, 1)
        yield
    finally:
        os.dup2(saved, 1)
        os.close(devnull)
        os.close(saved)


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def _mint(cmd: str) -> str:
    """Run a token-mint command; its last non-empty stdout line is the token."""
    if _TOKEN_CACHE.exists() and time.time() - _TOKEN_CACHE.stat().st_mtime < _TOKEN_TTL:
        cached = _TOKEN_CACHE.read_text(encoding="utf-8").strip()
        if cached:
            return cached
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    if proc.returncode != 0 or not lines:
        raise BackendUnavailable(
            f"DOCTEST_TOKEN_CMD failed (exit {proc.returncode}): {proc.stderr.strip()[:300] or '(no stderr)'}"
        )
    token = lines[-1]
    _TOKEN_CACHE.write_text(token, encoding="utf-8")
    _TOKEN_CACHE.chmod(0o600)
    return token


def config() -> dict[str, str]:
    """The environment a doc program runs under. Process env wins over the file."""
    env = {**_read_env_file(ENV_FILE), **{k: v for k, v in os.environ.items() if k in _PASSTHROUGH}}

    base = env.get("BASE_URL")
    if not base:
        raise BackendUnavailable(
            "No BASE_URL. Copy doctests/.env.example to doctests/.env and point it at a stack."
        )

    if not env.get("TOKEN"):
        mint = env.get("DOCTEST_TOKEN_CMD") or os.environ.get("DOCTEST_TOKEN_CMD")
        if mint:
            env["TOKEN"] = _mint(mint)
        elif not all(env.get(k) for k in ("CLIENT_ID", "CLIENT_SECRET", "TOKEN_URI")):
            raise BackendUnavailable(
                "No credentials. Set TOKEN, or CLIENT_ID/CLIENT_SECRET/TOKEN_URI, or DOCTEST_TOKEN_CMD."
            )
    return env


_PASSTHROUGH = (
    "BASE_URL",
    "TOKEN",
    "CLIENT_ID",
    "CLIENT_SECRET",
    "TOKEN_URI",
    "PROJECT_NAME",
    "DOCTEST_TOKEN_CMD",
)


def client(env: dict[str, str]):
    """The harness' own SDK client, built from the same env the doc programs get."""
    try:
        import intellistream_datahub_sdk as sdk
    except ImportError as exc:  # pragma: no cover - setup problem, not a doc problem
        raise BackendUnavailable(
            "The SDK is not installed in this venv. Run doctests/setup.sh."
        ) from exc

    for key in _PASSTHROUGH:
        if env.get(key):
            os.environ[key] = env[key]
    try:
        with quiet():
            return sdk.DataHubClient.from_env()
    except Exception as exc:
        raise BackendUnavailable(f"Could not build a client for {env['BASE_URL']}: {exc}") from exc


# ---------------------------------------------------------------- cleanup

# Every service's delete/by_ids accepts a bare external id string; only some also
# accept an IdCollection. Passing the wrong wrapper raises a TypeError from PyO3,
# which — inside the deliberately-forgiving sweep — would be swallowed, leaving
# entities behind and making the next run fail on a duplicate create that looks
# like a documentation bug. Strings are the one shape all of them take.


def _expand(cli, kind: str, values: list[str]) -> list[str]:
    """Resolve any ``*`` patterns to concrete external ids.

    Several guides mint an id at run time — ``f"overheat_press_07_{timestamp}"`` —
    so a plan cannot name what it will create. It declares the shape instead, and
    the sweep asks the backend which ids currently match. Without this those rows
    accumulate on the stack forever, one per suite run.
    """
    literal = [v for v in values if "*" not in v]
    patterns = [v for v in values if "*" in v]
    if not patterns:
        return literal

    found: list[str] = []
    for pattern in patterns:
        try:
            if kind == "events":
                page = cli.events.filter(external_id=[pattern], limit=1000)
            elif kind == "subscriptions":
                import fnmatch
                page = [s for s in cli.subscriptions.list()
                        if fnmatch.fnmatch(s.external_id or "", pattern)]
            else:
                page = cli.resources.filter(external_id=[pattern], limit=1000)
            found.extend(e.external_id for e in page if getattr(e, "external_id", None))
        except Exception:
            continue
    return literal + found


def sweep(cli, owns: dict[str, list[str]]) -> None:
    """Delete every entity a page declares it owns, before and after a run.

    Deleting *before* is what makes a run repeatable: the doc's fixed external ids
    (``engine_temperature`` and friends) would otherwise 409 on the second run, and
    a suite that only passes on a virgin backend is a suite nobody runs twice.

    Order matters — the backend refuses to delete a node that is the start of an
    edge, and a dataset sits above what belongs to it — so leaves go first and
    datasets last. Failures are swallowed on purpose: "already absent" is the
    desired state, and a delete that cannot run is caught by the run that follows.
    """
    order = [
        ("subscriptions", cli.subscriptions.delete),
        ("events", cli.events.delete),
        ("files", cli.files.delete),
        ("timeseries", cli.timeseries.delete),
        ("resources", cli.resources.delete),
        ("datasets", cli.datasets.delete),
    ]
    unknown = set(owns) - {name for name, _ in order}
    if unknown:
        raise ValueError(f"`owns` has unknown entity type(s): {sorted(unknown)}")

    with quiet():
        # Repeat while the pass is still removing things. The backend refuses to delete
        # a node that is the start of an edge, so a chain needs one pass per link and
        # the depth is not knowable from here. A single pass silently leaves the head of
        # every chain behind — and because a duplicate create answers 500, the next run
        # fails with what looks like a server fault in the middle of a tutorial.
        remaining = None
        for _ in range(6):
            deleted = 0
            for name, delete in order:
                values = owns.get(name) or []
                if not values:
                    continue
                for value in _expand(cli, name, values):
                    # One at a time: a batch delete fails wholesale if a single id is
                    # absent, which is the normal case on the pre-run sweep.
                    try:
                        delete([value])
                        deleted += 1
                    except Exception:
                        pass
            if deleted == 0 or deleted == remaining:
                break
            remaining = deleted


# ---------------------------------------------------------------- assertions

def _poll(check, timeout: float, interval: float = 0.5):
    """Retry ``check`` until it reports nothing wrong, or the window closes.

    Reads go through eventually-consistent projections, so a datapoint written a
    millisecond ago is genuinely not visible yet. Asserting immediately would make
    this suite flaky, and a flaky documentation test gets muted rather than fixed —
    which costs more than the bug it was built to catch. So the check is retried
    and the *last* result is what gets reported: a tutorial that never lands its
    data still fails, just after the backend has been given a fair chance.
    """
    deadline = time.monotonic() + timeout
    problems = check()
    while problems and time.monotonic() < deadline:
        time.sleep(interval)
        problems = check()
    return problems


def unmet_expectations(cli, plan) -> list[str]:
    """Everything a plan promised that the backend cannot show — entities and data.

    Both the tutorial tests and the seeding fixture ask this same question, and a
    seeding page that ran but whose data never became readable fails its dependants
    for a reason that is not theirs. One function so the two cannot drift.
    """
    return (missing_entities(cli, plan.expect_exists, plan.settle_secs)
            + datapoint_shortfall(cli, plan.expect_datapoints, plan.settle_secs))


def missing_entities(cli, expect: dict[str, list[str]], timeout: float = 30.0) -> list[str]:
    """Which declared entities the tutorial failed to leave behind."""
    lookups = {
        "timeseries": cli.timeseries.by_ids,
        "resources": cli.resources.by_ids,
        "datasets": cli.datasets.by_ids,
        "events": cli.events.by_ids,
        "files": lambda v: [n for x in v for n in cli.files.get_by_external_id(x)],
        "subscriptions": lambda v: [x for x in cli.subscriptions.list() if x.external_id in set(v)],
    }
    unknown = set(expect) - set(lookups)
    if unknown:
        raise ValueError(f"`expect` has unknown entity type(s): {sorted(unknown)}")

    def check() -> list[str]:
        gone: list[str] = []
        with quiet():
            for kind, wanted in expect.items():
                if not wanted:
                    continue
                # An id minted at run time cannot be named, only shaped. A pattern
                # asserts "the page produced at least one of these" — which is the
                # real claim for a page whose payoff is an event it raises.
                patterns = [w for w in wanted if "*" in w]
                literals = [w for w in wanted if "*" not in w]
                for pattern in patterns:
                    if not _expand(cli, kind, [pattern]):
                        gone.append(f"{kind}:{pattern} (nothing matched)")
                if not literals:
                    continue
                try:
                    found = {getattr(e, "external_id", None) for e in lookups[kind](literals)}
                except Exception as exc:
                    gone.extend(f"{kind}:{w} (lookup failed: {str(exc)[:120]})" for w in literals)
                    continue
                gone.extend(f"{kind}:{w}" for w in literals if w not in found)
        return gone

    return _poll(check, timeout) if expect else []


def datapoint_shortfall(cli, expect: dict[str, int], timeout: float = 30.0) -> list[str]:
    """Series that hold fewer datapoints than the tutorial claims to have written.

    This is the check that separates "the program did not crash" from "the tutorial
    worked". Several pages catch their own exceptions by design — the memory-ingest
    daemon must never die on a bad tick — so their exit code says nothing at all
    about whether data landed. Reading it back is the only honest proof.
    """
    import datetime as _dt

    import intellistream_datahub_sdk as sdk

    def _as_datetime(value):
        """Datapoint timestamps come back as datetimes or as strings, per endpoint."""
        if isinstance(value, _dt.datetime):
            return value if value.tzinfo else value.replace(tzinfo=_dt.timezone.utc)
        text = str(value).replace("Z", "+00:00")
        try:
            parsed = _dt.datetime.fromisoformat(text)
        except ValueError:
            return _dt.datetime.fromtimestamp(int(value) / 1000, _dt.timezone.utc)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=_dt.timezone.utc)

    # The retrieve endpoint rejects an unbounded window, so the check spans a
    # generously wide one: tutorials write "now", but a few of them backfill
    # historical ranges, and this must count those too.
    now = _dt.datetime.now(_dt.timezone.utc)
    start_at, end_at = now - _dt.timedelta(days=730), now + _dt.timedelta(days=1)

    # The retrieve endpoint refuses a limit above 100k, so a page claiming a million
    # readings has to be verified by paging. Asking for the whole million in one
    # call fails with a 400 that looks like the tutorial's fault and is not.
    PAGE = 100_000

    def count_datapoints(external_id: str, minimum: int) -> int:
        """Count readable datapoints, walking the window forward in 100k slices.

        The obvious approach — one call with a big limit — is capped at 100k, and the
        response carries no cursor to continue with (verified: 250k points come back
        as 100k with `next_cursor` None). So the window is advanced instead: each
        slice starts just after the last timestamp seen. That is what lets a page
        claiming a million readings actually be held to it, rather than to the first
        hundred thousand.
        """
        seen = 0
        cursor_time = start_at
        while seen < minimum and cursor_time < end_at:
            got = cli.timeseries.retrieve_datapoints(
                sdk.RetrieveFilter(
                    ts=sdk.IdCollection(external_id=external_id),
                    start=cursor_time,
                    end=end_at,
                    limit=PAGE,
                )
            )
            points = [p for g in got for p in g.get_datapoints()]
            if not points:
                break
            seen += len(points)
            last = max(_as_datetime(p.timestamp) for p in points)
            if last <= cursor_time:
                break  # no forward progress; stop rather than spin
            cursor_time = last + _dt.timedelta(milliseconds=1)
        return seen

    def check() -> list[str]:
        short: list[str] = []
        with quiet():
            for external_id, minimum in expect.items():
                try:
                    count = count_datapoints(external_id, minimum)
                except Exception as exc:
                    short.append(f"{external_id}: could not read datapoints back ({str(exc)[:120]})")
                    continue
                if count < minimum:
                    short.append(f"{external_id}: {count} datapoint(s), expected at least {minimum}")
        return short

    return _poll(check, timeout) if expect else []
