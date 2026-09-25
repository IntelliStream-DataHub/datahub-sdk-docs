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

import ast
import functools
import json
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


class SdkDrift(Exception):
    """The SDK checkout is not the version the docs describe — fail, don't skip.

    Deliberately not a `ToolchainMissing`: that one skips, and a silent skip is how this
    went unnoticed. A checkout on the wrong branch answers every question confidently and
    wrongly — it reported eight reference pages as broken when they were right, and passed
    edits made against an SDK nobody ships.
    """


# The repositories the docs describe, by URL rather than by remote name: on a working
# checkout `origin` was a personal mirror whose default branch was an old `master`, so a
# guard that trusted `origin/HEAD` would have called a 445-commit drift current.
UPSTREAM = {
    "java": ("IntelliStream-DataHub/datahub-platform", "main"),
    "rust": ("IntelliStream-DataHub/dataplatform-rust-sdk", "main"),
}


def sdk_repo(lang: str) -> Path:
    """The checkout a tier compiles against — one place, so the guard and the runners agree."""
    if lang == "java":
        return Path(os.environ.get("DOCTEST_JAVA_REPO", REPO.parent / "datahub-platform"))
    return Path(os.environ.get("DOCTEST_RUST_SDK_PATH", REPO.parent / "dataplatform-rust-sdk"))


def python_sdk_source() -> Path | None:
    """The checkout the installed Python bindings were built from, or None for a released wheel.

    The bindings are a maturin build of the Rust SDK, so they drift the same way — and more
    quietly, because a venv keeps whatever was compiled into it long after the checkout it
    came from has moved. `direct_url.json` is what an editable install leaves behind.
    """
    try:
        from importlib.metadata import distribution
        raw = distribution("intellistream-datahub-sdk").read_text("direct_url.json")
    except Exception:
        return None
    if not raw:
        return None
    try:
        url = json.loads(raw).get("url", "")
    except json.JSONDecodeError:
        return None
    if not url.startswith("file://"):
        return None  # a real wheel: it has a version, not a commit
    built_from = Path(url[len("file://"):])
    return built_from.parent if built_from.name == "datahub_python_bindings" else built_from


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, timeout=60)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def sdk_provenance(repo: Path, lang: str) -> str:
    """One line naming the commit a tier compiled against, and its distance from upstream.

    Every compile failure carries this. The question a failure raises first is "is the page
    wrong, or am I holding the wrong SDK?", and the answer should not take a source dive.
    """
    slug, branch = UPSTREAM[lang]
    head = _git(repo, "rev-parse", "--short", "HEAD") or "unknown"
    where = _git(repo, "rev-parse", "--abbrev-ref", "HEAD") or "detached"
    ref = _upstream_ref(repo, slug, branch)
    if not ref:
        return f"{repo.name} @ {head} ({where}; no remote for {slug}, so drift is unchecked)"
    behind = _git(repo, "rev-list", "--count", f"HEAD..{ref}")
    return f"{repo.name} @ {head} ({where}, {behind or '?'} behind {slug} {branch})"


def _upstream_ref(repo: Path, slug: str, branch: str) -> str:
    """`<remote>/<branch>` for the remote whose URL is `slug`, or "" if none is configured."""
    for line in _git(repo, "remote", "-v").splitlines():
        name, _, rest = line.partition("\t")
        url = rest.split(" ")[0]
        if slug in url.replace(":", "/") and _git(repo, "rev-parse", "--verify", f"{name}/{branch}"):
            return f"{name}/{branch}"
    return ""


def assert_sdk_current(repo: Path, lang: str) -> None:
    """Refuse to judge the docs against an SDK behind the branch they describe.

    AGENTS.md pins the target: the docs describe the default branch of each SDK repo, not
    whatever a contributor has checked out. Testing an unmerged SDK change is legitimate,
    so `DOCTEST_ALLOW_SDK_DRIFT=1` says "I mean this checkout" — but it has to be said.
    """
    if os.environ.get("DOCTEST_ALLOW_SDK_DRIFT"):
        return
    slug, branch = UPSTREAM[lang]
    ref = _upstream_ref(repo, slug, branch)
    if not ref:
        return  # nothing to compare against; sdk_provenance says so on any failure
    behind = _git(repo, "rev-list", "--count", f"HEAD..{ref}")
    if behind and behind != "0":
        raise SdkDrift(
            f"{repo} is {behind} commits behind {ref}, and the docs describe {slug} {branch}.\n"
            f"  {sdk_provenance(repo, lang)}\n"
            f"  Every {lang} result from this checkout is about an SDK nobody ships: it reports\n"
            f"  pages as broken that are not, and passes pages that are.\n"
            f"  Fix: `git -C {repo} fetch && git -C {repo} checkout {ref}` (a detached checkout is\n"
            f"  fine), or set DOCTEST_ALLOW_SDK_DRIFT=1 to test this checkout on purpose."
        )


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


# A program the reader would put inside an `async def`, because the page's example awaits
# something. Deciding by compiling is exact, where a regex for "await" would be fooled by the
# word in a string or a comment.
_ASYNC_LAUNCHER = """import ast, asyncio, pathlib, sys
source = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
code = compile(source, sys.argv[1], "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
namespace = {"__name__": "__main__", "__file__": sys.argv[1]}
result = eval(code, namespace)
if result is not None:
    asyncio.run(result)
"""


def needs_event_loop(source: str) -> bool:
    """Whether the composed program awaits at the top level, as an async example does."""
    try:
        compile(source, "tutorial.py", "exec")
    except SyntaxError:
        try:
            compile(source, "tutorial.py", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
        except SyntaxError:
            return False  # broken another way; let the run report it as the reader sees it
        return True
    return False


def run_python(source: str, line_map, workdir: Path, env: dict[str, str], lp: LangPlan) -> RunResult:
    path = workdir / "tutorial.py"
    path.write_text(source, encoding="utf-8")
    # The pages now show async clients (`AsyncDataHubClient`), whose examples await at the top
    # level, which a plain `python tutorial.py` refuses. The launcher compiles the same file with
    # top-level await allowed and runs the coroutine, so the file, and every line number in a
    # traceback, stays exactly what the page shows.
    argv = [sys.executable, str(path)]
    if needs_event_loop(source):
        launcher = workdir / "run_with_event_loop.py"
        launcher.write_text(_ASYNC_LAUNCHER, encoding="utf-8")
        argv = [sys.executable, str(launcher), str(path)]
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
    return _exec(argv, workdir, _child_env(env, extra), lp.timeout, source, line_map)


# --- Java ---------------------------------------------------------

_JAVA_IMPORT = re.compile(r"^\s*import\s+[\w.*]+;\s*$", re.MULTILINE)


@functools.cache
def java_classpath() -> str:
    """Resolve the datahub-java-sdk classpath from the platform repo, once per session.

    Asked of Gradle every session rather than cached in a file: a file cache outlived the
    jars it named (0.1.0 builds, long after the SDK moved to 0.3.0), and a stale classpath
    compiles every snippet against the wrong SDK, which reads as every page being broken.
    Gradle's own up-to-date check makes asking cheap.
    """
    platform = sdk_repo("java")
    init = HERE / "java-classpath.gradle"
    if not (platform / "gradlew").exists() or not init.exists():
        raise ToolchainMissing(
            f"Java SDK repo not found at {platform}. Set DOCTEST_JAVA_REPO to the "
            "datahub-platform checkout, or leave Java out of DOCTEST_LANGS."
        )
    assert_sdk_current(platform, "java")
    try:
        # Both jars: the SDK's runtime classpath names the api-model *jar*, and `:datahub-java-sdk:jar`
        # alone compiles against api-model's classes directory without ever writing it.
        subprocess.run([str(platform / "gradlew"), "-q", ":datahub-api-model:jar", ":datahub-java-sdk:jar"],
                       cwd=platform, capture_output=True, text=True, timeout=900, check=True)
        proc = subprocess.run([str(platform / "gradlew"), "-q", "-I", str(init), ":datahub-java-sdk:printSdkCp"],
                              cwd=platform, capture_output=True, text=True, timeout=900, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ToolchainMissing(f"Could not build the Java SDK classpath: {exc}") from exc
    cp = next((ln[len("SDKCP="):] for ln in proc.stdout.splitlines() if ln.startswith("SDKCP=")), "")
    if not cp:
        raise ToolchainMissing("Gradle produced no classpath line.")
    return cp


def run_java(source: str, line_map, workdir: Path, env: dict[str, str], lp: LangPlan) -> RunResult:
    if not shutil.which("java"):
        raise ToolchainMissing("`java` is not on PATH.")
    cp = java_classpath()
    # Java demands imports above the class, so any the doc shows are hoisted out of
    # the body. Everything else becomes the body of main.
    imports = "\n".join(m.group(0).strip() for m in _JAVA_IMPORT.finditer(source))
    body = _JAVA_IMPORT.sub("", source)
    # The same imports the compile tier gives a fragment, read off the jars: a hand-kept
    # list here went stale when the model types moved to models.forms and friends.
    import compile_check
    sdk_imports = "\n".join(compile_check.sdk_imports(cp))
    wrapped = (
        f"{sdk_imports}\n"
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
    sdk = sdk_repo("rust")
    if not (sdk / "Cargo.toml").exists():
        raise ToolchainMissing(
            f"Rust SDK not found at {sdk}. Set DOCTEST_RUST_SDK_PATH, or leave Rust out of DOCTEST_LANGS."
        )
    if not shutil.which("cargo"):
        raise ToolchainMissing("`cargo` is not on PATH.")
    assert_sdk_current(sdk, "rust")

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
