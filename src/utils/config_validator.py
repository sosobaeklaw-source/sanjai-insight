"""
Configuration Validation
Validates config/*.yaml files for required fields and correct schema
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """Configuration validation error"""
    pass


class ConfigValidator:
    """Configuration file validator"""

    # Schema definitions for each config file
    SCHEMAS = {
        "models.yaml": {
            "required_fields": ["models", "budget"],
            "models_schema": {
                "required_per_model": ["provider", "model_id", "pricing", "use_for"],
                "pricing_fields": ["input_per_1m_tokens", "output_per_1m_tokens"],
            },
            "budget_schema": {
                "required": ["monthly_limit_krw", "warning_threshold"],
            },
        },
        "competitors.yaml": {
            "required_fields": ["competitors", "crawl_options"],
            "competitor_schema": {
                "required": ["name", "blog_url", "enabled"],
            },
        },
        "keywords.yaml": {
            "required_fields": ["keywords"],
        },
        "schedule.yaml": {
            "required_fields": ["schedule"],
        },
        "templates.yaml": {
            "required_fields": ["templates"],
        },
        "thresholds.yaml": {
            "required_fields": ["thresholds"],
        },
    }

    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)

    def validate_all(self) -> Tuple[bool, List[str]]:
        """
        Validate all config files

        Returns:
            (is_valid, errors)
        """
        errors = []

        for config_file in self.SCHEMAS.keys():
            file_path = self.config_dir / config_file

            # Check file exists
            if not file_path.exists():
                errors.append(f"Missing config file: {config_file}")
                continue

            # Validate file
            try:
                is_valid, file_errors = self.validate_file(config_file)
                if not is_valid:
                    errors.extend(file_errors)
            except Exception as e:
                errors.append(f"Error validating {config_file}: {e}")

        return (len(errors) == 0, errors)

    def validate_file(self, filename: str) -> Tuple[bool, List[str]]:
        """
        Validate a single config file

        Returns:
            (is_valid, errors)
        """
        file_path = self.config_dir / filename
        errors = []

        try:
            # Load YAML
            with open(file_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            if config is None:
                errors.append(f"{filename}: Empty config file")
                return (False, errors)

            # Get schema
            schema = self.SCHEMAS.get(filename)
            if not schema:
                logger.warning(f"No schema defined for {filename}")
                return (True, [])

            # Validate required top-level fields
            for field in schema.get("required_fields", []):
                if field not in config:
                    errors.append(f"{filename}: Missing required field '{field}'")

            # Special validation per file type
            if filename == "models.yaml":
                errors.extend(self._validate_models_config(config, filename))
            elif filename == "competitors.yaml":
                errors.extend(self._validate_competitors_config(config, filename))

        except yaml.YAMLError as e:
            errors.append(f"{filename}: Invalid YAML syntax - {e}")
        except FileNotFoundError:
            errors.append(f"{filename}: File not found")
        except Exception as e:
            errors.append(f"{filename}: Unexpected error - {e}")

        return (len(errors) == 0, errors)

    def _validate_models_config(self, config: Dict, filename: str) -> List[str]:
        """Validate models.yaml structure"""
        errors = []

        models = config.get("models", {})
        if not isinstance(models, dict):
            errors.append(f"{filename}: 'models' must be a dictionary")
            return errors

        model_schema = self.SCHEMAS[filename]["models_schema"]
        for model_name, model_config in models.items():
            # Check required fields
            for field in model_schema["required_per_model"]:
                if field not in model_config:
                    errors.append(
                        f"{filename}: Model '{model_name}' missing field '{field}'"
                    )

            # Check pricing fields
            pricing = model_config.get("pricing", {})
            for field in model_schema["pricing_fields"]:
                if field not in pricing:
                    errors.append(
                        f"{filename}: Model '{model_name}' pricing missing '{field}'"
                    )

        # Validate budget
        budget = config.get("budget", {})
        budget_schema = self.SCHEMAS[filename]["budget_schema"]
        for field in budget_schema["required"]:
            if field not in budget:
                errors.append(f"{filename}: Budget missing field '{field}'")

        return errors

    def _validate_competitors_config(self, config: Dict, filename: str) -> List[str]:
        """Validate competitors.yaml structure"""
        errors = []

        competitors = config.get("competitors", [])
        if not isinstance(competitors, list):
            errors.append(f"{filename}: 'competitors' must be a list")
            return errors

        competitor_schema = self.SCHEMAS[filename]["competitor_schema"]
        for i, comp in enumerate(competitors):
            for field in competitor_schema["required"]:
                if field not in comp:
                    errors.append(
                        f"{filename}: Competitor #{i+1} missing field '{field}'"
                    )

        return errors

    def load_validated_config(self, filename: str) -> Dict[str, Any]:
        """
        Load and validate config, raise if invalid

        Raises:
            ConfigValidationError: If validation fails
        """
        is_valid, errors = self.validate_file(filename)
        if not is_valid:
            raise ConfigValidationError(f"Invalid config {filename}: {errors}")

        file_path = self.config_dir / filename
        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)


# Convenience function
def validate_all_configs(config_dir: str = "config") -> Tuple[bool, List[str]]:
    """
    Validate all configuration files

    Returns:
        (is_valid, errors)
    """
    validator = ConfigValidator(config_dir)
    return validator.validate_all()
