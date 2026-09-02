"""Turn a plan into something runnable.

Both callers need the same walk — resolve the chain of pages, read each one's
blocks, validate the plan still lines up with them, and compose the result into
one program or several. `test_tutorials` needs it to run a tutorial;
`conftest.seed` needs it to run a data-seeding page before the recipes that
depend on one. Having each do its own version meant two places to keep in step,
and they had already drifted: only one of them validated the plan against the
page it was about to run.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import docblocks
import entities
import plans as plans_mod
import runners


class MissingBlocks(Exception):
    """A plan declares a scenario for a language the page has no blocks in."""


@dataclass
class Scenario:
    """One plan, resolved against the pages it needs, ready to run."""

    plan: plans_mod.Plan
    lang: str
    links: list[plans_mod.Plan]  # prerequisites first, target last
    sections: list[tuple[plans_mod.LangPlan, list, str]]

    @property
    def lang_plan(self) -> plans_mod.LangPlan:
        return self.plan.lang(self.lang)

    def programs(self) -> list[tuple[str, list[tuple[int, str]]]]:
        """The program(s) to run: one for a tutorial, one per block for a reference.

        An API-reference page's blocks are independent examples; a tutorial's are a
        sequence. That single distinction is the only difference between the two.
        """
        lp = self.lang_plan
        if not lp.independent:
            return [runners.compose(self.lang, self.sections)]
        head, (_, target_blocks, page) = self.sections[:-1], self.sections[-1]
        return [
            runners.compose(self.lang, head + [(lp, [block], page)])
            for block in lp.select(target_blocks)
        ]

    def owns(self) -> dict[str, list[str]]:
        """Everything the whole chain creates, for the sweep."""
        return plans_mod.merged_owns(self.links)

    def creates(self) -> set[str]:
        """Ids this scenario's own code builds, as opposed to reads."""
        out: set[str] = set()
        for lp, blocks, _ in self.sections:
            source = "\n".join(b.body for b in lp.select(blocks))
            for ids in entities.owned(source, include_edge_refs=False).values():
                out.update(ids)
        return out


def build(slug: str, lang: str, all_plans: dict[str, plans_mod.Plan], repo: Path) -> Scenario:
    """Resolve a plan into a Scenario, checking it still matches its pages.

    The validation happens here rather than at composition time because both are
    properties of the plan as a whole: with `independent`, composition sees one
    block at a time and cannot tell a stale selection from a narrow one.
    """
    links = plans_mod.chain(slug, lang, all_plans)
    sections = []
    for link in links:
        page = docblocks.load(repo / link.page, repo)
        blocks = page.of_lang(lang)
        if not blocks:
            raise MissingBlocks(
                f"{link.page} has no {lang} blocks, but its plan declares a {lang} scenario."
            )
        link_lp = link.lang(lang)
        link_lp.validate_injects(blocks, link.page)
        link_lp.validate_replacements(blocks, link.page)
        sections.append((link_lp, blocks, link.page))
    return Scenario(plan=all_plans[slug], lang=lang, links=links, sections=sections)
