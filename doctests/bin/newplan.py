#!/usr/bin/env python3
"""Scaffold a test plan for a doc page.

Writes a plan pre-filled with what can be read off the page — its block counts and
a commented inventory of every block with its heading and line number — so the
person (or agent) writing the plan starts from the page's actual shape instead of
from a blank file. It never guesses at prologues or owned ids: those require
reading the tutorial, which is the part that has to be done by someone who
understands what it teaches.

    ./doctests/bin/newplan.py docs/guides/ingest-timeseries.mdx
    ./doctests/bin/newplan.py --untriaged "needs an MQTT broker" docs/guides/x.mdx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import docblocks  # noqa: E402
import plans as plans_mod  # noqa: E402

REPO = HERE.parent.parent


def inventory(page: docblocks.Page) -> str:
    rows = []
    for b in page.blocks:
        if b.lang not in docblocks.EXECUTABLE:
            continue
        title = f'  title={b.title}' if b.title else ""
        rows.append(f"#   {b.lang:6} #{b.lang_index:<3} L{b.start_line:<5} {b.heading}{title}")
    return "\n".join(rows) or "#   (no runnable blocks)"


def scaffold(page: docblocks.Page) -> str:
    counts = page.counts()
    present = [l for l in docblocks.EXECUTABLE if counts.get(l)]
    lines = [
        f'page = "{page.rel}"',
        "",
        "# The blocks on this page, for reference while writing the plan below:",
        inventory(page),
        "",
        "# Pinned so an edit to the page fails this plan instead of silently",
        "# re-pointing its block selections. Update deliberately, after re-reading.",
        "[blocks]",
    ]
    lines += [f"{lang} = {counts[lang]}" for lang in present]

    for lang in present:
        comment = "#" if lang == "python" else "//"
        lines += [
            "",
            f"[{lang}]",
            'disabled = "not written yet - remove this line once the scenario below runs"',
            "",
            "# By default every block of this language runs, concatenated in reading",
            "# order, which is what makes this an end-to-end test of the tutorial.",
            f"# only = [1]        {comment} run just these blocks (by the numbers above)",
            f"# exclude = [3]     {comment} run all but these",
            "# timeout = 180",
            "",
            "# What a reader already has that the page does not restate.",
            "# prologue = \"\"\"",
            "# \"\"\"",
            "",
            "# Bound anything that would otherwise never finish. Every replacement must",
            "# still match the page, so a doc edit surfaces here rather than hanging CI.",
            f"# [[{lang}.replace]]",
            '# find = "while True:"',
            '# repl = "for _doctest_tick in range(2):"',
        ]

    lines += [
        "",
        "# External ids this page creates. Deleted before the run (so reruns are clean)",
        "# and after it (so the backend does not accumulate doc fixtures).",
        "# Types: timeseries, events, resources, datasets, subscriptions, files.",
        "[owns]",
        "# timeseries = []",
        "",
        "# What must be true afterwards. Exit code 0 only proves nothing threw;",
        "# these prove the tutorial did the thing it claims to teach.",
        "[expect]",
        "# timeseries = []",
        "# stdout = []",
        "# [expect.datapoints]",
        '# "some_external_id" = 1',
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pages", nargs="+", help="doc page path(s), e.g. docs/quickstart.mdx")
    ap.add_argument("--untriaged", metavar="REASON",
                    help="instead of a plan, add the page(s) to UNTRIAGED.toml with this reason")
    ap.add_argument("--force", action="store_true", help="overwrite an existing plan")
    args = ap.parse_args()

    for raw in args.pages:
        path = (REPO / raw).resolve() if not Path(raw).is_absolute() else Path(raw)
        if not path.exists():
            print(f"error: {raw} does not exist", file=sys.stderr)
            return 1
        page = docblocks.load(path, REPO)

        if args.untriaged:
            _append_untriaged(page.slug, args.untriaged)
            print(f"UNTRIAGED.toml  += {page.slug}  ({args.untriaged})")
            continue

        target = plans_mod.PLAN_DIR / f"{page.slug}.toml"
        if target.exists() and not args.force:
            print(f"error: {target.relative_to(REPO)} exists (use --force)", file=sys.stderr)
            return 1
        target.write_text(scaffold(page), encoding="utf-8")
        print(f"wrote {target.relative_to(REPO)}  ({page.counts()})")
    return 0


def _append_untriaged(slug: str, reason: str) -> None:
    path = plans_mod.UNTRIAGED
    text = path.read_text(encoding="utf-8") if path.exists() else "[pages]\n"
    if f'"{slug}"' in text or f"\n{slug} =" in text:
        return
    if not text.rstrip().endswith("[pages]") and "[pages]" not in text:
        text += "\n[pages]\n"
    path.write_text(text.rstrip("\n") + f'\n"{slug}" = "{reason}"\n', encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
