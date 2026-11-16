"""Accepted Option 2 addressing rule: metre house numbers and ten-metre branch prefixes."""

from osmaddresssystem import numbering
from osmaddresssystem.app.project import ADDRESSING_RULE_VERSION, Project, Settings
from osmaddresssystem.app.store import Store


def test_option_two_is_the_default_and_matches_the_approved_examples():
    settings = Settings()
    assert settings.house_step_m == 1.0
    assert settings.branch_step_m == 10.0
    assert settings.addressing_rule_version == ADDRESSING_RULE_VERSION == 2
    assert numbering._house_number_from_distance(26, settings.house_step_m, "right") == 26
    assert numbering._house_number_from_distance(50, settings.branch_step_m, "left") == 5


def test_legacy_default_steps_are_migrated_without_changing_custom_values(tmp_path):
    old = Project.from_dict(tmp_path, {"settings": {"house_step_m": 2, "branch_step_m": 20}})
    assert old.settings.house_step_m == 1.0
    assert old.settings.branch_step_m == 10.0
    assert old.settings.addressing_rule_version == 2

    custom = Project.from_dict(tmp_path, {"settings": {"house_step_m": 3, "branch_step_m": 15}})
    assert custom.settings.house_step_m == 3.0
    assert custom.settings.branch_step_m == 15.0


def test_versioned_custom_steps_are_not_mistaken_for_legacy_defaults(tmp_path):
    project = Project.from_dict(tmp_path, {"settings": {
        "house_step_m": 2, "branch_step_m": 20, "addressing_rule_version": ADDRESSING_RULE_VERSION,
    }})
    assert project.settings.house_step_m == 2.0
    assert project.settings.branch_step_m == 20.0


def test_first_settings_edit_persists_the_addressing_rule_version(tmp_path):
    store = Store(tmp_path / "project", "test")
    store.set_settings({"house_step_m": 1.5}, "tester")
    project = store.project()
    assert project.settings.house_step_m == 1.5
    assert project.settings.branch_step_m == 10.0
    assert project.settings.addressing_rule_version == ADDRESSING_RULE_VERSION

