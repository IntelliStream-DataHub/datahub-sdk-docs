"""Work out which entities a page's code creates, so a plan can own and assert them.

Getting this list right is what makes a run repeatable. Anything a page creates and
a plan fails to declare survives the sweep, and the *next* run fails on a duplicate
create — an error that looks like a documentation bug and is not one. So the reading
has to cope with how these pages actually write ids, which is rarely a plain literal:

    TimeSeries(external_id="engine_temperature")                     # literal
    [Resource(external_id=x) for x in ["plant", "line"]]             # comprehension
    for s, u in [("flow_in", "m3h"), ...]: create(TimeSeries(external_id=s))   # loop
    TimeSeries(external_id=f"{cell}_prb_util")                       # built from a loop var
    Event(external_id=f"kick_{int(now.timestamp())}")                # minted at run time

The first four resolve to concrete ids. The last cannot — it is only known while the
program runs — so it becomes a ``prefix_*`` pattern the sweep expands against the
backend instead.
"""

from __future__ import annotations

import ast

# Constructor name -> the `owns` bucket its instances belong to.
CONSTRUCTORS = {
    "TimeSeries": "timeseries",
    "Resource": "resources",
    "Event": "events",
    "Subscription": "subscriptions",
    "Dataset": "datasets",
    "FileUpload": "files",
}


def _ctor_bucket(call: ast.Call) -> str | None:
    fn = call.func
    name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
    return CONSTRUCTORS.get(name)


def _strings(node: ast.AST) -> list[str]:
    return [n.value for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _from_joinedstr(node: ast.JoinedStr, bindings: dict[str, list[str]]) -> list[str]:
    """Resolve an f-string id, using loop bindings where the parts are known.

    ``f"{cell}_prb_util"`` with ``cell`` bound to two literals yields both ids. A part
    that cannot be resolved — a timestamp, a counter — collapses the whole thing to a
    prefix pattern, which is the honest answer: the id is not knowable until it exists.
    """
    prefix, resolvable = "", True
    options = [""]
    for part in node.values:
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            options = [o + part.value for o in options]
            if resolvable:
                prefix += part.value
        elif isinstance(part, ast.FormattedValue) and isinstance(part.value, ast.Name) \
                and part.value.id in bindings:
            values = bindings[part.value.id]
            options = [o + v for o in options for v in values]
            resolvable = False if not values else resolvable
            if not prefix:
                resolvable = False
        else:
            resolvable = False
            break
    else:
        return sorted(set(options))
    return [prefix.rstrip("_") + "_*"] if prefix else []


def _loop_bindings(tree: ast.AST) -> dict[str, list[str]]:
    """Names bound by `for` loops over literal sequences, mapped to their values."""
    out: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.For, ast.comprehension)):
            continue
        target = node.target
        iterable = node.iter
        if isinstance(target, ast.Name):
            # `for s in ["a", "b"]` — but a list of tuples would over-collect, so only
            # take the strings when the elements are strings.
            if isinstance(iterable, (ast.List, ast.Tuple)) and \
                    all(isinstance(e, ast.Constant) for e in iterable.elts):
                out.setdefault(target.id, []).extend(_strings(iterable))
            else:
                out.setdefault(target.id, []).extend(_strings(iterable))
        elif isinstance(target, ast.Tuple) and isinstance(iterable, (ast.List, ast.Tuple)):
            # `for s, u in [("flow_in", "m3h"), ...]` — position matters.
            for pos, elt in enumerate(target.elts):
                if not isinstance(elt, ast.Name):
                    continue
                values = []
                for row in iterable.elts:
                    if isinstance(row, (ast.Tuple, ast.List)) and pos < len(row.elts):
                        cell = row.elts[pos]
                        if isinstance(cell, ast.Constant) and isinstance(cell.value, str):
                            values.append(cell.value)
                if values:
                    out.setdefault(elt.id, []).extend(values)
    return out


def _plausible(value: str) -> bool:
    """Filter out strings that are clearly not external ids."""
    return bool(value) and " " not in value and not value.startswith(("http", "/", "."))


def _helper_creators(tree: ast.AST) -> dict[str, tuple[int, str]]:
    """Locally-defined functions that create an entity from one of their parameters.

    Pages that seed a lot of data factor the boilerplate into a helper —
    ``def ingest(external_id, index, values, ...)`` that creates the series and writes
    to it — and then call it thirty times with a literal id. Without following that
    one hop, every one of those ids is invisible to the sweep, the page cannot be run
    twice, and the failure surfaces as a duplicate-create in the middle of a tutorial.

    Returns ``{function name: (parameter position, bucket)}``.
    """
    out: dict[str, tuple[int, str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        params = [a.arg for a in (*node.args.posonlyargs, *node.args.args)]
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            bucket = _ctor_bucket(inner)
            if not bucket:
                continue
            for kw in inner.keywords:
                if kw.arg == "external_id" and isinstance(kw.value, ast.Name) \
                        and kw.value.id in params:
                    out[node.name] = (params.index(kw.value.id), bucket)
    return out


def owned(source: str, include_edge_refs: bool = True) -> dict[str, list[str]]:
    """`owns`-shaped mapping of entity kind -> external ids (and `prefix_*` patterns).

    ``include_edge_refs`` decides whether the nodes an edge *points at* count. For
    cleanup they should — an edge can name a node the page created elsewhere, and a
    missed id is a leak. For assertions they must not: a page can legitimately draw an
    edge to something it never creates, and asserting that it exists would turn the
    page's own bug into an assertion about the wrong thing.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    bindings = _loop_bindings(tree)
    helpers = _helper_creators(tree)
    out: dict[str, set[str]] = {}

    def add(bucket: str, value: str) -> None:
        if _plausible(value):
            out.setdefault(bucket, set()).add(value)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            bucket = _ctor_bucket(node)
            if bucket:
                for kw in node.keywords:
                    if kw.arg != "external_id":
                        continue
                    v = kw.value
                    if isinstance(v, ast.Constant) and isinstance(v.value, str):
                        add(bucket, v.value)
                    elif isinstance(v, ast.JoinedStr):
                        for candidate in _from_joinedstr(v, bindings):
                            add(bucket, candidate)
                    elif isinstance(v, ast.Name) and v.id in bindings:
                        for candidate in bindings[v.id]:
                            add(bucket, candidate)
            # A call to a local helper that creates an entity from one of its arguments.
            fname = node.func.id if isinstance(node.func, ast.Name) else None
            if fname in helpers:
                pos, bucket = helpers[fname]
                if pos < len(node.args):
                    arg = node.args[pos]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        add(bucket, arg.value)
                    elif isinstance(arg, ast.JoinedStr):
                        for candidate in _from_joinedstr(arg, bindings):
                            add(bucket, candidate)
                    elif isinstance(arg, ast.Name) and arg.id in bindings:
                        for candidate in bindings[arg.id]:
                            add(bucket, candidate)

            # An edge names two resources by external id.
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if include_edge_refs and name == "by_external_ids" and len(node.args) >= 2:
                for arg in node.args[:2]:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        add("resources", arg.value)

        # Comprehensions need no special case: the constructor inside one is an
        # ordinary Call, and its `external_id=<name>` resolves through the same loop
        # bindings. Taking every string out of the iterable instead would sweep up
        # whatever else rides along in it — the labels in
        # `[(x, "Cell"), (y, "Controller")]` are not external ids.

    # `ts=` names a series — but only on a write. The same keyword on a RetrieveFilter
    # is a *read*, and treating that as ownership makes a page claim series it merely
    # looks at. For a recipe reading a shared fixture that is actively harmful: the
    # sweep would delete the fixture out from under the next test.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in ("insert_from_lists", "insert_datapoints"):
            for kw in node.keywords:
                if kw.arg == "ts":
                    if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        add("timeseries", kw.value.value)
                    elif isinstance(kw.value, ast.JoinedStr):
                        for candidate in _from_joinedstr(kw.value, bindings):
                            add("timeseries", candidate)
                    elif isinstance(kw.value, ast.Name) and kw.value.id in bindings:
                        for candidate in bindings[kw.value.id]:
                            add("timeseries", candidate)

    return {k: sorted(v) for k, v in out.items()}
