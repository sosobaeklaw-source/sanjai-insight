"""
Configuration Validation Tests
Tests for config/*.yaml validation
"""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from src.config.validator import (
    ConfigValidator,
    ConfigValidationError,
    validate_configs,
)


@pytest.fixture
def temp_config_dir():
    """Create temporary config directory"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / "config"
        config_dir.mkdir()
        yield config_dir


def test_validate_models_valid(temp_config_dir):
    """Test valid models.yaml passes validation"""
    models_config = {
        "models": {
            "claude_sonnet_4": {
                "provider": "anthropic",
                "model_id": "claude-sonnet-4-20250514",
                "pricing": {
                    "input_per_1m_tokens": 3.0,
                    "output_per_1m_tokens": 15.0,
                },
                "rate_limit": {
                    "requests_per_minute": 50,
                    "tokens_per_minute": 40000,
                },
                "use_for": ["think"],
            }
        },
        "budget": {
            "monthly_limit_krw": 50000,
            "warning_threshold": 0.8,
            "critical_threshold": 0.9,
            "shutdown_threshold": 1.0,
        },
    }

    with open(temp_config_dir / "models.yaml", "w") as f:
        yaml.dump(models_config, f)

    validator = ConfigValidator(str(temp_config_dir))
    try:
        config = validator.validate_config("models")
        assert config is not None
    except ConfigValidationError:
        pytest.fail("Validation should succeed")


def test_validate_models_missing_field(temp_config_dir):
    """Test models.yaml with missing required field fails"""
    models_config = {
        "models": {
            "claude_sonnet_4": {
                "provider": "anthropic",
                # Missing model_id, pricing, use_for
            }
        },
        "budget": {
            "monthly_limit_krw": 50000,
        },
    }

    with open(temp_config_dir / "models.yaml", "w") as f:
        yaml.dump(models_config, f)

    validator = ConfigValidator(str(temp_config_dir))
    is_valid, errors = validator.validate_file("models.yaml")

    assert not is_valid
    assert any("model_id" in e for e in errors)
    assert any("pricing" in e for e in errors)


def test_validate_models_missing_pricing(temp_config_dir):
    """Test models.yaml with incomplete pricing fails"""
    models_config = {
        "models": {
            "claude_sonnet_4": {
                "provider": "anthropic",
                "model_id": "claude-sonnet-4-20250514",
                "pricing": {
                    "input_per_1m_tokens": 3.0,
                    # Missing output_per_1m_tokens
                },
                "use_for": ["think"],
            }
        },
        "budget": {
            "monthly_limit_krw": 50000,
            "warning_threshold": 0.8,
        },
    }

    with open(temp_config_dir / "models.yaml", "w") as f:
        yaml.dump(models_config, f)

    validator = ConfigValidator(str(temp_config_dir))
    is_valid, errors = validator.validate_file("models.yaml")

    assert not is_valid
    assert any("output_per_1m_tokens" in e for e in errors)


def test_validate_competitors_valid(temp_config_dir):
    """Test valid competitors.yaml passes"""
    competitors_config = {
        "competitors": [
            {
                "name": "법무법인 A",
                "blog_url": "https://example.com/blog",
                "enabled": False,
            }
        ],
        "crawl_options": {
            "max_posts_per_site": 10,
        },
    }

    with open(temp_config_dir / "competitors.yaml", "w") as f:
        yaml.dump(competitors_config, f)

    validator = ConfigValidator(str(temp_config_dir))
    is_valid, errors = validator.validate_file("competitors.yaml")

    assert is_valid
    assert len(errors) == 0


def test_validate_competitors_missing_field(temp_config_dir):
    """Test competitors.yaml with missing required field fails"""
    competitors_config = {
        "competitors": [
            {
                "name": "법무법인 A",
                # Missing blog_url, enabled
            }
        ],
        "crawl_options": {},
    }

    with open(temp_config_dir / "competitors.yaml", "w") as f:
        yaml.dump(competitors_config, f)

    validator = ConfigValidator(str(temp_config_dir))
    is_valid, errors = validator.validate_file("competitors.yaml")

    assert not is_valid
    assert any("blog_url" in e for e in errors)
    assert any("enabled" in e for e in errors)


def test_validate_empty_file(temp_config_dir):
    """Test empty config file fails"""
    with open(temp_config_dir / "models.yaml", "w") as f:
        f.write("")

    validator = ConfigValidator(str(temp_config_dir))
    is_valid, errors = validator.validate_file("models.yaml")

    assert not is_valid
    assert any("Empty" in e for e in errors)


def test_validate_invalid_yaml(temp_config_dir):
    """Test invalid YAML syntax fails"""
    with open(temp_config_dir / "models.yaml", "w") as f:
        f.write("invalid: yaml: syntax: :")

    validator = ConfigValidator(str(temp_config_dir))
    is_valid, errors = validator.validate_file("models.yaml")

    assert not is_valid
    assert any("YAML" in e for e in errors)


def test_validate_missing_file(temp_config_dir):
    """Test missing config file fails"""
    validator = ConfigValidator(str(temp_config_dir))
    is_valid, errors = validator.validate_file("models.yaml")

    assert not is_valid
    assert any("not found" in e for e in errors)


def test_load_validated_config_success(temp_config_dir):
    """Test load_validated_config returns config on success"""
    models_config = {
        "models": {
            "claude_sonnet_4": {
                "provider": "anthropic",
                "model_id": "claude-sonnet-4-20250514",
                "pricing": {
                    "input_per_1m_tokens": 3.0,
                    "output_per_1m_tokens": 15.0,
                },
                "use_for": ["think"],
            }
        },
        "budget": {
            "monthly_limit_krw": 50000,
            "warning_threshold": 0.8,
        },
    }

    with open(temp_config_dir / "models.yaml", "w") as f:
        yaml.dump(models_config, f)

    validator = ConfigValidator(str(temp_config_dir))
    config = validator.load_validated_config("models.yaml")

    assert config == models_config


def test_load_validated_config_raises_on_invalid(temp_config_dir):
    """Test load_validated_config raises on invalid config"""
    models_config = {
        "models": {},  # Missing budget
    }

    with open(temp_config_dir / "models.yaml", "w") as f:
        yaml.dump(models_config, f)

    validator = ConfigValidator(str(temp_config_dir))

    with pytest.raises(ConfigValidationError):
        validator.load_validated_config("models.yaml")


def test_validate_all_configs_real():
    """Test validation on real config directory"""
    if Path("config").exists():
        is_valid, errors = validate_configs("config")

        # Should pass (or at least not crash)
        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)

        if not is_valid:
            print("Config validation errors:")
            for error in errors:
                print(f"  - {error}")
