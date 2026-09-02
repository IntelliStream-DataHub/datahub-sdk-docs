"""Check the docs against the installed SDK's API surface. No backend needed.

This is the cheapest useful check in the suite and the one worth running from the
SDK's own CI: it needs the bindings built, nothing else. When `BasicEventFilter`,
`SearchAndFilterForm` and `TimeSeriesFilterForm` were removed in 0.2.0, six doc
pages started referring to things that no longer existed — and nothing said so
until someone ran the code months later. A build-time check would have caught it
in the pull request that removed them.

It deliberately only reports names the docs *state*: a class they construct, a
service method they call. Anything it cannot resolve confidently is left alone,
because a false failure here trains people to skip the check.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import docblocks

REPO = Path(__file__).parent.parent
MODULE = "intellistream_datahub_sdk"

sdk = pytest.importorskip(MODULE, reason="SDK not installed; run doctests/setup.sh")


def _doc_sources() -> list[tuple[str, str]]:
    return [(p.rel, "\n".join(b.body for b in p.of_lang("python")))
            for p in docblocks.all_pages(REPO) if p.of_lang("python")]


def _module_symbols(source: str) -> set[str]:
    """Names the page takes from the SDK, however it spells the import."""
    out: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return out

    aliases = {MODULE}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == MODULE:
                    aliases.add(a.asname or a.name)
        elif isinstance(node, ast.ImportFrom) and node.module == MODULE:
            out.update(a.name for a in node.names)

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                and node.value.id in aliases:
            out.add(node.attr)
    return out


def _sdk_imports(source: str) -> set[str]:
    """SDK-ish module roots the page imports, whatever they are called.

    Checking symbols inside `intellistream_datahub_sdk` misses the most basic
    failure of all: a page importing a module that does not exist. That is exactly
    what the 0.2.0 rename produced — 69 pages importing `datahub_sdk`, every Python
    tutorial dead on its first line — and a symbol check would have said nothing,
    because it was looking for a module the pages had stopped naming.
    """
    out: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            root = name.split(".")[0]
            if "datahub" in root.lower() or "intellistream" in root.lower():
                out.add(root)
    return out


IMPORT_CASES = [
    (rel, sorted(_sdk_imports(src)))
    for rel, src in _doc_sources()
    if _sdk_imports(src)
]


@pytest.mark.parametrize("rel,modules", IMPORT_CASES, ids=[r for r, _ in IMPORT_CASES])
def test_page_imports_a_module_that_exists(rel, modules):
    import importlib.util

    def importable(name: str) -> bool:
        # `find_spec` alone is not enough. A stale empty directory left on the path
        # answers as a namespace package — origin None, no loader — and satisfies a
        # naive check while importing nothing. That is exactly the shape the old
        # `datahub_sdk` directory has, which is why the rename went unnoticed.
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError):
            return False
        return spec is not None and spec.origin is not None

    missing = [m for m in modules if not importable(m)]
    assert not missing, (
        f"{rel} imports {', '.join(missing)}, which is not installed. The SDK's Python "
        f"package is `{MODULE}`; `pip install intellistream-datahub-sdk`.\n"
        "If the package was renamed, every page naming the old one is broken at its "
        "first line — this is the cheapest possible check and it needs no backend."
    )


SYMBOL_CASES = [
    (rel, sorted(_module_symbols(src)))
    for rel, src in _doc_sources()
    if _module_symbols(src)
]


@pytest.mark.parametrize("rel,symbols", SYMBOL_CASES, ids=[r for r, _ in SYMBOL_CASES])
def test_page_only_uses_symbols_the_sdk_has(rel, symbols):
    missing = [s for s in symbols if not hasattr(sdk, s)]
    assert not missing, (
        f"{rel} uses {MODULE} name(s) that this build does not have: {', '.join(missing)}.\n"
        "Either the SDK dropped them and the page needs updating, or the page never "
        "had them right. Check the built module, not a changelog:\n"
        f"    python -c \"import {MODULE} as s; print([n for n in dir(s) if not n.startswith('_')])\""
    )


# `client.<service>.<method>(...)` — the calls a reader actually makes.
#
# The service classes are not exported at module level, so the only way to see their
# methods is through a client. Building one is a local object construction — no
# request is made — so this stays a build-time check with no backend.
def _probe_client():
    try:
        return sdk.DataHubClient(base_url="http://127.0.0.1:9", token="offline.probe.token")
    except Exception:
        return None


_PROBE = _probe_client()
SERVICES = {
    name: type(getattr(_PROBE, name))
    for name in ("timeseries", "events", "resources", "files", "datasets",
                 "subscriptions", "units", "labels", "functions", "edges")
    if _PROBE is not None and hasattr(_PROBE, name)
}
_SERVICE_CALL = re.compile(
    r"\bclient\.(" + "|".join(SERVICES) + r")\.([a-z_][a-z0-9_]*)\s*\(", re.I
) if SERVICES else None


def _service_calls(source: str) -> set[tuple[str, str]]:
    return set(_SERVICE_CALL.findall(source)) if _SERVICE_CALL else set()


CALL_CASES = [
    (rel, sorted(_service_calls(src)))
    for rel, src in _doc_sources()
    if _service_calls(src)
]


@pytest.mark.parametrize("rel,calls", CALL_CASES, ids=[r for r, _ in CALL_CASES])
def test_page_only_calls_service_methods_the_sdk_has(rel, calls):
    """Catches a renamed service method — `retrieve` vs `retrieve_datapoints`.

    The service classes are PyO3 types, so their methods are read off the class
    rather than an instance; no client is built and no request is made.
    """
    if not SERVICES:
        pytest.skip("could not build a probe client to read the service surface from")
    surface = {
        service: {m for m in dir(SERVICES[service]) if not m.startswith("_")}
        for service in {s for s, _ in calls} if service in SERVICES
    }
    missing = [f"client.{s}.{m}()" for s, m in calls if m not in surface.get(s, set())]
    assert not missing, (
        f"{rel} calls method(s) this SDK build does not expose: {', '.join(missing)}.\n"
        "A service method was renamed, or the page guessed. The names differ per "
        "language — Java `retrieve`, Python and Rust `retrieve_datapoints` — so check "
        "this language's surface rather than the other tab's."
    )
