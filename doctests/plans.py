"""Test plans: the per-page declaration of how a tutorial is run and verified.

A plan is deliberately *thin*. It never contains the tutorial's code — that always
comes from the page. It contains only the things a reader supplies from context and
a test harness cannot guess:

- which of the page's blocks form the runnable program,
- the prologue a reader would already have (a `readings` list the page says "you
  have", a directory to write into),
- bounded-run substitutions for code that would otherwise never terminate,
- the external ids the page creates, so a run can start and end clean,
- what must be true on the backend afterwards for the tutorial to have worked.

Two rules keep plans honest, both enforced in code rather than by review:

1. ``[blocks]`` records how many fences of each language the page has. Edit the
   page and the count moves, the plan stops matching, and the suite fails until a
   human re-reads it. A doc test that silently keeps passing while the doc changes
   underneath it is worse than no test.
2. Every ``replace`` must actually match. A substitution that has stopped applying
   is a substitution that is quietly no longer bounding the loop it was written for.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from docblocks import EXECUTABLE

PLAN_DIR = Path(__file__).parent / "plans"
UNTRIAGED = PLAN_DIR / "UNTRIAGED.toml"


class PlanError(Exception):
    """A plan is malformed. Always a bug in the plan, never in the docs."""


@dataclass
class Replacement:
    find: str
    repl: str
    # Some substitutions only apply to one block; most apply to the whole program.
    required: bool = True

    def apply(self, src: str) -> str:
        """Apply where it matches. Whether a required replacement matched *anywhere*
        is checked once per plan by `validate_replacements` — applying is per
        fragment, and in independent mode a replacement rightly touches one block."""
        return src.replace(self.find, self.repl) if self.find in src else src


@dataclass
class Injection:
    """Code spliced in just before one block.

    A prologue runs before the whole page, which is the wrong place for anything a
    reader only has *part way down*: step 2 of a tutorial often uses arrays that
    step 1 has just built under different names ("your `timestamps`" is the `idx`
    from the demo-data block). Defining those up front is impossible; defining them
    at the point the reader reaches them is exactly right.
    """

    before: int  # 1-based index among this language's blocks
    code: str


@dataclass
class LangPlan:
    lang: str
    disabled: str | None = None  # a reason, when this language is not run
    # Pages this one continues from, by plan slug. Their program is prepended, so
    # a guide that opens "you already have a client" is tested the way a reader
    # arrives at it: having actually run the quickstart. Writing that setup by
    # hand in a prologue instead would quietly hide a broken quickstart, which is
    # the one thing a documentation test must never do.
    requires: list[str] = field(default_factory=list)
    # Pages whose job is to *populate the backend* rather than to be continued from —
    # `advanced/generate-sample-data` seeds every series the ML recipes read. Those run
    # once per session and are not composed into the dependent program: thirteen recipes
    # each re-generating a fortnight of minute data would dominate the suite, and the
    # recipes build their own client anyway. What they need from it is the data.
    requires_once: list[str] = field(default_factory=list)
    only: list[int] = field(default_factory=list)
    exclude: list[int] = field(default_factory=list)
    # Lines hoisted to the top of the file: Java `import`s, Rust `use`s, Python
    # imports the page assumes you already ran in an earlier tab.
    imports: str = ""
    prologue: str = ""
    epilogue: str = ""
    replace: list[Replacement] = field(default_factory=list)
    inject: list[Injection] = field(default_factory=list)
    # Run each block as its own program instead of concatenating them.
    #
    # Right for an API reference, wrong for a tutorial. A reference page lists
    # independent examples — create a series, delete a series, write datapoints —
    # and running them as one program invents conflicts the reader would never hit:
    # the delete example removes what the write example needs. A tutorial is the
    # opposite: its steps only mean anything in sequence, which is why concatenation
    # is the default and this has to be asked for.
    independent: bool = False
    env: dict[str, str] = field(default_factory=dict)
    # Environment a tutorial genuinely needs, beyond a reachable backend — e.g. a
    # page that teaches the OAuth2 client-credentials constructor cannot be tested
    # honestly against a token-only stack. Missing vars skip the test with that
    # reason rather than failing it, because an unconfigurable environment is not
    # a broken document.
    requires_env: list[str] = field(default_factory=list)
    # Python packages the page tells the reader to install.
    requires_python: list[str] = field(default_factory=list)
    timeout: int = 180

    def validate_replacements(self, blocks: list, page: str) -> None:
        """Every required replacement must still match something the plan runs.

        This is the guard that stops a bounded-run substitution from lapsing: if a
        page rewrites the loop a `replace` was written for, the substitution silently
        stops applying and the next run hangs until its timeout. Checked against the
        whole selection, since `independent` composes one block at a time.
        """
        haystack = "\n".join([self.prologue, self.epilogue,
                               *(b.body for b in self.select(blocks)),
                               *(i.code for i in self.inject)])
        stale = [r.find for r in self.replace if r.required and r.find not in haystack]
        if stale:
            raise PlanError(
                f"{page} [{self.lang}]: replacement(s) {stale!r} no longer match the page. "
                "The doc changed — re-read it and update (or drop) them. Do not delete "
                "one just to get green: it exists to bound a run."
            )

    def validate_injects(self, blocks: list, page: str) -> None:
        """Every injection must land on a block this plan actually runs.

        Block numbering shifts when a page is edited, so an injection left pointing
        at nothing is a plan that has quietly stopped supplying what its page needs.
        Checked against the whole selection rather than during composition, because
        `independent` composes one block at a time.
        """
        homes = {b.lang_index for b in self.select(blocks)}
        orphans = sorted({i.before for i in self.inject} - homes)
        if orphans:
            raise PlanError(
                f"{page} [{self.lang}]: inject targets block(s) {orphans}, which this plan "
                "does not run. Block numbering may have shifted — re-read the page."
            )

    def select(self, blocks: list) -> list:
        """The blocks that make up the program, in the order the reader meets them."""
        if self.only:
            by_index = {b.lang_index: b for b in blocks}
            missing = [i for i in self.only if i not in by_index]
            if missing:
                raise PlanError(
                    f"{self.lang}: plan selects block(s) {missing} but the page has "
                    f"{len(blocks)} {self.lang} block(s)."
                )
            return [by_index[i] for i in self.only]
        return [b for b in blocks if b.lang_index not in set(self.exclude)]


@dataclass
class Plan:
    slug: str
    page: str
    path: Path
    disabled: str | None
    blocks: dict[str, int]
    langs: dict[str, LangPlan]
    owns: dict[str, list[str]]
    expect_exists: dict[str, list[str]]
    expect_datapoints: dict[str, int]
    expect_stdout: list[str]
    # How long to let eventually-consistent reads settle before calling it a failure.
    settle_secs: float

    def lang(self, lang: str) -> LangPlan:
        return self.langs.get(lang, LangPlan(lang=lang, disabled="no scenario declared for this language"))


def chain(slug: str, lang: str, all_plans: dict[str, "Plan"], _seen: tuple[str, ...] = ()) -> list["Plan"]:
    """The plans to run, prerequisites first, ending with `slug`.

    Depth-first so a chain of two hops (a guide that needs a guide that needs the
    quickstart) arrives in reading order. A cycle is a plan bug and says so.
    """
    if slug in _seen:
        raise PlanError(f"`requires` forms a cycle: {' -> '.join((*_seen, slug))}")
    if slug not in all_plans:
        raise PlanError(f"`requires` names {slug!r}, which has no plan in doctests/plans/.")

    plan = all_plans[slug]
    out: list[Plan] = []
    for dep in plan.lang(lang).requires:
        for p in chain(dep, lang, all_plans, (*_seen, slug)):
            if p.slug not in {q.slug for q in out}:
                out.append(p)
    out.append(plan)
    return out


def merged_owns(plans: list["Plan"]) -> dict[str, list[str]]:
    """Everything a whole chain creates, so the sweep covers the prerequisites too."""
    out: dict[str, list[str]] = {}
    for p in plans:
        for kind, ids in p.owns.items():
            out.setdefault(kind, [])
            out[kind].extend(i for i in ids if i not in out[kind])
    return out


def _replacements(raw: list, where: str) -> list[Replacement]:
    out = []
    for item in raw:
        if "find" not in item or "repl" not in item:
            raise PlanError(f"{where}: each [[replace]] needs both `find` and `repl`.")
        out.append(Replacement(find=item["find"], repl=item["repl"], required=item.get("required", True)))
    return out


def load(path: Path) -> Plan:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise PlanError(f"{path.name}: not valid TOML — {exc}") from exc

    if "page" not in raw:
        raise PlanError(f"{path.name}: missing `page` (the doc file this plan tests).")

    langs: dict[str, LangPlan] = {}
    for lang in EXECUTABLE:
        section = raw.get(lang)
        if section is None:
            continue
        langs[lang] = LangPlan(
            lang=lang,
            disabled=section.get("disabled"),
            requires=list(section.get("requires", [])),
            requires_once=list(section.get("requires_once", [])),
            only=section.get("only", []),
            exclude=section.get("exclude", []),
            imports=section.get("imports", ""),
            prologue=section.get("prologue", ""),
            epilogue=section.get("epilogue", ""),
            replace=_replacements(section.get("replace", []), f"{path.name} [{lang}]"),
            independent=bool(section.get("independent", False)),
            inject=[
                Injection(before=int(i["before"]), code=i["code"])
                for i in section.get("inject", [])
            ],
            env={str(k): str(v) for k, v in section.get("env", {}).items()},
            requires_env=list(section.get("requires_env", [])),
            requires_python=list(section.get("requires_python", [])),
            timeout=int(section.get("timeout", 180)),
        )
        if langs[lang].only and langs[lang].exclude:
            raise PlanError(f"{path.name} [{lang}]: use `only` or `exclude`, not both.")

    expect = raw.get("expect", {})
    return Plan(
        slug=path.stem,
        page=raw["page"],
        path=path,
        disabled=raw.get("disabled"),
        blocks={str(k): int(v) for k, v in raw.get("blocks", {}).items()},
        langs=langs,
        owns={str(k): list(v) for k, v in raw.get("owns", {}).items()},
        expect_exists={
            str(k): list(v) for k, v in expect.items() if k not in ("datapoints", "stdout", "settle_secs")
        },
        expect_datapoints={str(k): int(v) for k, v in expect.get("datapoints", {}).items()},
        expect_stdout=list(expect.get("stdout", [])),
        settle_secs=float(expect.get("settle_secs", 30.0)),
    )


def load_all() -> dict[str, Plan]:
    return {p.stem: load(p) for p in sorted(PLAN_DIR.glob("*.toml")) if p.name != UNTRIAGED.name}


def untriaged() -> dict[str, str]:
    """Slug -> reason for pages that carry runnable code but have no scenario yet.

    This list is the suite's backlog, and it is meant to shrink. It exists so a
    page can be *knowingly* uncovered; a page that is neither planned nor listed
    here fails the coverage gate, which is what stops a new tutorial from landing
    untested.
    """
    if not UNTRIAGED.exists():
        return {}
    raw = tomllib.loads(UNTRIAGED.read_text(encoding="utf-8"))
    out = {}
    for slug, reason in raw.get("pages", {}).items():
        if not str(reason).strip():
            raise PlanError(f"UNTRIAGED.toml: {slug} needs a reason, not an empty string.")
        out[slug] = str(reason)
    return out
