"""
Automatic Documentation Generator.

Features:
- OpenAPI/Swagger spec generation
- Markdown documentation
- API endpoint discovery
- Type hint extraction
- Example generation
"""

import inspect
import logging
import json
import os
from typing import Dict, List, Optional, Any, Callable, get_type_hints
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import ast
import re

logger = logging.getLogger(__name__)


class DocFormat(Enum):
    """Documentation formats."""
    OPENAPI = "openapi"
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"


@dataclass
class Parameter:
    """API parameter definition."""
    name: str
    param_type: str  # path, query, header, body
    data_type: str
    required: bool = True
    description: str = ""
    default: Optional[Any] = None
    example: Optional[Any] = None


@dataclass
class Endpoint:
    """API endpoint definition."""
    path: str
    method: str
    summary: str
    description: str = ""
    parameters: List[Parameter] = field(default_factory=list)
    request_body: Optional[Dict] = None
    responses: Dict[str, Dict] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    deprecated: bool = False


@dataclass
class APIDocumentation:
    """Complete API documentation."""
    title: str
    version: str
    description: str
    base_url: str
    endpoints: List[Endpoint] = field(default_factory=list)
    schemas: Dict[str, Dict] = field(default_factory=dict)
    tags: List[Dict] = field(default_factory=list)


class OpenAPIGenerator:
    """
    Generate OpenAPI 3.0 specification.

    Features:
    - Automatic schema generation from type hints
    - Example generation
    - Security scheme definition
    """

    def __init__(self, title: str, version: str, description: str):
        """Initialize OpenAPI generator."""
        self.title = title
        self.version = version
        self.description = description
        self.endpoints: List[Endpoint] = []
        self.schemas: Dict[str, Dict] = {}

    def add_endpoint(self, endpoint: Endpoint):
        """Add endpoint to documentation."""
        self.endpoints.append(endpoint)

    def add_schema(self, name: str, schema: Dict):
        """Add schema definition."""
        self.schemas[name] = schema

    def generate(self) -> Dict:
        """
        Generate OpenAPI specification.

        Returns:
            OpenAPI spec dict
        """
        spec = {
            "openapi": "3.0.0",
            "info": {
                "title": self.title,
                "version": self.version,
                "description": self.description
            },
            "paths": {},
            "components": {
                "schemas": self.schemas,
                "securitySchemes": {
                    "ApiKeyAuth": {
                        "type": "apiKey",
                        "in": "header",
                        "name": "Authorization"
                    }
                }
            }
        }

        # Group endpoints by path
        for endpoint in self.endpoints:
            if endpoint.path not in spec["paths"]:
                spec["paths"][endpoint.path] = {}

            method = endpoint.method.lower()

            spec["paths"][endpoint.path][method] = {
                "summary": endpoint.summary,
                "description": endpoint.description,
                "tags": endpoint.tags,
                "parameters": [self._parameter_to_openapi(p) for p in endpoint.parameters],
                "responses": endpoint.responses
            }

            if endpoint.request_body:
                spec["paths"][endpoint.path][method]["requestBody"] = endpoint.request_body

            if endpoint.deprecated:
                spec["paths"][endpoint.path][method]["deprecated"] = True

        return spec

    def _parameter_to_openapi(self, param: Parameter) -> Dict:
        """Convert Parameter to OpenAPI format."""
        openapi_param = {
            "name": param.name,
            "in": param.param_type,
            "required": param.required,
            "schema": {"type": param.data_type}
        }

        if param.description:
            openapi_param["description"] = param.description

        if param.default is not None:
            openapi_param["schema"]["default"] = param.default

        if param.example is not None:
            openapi_param["example"] = param.example

        return openapi_param

    def save_to_file(self, file_path: str):
        """Save OpenAPI spec to file."""
        spec = self.generate()

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(spec, f, indent=2)

        logger.info(f"Saved OpenAPI spec to {file_path}")


class MarkdownGenerator:
    """
    Generate Markdown API documentation.

    Features:
    - Human-readable format
    - Table of contents
    - Code examples
    - Response examples
    """

    def __init__(self, api_doc: APIDocumentation):
        """Initialize markdown generator."""
        self.api_doc = api_doc

    def generate(self) -> str:
        """
        Generate markdown documentation.

        Returns:
            Markdown string
        """
        lines = []

        # Header
        lines.append(f"# {self.api_doc.title}")
        lines.append(f"\n**Version:** {self.api_doc.version}\n")
        lines.append(f"{self.api_doc.description}\n")
        lines.append(f"**Base URL:** `{self.api_doc.base_url}`\n")

        # Table of contents
        lines.append("## Table of Contents\n")
        for i, endpoint in enumerate(self.api_doc.endpoints, 1):
            lines.append(f"{i}. [{endpoint.method} {endpoint.path}](#{self._anchor(endpoint)})")
        lines.append("")

        # Endpoints
        lines.append("## Endpoints\n")

        for endpoint in self.api_doc.endpoints:
            lines.append(f"### {endpoint.method} {endpoint.path}\n")
            lines.append(f"**Summary:** {endpoint.summary}\n")

            if endpoint.description:
                lines.append(f"{endpoint.description}\n")

            if endpoint.tags:
                lines.append(f"**Tags:** {', '.join(endpoint.tags)}\n")

            # Parameters
            if endpoint.parameters:
                lines.append("**Parameters:**\n")
                lines.append("| Name | Type | In | Required | Description |")
                lines.append("|------|------|------|----------|-------------|")

                for param in endpoint.parameters:
                    required = "Yes" if param.required else "No"
                    lines.append(
                        f"| {param.name} | {param.data_type} | {param.param_type} | "
                        f"{required} | {param.description or '-'} |"
                    )

                lines.append("")

            # Request body
            if endpoint.request_body:
                lines.append("**Request Body:**\n")
                lines.append("```json")
                lines.append(json.dumps(endpoint.request_body, indent=2))
                lines.append("```\n")

            # Responses
            if endpoint.responses:
                lines.append("**Responses:**\n")

                for status, response in endpoint.responses.items():
                    lines.append(f"**{status}:** {response.get('description', '')}\n")

                    if "content" in response:
                        lines.append("```json")
                        lines.append(json.dumps(
                            response.get("content", {}),
                            indent=2
                        ))
                        lines.append("```\n")

            lines.append("---\n")

        return "\n".join(lines)

    def _anchor(self, endpoint: Endpoint) -> str:
        """Generate anchor link for endpoint."""
        return f"{endpoint.method.lower()}-{endpoint.path.replace('/', '-')}"

    def save_to_file(self, file_path: str):
        """Save markdown to file."""
        content = self.generate()

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Saved markdown documentation to {file_path}")


class CodeInspector:
    """
    Inspect Python code to extract documentation.

    Features:
    - Function signature extraction
    - Type hint parsing
    - Docstring parsing
    - Decorator detection
    """

    @staticmethod
    def extract_function_doc(func: Callable) -> Dict:
        """
        Extract documentation from function.

        Args:
            func: Function to inspect

        Returns:
            Documentation dict
        """
        doc = {
            "name": func.__name__,
            "signature": str(inspect.signature(func)),
            "docstring": inspect.getdoc(func) or "",
            "parameters": [],
            "return_type": None
        }

        # Extract type hints
        try:
            hints = get_type_hints(func)
            for param_name, param_type in hints.items():
                if param_name == "return":
                    doc["return_type"] = str(param_type)
                else:
                    doc["parameters"].append({
                        "name": param_name,
                        "type": str(param_type)
                    })
        except Exception as e:
            logger.warning(f"Failed to extract type hints from {func.__name__}: {e}")

        return doc

    @staticmethod
    def extract_class_doc(cls: type) -> Dict:
        """
        Extract documentation from class.

        Args:
            cls: Class to inspect

        Returns:
            Documentation dict
        """
        doc = {
            "name": cls.__name__,
            "docstring": inspect.getdoc(cls) or "",
            "methods": []
        }

        # Extract methods
        for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
            if not name.startswith("_"):
                doc["methods"].append(
                    CodeInspector.extract_function_doc(method)
                )

        return doc


class AutoDocGenerator:
    """
    Automatic documentation generator from Flask/FastAPI apps.

    Features:
    - Route discovery
    - Parameter extraction
    - Example generation
    - Multi-format output
    """

    def __init__(self, app_module: Any):
        """
        Initialize auto doc generator.

        Args:
            app_module: Flask or FastAPI app module
        """
        self.app_module = app_module
        self.endpoints: List[Endpoint] = []

    def discover_endpoints(self):
        """Discover endpoints from app."""
        # Check if Flask app
        if hasattr(self.app_module, "url_map"):
            self._discover_flask_endpoints()
        # Check if FastAPI app
        elif hasattr(self.app_module, "routes"):
            self._discover_fastapi_endpoints()
        else:
            logger.warning("Unknown app type, manual endpoint registration required")

    def _discover_flask_endpoints(self):
        """Discover Flask endpoints."""
        for rule in self.app_module.url_map.iter_rules():
            if rule.endpoint != "static":
                view_func = self.app_module.view_functions[rule.endpoint]

                endpoint = Endpoint(
                    path=rule.rule,
                    method=list(rule.methods)[0] if rule.methods else "GET",
                    summary=view_func.__name__.replace("_", " ").title(),
                    description=inspect.getdoc(view_func) or ""
                )

                self.endpoints.append(endpoint)

    def _discover_fastapi_endpoints(self):
        """Discover FastAPI endpoints."""
        for route in self.app_module.routes:
            if hasattr(route, "path") and hasattr(route, "methods"):
                endpoint = Endpoint(
                    path=route.path,
                    method=list(route.methods)[0],
                    summary=route.name.replace("_", " ").title(),
                    description=route.description or ""
                )

                self.endpoints.append(endpoint)

    def generate_openapi(self, output_path: str):
        """Generate OpenAPI specification."""
        generator = OpenAPIGenerator(
            title="Sanjai Insight API",
            version="1.0.0",
            description="산재AI 능동적 인사이트 시스템 API"
        )

        for endpoint in self.endpoints:
            generator.add_endpoint(endpoint)

        generator.save_to_file(output_path)

    def generate_markdown(self, output_path: str):
        """Generate Markdown documentation."""
        api_doc = APIDocumentation(
            title="Sanjai Insight API",
            version="1.0.0",
            description="산재AI 능동적 인사이트 시스템 API",
            base_url="https://api.sanjai.com",
            endpoints=self.endpoints
        )

        generator = MarkdownGenerator(api_doc)
        generator.save_to_file(output_path)

    def generate_all(self, output_dir: str = "docs"):
        """Generate all documentation formats."""
        os.makedirs(output_dir, exist_ok=True)

        self.discover_endpoints()

        # OpenAPI
        self.generate_openapi(f"{output_dir}/openapi.json")

        # Markdown
        self.generate_markdown(f"{output_dir}/API.md")

        logger.info(f"Generated all documentation in {output_dir}")
