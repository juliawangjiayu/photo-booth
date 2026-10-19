from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STUDIO_PARENT = ROOT / "apps" / "studio"
if str(STUDIO_PARENT) not in sys.path:
    sys.path.insert(0, str(STUDIO_PARENT))


@pytest.fixture
def repository(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTO_BOOTH_DATA_DIR", str(tmp_path / "data"))
    for name in list(sys.modules):
        if name.startswith("backend"):
            del sys.modules[name]
    from backend import ai_config
    from backend.db import connect

    conn = connect()
    try:
        yield ai_config, conn
    finally:
        conn.close()


def test_initial_draft_uses_deepseek_flash_and_the_approved_prompt(repository):
    config, conn = repository
    draft = config.load_or_create_draft(conn)
    assert draft.provider == "deepseek"
    assert draft.base_url == "https://api.deepseek.com"
    assert draft.model == "deepseek-flash"
    assert draft.prompt_text == config.APPROVED_INITIAL_PROMPT
    assert draft.prompt_text.startswith("You help a map search")
    assert "Never invent specificity." in draft.prompt_text
    assert len(draft.config_hash) == 64
    assert draft.test_state == "untested"


def test_saving_draft_changes_hash_and_invalidates_prior_test(repository):
    config, conn = repository
    original = config.load_or_create_draft(conn)
    tested = config.record_test(conn, original.config_hash, "searchable example passed")
    assert tested.test_state == "passed"
    changed = config.save_draft(conn, {"model": "deepseek-v4-pro"})
    assert changed.config_hash != original.config_hash
    assert changed.test_state == "untested"
    assert changed.tested_hash == ""
    assert changed.test_summary == ""


def test_only_exact_tested_hash_can_activate(repository):
    config, conn = repository
    draft = config.load_or_create_draft(conn)
    with pytest.raises(config.AiConfigNotTested):
        config.activate_draft(conn)
    with pytest.raises(config.AiConfigConflict):
        config.record_test(conn, "0" * 64, "stale test")
    config.record_test(conn, draft.config_hash, "passed")
    version = config.activate_draft(conn)
    assert version.version == 1
    assert version.config_hash == draft.config_hash
    assert config.load_or_create_draft(conn).active_version == 1


def test_restore_creates_a_new_draft_without_mutating_history(repository):
    config, conn = repository
    first = config.load_or_create_draft(conn)
    config.record_test(conn, first.config_hash, "passed")
    activated = config.activate_draft(conn)
    config.save_draft(conn, {"prompt_text": first.prompt_text + "\nPrefer the user's language."})
    before = config.list_versions(conn)
    restored = config.restore_version(conn, activated.version)
    after = config.list_versions(conn)
    assert after == before
    assert restored.prompt_text == activated.prompt_text
    assert restored.config_hash == activated.config_hash
    assert restored.test_state == "untested"
    assert restored.tested_hash == ""
    assert restored.active_version == activated.version


def test_ai_config_tables_never_store_secret_values(repository):
    config, conn = repository
    config.load_or_create_draft(conn)
    secret = "test-secret-never-store"
    with pytest.raises(ValueError):
        config.save_draft(conn, {"api_key": secret})
    table_names = ("ai_place_draft", "ai_place_versions")
    columns = {
        table: [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]
        for table in table_names
    }
    assert all(
        forbidden not in column.lower()
        for names in columns.values()
        for column in names
        for forbidden in ("api_key", "token", "secret")
    )
    serialized = json.dumps({
        table: [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]
        for table in table_names
    })
    assert secret not in serialized
