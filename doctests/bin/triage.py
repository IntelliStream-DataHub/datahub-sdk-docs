#!/usr/bin/env python3
"""Report what a page's code needs before it can run, so a plan can be written fast.

Writing a plan by hand means reading a page and noticing every name it uses but
never defines, every call that blocks forever, and every external id it creates.
That is mechanical work and easy to get subtly wrong — a missed id leaks rows onto
the stack, a missed blocking call hangs CI for a full timeout.

This does the mechanical half and leaves the judgement: it walks the composed
program's AST and reports free variables, third-party imports, blocking
constructs, and the external ids the page appears to create.

    ./doctests/bin/triage.py docs/industries/energy-utilities/wind.mdx
    ./doctests/bin/triage.py --all --unplanned      # everything still in the backlog
"""

from __future__ import annotations

import argparse
import ast
import builtins
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import docblocks  # noqa: E402
import entities  # noqa: E402
import plans as plans_mod  # noqa: E402

REPO = HERE.parent.parent

# Calls that never return on their own, so a plan must exclude or bound the block.
BLOCKING = {
    "listen": "websocket listen loop — runs until the connection drops",
    "show": "matplotlib show() — blocks on a GUI window (set MPLBACKEND=Agg)",
    "input": "waits for the reader to type something",
    "sleep": "sleeps; check the duration is bounded",
}
# Packages a reader installs for the recipe, not part of the SDK.
THIRD_PARTY = {"numpy", "pandas", "sklearn", "torch", "matplotlib", "networkx",
               "scipy", "xgboost", "statsmodels", "psutil", "seaborn", "plotly",
               "tensorflow", "keras"}


class Scope(ast.NodeVisitor):
    """Collect names bound at any point in the module against names merely read.

    Deliberately flow-insensitive: a name bound anywhere counts as bound. The goal
    is to surface what a page never defines at all, and a stricter analysis would
    drown that signal in false positives from ordinary control flow.
    """

    def __init__(self) -> None:
        self.bound: set[str] = set()
        self.read: set[str] = set()
        self.attr_roots: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self.bound.add(node.id)
        elif isinstance(node.ctx, ast.Load):
            self.read.add(node.id)
        self.generic_visit(node)

    def _bind_args(self, args: ast.arguments) -> None:
        for a in (*args.posonlyargs, *args.args, *args.kwonlyargs):
            self.bound.add(a.arg)
        for a in (args.vararg, args.kwarg):
            if a:
                self.bound.add(a.arg)

    def visit_FunctionDef(self, node) -> None:
        self.bound.add(node.name)
        self._bind_args(node.args)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node) -> None:
        self._bind_args(node.args)
        self.generic_visit(node)

    def visit_ClassDef(self, node) -> None:
        self.bound.add(node.name)
        self.generic_visit(node)

    def visit_alias(self, node: ast.alias) -> None:
        self.bound.add((node.asname or node.name).split(".")[0])

    def visit_ExceptHandler(self, node) -> None:
        if node.name:
            self.bound.add(node.name)
        self.generic_visit(node)

    def visit_Global(self, node) -> None:
        self.bound.update(node.names)

    visit_Nonlocal = visit_Global


def analyse(page: docblocks.Page, lang: str = "python") -> dict:
    blocks = page.of_lang(lang)
    source = "\n".join(b.body for b in blocks)

    out: dict = {"blocks": len(blocks), "source": source, "syntax_error": None,
                 "free": [], "third_party": [], "blocking": [], "creates": []}
    if not blocks:
        return out

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        # Fragments often do not parse as one unit; fall back to per-block parsing
        # so the rest of the report still has something to say.
        out["syntax_error"] = f"line {exc.lineno}: {exc.msg}"
        trees = []
        for b in blocks:
            try:
                trees.append(ast.parse(b.body))
            except SyntaxError:
                pass
        tree = ast.Module(body=[n for t in trees for n in t.body], type_ignores=[])

    scope = Scope()
    scope.visit(tree)
    known = set(dir(builtins)) | {"__name__", "__file__", "_"}
    out["free"] = sorted(scope.read - scope.bound - known)

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = node.module if isinstance(node, ast.ImportFrom) else None
            names = [mod] if mod else [a.name for a in node.names]
            for n in names:
                root = (n or "").split(".")[0]
                if root in THIRD_PARTY:
                    out["third_party"].append(root)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in BLOCKING:
                out["blocking"].append(f"{node.func.attr}() — {BLOCKING[node.func.attr]}")
        if isinstance(node, ast.While) and isinstance(node.test, ast.Constant) and node.test.value is True:
            out["blocking"].append("while True: — needs a bounded-run replacement")

    out["third_party"] = sorted(set(out["third_party"]))
    out["blocking"] = sorted(set(out["blocking"]))
    # External ids are the cleanup contract; a literal is all a static pass can see,
    # and an f-string id is flagged so the plan author writes a `prefix_*` pattern.
    owned = entities.owned(source)
    out["creates"] = sorted(i for ids in owned.values() for i in ids if "*" not in i)
    out["dynamic_ids"] = sorted(i for ids in owned.values() for i in ids if "*" in i)
    out["owned"] = owned
    return out


def report(page: docblocks.Page) -> None:
    a = analyse(page)
    print(f"\n\033[1m{page.rel}\033[0m  ({a['blocks']} python blocks)")
    if a["syntax_error"]:
        print(f"  concatenation does not parse: {a['syntax_error']}")
    for key, label in (("third_party", "needs packages"), ("blocking", "blocking"),
                       ("free", "undefined names"), ("creates", "creates ids"),
                       ("dynamic_ids", "runtime ids")):
        if a.get(key):
            print(f"  {label:16} {', '.join(map(str, a[key]))}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pages", nargs="*")
    ap.add_argument("--all", action="store_true", help="every page with runnable code")
    ap.add_argument("--unplanned", action="store_true", help="only pages without a plan")
    args = ap.parse_args()

    if args.all or args.unplanned:
        pages = [p for p in docblocks.all_pages(REPO) if p.of_lang("python")]
        if args.unplanned:
            planned = {docblocks.slug_for(p.page) for p in plans_mod.load_all().values()}
            pages = [p for p in pages if p.slug not in planned]
    else:
        pages = [docblocks.load((REPO / p).resolve(), REPO) for p in args.pages]

    for page in pages:
        report(page)
    print(f"\n{len(pages)} page(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
