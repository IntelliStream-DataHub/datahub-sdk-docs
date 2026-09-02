"""Pull fenced code blocks out of a Docusaurus page.

The whole suite rests on this: a doc test must execute *the code the reader sees*,
never a copy of it. So every runnable program is assembled from the page's own
fences at test time. If a page is edited, the next run assembles the new text.

What a block carries beyond its body is what makes plans readable and stable:

- ``lang_index`` — position among the blocks of the *same* language on the page.
  Plans address blocks by this, not by absolute position, so adding a ``bash``
  fence to a page does not renumber every Python block in its plan.
- ``heading`` — the nearest preceding ``#`` heading, so a failure can say
  "Step 2 — Ensure the time series exist" instead of "block 4".
- ``tab`` — the enclosing ``<TabItem value="...">``, which is how the language
  tabs are built. A ``bash`` fence inside the Python tab belongs to the Python
  reader's flow even though its language is not ``python``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# A fence opener: indent, >=3 backticks, optional language, optional metastring
# (Docusaurus uses the metastring for `title="x.py"`).
_FENCE = re.compile(r"^(\s*)(`{3,})[ \t]*([A-Za-z0-9_+#-]*)[ \t]*(.*)$")
_HEADING = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*#*$")
_TAB_OPEN = re.compile(r"<TabItem\b[^>]*?\bvalue=[\"']([^\"']+)[\"']")
_TAB_CLOSE = re.compile(r"</TabItem>")

# Languages this suite knows how to execute. Everything else (bash, toml, text,
# json, kotlin, http) is documentation *about* running, not a program.
EXECUTABLE = ("python", "java", "rust")


@dataclass(frozen=True)
class Block:
    """One fenced code block, with enough context to name it in a failure."""

    index: int  # 1-based, among all blocks on the page
    lang_index: int  # 1-based, among blocks of this language — what plans use
    lang: str
    meta: str  # the metastring, e.g. 'title="memory_ingest.py"'
    body: str
    start_line: int  # 1-based line of the opening fence, for jump-to-source
    heading: str
    tab: str | None

    @property
    def title(self) -> str | None:
        m = re.search(r'title=["\']([^"\']+)["\']', self.meta)
        return m.group(1) if m else None

    def where(self, page: str) -> str:
        """A clickable, human location: ``docs/quickstart.mdx:57 (python #2)``."""
        return f"{page}:{self.start_line} ({self.lang} #{self.lang_index})"


@dataclass
class Page:
    path: Path
    rel: str  # repo-relative, e.g. docs/guides/ingest-timeseries.mdx
    slug: str  # plan filename stem, e.g. guides__ingest-timeseries
    blocks: list[Block]

    def of_lang(self, lang: str) -> list[Block]:
        return [b for b in self.blocks if b.lang == lang]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for b in self.blocks:
            out[b.lang] = out.get(b.lang, 0) + 1
        return out


def slug_for(rel: str) -> str:
    """docs/guides/x.mdx -> guides__x — a flat, filesystem-safe plan name."""
    stem = re.sub(r"\.mdx?$", "", rel)
    stem = re.sub(r"^docs/", "", stem)
    return stem.replace("/", "__")


def parse(text: str) -> list[Block]:
    lines = text.split("\n")
    blocks: list[Block] = []
    heading = ""
    tabs: list[str] = []
    open_fence: tuple[str, str, str, int] | None = None  # ticks, lang, meta, start
    body: list[str] = []
    per_lang: dict[str, int] = {}

    for n, line in enumerate(lines, start=1):
        fence = _FENCE.match(line)

        if open_fence is not None:
            ticks, lang, meta, start = open_fence
            # A closing fence is >= as many backticks as the opener and nothing else.
            if fence and fence.group(2).startswith(ticks) and not fence.group(3) and not fence.group(4):
                per_lang[lang] = per_lang.get(lang, 0) + 1
                blocks.append(
                    Block(
                        index=len(blocks) + 1,
                        lang_index=per_lang[lang],
                        lang=lang,
                        meta=meta,
                        body="\n".join(body),
                        start_line=start,
                        heading=heading,
                        tab=tabs[-1] if tabs else None,
                    )
                )
                open_fence, body = None, []
            else:
                body.append(line)
            continue

        if fence and fence.group(2):
            open_fence = (fence.group(2), (fence.group(3) or "text").lower(), fence.group(4).strip(), n)
            body = []
            continue

        h = _HEADING.match(line)
        if h:
            heading = h.group(2)
        for m in _TAB_OPEN.finditer(line):
            tabs.append(m.group(1))
        for _ in _TAB_CLOSE.finditer(line):
            if tabs:
                tabs.pop()

    return blocks


def load(path: Path, root: Path) -> Page:
    rel = str(path.relative_to(root))
    return Page(path=path, rel=rel, slug=slug_for(rel), blocks=parse(path.read_text(encoding="utf-8")))


def all_pages(root: Path) -> list[Page]:
    """Every doc page, sorted, so test ids and reports are stable run to run."""
    docs = root / "docs"
    files = sorted(p for p in docs.rglob("*") if p.suffix in (".md", ".mdx"))
    return [load(p, root) for p in files]
