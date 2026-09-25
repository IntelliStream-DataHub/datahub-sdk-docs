"""Type-check every Java and Rust example against the SDK. No backend needed.

The Python tier runs pages; this one compiles them. It exists because the Java and Rust
tabs are most of these docs — seventy pages carry both — and before it, one page of each
language was checked by anything at all. A removed factory method, a field that became an
`Option`, a type that moved package: each leaves a tab broken for every reader who copies
it, and none needs a stack to detect. The compiler already knows. This asks it.

What "compiles" means for a fragment
-------------------------------------
Most blocks are fragments. They use a `client` (Java) or `api` (Rust) built on an earlier
page, and they call helpers the page leaves to the reader — `latest(...)`, `shiftStart`, a
`readings` map "from your historian". So a page is composed the way a reader accumulates
it, blocks in order, inside a `main` that already has the client, and compiled. Errors fall
in two kinds, and the compiler says which:

* **An unresolved value or function** — `shiftStart`, `latest(...)`. The reader's to
  supply, and the page says so in prose. Allowed.
* **Everything else** — an unresolved *type* or import, a method that does not exist, a
  wrong argument type, a missing field, a syntax error. A failure, at the doc line.

The line between the two is where it is because of what each kind of drift looks like. A
page never asks its reader to invent `EventModel` or `BasicEventFilter`; when one of those
stops resolving, the SDK removed it. Unresolved names do not mask errors elsewhere either:
both compilers give an unknown name an error type and suppress only what flows from it, so
a call on the client three lines later is still checked in full.

Imports follow each language's own convention on the page. Java fragments never show
theirs, so the wrapper imports every package the SDK jars contain, derived from the jars
so the list cannot go stale. Rust blocks carry their `use` lines, so nothing is added: a
Rust fragment that names a type it never imports fails, as it would for the reader.

Which blocks compile together comes from the page's plan, through the knobs the live tier
already has: `only`/`exclude`/`independent`/`imports` in the plan's `[java]` or `[rust]`
section (whether or not that section is `disabled` for running), else the `[python]`
section's `independent`, since a reference page is a reference page in every tab.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass, field, replace
from pathlib import Path

import docblocks
import plans as plans_mod

HERE = Path(__file__).parent
REPO = HERE.parent
COMPILED = ("java", "rust")


class ToolchainMissing(Exception):
    """No compiler or no SDK to compile against: skip, don't fail."""


# ---------------------------------------------------------------- model

@dataclass
class Segment:
    """Where doc lines landed in a generated file."""

    first_line: int  # 1-based line in the generated file
    lines: int
    block: docblocks.Block
    offset: int = 0  # body line of `block` that `first_line` holds

    def doc_line(self, generated_line: int) -> int:
        # The body starts on the line after the opening fence.
        return self.block.start_line + 1 + self.offset + (generated_line - self.first_line)


@dataclass
class Unit:
    """One compilable file: one page's blocks for one language (one tab, where a page has two)."""

    page: str
    lang: str
    name: str  # module (Rust) or class (Java) name, unique across the run
    source: str = ""
    segments: list[Segment] = field(default_factory=list)
    program: int | None = None  # the block index, when this unit is a complete program

    def locate(self, line: int) -> str:
        for seg in self.segments:
            if seg.first_line <= line < seg.first_line + seg.lines:
                return f"{self.page}:{seg.doc_line(line)} ({self.lang} #{seg.block.lang_index})"
        return f"{self.page} (compile wrapper, generated line {line})"


@dataclass
class Diagnostic:
    page: str
    lang: str
    where: str
    message: str
    placeholder: str | None = None  # set when this is only "the reader supplies X"

    def __str__(self) -> str:
        return f"{self.where}: {self.message}"


@dataclass
class Selection:
    blocks: list[docblocks.Block]
    independent: bool
    imports: list[str]


def _ident(slug: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", slug)


def selection(page: docblocks.Page, lang: str, plan: plans_mod.Plan | None) -> Selection:
    blocks = page.of_lang(lang)
    if plan is None:
        return Selection(blocks, False, [])
    own = plan.langs.get(lang)
    if own is not None:
        return Selection(own.select(blocks), own.independent,
                         [ln.strip() for ln in own.imports.splitlines() if ln.strip()])
    python = plan.langs.get("python")
    return Selection(blocks, bool(python and python.independent), [])


def flows(blocks: list[docblocks.Block], lang: str) -> dict[str, list[docblocks.Block]]:
    """Blocks split by the tab they sit in.

    The tutorial has `Rust (async)` and `Rust (blocking)` tabs side by side. They are two
    programs, not one: composed together they would declare `api` twice with two types and
    report errors no reader can meet.
    """
    out: dict[str, list[docblocks.Block]] = {}
    for b in blocks:
        tab = b.tab if b.tab and b.tab != lang else ""
        out.setdefault(tab, []).append(b)
    return out


def units_for(page: docblocks.Page, lang: str, plan: plans_mod.Plan | None, tag: str = "") -> list[Unit]:
    sel = selection(page, lang, plan)
    units: list[Unit] = []
    for flow, blocks in flows(sel.blocks, lang).items():
        base = _ident(page.slug) + (f"__{_ident(flow)}" if flow else "") + tag
        programs = [b for b in blocks if _is_program(lang, b.body)]
        fragments = [b for b in blocks if not _is_program(lang, b.body)]
        groups = [[b] for b in fragments] if sel.independent else ([fragments] if fragments else [])
        # Snippets on a reference page share the imports the page shows once: a reader of
        # "Delete a series" has the `use` from "Create a series" three headings up.
        shared = fragments if sel.independent else []
        for group in groups:
            name = base if len(groups) == 1 else f"{base}__{group[0].lang_index}"
            if lang == "rust":
                units.append(_rust_fragment(page, name, group, shared, blocking="blocking" in flow))
            else:
                units.append(_java_fragment(page, "P_" + name, group, sel.imports, shared))
        for b in programs:
            units.append(_rust_program(page, f"{base}__program{b.lang_index}", b) if lang == "rust"
                         else _java_program(page, b))
    return units


def _is_program(lang: str, body: str) -> bool:
    if lang == "rust":
        return re.search(r"^(pub\s+)?(async\s+)?fn\s+main\s*\(", body, re.M) is not None
    return re.search(r"\bstatic\s+void\s+main\s*\(", body) is not None


# ---------------------------------------------------------------- Rust

_RUST_USE = re.compile(r"^use\s[^;]*;[ \t]*(?://[^\n]*)?$", re.M)


def flatten_use(decl: str) -> list[str]:
    """`use a::{b, c::{d, e as f}};` -> `use a::b;`, `use a::c::d;`, `use a::c::e as f;`.

    Blocks on one page repeat and regroup their imports — one says `use generic::DataWrapper`,
    the next `use generic::{DataWrapper, IdAndExtId}`. In one file that is an E0252 no reader
    meets, so imports are compared one name at a time.
    """
    body = re.sub(r"\s+", " ", decl.strip())
    body = re.sub(r"^use\s+|;$", "", body).strip()

    def expand(prefix: str, tree: str) -> list[str]:
        tree = tree.strip()
        brace = tree.find("{")
        if brace == -1:
            return [f"{prefix}{tree}"]
        head, inner = tree[:brace], tree[brace + 1:tree.rstrip().rfind("}")]
        parts, depth, cur = [], 0, ""
        for ch in inner:
            if ch == "," and depth == 0:
                parts.append(cur)
                cur = ""
                continue
            depth += ch == "{"
            depth -= ch == "}"
            cur += ch
        parts.append(cur)
        out = []
        for part in (p.strip() for p in parts):
            if not part:
                continue
            if part == "self":
                out.append(f"{prefix}{head.rstrip(':')}")
            else:
                out += expand(f"{prefix}{head}", part)
        return out

    return [f"use {p};" for p in expand("", body)]


def _rust_fragment(page: docblocks.Page, name: str, blocks: list[docblocks.Block],
                   shared: list[docblocks.Block] = (), blocking: bool = False) -> Unit:
    unit = Unit(page=page.rel, lang="rust", name=name)
    hoisted: list[tuple[str, docblocks.Block, int]] = []
    seen: set[str] = set()

    def take(m: re.Match, b: docblocks.Block) -> str:
        offset = b.body[:m.start()].count("\n")
        for flat in flatten_use(m.group(0).split("//")[0]):
            if flat not in seen:
                seen.add(flat)
                hoisted.append((flat, b, offset))
        return "\n" * m.group(0).count("\n")  # keep the block's own line numbers

    bodies = [(b, _RUST_USE.sub(lambda m, b=b: take(m, b), b.body)) for b in blocks]
    for b in shared:
        if b not in blocks:
            for m in _RUST_USE.finditer(b.body):
                take(m, b)

    lines = ["#![allow(unused, unreachable_code, clippy::all)]"]
    for flat, b, offset in hoisted:
        unit.segments.append(Segment(len(lines) + 1, 1, b, offset))
        lines.append(flat)
    lines += [
        "",
        "pub async fn run() -> Result<(), Box<dyn std::error::Error>> {",
        # The client every fragment assumes, of the kind its tab teaches. A page that builds
        # its own shadows it.
        "let api = intellistream_datahub_sdk::blocking::create_api_service();" if blocking
        else "let api = intellistream_datahub_sdk::create_api_service();",
    ]
    for b, rest in bodies:
        lines.append(f"// --- {page.rel}:{b.start_line} · rust #{b.lang_index} · {b.heading} ---")
        unit.segments.append(Segment(len(lines) + 1, rest.count("\n") + 1, b))
        lines.extend(rest.split("\n"))
    lines += ["Ok(())", "}", ""]
    unit.source = "\n".join(lines)
    return unit


def _rust_program(page: docblocks.Page, name: str, block: docblocks.Block) -> Unit:
    """A complete program keeps its own `main`, compiled as a module of items."""
    unit = Unit(page=page.rel, lang="rust", name=name, program=block.index)
    lines = ["#![allow(unused, unreachable_code, clippy::all)]"]
    unit.segments.append(Segment(len(lines) + 1, block.body.count("\n") + 1, block))
    lines.extend(block.body.split("\n"))
    unit.source = "\n".join(lines) + "\n"
    return unit


def rust_project(workdir: Path, sdk: Path) -> Path:
    if not (sdk / "Cargo.toml").exists():
        raise ToolchainMissing(f"Rust SDK not found at {sdk}. Set DOCTEST_RUST_SDK_PATH.")
    if not shutil.which("cargo"):
        raise ToolchainMissing("`cargo` is not on PATH.")
    manifest = (sdk / "Cargo.toml").read_text(encoding="utf-8")
    crate = next((ln.split("=", 1)[1].strip().strip('"') for ln in manifest.splitlines()
                  if ln.startswith("name")), "intellistream-datahub-sdk")
    (workdir / "src").mkdir(parents=True, exist_ok=True)
    wanted = (
        "[package]\nname = \"doc-compile\"\nversion = \"0.0.0\"\nedition = \"2021\"\n\n"
        "[dependencies]\n"
        # `blocking`, because the docs teach the blocking client beside the async one.
        f"{crate} = {{ path = \"{sdk}\", features = [\"blocking\"] }}\n"
        # What the pages import, as the tutorial's Cargo.toml tells a reader to add them.
        "tokio = { version = \"1\", features = [\"full\"] }\n"
        "chrono = \"0.4\"\nserde_json = \"1\"\nsysinfo = \"0.33\"\nhostname = \"0.4\"\n"
    )
    cargo_toml = workdir / "Cargo.toml"
    if not cargo_toml.exists() or cargo_toml.read_text(encoding="utf-8") != wanted:
        cargo_toml.write_text(wanted, encoding="utf-8")
    return workdir


def check_rust(units: list[Unit], workdir: Path, sdk: Path, timeout: int = 1800) -> dict[str, list[Diagnostic]]:
    project = rust_project(workdir, sdk)
    src = project / "src"
    for stale in src.glob("p_*.rs"):
        stale.unlink()
    by_file: dict[str, Unit] = {}
    mods = []
    for u in units:
        mod = f"p_{u.name}".lower()
        (src / f"{mod}.rs").write_text(u.source, encoding="utf-8")
        by_file[f"src/{mod}.rs"] = u
        mods.append(mod)
    (src / "main.rs").write_text("".join(f"mod {m};\n" for m in mods) + "fn main() {}\n", encoding="utf-8")

    try:
        proc = subprocess.run(["cargo", "check", "--quiet", "--message-format=json"], cwd=project,
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise ToolchainMissing(f"cargo check did not finish in {timeout}s") from exc
    out: dict[str, list[Diagnostic]] = {u.name: [] for u in units}
    reached = False
    for line in proc.stdout.splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("reason") != "compiler-message":
            continue
        m = msg["message"]
        primary = next((s for s in m.get("spans", []) if s.get("is_primary")), None)
        if primary is None or primary["file_name"] not in by_file:
            continue
        reached = True
        if m.get("level") != "error":
            continue
        unit = by_file[primary["file_name"]]
        code = (m.get("code") or {}).get("code") or ""
        text = f"{code + ': ' if code else ''}{m['message']}"
        if primary.get("label"):
            text += f" ({primary['label']})"
        out[unit.name].append(Diagnostic(unit.page, "rust", unit.locate(primary["line_start"]), text,
                                         rust_placeholder(code, m["message"])))
    if proc.returncode != 0 and not reached:
        raise ToolchainMissing(f"cargo check failed before it reached the docs:\n{proc.stderr[-3000:]}")
    return out


def rust_placeholder(code: str, message: str) -> str | None:
    """The name, when an error only says "this page never defines value/function X".

    Types, modules and imports are never placeholders, and neither is anything reached
    through a path: `cannot find function \\`retrieve\\` in module \\`timeseries\\`` is the SDK
    losing something, not the reader being asked for it.
    """
    if code != "E0425":
        return None
    m = re.match(r"cannot find (?:value|function) `([^`]+)` in this scope", message)
    return m.group(1) if m else None


# ---------------------------------------------------------------- Java

_JAVA_IMPORT = re.compile(r"^[ \t]*import[ \t]+(?:static[ \t]+)?[\w.*]+;[ \t]*$", re.M)
_JAVA_PACKAGE = re.compile(r"^[ \t]*package[ \t]+[\w.]+;[ \t]*$", re.M)
_JAVA_STATIC_METHOD = re.compile(
    r"^(?:(?:public|private|protected)\s+)?static\s+(?!final\b|class\b|record\b)[\w<>\[\],.? ]+?\s+\w+\s*\(")
_JAVA_CLIENT_DECL = re.compile(r"\b(?:var|DatahubClient)\s+client\s*=")
_SDK_IMPORTS_MARK = "// @@SDK_IMPORTS@@"

# What an IDE would import for a fragment without asking. `com.sun.management` is left out
# on purpose: it has an `OperatingSystemMXBean` of its own, and the page that wants that one
# names it in prose, so that page's plan imports it by name.
JDK_IMPORTS = ("java.util", "java.util.function", "java.util.stream", "java.util.concurrent",
               "java.time", "java.nio.file", "java.lang.management")

# A simple name two SDK packages both define. The SDK's own type wins: it is the one the
# client's methods take.
_PREFER = ("ai.intellistream.datahub.sdk.",)


def sdk_imports(classpath: str) -> list[str]:
    """`import pkg.*;` for every package in the SDK's jars, plus explicit picks for clashes."""
    packages: dict[str, set[str]] = {}
    for entry in classpath.split(os.pathsep):
        path = Path(entry)
        if path.suffix != ".jar" or not path.exists():
            continue
        with zipfile.ZipFile(path) as jar:
            for name in jar.namelist():
                if not name.startswith("ai/intellistream/") or not name.endswith(".class") or "$" in name:
                    continue
                pkg, _, cls = name[:-len(".class")].rpartition("/")
                if cls in ("package-info", "module-info"):
                    continue
                packages.setdefault(pkg.replace("/", "."), set()).add(cls)
    if not packages:
        raise ToolchainMissing("The Java classpath holds no ai.intellistream classes: is the SDK jar built?")

    owners: dict[str, list[str]] = {}
    for pkg, classes in packages.items():
        for cls in classes:
            owners.setdefault(cls, []).append(pkg)
    explicit = []
    for cls, pkgs in sorted(owners.items()):
        if len(pkgs) > 1:
            pick = next((p for p in sorted(pkgs) if p.startswith(_PREFER)), sorted(pkgs)[0])
            explicit.append(f"import {pick}.{cls};")
    return ([f"import {p}.*;" for p in sorted(packages)] + [f"import {p}.*;" for p in JDK_IMPORTS]
            + explicit)


def _split_java_methods(body: str) -> tuple[list[tuple[int, str]], str]:
    """Static helper methods declared at the top of a block, and the body without them.

    A page that shows `static RelForm rel(...)` means "put this beside your main", which a
    method body cannot hold. They move to class scope, keeping their line offsets so an
    error inside one still points at its line on the page.
    """
    lines = body.split("\n")
    methods: list[tuple[int, str]] = []
    keep = list(lines)
    i = 0
    while i < len(lines):
        if _JAVA_STATIC_METHOD.match(lines[i]):
            depth, j, opened = 0, i, False
            while j < len(lines):
                depth += lines[j].count("{") - lines[j].count("}")
                opened = opened or "{" in lines[j]
                if opened and depth <= 0:
                    break
                j += 1
            methods.append((i, "\n".join(lines[i:j + 1])))
            for k in range(i, min(j + 1, len(lines))):
                keep[k] = ""
            i = j + 1
            continue
        i += 1
    return methods, "\n".join(keep)


def _java_fragment(page: docblocks.Page, name: str, blocks: list[docblocks.Block], plan_imports: list[str],
                   shared: list[docblocks.Block] = ()) -> Unit:
    unit = Unit(page=page.rel, lang="java", name=name)
    page_imports: list[tuple[str, docblocks.Block, int]] = []
    prepared = []
    for b in [*blocks, *(b for b in shared if b not in blocks)]:
        for m in _JAVA_IMPORT.finditer(b.body):
            page_imports.append((m.group(0).strip(), b, b.body[:m.start()].count("\n")))
    for b in blocks:
        body = _JAVA_IMPORT.sub("", b.body)  # blanked, not removed: line numbers still map
        methods, rest = _split_java_methods(body)
        prepared.append((b, methods, rest))

    lines = [_SDK_IMPORTS_MARK, *plan_imports]
    seen = set(plan_imports)
    for text, b, offset in page_imports:
        if text not in seen:
            seen.add(text)
            unit.segments.append(Segment(len(lines) + 1, 1, b, offset))
            lines.append(text)
    lines += ["", f"public class {name} {{"]
    for b, methods, _ in prepared:
        for offset, text in methods:
            unit.segments.append(Segment(len(lines) + 1, text.count("\n") + 1, b, offset))
            lines.extend(text.split("\n"))
    lines.append("  public static void main(String[] args) throws Exception {")
    if not any(_JAVA_CLIENT_DECL.search(b.body) for b in blocks):
        # The client every fragment assumes, under the name the pages use.
        lines.append("    var client = DatahubClient.fromEnv();")
    for b, _, rest in prepared:
        lines.append(f"// --- {page.rel}:{b.start_line} · java #{b.lang_index} · {b.heading} ---")
        unit.segments.append(Segment(len(lines) + 1, rest.count("\n") + 1, b))
        lines.extend(rest.split("\n"))
    lines += ["  }", "}", ""]
    unit.source = "\n".join(lines)
    return unit


def _java_program(page: docblocks.Page, block: docblocks.Block) -> Unit:
    """A complete program keeps its own class and imports; only its package line goes."""
    m = re.search(r"\b(?:public\s+)?(?:final\s+)?class\s+(\w+)", block.body)
    name = m.group(1) if m else f"P_{_ident(page.slug)}__program{block.lang_index}"
    unit = Unit(page=page.rel, lang="java", name=name, program=block.index)
    body = _JAVA_PACKAGE.sub("", block.body)
    unit.segments.append(Segment(1, body.count("\n") + 1, block))
    unit.source = body + "\n"
    return unit


def java_classpath() -> str:
    """DOCTEST_JAVA_CLASSPATH if set, else built from the platform repo like the live runner."""
    explicit = os.environ.get("DOCTEST_JAVA_CLASSPATH")
    if explicit:
        return explicit
    import runners
    try:
        return runners.java_classpath()
    except runners.ToolchainMissing as exc:
        raise ToolchainMissing(str(exc)) from exc


_JAVAC_ERROR = re.compile(r"^(?P<file>.+?\.java):(?P<line>\d+): error: (?P<msg>.*)$")


@dataclass
class _JavacError:
    unit: Unit
    line: int  # in the generated file
    message: str
    detail: list[str]

    def field(self, name: str) -> str | None:
        return next((d.split(":", 1)[1].strip() for d in self.detail if d.startswith(f"{name}:")), None)


def _javac(sources: dict[str, Unit], workdir: Path, classpath: str, timeout: int) -> list[_JavacError]:
    """Compile generated sources (file name -> unit) in one javac run; the errors, parsed."""
    src = workdir / "src"
    if src.exists():
        shutil.rmtree(src)
    src.mkdir(parents=True)
    by_file: dict[str, Unit] = {}
    for name, unit in sources.items():
        path = src / name
        path.write_text(unit.source, encoding="utf-8")
        by_file[str(path)] = unit
    # -XDshould-stop.ifError=FLOW: keep attributing every file even when one fails to
    # parse, or one syntax error would hide every type error on every other page.
    cmd = ["javac", "-proc:none", "-nowarn", "-Xmaxerrs", "100000", "-XDshould-stop.ifError=FLOW",
           "-d", str(workdir / "classes"), "-cp", classpath, *by_file]
    try:
        proc = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise ToolchainMissing(f"javac did not finish in {timeout}s") from exc
    errors: list[_JavacError] = []
    lines = proc.stderr.splitlines()
    i = 0
    while i < len(lines):
        m = _JAVAC_ERROR.match(lines[i])
        if not m or m.group("file") not in by_file:
            i += 1
            continue
        j = i + 1
        while j < len(lines) and not _JAVAC_ERROR.match(lines[j]) and not re.match(r"^\d+ errors?$", lines[j]):
            j += 1
        errors.append(_JavacError(by_file[m.group("file")], int(m.group("line")), m.group("msg"),
                                  [ln.strip() for ln in lines[i + 1:j]]))
        i = j
    if proc.returncode != 0 and not errors:
        raise ToolchainMissing(f"javac failed before it reached the docs:\n{proc.stderr[-3000:]}")
    return errors


def check_java(units: list[Unit], workdir: Path, classpath: str, timeout: int = 900) -> dict[str, list[Diagnostic]]:
    if not shutil.which("javac"):
        raise ToolchainMissing("`javac` is not on PATH.")
    imports = sdk_imports(classpath)
    for u in units:
        if _SDK_IMPORTS_MARK in u.source:
            # One marker line becomes the whole import block; everything below it shifts.
            shift = len(imports) - 1
            u.source = u.source.replace(_SDK_IMPORTS_MARK, "\n".join(imports), 1)
            u.segments = [replace(s, first_line=s.first_line + shift) for s in u.segments]

    first: dict[str, list[tuple[int, Diagnostic]]] = {u.name: [] for u in units}
    stubs: dict[str, dict[int, list[tuple[str, str]]]] = {}  # unit -> line -> (kind, name)
    for e in _javac({f"{u.name}.java": u for u in units}, workdir, classpath, timeout):
        symbol, location = e.field("symbol"), e.field("location")
        text = e.message + (f": {symbol}" if symbol else "") + (f" (in {location})" if symbol and location else "")
        name = java_placeholder(e.message, symbol, location, e.unit.name)
        first[e.unit.name].append((e.line, Diagnostic(e.unit.page, "java", e.unit.locate(e.line), text, name)))
        if name and e.unit.program is None:
            kind = symbol.split()[0]
            stubs.setdefault(e.unit.name, {}).setdefault(e.line, []).append((kind, name))

    # Second pass, for what the first cannot see. javac does not look a method up at all
    # when an argument is unresolved, so `client.resources().create(stations, track)` —
    # `stations` being the reader's — says nothing about whether `create` still exists.
    # Every unresolved name is replaced by a generic `__doctestAny()`, whose type javac
    # infers from where it stands, and the same lines are compiled again. Only lookups
    # that fail on those lines count: anything else in this pass is a consequence of the
    # stub, not of the page.
    by_name = {u.name: u for u in units}
    stubbed: dict[str, Unit] = {}
    for unit_name, at in stubs.items():
        u = by_name[unit_name]
        lines = u.source.split("\n")
        for line, names in at.items():
            text = lines[line - 1]
            for kind, name in names:
                if kind == "method":
                    text = re.sub(rf"(?<![\w.]){re.escape(name)}\s*\(", "__doctestAny(", text)
                else:
                    text = re.sub(rf"(?<![\w.]){re.escape(name)}\b(?!\s*\()", "__doctestAny()", text)
            lines[line - 1] = text
        # On the class line itself, so no line below it moves.
        lines = [ln + " @SuppressWarnings(\"unchecked\") static <T> T __doctestAny(Object... ignored) { return null; }"
                 if ln.startswith(f"public class {u.name} {{") else ln for ln in lines]
        stubbed[f"{u.name}.java"] = replace(u, source="\n".join(lines))
    survives: dict[str, set[int]] = {}
    extra: dict[str, list[Diagnostic]] = {}
    if stubbed:
        for e in _javac(stubbed, workdir / "stubbed", classpath, timeout):
            if e.line not in stubs[e.unit.name]:
                continue
            survives.setdefault(e.unit.name, set()).add(e.line)
            if not _lookup_failed(e):
                continue
            symbol, location = e.field("symbol"), e.field("location")
            text = (e.message + (f": {symbol} (in {location})" if symbol else "")
                    + " [with the page's reader-supplied names stubbed]")
            extra.setdefault(e.unit.name, []).append(Diagnostic(e.unit.page, "java", e.unit.locate(e.line), text))

    out: dict[str, list[Diagnostic]] = {}
    for unit in units:
        kept = []
        for line, diag in first[unit.name]:
            # An error on a line whose reader-supplied names were stubbed, which then goes away
            # once they are stubbed, was about the placeholder and not about the page:
            # `ingest(Map.of("x", readings))` cannot infer its map type while `readings` is
            # unknown, and reports as a type mismatch on a call the reader would make correctly.
            near_stub = any(abs(line - stubbed_line) <= 3 for stubbed_line in stubs.get(unit.name, {}))
            if (diag.placeholder is None and near_stub
                    and line not in survives.get(unit.name, set())):
                continue
            kept.append(diag)
        seen = {(d.where, d.message) for d in kept}
        kept += [d for d in extra.get(unit.name, []) if (d.where, d.message) not in seen]
        out[unit.name] = kept
    return out


def _lookup_failed(e: _JavacError) -> bool:
    """A method or constructor that does not exist, or does not take that many arguments.

    The two things a stubbed argument cannot fake. Anything about argument *types* is out:
    a stub's type is whatever javac inferred, not what the reader will pass.
    """
    symbol, location = e.field("symbol") or "", e.field("location") or ""
    if e.message.strip() == "cannot find symbol":
        # A stub standing where a receiver belongs (`listener.poll()`) is an Object.
        return symbol.startswith("method") \
            and location not in ("class Object", f"class {e.unit.name}") and not location.endswith("of type Object")
    if "cannot be applied to given types" in e.message:
        return any("differ in length" in d for d in e.detail)
    if e.message.startswith("no suitable"):
        reasons = [d for d in e.detail if d.startswith(("method ", "constructor "))]
        return bool(reasons) and all("differ in length" in d for d in reasons)
    return False


def java_placeholder(msg: str, symbol: str | None, location: str | None, cls: str) -> str | None:
    """The name, when an error only says "this page never defines value/method X".

    Only a variable or method looked up in the wrapper class itself counts. A missing
    *class* is never a placeholder, and neither is a method looked up on anything else:
    `method of(String)` *in* `class Timeseries` is the SDK losing a factory.

    Nor is a "variable" named like a type. `FileUploadRequest.builder()` with the class gone
    reaches javac as an unknown *variable* `FileUploadRequest`, which would otherwise pass as
    something the reader supplies. Constants (`METRICS`) are the reader's; `UpperCamel` is not.
    """
    if msg.strip() != "cannot find symbol" or not symbol or location != f"class {cls}":
        return None
    m = re.match(r"(variable|method)\s+(\w+)", symbol)
    if not m:
        return None
    if m.group(1) == "variable" and re.match(r"^[A-Z](?![A-Z0-9_]*$)", m.group(2)):
        return None
    return m.group(2)


# ---------------------------------------------------------------- orchestration

def all_units(lang: str, repo: Path = REPO, errors: dict[str, str] | None = None) -> dict[str, list[Unit]]:
    """page rel -> units, for every page with blocks in `lang`.

    A plan whose selection no longer fits its page is that page's failure, recorded in
    `errors`, not a crash that takes every other page's result with it.
    """
    all_plans = list(plans_mod.load_all().values())
    out: dict[str, list[Unit]] = {}
    for page in docblocks.all_pages(repo):
        if page.of_lang(lang):
            # A page can carry several plans when it makes several promises: the
            # tutorial's steps and its complete program, or a replay and a live run that
            # each declare the same variable. Every plan with a section for this language
            # is a program to compile; identical selections compile once.
            mine = [p for p in all_plans if p.page == page.rel]
            chosen = [p for p in mine if lang in p.langs] or mine[:1] or [None]
            units, seen = [], set()
            try:
                selections = [(plan, selection(page, lang, plan)) for plan in chosen]
            except plans_mod.PlanError as exc:
                if errors is not None:
                    errors[page.rel] = f"the plan's block selection does not fit the page: {exc}"
                continue
            for plan, sel in selections:
                key = (tuple(b.index for b in sel.blocks), sel.independent, tuple(sel.imports))
                if key in seen:
                    continue
                seen.add(key)
                for unit in units_for(page, lang, plan, tag=f"__{_ident(plan.slug)}" if len(chosen) > 1 else ""):
                    # A complete program is the same file whichever plan selected it.
                    if unit.program is None or all(u.program != unit.program for u in units):
                        units.append(unit)
            if units:
                out[page.rel] = units
    return out


def run(lang: str, workdir: Path, repo: Path = REPO,
        extra_pages: tuple[docblocks.Page, ...] = ()) -> dict[str, list[Diagnostic]]:
    """Compile every page in one compiler invocation; page rel -> diagnostics.

    `extra_pages` ride along in the same invocation, unplanned — the controls in
    test_compile.py, which cost nothing extra there and would cost a second SDK build apart.
    """
    plan_errors: dict[str, str] = {}
    pages = all_units(lang, repo, plan_errors)
    for page in extra_pages:
        pages[page.rel] = units_for(page, lang, None)
    units = [u for us in pages.values() for u in us]
    if lang == "rust":
        sdk = Path(os.environ.get("DOCTEST_RUST_SDK_PATH", repo.parent / "dataplatform-rust-sdk"))
        found = check_rust(units, workdir, sdk)
    else:
        found = check_java(units, workdir, java_classpath())
    out: dict[str, list[Diagnostic]] = {}
    for page, us in pages.items():
        # Independent snippets share the page's imports, so one bad import is reported by
        # every snippet that carries it. Once per doc line is enough.
        seen: set[tuple[str, str]] = set()
        out[page] = [d for u in us for d in found[u.name]
                     if (d.where, d.message) not in seen and not seen.add((d.where, d.message))]
    for page, message in plan_errors.items():
        out[page] = [Diagnostic(page, lang, page, message)]
    return out
