"""
Configuration management using Pydantic Settings.

Configuration is loaded from:
1. Environment variables (SKYNERD_*)
2. ~/.skynerd/config.yaml
"""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_config_dir() -> Path:
    """Get the configuration directory (~/.skynerd/)."""
    config_dir = Path.home() / ".skynerd"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def load_yaml_config() -> dict[str, Any]:
    """Load configuration from YAML file."""
    config_file = get_config_dir() / "config.yaml"
    if config_file.exists():
        try:
            # Read with UTF-8 encoding, handle BOM
            content = config_file.read_text(encoding="utf-8-sig")
            return yaml.safe_load(content) or {}
        except yaml.YAMLError as e:
            print(f"Error parsing config file {config_file}: {e}")
            raise
    return {}


class APISettings(BaseSettings):
    """SkyNerd API connection settings."""

    base_url: str = Field(
        default="https://skynerd-control.com",
        description="Base URL for SkyNerd Control API",
    )
    api_key: str = Field(
        default="",
        description="API key for authentication",
    )
    timeout: int = Field(default=30, description="Request timeout in seconds")


class OllamaSettings(BaseSettings):
    """Local Ollama settings for Gemma 3 12B."""

    enabled: bool = Field(default=True, description="Enable Ollama for local AI")
    base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama API base URL",
    )
    model: str = Field(
        default="gemma3:12b",
        description="Model to use for local AI",
    )
    timeout: int = Field(default=120, description="Model inference timeout")


class MonitorSettings(BaseSettings):
    """Monitor polling intervals (all in minutes)."""

    email_interval: int = Field(default=1, description="Email check interval")
    task_interval: int = Field(default=1, description="Task check interval")
    calendar_interval: int = Field(default=1, description="Calendar check interval")
    voice_interval: int = Field(default=1, description="Voice notification check interval")
    reminder_interval: int = Field(default=1, description="Reminder check interval")


class NotificationSettings(BaseSettings):
    """Notification preferences."""

    desktop: bool = Field(default=True, description="Enable desktop notifications")
    slack: bool = Field(default=True, description="Enable Slack notifications")
    sound: bool = Field(default=True, description="Play notification sounds")


class VoiceSettings(BaseSettings):
    """Voice/TTS settings."""

    enabled: bool = Field(default=True, description="Enable voice notifications")
    tts_engine: str = Field(
        default="pyttsx3",
        description="TTS engine: pyttsx3, sapi, polly",
    )
    voice_rate: int = Field(default=150, description="Words per minute")
    voice_volume: float = Field(default=0.8, description="Volume (0.0 to 1.0)")


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_prefix="SKYNERD_",
        env_nested_delimiter="__",
    )

    # Sub-settings
    api: APISettings = Field(default_factory=APISettings)
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    monitors: MonitorSettings = Field(default_factory=MonitorSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)

    # Paths
    data_dir: Path = Field(
        default_factory=get_config_dir,
        description="Data directory (~/.skynerd/)",
    )
    config_path: Path = Field(
        default_factory=lambda: get_config_dir() / "config.yaml",
        description="Path to config file",
    )
    db_path: Path = Field(
        default_factory=lambda: get_config_dir() / "agent.db",
        description="Path to SQLite database",
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_file: Path | None = Field(
        default=None,
        description="Log file path (None for stdout only)",
    )

    @classmethod
    def load(cls) -> "Settings":
        """Load settings from YAML and environment."""
        yaml_config = load_yaml_config()

        # Flatten nested config for Pydantic
        env_overrides = {}

        # API settings
        if "api" in yaml_config:
            for key, value in yaml_config["api"].items():
                env_overrides[f"api__{key}"] = value

        # Ollama settings
        if "ollama" in yaml_config:
            for key, value in yaml_config["ollama"].items():
                env_overrides[f"ollama__{key}"] = value

        # Monitor settings
        if "monitors" in yaml_config:
            for key, value in yaml_config["monitors"].items():
                # Convert xxx_interval_minutes to xxx_interval
                new_key = key.replace("_minutes", "")
                env_overrides[f"monitors__{new_key}"] = value

        # Notification settings
        if "notifications" in yaml_config:
            for key, value in yaml_config["notifications"].items():
                env_overrides[f"notifications__{key}"] = value

        # Voice settings
        if "voice" in yaml_config:
            for key, value in yaml_config["voice"].items():
                env_overrides[f"voice__{key}"] = value

        # Set environment variables for Pydantic to pick up
        for key, value in env_overrides.items():
            env_key = f"SKYNERD_{key.upper()}"
            if env_key not in os.environ:
                os.environ[env_key] = str(value)

        return cls()


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings.load()
    return _settings


def load_settings() -> Settings:
    """Load settings from config file. Alias for get_settings()."""
    return get_settings()


def create_default_config():
    """Create a default configuration file."""
    config_file = get_config_dir() / "config.yaml"

    default_config = """# SkyNerd Assistant Configuration
# All monitors poll every 1 minute by default

api:
  base_url: https://skynerd-control.com
  api_key: your-api-key-here

ollama:
  base_url: http://localhost:11434
  model: gemma3:12b

monitors:
  email_interval_minutes: 1
  task_interval_minutes: 1
  calendar_interval_minutes: 1
  voice_interval_minutes: 1
  reminder_interval_minutes: 1

notifications:
  desktop: true
  slack: true
  sound: true

voice:
  enabled: true
  tts_engine: pyttsx3  # or 'sapi' for Windows SAPI, 'polly' for AWS Polly
  voice_rate: 150      # Words per minute
  voice_volume: 0.8    # 0.0 to 1.0
"""

    if not config_file.exists():
        with open(config_file, "w") as f:
            f.write(default_config)
        return config_file

    return None
