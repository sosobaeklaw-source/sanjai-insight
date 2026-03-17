"""
Configuration Validator
YAML 설정 파일 스키마 검증 및 필수 필드 체크
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
    """YAML 설정 파일 검증"""

    # 스키마 정의
    SCHEMAS = {
        "competitors": {
            "required_fields": ["competitors", "crawl_options"],
            "competitors_fields": ["name", "blog_url", "enabled"],
            "crawl_options_fields": [
                "max_posts_per_site",
            ],
        },
        "keywords": {
            "required_fields": [
                "precedent_keywords",
                "trend_keywords",
                "policy_keywords",
                "exclude_keywords",
            ],
            "list_type": True,
        },
        "models": {
            "required_fields": ["models", "budget"],
            "model_fields": ["provider", "model_id", "pricing", "use_for"],
            "pricing_fields": ["input_per_1m_tokens", "output_per_1m_tokens"],
            "rate_limit_fields": ["requests_per_minute", "tokens_per_minute"],
            "budget_fields": [
                "monthly_limit_krw",
                "warning_threshold",
            ],
        },
        "schedule": {
            "required_fields": ["crawlers", "engines"],
            "crawler_fields": ["cron", "enabled"],
        },
        "templates": {
            "required_fields": ["templates"],
        },
        "thresholds": {
            "required_fields": [
                "insight",
                "cost",
                "crawler",
                "marketing",
            ],
            "insight_fields": ["confidence_threshold", "daily_proposal_limit"],
            "cost_fields": ["monthly_budget_krw", "warning_ratio"],
        },
    }

    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)

    def validate_all(self) -> Tuple[bool, List[str]]:
        """
        모든 설정 파일 검증

        Returns:
            (is_valid, error_messages)
        """
        errors = []

        for config_name in self.SCHEMAS.keys():
            try:
                self.validate_config(config_name)
            except ConfigValidationError as e:
                errors.append(str(e))
            except FileNotFoundError as e:
                errors.append(f"Config file not found: {config_name}.yaml")
            except Exception as e:
                errors.append(f"Unexpected error validating {config_name}: {e}")

        is_valid = len(errors) == 0
        return is_valid, errors

    def validate_config(self, config_name: str) -> Dict[str, Any]:
        """
        개별 설정 파일 검증

        Args:
            config_name: 설정 파일 이름 (확장자 제외)

        Returns:
            검증된 설정 딕셔너리

        Raises:
            ConfigValidationError: 검증 실패 시
            FileNotFoundError: 파일이 없을 때
        """
        # 파일 로드
        config_path = self.config_dir / f"{config_name}.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigValidationError(f"Invalid YAML in {config_name}: {e}")

        if config is None:
            raise ConfigValidationError(f"Empty config file: {config_name}")

        # 스키마 검증
        schema = self.SCHEMAS.get(config_name)
        if not schema:
            logger.warning(f"No schema defined for {config_name}, skipping validation")
            return config

        # 필수 필드 체크
        required_fields = schema.get("required_fields", [])
        for field in required_fields:
            if field not in config:
                raise ConfigValidationError(
                    f"Missing required field '{field}' in {config_name}"
                )

        # 개별 설정별 추가 검증
        if config_name == "competitors":
            self._validate_competitors(config)
        elif config_name == "keywords":
            self._validate_keywords(config)
        elif config_name == "models":
            self._validate_models(config)
        elif config_name == "schedule":
            self._validate_schedule(config)
        elif config_name == "templates":
            self._validate_templates(config)
        elif config_name == "thresholds":
            self._validate_thresholds(config)

        return config

    def _validate_competitors(self, config: Dict):
        """경쟁사 설정 검증"""
        competitors = config.get("competitors", [])
        if not isinstance(competitors, list):
            raise ConfigValidationError("competitors must be a list")

        schema = self.SCHEMAS["competitors"]
        for i, comp in enumerate(competitors):
            for field in schema["competitors_fields"]:
                if field not in comp:
                    raise ConfigValidationError(
                        f"Competitor #{i} missing field: {field}"
                    )

        crawl_options = config.get("crawl_options", {})
        for field in schema["crawl_options_fields"]:
            if field not in crawl_options:
                raise ConfigValidationError(
                    f"crawl_options missing field: {field}"
                )

    def _validate_keywords(self, config: Dict):
        """키워드 설정 검증"""
        schema = self.SCHEMAS["keywords"]
        for field in schema["required_fields"]:
            value = config.get(field)
            if not isinstance(value, list):
                raise ConfigValidationError(f"{field} must be a list")
            if len(value) == 0:
                logger.warning(f"{field} is empty")

    def _validate_models(self, config: Dict):
        """모델 설정 검증"""
        models = config.get("models", {})
        if not isinstance(models, dict):
            raise ConfigValidationError("models must be a dictionary")

        schema = self.SCHEMAS["models"]
        for model_name, model_config in models.items():
            for field in schema["model_fields"]:
                if field not in model_config:
                    raise ConfigValidationError(
                        f"Model {model_name} missing field: {field}"
                    )

            pricing = model_config.get("pricing", {})
            if not isinstance(pricing, dict):
                raise ConfigValidationError(f"Model {model_name} pricing must be a dictionary")
            for field in schema["pricing_fields"]:
                if field not in pricing:
                    raise ConfigValidationError(
                        f"Model {model_name} pricing missing field: {field}"
                    )

            if "rate_limit" in model_config:
                rate_limit = model_config.get("rate_limit", {})
                if not isinstance(rate_limit, dict):
                    raise ConfigValidationError(
                        f"Model {model_name} rate_limit must be a dictionary"
                    )
                for field in schema["rate_limit_fields"]:
                    if field not in rate_limit:
                        raise ConfigValidationError(
                            f"Model {model_name} rate_limit missing field: {field}"
                        )

        budget = config.get("budget", {})
        for field in schema["budget_fields"]:
            if field not in budget:
                raise ConfigValidationError(f"budget missing field: {field}")

        # 예산 임계값 검증 (0~1 사이)
        for field in ["warning_threshold", "critical_threshold", "shutdown_threshold"]:
            value = budget.get(field)
            if not isinstance(value, (int, float)) or value < 0 or value > 1:
                raise ConfigValidationError(
                    f"budget.{field} must be between 0 and 1"
                )

    def _validate_schedule(self, config: Dict):
        """스케줄 설정 검증"""
        schema = self.SCHEMAS["schedule"]

        crawlers = config.get("crawlers", {})
        if not isinstance(crawlers, dict):
            raise ConfigValidationError("crawlers must be a dictionary")

        # 최소 1개 크롤러는 있어야 함
        if len(crawlers) == 0:
            logger.warning("No crawlers defined in schedule")

        for crawler_name, crawler_config in crawlers.items():
            if not isinstance(crawler_config, dict):
                raise ConfigValidationError(f"Crawler {crawler_name} must be a dictionary")

            for field in schema["crawler_fields"]:
                if field not in crawler_config:
                    raise ConfigValidationError(
                        f"Crawler {crawler_name} missing field: {field}"
                    )

        engines = config.get("engines", {})
        if not isinstance(engines, dict):
            raise ConfigValidationError("engines must be a dictionary")

    def _validate_templates(self, config: Dict):
        """템플릿 설정 검증"""
        templates = config.get("templates")
        if not isinstance(templates, dict):
            raise ConfigValidationError("templates must be a dictionary")

        # 최소 1개 템플릿은 있어야 함
        if len(templates) == 0:
            raise ConfigValidationError("templates must contain at least one template")

    def _validate_thresholds(self, config: Dict):
        """임계값 설정 검증"""
        schema = self.SCHEMAS["thresholds"]

        # insight
        insight = config.get("insight")
        if not isinstance(insight, dict):
            raise ConfigValidationError("insight must be a dictionary")

        for field in schema["insight_fields"]:
            if field not in insight:
                raise ConfigValidationError(f"insight missing field: {field}")

        # confidence_threshold 범위 검증
        confidence = insight.get("confidence_threshold")
        if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
            raise ConfigValidationError(
                "insight.confidence_threshold must be between 0 and 1"
            )

        # cost
        cost = config.get("cost")
        if not isinstance(cost, dict):
            raise ConfigValidationError("cost must be a dictionary")

        for field in schema["cost_fields"]:
            if field not in cost:
                raise ConfigValidationError(f"cost missing field: {field}")

        # 비용 임계값 검증
        for field in ["warning_ratio", "critical_ratio", "shutdown_ratio"]:
            if field in cost:
                value = cost[field]
                if not isinstance(value, (int, float)) or value < 0 or value > 1:
                    raise ConfigValidationError(
                        f"cost.{field} must be between 0 and 1"
                    )

        # crawler
        crawler = config.get("crawler")
        if not isinstance(crawler, dict):
            raise ConfigValidationError("crawler must be a dictionary")

        # marketing
        marketing = config.get("marketing")
        if not isinstance(marketing, dict):
            raise ConfigValidationError("marketing must be a dictionary")

    def validate_file(self, filename: str) -> Tuple[bool, List[str]]:
        """
        Backward-compatible single-file validator used by the test suite.

        Args:
            filename: config filename like "models.yaml"

        Returns:
            (is_valid, error_messages)
        """
        config_name = Path(filename).stem
        config_path = self.config_dir / filename
        if not config_path.exists():
            return (False, [f"Config file not found: {config_path}"])

        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                config = yaml.safe_load(handle)
        except yaml.YAMLError as exc:
            return (False, [f"Invalid YAML in {config_name}: {exc}"])

        if config is None:
            return (False, [f"Empty config file: {config_name}"])

        errors: List[str] = []
        schema = self.SCHEMAS.get(config_name)
        if not schema:
            return (True, [])

        for field in schema.get("required_fields", []):
            if field not in config:
                errors.append(f"Missing required field '{field}' in {config_name}")

        if config_name == "models":
            models = config.get("models", {})
            if not isinstance(models, dict):
                errors.append("models must be a dictionary")
            else:
                for model_name, model_config in models.items():
                    for field in schema["model_fields"]:
                        if field not in model_config:
                            errors.append(f"Model {model_name} missing field: {field}")
                    pricing = model_config.get("pricing")
                    if pricing is not None and isinstance(pricing, dict):
                        for field in schema["pricing_fields"]:
                            if field not in pricing:
                                errors.append(
                                    f"Model {model_name} pricing missing field: {field}"
                                )
                    elif "pricing" in model_config:
                        errors.append(f"Model {model_name} pricing must be a dictionary")
            budget = config.get("budget", {})
            if not isinstance(budget, dict):
                errors.append("budget must be a dictionary")
            else:
                for field in schema["budget_fields"]:
                    if field not in budget:
                        errors.append(f"budget missing field: {field}")

        elif config_name == "competitors":
            competitors = config.get("competitors", [])
            if not isinstance(competitors, list):
                errors.append("competitors must be a list")
            else:
                for index, competitor in enumerate(competitors):
                    for field in schema["competitors_fields"]:
                        if field not in competitor:
                            errors.append(f"Competitor #{index} missing field: {field}")
            crawl_options = config.get("crawl_options", {})
            if not isinstance(crawl_options, dict):
                errors.append("crawl_options must be a dictionary")
            else:
                for field in schema["crawl_options_fields"]:
                    if field not in crawl_options:
                        errors.append(f"crawl_options missing field: {field}")

        else:
            try:
                self.validate_config(config_name)
            except ConfigValidationError as exc:
                errors.append(str(exc))

        return (len(errors) == 0, errors)

    def load_validated_config(self, filename: str) -> Dict[str, Any]:
        """
        Load one config and raise if validation fails.
        """
        is_valid, errors = self.validate_file(filename)
        if not is_valid:
            raise ConfigValidationError("; ".join(errors))
        config_path = self.config_dir / filename
        with open(config_path, "r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)


def validate_configs(config_dir: str = "config") -> Tuple[bool, List[str]]:
    """
    설정 파일 일괄 검증 (편의 함수)

    Returns:
        (is_valid, error_messages)
    """
    validator = ConfigValidator(config_dir)
    return validator.validate_all()


if __name__ == "__main__":
    # 독립 실행 테스트
    logging.basicConfig(level=logging.INFO)
    is_valid, errors = validate_configs()

    if is_valid:
        print("[OK] All configuration files are valid")
    else:
        print("[FAIL] Configuration validation failed:")
        for error in errors:
            print(f"  - {error}")
