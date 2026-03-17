from __future__ import annotations

import json
from pathlib import Path

from src.insight_engine.config import load_doppler_env, load_runtime_config


class CompletedProcessStub:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_load_doppler_env_from_cli(monkeypatch, tmp_path):
    payload = {
        "ANTHROPIC_API_KEY": "secret",
        "OBSIDIAN_VAULT_PATH": str(tmp_path / "vault"),
    }

    def fake_run(*args, **kwargs):
        return CompletedProcessStub(0, stdout=json.dumps(payload))

    monkeypatch.setattr("src.insight_engine.config.subprocess.run", fake_run)

    source, loaded = load_doppler_env(tmp_path)

    assert source == "doppler"
    assert loaded["ANTHROPIC_API_KEY"] == "secret"


def test_load_doppler_env_from_file(monkeypatch, tmp_path):
    env_file = tmp_path / ".env.doppler"
    env_file.write_text("ANTHROPIC_API_KEY=file-secret\nOBSIDIAN_VAULT_PATH=/vault\n", encoding="utf-8")

    def fake_run(*args, **kwargs):
        return CompletedProcessStub(1, stderr="failed")

    monkeypatch.setattr("src.insight_engine.config.subprocess.run", fake_run)

    source, loaded = load_doppler_env(tmp_path)

    assert source == ".env.doppler"
    assert loaded["OBSIDIAN_VAULT_PATH"] == "/vault"


def test_runtime_config_redacts_secrets(monkeypatch, tmp_path):
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    payload = {
        "ANTHROPIC_API_KEY": "secret",
        "OBSIDIAN_VAULT_PATH": str(vault_path),
        "WORDPRESS_URL": "https://example.com/wp-json/wp/v2/posts",
        "WORDPRESS_USER": "user",
        "WORDPRESS_APP_PASSWORD": "password",
        "TELEGRAM_BOT_TOKEN": "token",
        "BOSS_CHAT_ID": "1",
    }

    def fake_run(*args, **kwargs):
        return CompletedProcessStub(0, stdout=json.dumps(payload))

    monkeypatch.setattr("src.insight_engine.config.subprocess.run", fake_run)

    config = load_runtime_config(tmp_path)
    summary = config.redacted_summary()

    assert summary["anthropic_api_key"] is True
    assert summary["word_press_app_password"] is True
    assert summary["telegram_bot_token"] is True
    assert summary["vault_path"] == str(vault_path)
