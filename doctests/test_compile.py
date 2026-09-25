"""Every Java and Rust example compiles against the SDK. No backend needed.

One test per (language, page). Each compiler runs once per session over every page, so
the whole tier costs a `javac` and a `cargo check` — seconds, once the SDK's own
dependencies are built.

A failure is a claim about the page, located at the doc line: the SDK no longer has what
the page calls, or the page never had it right. What passes is spelled out in
`compile_check.py`: unresolved values and functions are the reader's to supply; anything
else — a missing type, a missing method, a wrong argument — is not.

Needs, per language (missing ones skip with the reason):

* Rust: `cargo`, and the SDK checkout at `DOCTEST_RUST_SDK_PATH` (default
  `../dataplatform-rust-sdk`).
* Java: `javac`, and the SDK classpath — `DOCTEST_JAVA_CLASSPATH`, or built from the
  platform repo at `DOCTEST_JAVA_REPO` (default `../datahub-platform`).

`--compile-langs none` (or `DOCTEST_COMPILE_LANGS=none`) turns the tier off, for a run that
should not start a Gradle or Cargo build.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

import compile_check as cc
import docblocks

REPO = Path(__file__).parent.parent


@dataclass(frozen=True)
class Control:
    """A synthetic page whose compile result is known in advance.

    The tier trusts the compilers to phrase an unresolved *value* differently from an
    unresolved *type* or a missing *method*, and trusts javac to look a method up once its
    arguments are stubbed. A JDK or Rust upgrade that rewords one message would flip what
    passes without failing anything — every doc page would just quietly start passing, or
    failing. These controls compile beside the docs, in the same invocation, and fail
    loudly if the classification drifts.
    """

    name: str
    body: str
    hard_lines: tuple[int, ...] = ()  # body line numbers (1-based) that must be hard errors
    placeholders: frozenset[str] = frozenset()

    def page(self, lang: str) -> docblocks.Page:
        block = docblocks.Block(index=1, lang_index=1, lang=lang, meta="", body=self.body,
                                start_line=10, heading="control", tab=lang)
        rel = f"doctests/controls/{lang}/{self.name}"
        return docblocks.Page(path=Path(rel), rel=rel, slug=f"control__{self.name}", blocks=[block])


CONTROLS = {
    "java": [
        Control("compiles", 'var series = new Timeseries();\nseries.setExternalId("x");\n'
                            "client.timeseries().create(series);"),
        Control("missing_method", "client.timeseries().noSuchMethodForDoctest();", hard_lines=(1,)),
        Control("missing_type", "NoSuchTypeForDoctest t = null;", hard_lines=(1,)),
        Control("static_call_on_missing_type", "NoSuchTypeForDoctest.builder();", hard_lines=(1,)),
        Control("reader_supplied", "double n = readerValue;\nrecordReading(n);",
                placeholders=frozenset({"readerValue", "recordReading"})),
        Control("missing_method_with_reader_argument", "client.timeseries().noSuchMethodForDoctest(readerValue);",
                hard_lines=(1,), placeholders=frozenset({"readerValue"})),
        # The other half of that pair: a call the reader would make correctly, which javac cannot
        # type while one argument is unknown. `Map.of("x", readings)` cannot infer its value type,
        # and the error lands on the ingest call as a mismatch. Stubbing the name resolves it, so
        # it is the placeholder's error, not the page's.
        Control("inference_blocked_by_reader_argument",
                'client.timeseries().ingest(Map.of("x", readerReadings));',
                placeholders=frozenset({"readerReadings"})),
    ],
    "rust": [
        Control("compiles", "use intellistream_datahub_sdk::timeseries::TimeSeries;\n"
                            'let ts = TimeSeries::new("x", "x");\napi.time_series.create_one(&ts).await?;'),
        Control("missing_method", "api.time_series.no_such_method_for_doctest().await?;", hard_lines=(1,)),
        Control("missing_type", "let t: NoSuchTypeForDoctest = todo!();", hard_lines=(1,)),
        Control("missing_import", "use intellistream_datahub_sdk::NoSuchThingForDoctest;", hard_lines=(1,)),
        Control("reader_supplied", "let n = reader_value;\nrecord_reading(n);",
                placeholders=frozenset({"reader_value", "record_reading"})),
        Control("missing_method_with_reader_argument",
                "api.time_series.no_such_method_for_doctest(reader_value).await?;",
                hard_lines=(1,), placeholders=frozenset({"reader_value"})),
    ],
}

CASES = [
    pytest.param(lang, page.rel, id=f"{lang}:{page.rel}")
    for lang in cc.COMPILED
    for page in docblocks.all_pages(REPO)
    if page.of_lang(lang)
]


@pytest.fixture(scope="session")
def compiled(pytestconfig, tmp_path_factory):
    wanted = pytestconfig.getoption("--compile-langs")
    results: dict[str, dict | str] = {}

    def get(lang: str) -> dict[str, list[cc.Diagnostic]]:
        if lang not in wanted:
            pytest.skip(f"{lang} compile checks not selected (--compile-langs={','.join(sorted(wanted)) or 'none'})")
        if lang not in results:
            # Rust keeps its target/ between runs: a fresh one means rebuilding the SDK's
            # dependencies, which is minutes rather than seconds.
            workdir = (Path(__file__).parent / ".compile" / lang) if lang == "rust" \
                else tmp_path_factory.mktemp(f"compile-{lang}")
            try:
                results[lang] = cc.run(lang, workdir, REPO, extra_pages=tuple(c.page(lang) for c in CONTROLS[lang]))
            except cc.ToolchainMissing as exc:
                results[lang] = str(exc)
        if isinstance(results[lang], str):
            pytest.skip(f"cannot compile {lang}: {results[lang]}")
        return results[lang]

    return get


@pytest.mark.parametrize("lang,page", CASES)
def test_examples_compile_against_the_sdk(lang, page, compiled):
    found = compiled(lang).get(page, [])
    errors = [d for d in found if not d.placeholder]
    if not errors:
        return

    supplied = sorted({d.placeholder for d in found if d.placeholder})
    lines = [
        f"The {lang} examples on {page} do not compile against the SDK ({len(errors)} error(s)):",
        "",
        *(f"  {d}" for d in errors),
        "",
        "  Each line names the doc line. The usual causes, in order: the SDK renamed or removed",
        "  what the page calls (fix the page); the page never had it right (fix the page); two",
        "  blocks are alternatives that one program cannot hold (say so in the plan, with",
        "  `independent`, `only` or `exclude` under [" + lang + "]).",
    ]
    if supplied:
        lines += ["", f"  Left to the reader, and not counted: {', '.join(supplied)}"]
    pytest.fail("\n".join(lines), pytrace=False)


@pytest.mark.parametrize("lang,control", [(lang, c) for lang, cs in CONTROLS.items() for c in cs],
                         ids=[f"{lang}:{c.name}" for lang, cs in CONTROLS.items() for c in cs])
def test_the_compiler_still_reports_what_the_tier_relies_on(lang, control, compiled):
    page = control.page(lang)
    found = compiled(lang).get(page.rel, [])
    hard = sorted({d.where for d in found if not d.placeholder})
    supplied = {d.placeholder for d in found if d.placeholder}
    want = sorted(f"{page.rel}:{10 + n} ({lang} #1)" for n in control.hard_lines)
    assert hard == want and supplied == control.placeholders, (
        f"The {lang} compiler no longer reports the '{control.name}' control the way compile_check.py "
        f"expects.\n  hard errors at: {hard} (expected {want})\n  reader-supplied: {sorted(supplied)} "
        f"(expected {sorted(control.placeholders)})\n  diagnostics: {[str(d) for d in found]}\n"
        "A compiler upgrade has probably reworded a message. Until the classifier in compile_check.py "
        "is updated, the doc results from this tier cannot be trusted in either direction."
    )
