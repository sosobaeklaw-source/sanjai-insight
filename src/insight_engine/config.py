from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


SECRET_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "dart": "DART_API",
    "data_go_kr": "DATA_GO_KR_API_KEY",
    "kosis": "KOSIS_API",
    "ecos": "ECOS_API",
    "law_api_key": "LAW_API_KEY",
    "law_api_oc": "LAW_API_OC",
    "vault": "OBSIDIAN_VAULT_PATH",
    "pinecone": "PINECONE_API_KEY",
    "brave": "BRAVE_API_KEY",
    "naver_client_id": "NAVER_CLIENT_ID",
    "naver_client_secret": "NAVER_CLIENT_SECRET",
    "google_api_key": "GOOGLE_API_KEY",
    "google_cse_api_key": "GOOGLE_CSE_API_KEY",
    "google_cse_id": "GOOGLE_CSE_ID",
    "wordpress_url": "WORDPRESS_URL",
    "wordpress_site_url": "WORDPRESS_SITE_URL",
    "wordpress_user": "WORDPRESS_USER",
    "wordpress_app_password": "WORDPRESS_APP_PASSWORD",
    "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
    "telegram_chat_id": "TELEGRAM_CHAT_ID",
    "boss_chat_id": "BOSS_CHAT_ID",
    "opus_model": "OPUS_MODEL",
    "sonnet_model": "SONNET_MODEL",
    "haiku_model": "HAIKU_MODEL",
}


def _strip_quotes(value: str) -> str:
    """Remove surrounding quotes from environment variable values."""
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def _parse_env_lines(lines: Iterable[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = _strip_quotes(value.strip())
    return values


def _load_env_file(path: Path) -> dict[str, str]:
    return _parse_env_lines(path.read_text(encoding="utf-8").splitlines())


def load_doppler_env(
    repo_root: Path,
    project: str = "sanjai-ai",
    config: str = "prd",
) -> tuple[str, dict[str, str]]:
    command = [
        "doppler",
        "secrets",
        "download",
        "--no-file",
        "--format",
        "json",
        "-p",
        project,
        "-c",
        config,
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError:
        result = None

    if result and result.returncode == 0:
        payload = json.loads(result.stdout)
        for key, value in payload.items():
            os.environ[key] = value
        return ("doppler", payload)

    env_file = repo_root / ".env.doppler"
    if env_file.exists():
        payload = _load_env_file(env_file)
        for key, value in payload.items():
            os.environ[key] = value
        return (".env.doppler", payload)

    if result is not None:
        raise RuntimeError(
            f"Doppler env load failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    raise RuntimeError("Doppler CLI not found and .env.doppler is missing")


@dataclass(slots=True)
class RuntimeConfig:
    repo_root: Path
    data_root: Path
    published_root: Path
    reports_root: Path
    env_source: str
    doppler_project: str
    doppler_config: str
    vault_path: Path | None
    secret_presence: dict[str, bool]
    anthropic_api_key: str = field(default="", repr=False)
    word_press_url: str = field(default="", repr=False)
    word_press_site_url: str = field(default="", repr=False)
    word_press_user: str = field(default="", repr=False)
    word_press_app_password: str = field(default="", repr=False)
    telegram_bot_token: str = field(default="", repr=False)
    telegram_chat_id: str = field(default="", repr=False)
    boss_chat_id: str = field(default="", repr=False)
    opus_model: str = "claude-opus"
    sonnet_model: str = "claude-sonnet"
    haiku_model: str = "claude-haiku"

    @property
    def notify_chat_id(self) -> str:
        return self.boss_chat_id or self.telegram_chat_id

    def redacted_summary(self) -> dict[str, object]:
        data = asdict(self)
        for key in (
            "anthropic_api_key",
            "word_press_url",
            "word_press_site_url",
            "word_press_user",
            "word_press_app_password",
            "telegram_bot_token",
            "telegram_chat_id",
            "boss_chat_id",
        ):
            data[key] = bool(data[key])
        data["repo_root"] = str(self.repo_root)
        data["data_root"] = str(self.data_root)
        data["published_root"] = str(self.published_root)
        data["reports_root"] = str(self.reports_root)
        data["vault_path"] = str(self.vault_path) if self.vault_path else None
        return data


def load_runtime_config(repo_root: Path | None = None) -> RuntimeConfig:
    root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
    env_source, _ = load_doppler_env(root)

    secret_presence = {
        label: bool(os.getenv(env_key))
        for label, env_key in SECRET_KEYS.items()
    }
    vault_value = os.getenv(SECRET_KEYS["vault"])
    vault_path = Path(vault_value).expanduser() if vault_value else None

    return RuntimeConfig(
        repo_root=root,
        data_root=root / "data",
        published_root=root / "published",
        reports_root=root / "reports",
        env_source=env_source,
        doppler_project=os.getenv("DOPPLER_PROJECT", "sanjai-ai"),
        doppler_config=os.getenv("DOPPLER_CONFIG", "prd"),
        vault_path=vault_path,
        secret_presence=secret_presence,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        word_press_url=os.getenv("WORDPRESS_URL", ""),
        word_press_site_url=os.getenv("WORDPRESS_SITE_URL", ""),
        word_press_user=os.getenv("WORDPRESS_USER", "")
        or os.getenv("WORDPRESS_API_USER", ""),
        word_press_app_password=os.getenv("WORDPRESS_APP_PASSWORD", "")
        or os.getenv("WORDPRESS_API_PASSWORD", ""),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        boss_chat_id=os.getenv("BOSS_CHAT_ID", ""),
        opus_model=os.getenv("OPUS_MODEL", "claude-opus"),
        sonnet_model=os.getenv("SONNET_MODEL", "claude-sonnet"),
        haiku_model=os.getenv("HAIKU_MODEL", "claude-haiku"),
    )
