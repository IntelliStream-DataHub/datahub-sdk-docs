"""Helpers a composed tutorial program can import, for things a page leaves to you.

Doc pages hand the reader two kinds of loose end. Some are *placeholders* — a
`record_capacity_factor(...)` the page never defines because it is your dashboard,
not theirs. Some are *unbounded* — a `for msg in listener:` that is correct in a
service and cannot be in a test.

The tempting fix for both is to drop the block. That is also the wrong fix: the
listen loop is usually the whole point of the page, and a test that skips it proves
nothing about the pipeline the tutorial teaches. So instead this module supplies the
missing edges — a recording stub, a bounded take, a background writer that makes
traffic actually arrive — and the page's own code runs unchanged in the middle.

Everything here is deliberately importable only by test programs; nothing in `docs/`
should ever mention it.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Iterable, Iterator


class Recorder:
    """A callable that accepts anything, remembers it, and returns something usable.

    Stands in for the "and then do something with it" function a page leaves to the
    reader. It records rather than discards so a plan can assert the tutorial's logic
    actually reached it — `len(record) > 0` is often the only evidence that a pipeline
    produced anything at all.

    The return value defaults to ``True`` for a specific reason. These placeholders sit
    in two positions: predicates (`if out_of_band(value):`) and small computations
    (`closing - opening`). Returning ``None`` satisfies neither — it makes every
    predicate false, so the interesting branch never runs and the test passes over a
    pipeline it never exercised, and it makes arithmetic raise. ``True`` is an int, so
    it reads as 1 in a calculation and takes the branch the tutorial is actually about.

    Where a page needs a particular value, a plan says so: ``Recorder("latest",
    returns=95.0)``.
    """

    def __init__(self, name: str = "stub", returns: Any = True) -> None:
        self.name = name
        self.returns = returns
        self.calls: list[tuple[tuple, dict]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        return self.returns

    def __len__(self) -> int:
        return len(self.calls)

    def __bool__(self) -> bool:
        return True

    def __repr__(self) -> str:
        return f"<Recorder {self.name}: {len(self.calls)} call(s)>"


def stubs(*names: str) -> dict[str, Recorder]:
    """Recorders for several placeholder names at once."""
    return {name: Recorder(name) for name in names}


def take(source: Iterable, limit: int = 3, timeout: float = 30.0) -> Iterator:
    """Yield at most `limit` items from a stream, and stop waiting after `timeout`.

    A subscription listener blocks until a message arrives and then blocks again;
    iterating it is correct in a daemon and fatal in a test. This bounds both the
    count and the wall clock, so a page whose stream stays silent finishes and fails
    on its assertions rather than hanging until the suite timeout — a much more
    legible outcome than a killed run.

    The timeout is enforced between items, which is the only place it can be:
    the underlying iterator's blocking read cannot be interrupted from here.
    """
    deadline = time.monotonic() + timeout
    taken = 0
    for item in source:
        yield item
        taken += 1
        if taken >= limit or time.monotonic() > deadline:
            return


def feed(client, series: str | list[str], *, points: int = 20, every: float = 0.25,
         value: float = 100.0) -> Callable[[], None]:
    """Write datapoints in the background so a listener has something to receive.

    Returns a stop function. Started as a daemon thread: if the tutorial under test
    dies, the writer must not keep the process alive.

    Without this, testing a subscription page means either faking the listener —
    which tests nothing — or hoping the stack happens to have live traffic, which
    makes the result depend on what else is running. Generating the traffic is what
    lets the page's own detect-and-react code be exercised for real.
    """
    names = [series] if isinstance(series, str) else list(series)
    done = threading.Event()

    def run() -> None:
        import datetime as dt

        for i in range(points):
            if done.is_set():
                return
            now = dt.datetime.now(dt.timezone.utc)
            for name in names:
                try:
                    client.timeseries.insert_from_lists(
                        timestamps=[now], values=[value + i], ts=name)
                except Exception:
                    return  # the test's own assertions report the failure
            time.sleep(every)

    threading.Thread(target=run, daemon=True).start()
    return done.set


def wait_for_datapoints(client, external_id: str, minimum: int = 1, timeout: float = 30.0) -> int:
    """Block until a series has at least `minimum` readable datapoints.

    Several pages write a datapoint and read it back in the next breath. Storage is
    eventually consistent, so that read can legitimately come back empty — a race the
    page has, and one a reader mostly does not notice because their data was already
    there. Waiting here reproduces the reader's situation instead of testing how fast
    the projection happens to be today.

    Returns the count seen, so a caller can tell "arrived" from "gave up".
    """
    import datetime as dt

    import intellistream_datahub_sdk as sdk

    deadline = time.monotonic() + timeout
    while True:
        now = dt.datetime.now(dt.timezone.utc)
        try:
            got = client.timeseries.retrieve_datapoints(
                sdk.RetrieveFilter(
                    ts=external_id,
                    start=now - dt.timedelta(days=730),
                    end=now + dt.timedelta(days=1),
                    limit=minimum,
                )
            )
            count = sum(len(c.get_datapoints()) for c in got)
        except Exception:
            count = 0
        if count >= minimum or time.monotonic() > deadline:
            return count
        time.sleep(0.5)


def wait_for_related(client, external_id: str, *, minimum: int = 1, timeout: float = 30.0,
                     relationship_types=None) -> int:
    """Block until a node's neighbourhood is visible to the graph read path.

    Writes to the graph land in a projection that trails them by a second or two.
    Sixteen pages model a network and traverse it in the very next block, so the
    traversal can legitimately come back empty — and because "no neighbours" is a
    valid answer rather than an error, that surfaces as a tutorial quietly printing
    the wrong conclusion instead of failing. This makes the read deterministic
    without changing what the page's own code does.

    Returns how many nodes were visible, so a caller can distinguish "arrived" from
    "gave up".
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            kwargs = {"external_id": external_id, "depth": 10}
            if relationship_types:
                kwargs["relationship_types"] = relationship_types
            found = len(client.resources.fetch_related(**kwargs).nodes)
        except Exception:
            found = 0
        if found >= minimum or time.monotonic() > deadline:
            return found
        time.sleep(0.5)
