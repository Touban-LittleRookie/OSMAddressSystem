"""Naming rules of the todo list (section 3.1).

R1: ranks 0, 1 and 2 always need a name of their own; a derived street is never more important or longer than its main street.
R2: only first-order derived names (``3-xyz``), never ``3-3-xyz``.
"""

import re

import pytest
from fastapi.testclient import TestClient

from osmaddresssystem import branches, naming_plan
from osmaddresssystem.app.project import Project, Settings
from osmaddresssystem.app.server import create_app

import app_helpers as H
from test_branch_names import _network
from test_app_backend import client, compute, root, set_reference  # noqa: F401  (pytest fixtures)


def _secondary_branch():
    """The synthetic network with street 3 (a branch of ``xyz`` at 100 m) promoted to rank 2.

    Returns:
        ``(edges, streets)``.
    """
    e, s = _network()
    s.loc[s["street_id"] == 3, "street_rank"] = 2
    return e, s


def _branch_names(e, s, **kw):
    _, out = branches.assign_branch_names(None, e, s, **kw)
    return {k: (v if isinstance(v, str) else None) for k, v in out.set_index("street_id")["branch_name"].items()}


# ---- R1: important roads need their own name -------------------------------------------------------------

def test_library_default_still_derives_a_secondary_branch():
    """Without the rule the library keeps its old behaviour: a rank-2 road off a rank-1 road is ``6-xyz``."""
    e, s = _secondary_branch()
    assert _branch_names(e, s)[3] == "6-xyz"


def test_ranks_0_to_2_never_take_a_derived_name():
    e, s = _secondary_branch()
    names = _branch_names(e, s, own_name_max_rank=2)
    assert names[3] is None
    assert names[2] == "3-xyz"                                  # a residential branch is still derived


def test_ranks_0_to_2_have_no_possible_parent():
    e, s = _secondary_branch()
    parents = branches.branch_parents(None, e, s, own_name_max_rank=2)
    assert parents[3] == set() and parents[2] == {1}


def test_planner_asks_for_a_name_for_an_unnamed_secondary_road():
    e, s = _secondary_branch()
    before = naming_plan.plan_minimal_naming(None, e, s, max_levels=1)
    after = naming_plan.plan_minimal_naming(None, e, s, max_levels=1, own_name_max_rank=2)
    assert 3 not in set(before.chosen["street_id"])            # today it is covered by xyz
    assert 3 in set(after.chosen["street_id"]) and not after.uncovered


def test_derived_street_is_never_more_important_or_longer_than_its_main_street():
    """The two parts of R1 that already held: checked on every derived name of the synthetic network."""
    e, s = _network()
    _, out = branches.assign_branch_names(None, e, s, max_levels=1, own_name_max_rank=2)
    rank = out.set_index("street_id")["street_rank"]
    own_len, group_len = branches.street_lengths(e, s)
    derived = out.dropna(subset=["branch_parent_id"])
    assert len(derived)
    for sid, parent in zip(derived["street_id"], derived["branch_parent_id"].astype(int)):
        assert rank[parent] <= rank[sid] and group_len[parent] > own_len[sid]


# ---- R2: first-order derived names only -------------------------------------------------------------------

def test_app_settings_allow_one_derivation_level_only():
    assert Settings().max_levels == 1 and Settings().own_name_max_rank == 2
    assert Settings(max_levels=2).max_levels == 1
    assert Settings(max_levels=0).max_levels == 0               # "no derived names at all" stays possible


def test_a_saved_two_level_setting_is_read_as_one_level():
    """Projects saved before the rule change (Fotouni stored max_levels=2) follow the new rule without losing other settings."""
    p = Project.from_dict(".", {"settings": {"max_levels": 2, "house_step_m": 3.0}})
    assert p.settings.max_levels == 1 and p.settings.house_step_m == 3.0


def test_first_order_planner_names_the_branch_of_a_branch():
    """Street 4 branches from street 2 (``3-xyz``): with one level it can only be covered by naming 2 or 4."""
    plan = naming_plan.plan_minimal_naming(None, *_network(), max_levels=1, own_name_max_rank=2)
    covered = plan.coverage.set_index("street_id")
    assert covered["depth"].dropna().max() <= 1


DERIVED_TWICE = re.compile(r"^\d+[A-Z]?-\d+[A-Z]?-")


def test_computed_app_network_follows_r1_and_r2(client):  # noqa: F811
    """End to end on a synthetic project: no ``x-y-name`` names, no derived names on ranks 0-2, nothing uncovered."""
    set_reference(client)
    net = compute(client)
    props = [f["properties"] for f in net["streets"]["features"]]
    assert net["stats"]["uncovered"] == 0
    assert all(not DERIVED_TWICE.match(p["display"] or "") for p in props)
    assert all((p["level"] or 0) <= 1 for p in props)
    assert all(p["status"] != "derived" for p in props if p["rank"] <= 2)


# ---- R3: minimum final naming set ------------------------------------------------------------------------

def test_final_cut_network_uses_the_known_minimum_naming_set(tmp_path):
    """A 3x3 grid needs two original-street naming decisions, not five cut-part decisions."""
    project_root = H.make_project(tmp_path / "r3", rows=3, cols=3)
    with TestClient(create_app(project_root, auth_enabled=False, auto_compute=False)) as app:
        set_reference(app)
        net = compute(app)
    stats = net["stats"]
    assert stats["cut_points"] > 0 and stats["uncovered"] == 0
    assert stats["initial_plan_count"] == 5
    assert stats["pre_optimization_count"] == 2
    assert stats["to_be_named"] == len(net["plan"]) == 2
    assert stats["initial_plan_count"] - stats["to_be_named"] == 3
    assert stats["plan_reduced_by"] == 3
    assert stats["plan_method"] == "exact"
    assert stats["plan_scope"] == "final_cut_graph"
