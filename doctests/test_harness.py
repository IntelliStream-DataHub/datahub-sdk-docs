"""Tests for the test harness itself — no backend required.

A documentation suite is only worth its guards. If block-count pinning stops
firing, or a stale bounded-run substitution starts passing silently, the suite
keeps reporting green over code nobody ran, and that is worse than having no
suite at all. These tests exercise the guards directly on synthetic input, so a
regression in the harness surfaces here rather than as a quiet false pass six
months later.

They are also the part of the suite that runs anywhere: no stack, no credentials.
"""

from __future__ import annotations

import textwrap

import pytest

import docblocks
import entities
import plans as plans_mod
import runners

# ------------------------------------------------------------------ extraction


def test_blocks_carry_heading_tab_and_line():
    page = textwrap.dedent("""\
        # Title

        ## Step one

        <Tabs>
        <TabItem value="python" label="Python">

        ```python title="a.py"
        x = 1
        ```

        </TabItem>
        <TabItem value="rust" label="Rust">

        ```rust
        let x = 1;
        ```

        </TabItem>
        </Tabs>
        """)
    blocks = docblocks.parse(page)
    assert [b.lang for b in blocks] == ["python", "rust"]
    assert blocks[0].heading == "Step one"
    assert blocks[0].tab == "python"
    assert blocks[0].title == "a.py"
    assert blocks[0].start_line == 8
    assert blocks[1].tab == "rust"


def test_lang_index_counts_per_language():
    """Plans address blocks per language, so adding a bash fence must not renumber."""
    page = "```python\na\n```\n\n```bash\nls\n```\n\n```python\nb\n```\n"
    blocks = docblocks.parse(page)
    assert [(b.lang, b.lang_index) for b in blocks] == [
        ("python", 1), ("bash", 1), ("python", 2)]


def test_a_fence_inside_a_longer_fence_is_not_a_block():
    page = "````markdown\n```python\nnot code under test\n```\n````\n"
    blocks = docblocks.parse(page)
    assert [b.lang for b in blocks] == ["markdown"]


# ------------------------------------------------------------------ entities


def test_entities_from_literals_comprehensions_and_loops():
    src = textwrap.dedent("""\
        TimeSeries(external_id="plain")
        [Resource(external_id=x, labels=["Ignore"]) for x in ["comp_a", "comp_b"]]
        for s, u in [("loop_a", "m3h"), ("loop_b", "bar")]:
            client.timeseries.create([TimeSeries(external_id=s, unit=u)])
        """)
    owned = entities.owned(src)
    assert owned["timeseries"] == ["loop_a", "loop_b", "plain"]
    assert owned["resources"] == ["comp_a", "comp_b"]
    # The label rode along in the comprehension's iterable and must not be taken
    # for an external id.
    assert "Ignore" not in owned["resources"]


def test_runtime_ids_become_patterns():
    src = 'Event(external_id=f"kick_{int(now.timestamp())}", type="kick")'
    assert entities.owned(src)["events"] == ["kick_*"]


def test_ids_flow_through_a_local_helper():
    """The seeding pages factor creation into a helper and call it with literals."""
    src = textwrap.dedent("""\
        def ingest(external_id, values):
            client.timeseries.create([TimeSeries(external_id=external_id, unit="v")])

        ingest("helper_a", [1])
        ingest("helper_b", [2])
        """)
    assert entities.owned(src)["timeseries"] == ["helper_a", "helper_b"]


def test_retrieve_is_a_read_not_an_ownership_claim():
    """`ts=` on a filter is a read; treating it as ownership deletes shared fixtures."""
    read = 'RetrieveFilter(ts="someone_elses_series", start=a, end=b)'
    write = 'client.timeseries.insert_from_lists(timestamps=t, values=v, ts="mine")'
    assert entities.owned(read) == {}
    assert entities.owned(write)["timeseries"] == ["mine"]


def test_edge_targets_count_for_cleanup_but_not_for_assertions():
    src = 'RelForm.by_external_ids("start_node", "end_node", "contains")'
    assert entities.owned(src)["resources"] == ["end_node", "start_node"]
    assert entities.owned(src, include_edge_refs=False) == {}


# ------------------------------------------------------------------ guards


def _lang_plan(**kw) -> plans_mod.LangPlan:
    return plans_mod.LangPlan(lang="python", **kw)


def _block(body: str, index: int = 1) -> docblocks.Block:
    return docblocks.Block(index=index, lang_index=index, lang="python", meta="",
                           body=body, start_line=1, heading="Step", tab="python")


def test_a_stale_replacement_fails_loudly():
    """The guard that stops a bounded-run substitution from silently lapsing."""
    lp = _lang_plan(replace=[plans_mod.Replacement(find="while True:", repl="for _ in range(2):")])
    with pytest.raises(plans_mod.PlanError, match="no longer match"):
        lp.validate_replacements([_block("print('no loop here')")], "docs/x.mdx")


def test_a_replacement_marked_optional_may_miss():
    lp = _lang_plan(replace=[plans_mod.Replacement(find="absent", repl="x", required=False)])
    lp.validate_replacements([_block("kept = 1")], "docs/x.mdx")   # must not raise
    source, _ = runners.compose("python", [(lp, [_block("kept = 1")], "docs/x.mdx")])
    assert "kept = 1" in source


def test_inject_pointing_at_an_unrun_block_fails():
    """Block numbering shifts when a page is edited; a dangling inject must not pass."""
    lp = _lang_plan(inject=[plans_mod.Injection(before=9, code="x = 1")])
    with pytest.raises(plans_mod.PlanError, match="inject targets block"):
        lp.validate_injects([_block("y = 2")], "docs/x.mdx")


def test_selecting_a_block_the_page_does_not_have_fails():
    lp = _lang_plan(only=[3])
    with pytest.raises(plans_mod.PlanError, match="plan selects block"):
        lp.select([_block("a")])


def test_only_and_exclude_together_is_rejected(tmp_path):
    plan = tmp_path / "p.toml"
    plan.write_text('page = "docs/x.mdx"\n[python]\nonly = [1]\nexclude = [2]\n')
    with pytest.raises(plans_mod.PlanError, match="use `only` or `exclude`"):
        plans_mod.load(plan)


def test_a_plan_without_a_page_is_rejected(tmp_path):
    plan = tmp_path / "p.toml"
    plan.write_text("[python]\n")
    with pytest.raises(plans_mod.PlanError, match="missing `page`"):
        plans_mod.load(plan)


def test_requires_cycles_are_caught():
    def stub(slug, dep):
        return plans_mod.Plan(slug=slug, page=f"docs/{slug}.mdx", path=None, disabled=None,
                              blocks={}, langs={"python": _lang_plan(requires=[dep])},
                              owns={}, expect_exists={}, expect_datapoints={},
                              expect_stdout=[], settle_secs=1.0)
    all_plans = {"a": stub("a", "b"), "b": stub("b", "a")}
    with pytest.raises(plans_mod.PlanError, match="cycle"):
        plans_mod.chain("a", "python", all_plans)


# ------------------------------------------------------------------ composition


def test_blocks_are_concatenated_in_reading_order_and_blamed_correctly():
    lp = _lang_plan(prologue="fixture = 1")
    first = docblocks.Block(index=1, lang_index=1, lang="python", meta="", body="step_one()",
                            start_line=10, heading="Step 1", tab="python")
    second = docblocks.Block(index=2, lang_index=2, lang="python", meta="", body="step_two()",
                             start_line=40, heading="Step 2", tab="python")
    source, line_map = runners.compose("python", [(lp, [first, second], "docs/t.mdx")])

    assert source.index("step_one()") < source.index("step_two()")
    result = runners.RunResult(0, "", "", source, 0.0, line_map=line_map)
    at_step_two = source[: source.index("step_two()")].count("\n") + 1
    assert "docs/t.mdx:40" in result.blame(at_step_two)
    assert "prologue" in result.blame(1)


def test_prerequisites_are_prepended():
    lp = _lang_plan()
    prereq = _block("from_quickstart()")
    target = _block("uses_the_client()")
    source, _ = runners.compose("python", [(lp, [prereq], "docs/quickstart.mdx"),
                                           (lp, [target], "docs/guide.mdx")])
    assert source.index("from_quickstart()") < source.index("uses_the_client()")
    assert "docs/quickstart.mdx" in source and "docs/guide.mdx" in source


def test_sdk_response_noise_is_folded_out_of_reports():
    noisy = 'Response body for path: http://x/y\n{"items":[1]}\nreal failure here'
    assert "real failure here" in runners.tidy(noisy)
    assert "Response body for path" not in runners.tidy(noisy)
