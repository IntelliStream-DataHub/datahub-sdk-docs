"""Assemble a page's blocks into a program and run it against the live stack.

Assembly is the interesting half. A tutorial is written as a sequence of fragments
that a reader accumulates — Step 1 builds a client, Step 4 uses it — so the program
under test is the page's blocks *concatenated in reading order*. That is what makes
this an end-to-end test of the tutorial rather than a spot-check of its last snippet:
if Step 2 stops working with Step 1, the run breaks.

Each block is fenced in the composed source with a comment naming its line in the
page, so a traceback points at the doc rather than at a temp file.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from plans import LangPlan, PlanError

HERE = Path(__file__).parent
REPO = HERE.parent


class ToolchainMissing(Exception):
    """A language's compiler or SDK build is absent — skip, don't fail."""


@dataclass
class RunResult:
    exit_code: int
    stdout: str
    stderr: str
    source: str
    duration: float
    timed_out: bool = False
    # Where each block landed in the composed file, for mapping a traceback back
    # to the page: composed line number -> doc location.
    line_map: list[tuple[int, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def blame(self, composed_line: int) -> str:
        """The doc location whose block contains this line of the composed file."""
        where = "prologue/harness"
        for start, label in self.line_map:
            if composed_line >= start:
                where = label
            else:
                break
        return where


# The bindings echo every HTTP response body. Useful when debugging one call,
# overwhelming in a failure report, so it is folded away rather than discarded.
_NOISE = re.compile(r"^Response body for path: .*$|^\{\"items\":.*$", re.MULTILINE)


def tidy(text: str, limit: int = 4000) -> str:
    folded = _NOISE.sub("«sdk response body»", text).strip()
    folded = re.sub(r"(«sdk response body»\n?){2,}", "«sdk response bodies»\n", folded)
    if len(folded) > limit:
        head, tail = folded[: limit // 2], folded[-limit // 2 :]
        folded = f"{head}\n… {len(folded) - limit} chars elided …\n{tail}"
    return folded


# ---------------------------------------------------------------- assembly

_COMMENT = {"python": "#", "rust": "//", "java": "//"}


def compose_one(lang: str, lp: LangPlan, blocks: list, page: str) -> tuple[str, list[tuple[int, str]]]:
    """One page's contribution: its harness prologue plus its own blocks, in order."""
    selected = lp.select(blocks)
    if not selected:
        raise PlanError(f"{page} [{lang}]: the plan selects no blocks, so there is nothing to run.")

    c = _COMMENT[lang]
    parts: list[str] = []
    marks: list[tuple[int, str]] = []  # offsets within this fragment, fixed up by caller
    line = 1

    def emit(text: str, label: str | None = None) -> None:
        nonlocal line
        if label:
            marks.append((line, label))
        parts.append(text)
        line += text.count("\n") + 1

    if lp.prologue.strip():
        # Labelled like a block so a traceback landing in fixture code is blamed on
        # the plan, not on whichever doc block happened to precede it.
        emit(f"{c} --- harness prologue for {page} ---\n{lp.prologue.rstrip()}",
             f"doctests/plans (prologue for {page})")

    # Applied where they match. Whether every injection has a home is a property of
    # the plan as a whole, checked once by `LangPlan.validate_injects` — in
    # independent mode this function is called per block, so a valid injection for
    # block 5 would look unused while composing block 1.
    injections = {i.before: i.code for i in lp.inject}

    for b in selected:
        if b.lang_index in injections:
            emit(f"\n{c} --- harness inject before {lang} #{b.lang_index} ---\n"
                 f"{injections[b.lang_index].rstrip()}",
                 f"doctests/plans (inject before {lang} #{b.lang_index} of {page})")
        emit(f"\n{c} --- {page}:{b.start_line} · {lang} #{b.lang_index} · {b.heading} ---", b.where(page))
        emit(b.body.rstrip())

    if lp.epilogue.strip():
        emit(f"\n{c} --- harness epilogue for {page} ---\n{lp.epilogue.rstrip()}",
             f"doctests/plans (epilogue for {page})")

    fragment = "\n".join(parts) + "\n"
    # A plan's replacements only ever touch its own page's code. Letting them reach
    # into a prerequisite's fragment would mean one plan silently rewriting another
    # page's tutorial.
    for r in lp.replace:
        fragment = r.apply(fragment)
    return fragment, marks


def compose(lang: str, sections: list[tuple[LangPlan, list, str]]) -> tuple[str, list[tuple[int, str]]]:
    """Stitch a whole chain into one program: prerequisites first, target last.

    Imports from every section are hoisted to the top so a prerequisite's `import`
    is in scope for the page that continues from it, and so Java gets them where
    the language demands they go.
    """
    c = _COMMENT[lang]
    header = [ln for lp, _, _ in sections for ln in lp.imports.rstrip().splitlines() if ln.strip()]
    seen: set[str] = set()
    header = [ln for ln in header if not (ln in seen or seen.add(ln))]

    body_parts: list[str] = []
    line_map: list[tuple[int, str]] = []
    line = len(header) + (2 if header else 1)

    for lp, blocks, page in sections:
        banner = f"{c} ═══ {page} ═══"
        fragment, marks = compose_one(lang, lp, blocks, page)
        body_parts.append(banner)
        line += 1
        line_map.extend((line + off - 1, label) for off, label in marks)
        body_parts.append(fragment.rstrip("\n"))
        line += fragment.rstrip("\n").count("\n") + 1

    source = ("\n".join(header) + "\n\n" if header else "") + "\n".join(body_parts) + "\n"
    return source, sorted(line_map)


# ---------------------------------------------------------------- execution

def _exec(cmd: list[str], cwd: Path, env: dict[str, str], timeout: int, source: str,
          line_map: list[tuple[int, str]]) -> RunResult:
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        return RunResult(proc.returncode, proc.stdout, proc.stderr, source,
                         time.monotonic() - started, line_map=line_map)
    except subprocess.TimeoutExpired as exc:
        return RunResult(
            -1,
            exc.stdout or "" if isinstance(exc.stdout, str) else (exc.stdout or b"").decode(errors="replace"),
            exc.stderr or "" if isinstance(exc.stderr, str) else (exc.stderr or b"").decode(errors="replace"),
            source, time.monotonic() - started, timed_out=True, line_map=line_map,
        )


def _child_env(env: dict[str, str], extra: dict[str, str]) -> dict[str, str]:
    out = {**os.environ, **env, **extra}
    # A doc program must not inherit the harness' pytest plumbing.
    for key in ("PYTEST_CURRENT_TEST", "PYTEST_XDIST_WORKER"):
        out.pop(key, None)
    return out


def run_python(source: str, line_map, workdir: Path, env: dict[str, str], lp: LangPlan) -> RunResult:
    path = workdir / "tutorial.py"
    path.write_text(source, encoding="utf-8")
    extra = {
        # Thirteen pages end by plotting what they just computed. On a headless runner
        # `plt.show()` either blocks or dies; Agg makes it a no-op, so the page keeps
        # its final block instead of the plan having to cut it.
        "MPLBACKEND": "Agg",
        # So a prologue can `from tutorial_support import ...` for a bounded listener
        # or a placeholder stub.
        "PYTHONPATH": os.pathsep.join(filter(None, [str(HERE), os.environ.get("PYTHONPATH", "")])),
        **lp.env,
    }
    return _exec([sys.executable, str(path)], workdir, _child_env(env, extra), lp.timeout, source, line_map)


# --- Java ---------------------------------------------------------

_JAVA_IMPORT = re.compile(r"^\s*import\s+[\w.*]+;\s*$", re.MULTILINE)
_CP_CACHE = HERE / ".java-classpath"


def java_classpath() -> str:
    """Resolve (once) the datahub-java-sdk classpath from the platform repo."""
    if _CP_CACHE.exists() and _CP_CACHE.read_text().strip():
        return _CP_CACHE.read_text().strip()
    platform = Path(os.environ.get("DOCTEST_JAVA_REPO", REPO.parent / "datahub-platform"))
    init = HERE / "java-classpath.gradle"
    if not (platform / "gradlew").exists() or not init.exists():
        raise ToolchainMissing(
            f"Java SDK repo not found at {platform}. Set DOCTEST_JAVA_REPO to the "
            "datahub-platform checkout, or leave Java out of DOCTEST_LANGS."
        )
    try:
        subprocess.run([str(platform / "gradlew"), "-q", ":datahub-java-sdk:jar"],
                       cwd=platform, capture_output=True, text=True, timeout=900, check=True)
        proc = subprocess.run([str(platform / "gradlew"), "-q", "-I", str(init), ":datahub-java-sdk:printSdkCp"],
                              cwd=platform, capture_output=True, text=True, timeout=900, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ToolchainMissing(f"Could not build the Java SDK classpath: {exc}") from exc
    cp = next((ln[len("SDKCP="):] for ln in proc.stdout.splitlines() if ln.startswith("SDKCP=")), "")
    if not cp:
        raise ToolchainMissing("Gradle produced no classpath line.")
    _CP_CACHE.write_text(cp)
    return cp


def run_java(source: str, line_map, workdir: Path, env: dict[str, str], lp: LangPlan) -> RunResult:
    if not shutil.which("java"):
        raise ToolchainMissing("`java` is not on PATH.")
    cp = java_classpath()
    # Java demands imports above the class, so any the doc shows are hoisted out of
    # the body. Everything else becomes the body of main.
    imports = "\n".join(m.group(0).strip() for m in _JAVA_IMPORT.finditer(source))
    body = _JAVA_IMPORT.sub("", source)
    wrapped = (
        "import ai.intellistream.datahub.sdk.client.*;\n"
        "import ai.intellistream.datahub.sdk.services.*;\n"
        "import ai.intellistream.datahub.sdk.ingest.*;\n"
        "import ai.intellistream.datahub.sdk.timeseries.*;\n"
        "import ai.intellistream.datahub.api.responses.*;\n"
        # The model types live in a sibling package to the SDK's own, and both are
        # imported on demand — so Datapoint is named explicitly to keep it unambiguous.
        "import ai.intellistream.datahub.timeseries.*;\n"
        "import ai.intellistream.datahub.sdk.timeseries.Datapoint;\n"
        "import ai.intellistream.datahub.models.*;\n"
        "import ai.intellistream.datahub.resource.*;\n"
        "import java.util.*;\nimport java.time.*;\n"
        f"{imports}\n\npublic class Tutorial {{\n"
        "  public static void main(String[] args) throws Exception {\n"
        f"{body}\n  }}\n}}\n"
    )
    path = workdir / "Tutorial.java"
    path.write_text(wrapped, encoding="utf-8")
    return _exec(["java", "-cp", cp, str(path)], workdir, _child_env(env, lp.env), lp.timeout, wrapped, line_map)


# --- Rust ---------------------------------------------------------

_RUST_DIR = HERE / ".rust-runner"


def rust_project() -> Path:
    """A cargo project wired to the local SDK by path, reused across runs.

    Kept outside the temp dir on purpose: a fresh target/ per test would mean a
    full SDK rebuild per page, which is minutes rather than seconds.
    """
    sdk = Path(os.environ.get("DOCTEST_RUST_SDK_PATH", REPO.parent / "dataplatform-rust-sdk"))
    if not (sdk / "Cargo.toml").exists():
        raise ToolchainMissing(
            f"Rust SDK not found at {sdk}. Set DOCTEST_RUST_SDK_PATH, or leave Rust out of DOCTEST_LANGS."
        )
    if not shutil.which("cargo"):
        raise ToolchainMissing("`cargo` is not on PATH.")

    # Read the crate name rather than assuming it: the crate has been renamed once
    # already (dataplatform-rust-sdk -> intellistream-datahub-sdk), and a runner that
    # hardcodes it fails with "no matching package" instead of the doc error it was
    # built to report.
    manifest = (sdk / "Cargo.toml").read_text(encoding="utf-8")
    crate = next(
        (ln.split("=", 1)[1].strip().strip('"')
         for ln in manifest.splitlines() if ln.startswith("name")),
        "intellistream-datahub-sdk",
    )
    (_RUST_DIR / "src").mkdir(parents=True, exist_ok=True)
    (_RUST_DIR / "Cargo.toml").write_text(
        "[package]\nname = \"doc-tutorial\"\nversion = \"0.0.0\"\nedition = \"2021\"\n\n"
        "[dependencies]\n"
        f"{crate} = {{ path = \"{sdk}\" }}\n"
        "tokio = { version = \"1\", features = [\"full\"] }\n"
        "chrono = \"0.4\"\nserde_json = \"1\"\n",
        encoding="utf-8",
    )
    return _RUST_DIR


def run_rust(source: str, line_map, workdir: Path, env: dict[str, str], lp: LangPlan) -> RunResult:
    project = rust_project()
    wrapped = (
        "#![allow(unused_imports, unused_variables, unused_mut, dead_code)]\n"
        "#[tokio::main]\nasync fn main() -> Result<(), Box<dyn std::error::Error>> {\n"
        f"{source}\n    Ok(())\n}}\n"
    )
    (project / "src" / "main.rs").write_text(wrapped, encoding="utf-8")
    # The SDK also reads a .env next to the binary; write it so both paths agree.
    (project / ".env").write_text(
        "".join(f"{k}={env[k]}\n" for k in ("BASE_URL", "TOKEN") if env.get(k)), encoding="utf-8"
    )
    return _exec(["cargo", "run", "--quiet"], project, _child_env(env, lp.env), lp.timeout, wrapped, line_map)


RUNNERS = {"python": run_python, "java": run_java, "rust": run_rust}
