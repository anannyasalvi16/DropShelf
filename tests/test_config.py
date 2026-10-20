"""
Unit tests for dropsort.config rules loading, saving, recovery, and thread safety.
"""

import json
import threading
from dropsort.config import (
    APP_NAME,
    DEFAULT_DB_PATH,
    ThreadSafeRulesManager,
    get_default_rules,
    load_rules,
    save_rules,
)


def test_app_name_and_db_name_derivation():
    assert APP_NAME == "DropShelf"
    assert DEFAULT_DB_PATH.name == f"{APP_NAME.lower()}.db"


def test_default_rules_structure():
    defaults = get_default_rules()
    assert "watch_folder" in defaults
    assert "custom_rules" in defaults
    assert "type_rules" in defaults
    assert "fallback_folder" in defaults
    assert "ignore_extensions" in defaults
    assert defaults["fallback_folder"] == "Other"
    assert defaults["stability_checks"] == 3
    assert defaults["stability_interval"] == 0.5


def test_stability_configuration_persistence(tmp_path):
    rules_file = tmp_path / "rules.json"
    rules = get_default_rules()
    rules["stability_checks"] = 5
    rules["stability_interval"] = 1.0
    save_rules(rules, rules_file)

    loaded = load_rules(rules_file)
    assert loaded["stability_checks"] == 5
    assert loaded["stability_interval"] == 1.0


def test_load_rules_creates_file_if_missing(tmp_path):
    rules_file = tmp_path / "rules.json"
    assert not rules_file.exists()
    loaded = load_rules(rules_file)
    assert rules_file.exists()
    assert loaded["fallback_folder"] == "Other"
    assert "Documents" in loaded["type_rules"]


def test_load_rules_restores_defaults_on_corrupt_json(tmp_path):
    rules_file = tmp_path / "rules.json"
    rules_file.write_text("{corrupt: json content", encoding="utf-8")
    loaded = load_rules(rules_file)
    assert loaded["fallback_folder"] == "Other"
    # Should have overwritten the corrupt file with valid JSON
    with open(rules_file, "r", encoding="utf-8") as f:
        re_read = json.load(f)
    assert re_read["fallback_folder"] == "Other"


def test_load_rules_restores_defaults_on_invalid_schema(tmp_path):
    rules_file = tmp_path / "rules.json"
    rules_file.write_text(json.dumps({"invalid_key": 123}), encoding="utf-8")
    loaded = load_rules(rules_file)
    assert "type_rules" in loaded


def test_save_and_reload_rules(tmp_path):
    rules_file = tmp_path / "rules.json"
    rules = get_default_rules()
    rules["custom_rules"].append({"contains": "Exam", "folder": "College/Exams"})
    save_rules(rules, rules_file)

    loaded = load_rules(rules_file)
    assert any(r["contains"] == "Exam" for r in loaded["custom_rules"])


def test_thread_safe_rules_manager(tmp_path):
    rules_file = tmp_path / "rules.json"
    manager = ThreadSafeRulesManager(rules_file)

    initial_rules = manager.get_rules()
    assert "watch_folder" in initial_rules

    # Concurrent read and update
    def writer():
        for i in range(20):
            current = manager.get_rules()
            current["custom_rules"].append({"contains": f"Tag{i}", "folder": f"Folder{i}"})
            manager.update_rules(current)

    def reader():
        for _ in range(50):
            rules = manager.get_rules()
            assert "type_rules" in rules

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final_rules = manager.get_rules()
    assert len(final_rules["custom_rules"]) >= 20
