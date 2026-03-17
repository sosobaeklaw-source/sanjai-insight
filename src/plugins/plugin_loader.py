"""
Plugin System with dynamic loading and sandboxing.

Features:
- Dynamic plugin loading from directory
- Plugin sandboxing via subprocess
- YAML-based plugin manifests
- Plugin lifecycle management
- Plugin marketplace foundation
"""

import os
import sys
import yaml
import importlib.util
import subprocess
import json
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from abc import ABC, abstractmethod
import sqlite3

logger = logging.getLogger(__name__)


@dataclass
class PluginManifest:
    """Plugin manifest from YAML."""
    name: str
    version: str
    author: str
    description: str
    entry_point: str
    dependencies: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    sandbox: bool = True
    timeout_seconds: int = 30
    metadata: Dict = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "PluginManifest":
        """Load manifest from YAML file."""
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f)

        return cls(
            name=data["name"],
            version=data["version"],
            author=data["author"],
            description=data["description"],
            entry_point=data["entry_point"],
            dependencies=data.get("dependencies", []),
            permissions=data.get("permissions", []),
            sandbox=data.get("sandbox", True),
            timeout_seconds=data.get("timeout_seconds", 30),
            metadata=data.get("metadata", {})
        )


class Plugin(ABC):
    """
    Base plugin class.

    Plugins should inherit from this and implement execute().
    """

    def __init__(self, manifest: PluginManifest):
        """Initialize plugin."""
        self.manifest = manifest
        self.logger = logging.getLogger(f"plugin.{manifest.name}")

    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute plugin with context.

        Args:
            context: Execution context

        Returns:
            Result dictionary
        """
        pass

    def on_load(self):
        """Called when plugin is loaded."""
        pass

    def on_unload(self):
        """Called when plugin is unloaded."""
        pass


@dataclass
class PluginRecord:
    """Plugin registration record."""
    plugin_id: str
    name: str
    version: str
    author: str
    installed_at: datetime
    is_enabled: bool = True
    execution_count: int = 0
    last_execution: Optional[datetime] = None


class PluginLoader:
    """
    Dynamic plugin loader with sandboxing.

    Features:
    - Load plugins from directory
    - Subprocess sandboxing
    - Plugin registry
    - Error isolation
    """

    def __init__(
        self,
        plugins_dir: str = "plugins",
        db_path: str = "data/plugins.db"
    ):
        """
        Initialize plugin loader.

        Args:
            plugins_dir: Directory containing plugins
            db_path: Plugin registry database
        """
        self.plugins_dir = Path(plugins_dir)
        self.db_path = db_path
        self._plugins: Dict[str, Plugin] = {}
        self._manifests: Dict[str, PluginManifest] = {}
        self._ensure_db()

    def _ensure_db(self):
        """Create plugin registry database."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS plugins (
                    plugin_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    author TEXT NOT NULL,
                    installed_at TEXT NOT NULL,
                    is_enabled INTEGER DEFAULT 1,
                    execution_count INTEGER DEFAULT 0,
                    last_execution TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS plugin_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plugin_id TEXT NOT NULL,
                    executed_at TEXT NOT NULL,
                    duration_ms REAL NOT NULL,
                    success INTEGER NOT NULL,
                    error_message TEXT,
                    FOREIGN KEY (plugin_id) REFERENCES plugins(plugin_id)
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_executions_plugin
                ON plugin_executions(plugin_id, executed_at)
            """)

    def discover_plugins(self) -> List[str]:
        """
        Discover plugins in plugins directory.

        Returns:
            List of discovered plugin names
        """
        if not self.plugins_dir.exists():
            logger.warning(f"Plugins directory not found: {self.plugins_dir}")
            return []

        discovered = []

        for plugin_dir in self.plugins_dir.iterdir():
            if not plugin_dir.is_dir():
                continue

            manifest_path = plugin_dir / "plugin.yaml"
            if not manifest_path.exists():
                continue

            try:
                manifest = PluginManifest.from_yaml(str(manifest_path))
                discovered.append(manifest.name)
                logger.info(f"Discovered plugin: {manifest.name} v{manifest.version}")

            except Exception as e:
                logger.error(f"Failed to load manifest from {plugin_dir}: {e}")

        return discovered

    def load_plugin(self, plugin_name: str) -> bool:
        """
        Load plugin by name.

        Args:
            plugin_name: Name of plugin to load

        Returns:
            True if loaded successfully
        """
        if plugin_name in self._plugins:
            logger.warning(f"Plugin {plugin_name} already loaded")
            return True

        plugin_dir = self.plugins_dir / plugin_name
        manifest_path = plugin_dir / "plugin.yaml"

        if not manifest_path.exists():
            logger.error(f"Plugin manifest not found: {manifest_path}")
            return False

        try:
            # Load manifest
            manifest = PluginManifest.from_yaml(str(manifest_path))
            self._manifests[plugin_name] = manifest

            # Load plugin module
            entry_path = plugin_dir / manifest.entry_point
            spec = importlib.util.spec_from_file_location(
                f"plugin.{plugin_name}",
                entry_path
            )

            if not spec or not spec.loader:
                raise ImportError(f"Failed to load spec for {plugin_name}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)

            # Instantiate plugin
            if not hasattr(module, "PluginClass"):
                raise AttributeError("Plugin must define PluginClass")

            plugin_instance = module.PluginClass(manifest)
            plugin_instance.on_load()

            self._plugins[plugin_name] = plugin_instance

            # Register in database
            self._register_plugin(manifest)

            logger.info(f"Loaded plugin: {plugin_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to load plugin {plugin_name}: {e}")
            return False

    def _register_plugin(self, manifest: PluginManifest):
        """Register plugin in database."""
        plugin_id = f"{manifest.name}_{manifest.version}"

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO plugins
                (plugin_id, name, version, author, installed_at, is_enabled)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (
                    plugin_id,
                    manifest.name,
                    manifest.version,
                    manifest.author,
                    datetime.utcnow().isoformat()
                )
            )

    def unload_plugin(self, plugin_name: str):
        """
        Unload plugin.

        Args:
            plugin_name: Name of plugin to unload
        """
        if plugin_name not in self._plugins:
            logger.warning(f"Plugin {plugin_name} not loaded")
            return

        try:
            plugin = self._plugins[plugin_name]
            plugin.on_unload()

            del self._plugins[plugin_name]
            del self._manifests[plugin_name]

            logger.info(f"Unloaded plugin: {plugin_name}")

        except Exception as e:
            logger.error(f"Error unloading plugin {plugin_name}: {e}")

    async def execute_plugin(
        self,
        plugin_name: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute plugin with context.

        Args:
            plugin_name: Plugin to execute
            context: Execution context

        Returns:
            Plugin result

        Raises:
            ValueError: If plugin not found
            RuntimeError: If execution fails
        """
        if plugin_name not in self._plugins:
            raise ValueError(f"Plugin {plugin_name} not loaded")

        plugin = self._plugins[plugin_name]
        manifest = self._manifests[plugin_name]

        start_time = datetime.utcnow()
        success = False
        error_message = None

        try:
            # Execute in sandbox if enabled
            if manifest.sandbox:
                result = await self._execute_sandboxed(
                    plugin_name,
                    context,
                    manifest.timeout_seconds
                )
            else:
                result = await plugin.execute(context)

            success = True
            return result

        except Exception as e:
            error_message = str(e)
            logger.error(f"Plugin {plugin_name} execution failed: {e}")
            raise RuntimeError(f"Plugin execution failed: {e}")

        finally:
            # Record execution
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            self._record_execution(
                plugin_name,
                start_time,
                duration,
                success,
                error_message
            )

    async def _execute_sandboxed(
        self,
        plugin_name: str,
        context: Dict[str, Any],
        timeout: int
    ) -> Dict[str, Any]:
        """
        Execute plugin in subprocess sandbox.

        Args:
            plugin_name: Plugin name
            context: Execution context
            timeout: Timeout in seconds

        Returns:
            Plugin result
        """
        plugin_dir = self.plugins_dir / plugin_name
        manifest = self._manifests[plugin_name]
        entry_path = plugin_dir / manifest.entry_point

        # Create sandbox script
        sandbox_script = f"""
import sys
import json
import asyncio
sys.path.insert(0, '{plugin_dir}')

from {manifest.entry_point.replace('.py', '')} import PluginClass

async def main():
    context = json.loads(sys.stdin.read())
    manifest_data = {repr(manifest.__dict__)}

    # Mock manifest
    class MockManifest:
        def __init__(self, data):
            for k, v in data.items():
                setattr(self, k, v)

    plugin = PluginClass(MockManifest(manifest_data))
    result = await plugin.execute(context)
    print(json.dumps(result))

if __name__ == '__main__':
    asyncio.run(main())
"""

        try:
            # Run in subprocess
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                sandbox_script,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(json.dumps(context).encode()),
                timeout=timeout
            )

            if proc.returncode != 0:
                raise RuntimeError(
                    f"Sandbox execution failed: {stderr.decode()}"
                )

            return json.loads(stdout.decode())

        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"Plugin execution timed out after {timeout}s")

    def _record_execution(
        self,
        plugin_name: str,
        executed_at: datetime,
        duration_ms: float,
        success: bool,
        error_message: Optional[str]
    ):
        """Record plugin execution."""
        manifest = self._manifests.get(plugin_name)
        if not manifest:
            return

        plugin_id = f"{manifest.name}_{manifest.version}"

        with sqlite3.connect(self.db_path) as conn:
            # Update plugin stats
            conn.execute(
                """
                UPDATE plugins
                SET execution_count = execution_count + 1,
                    last_execution = ?
                WHERE plugin_id = ?
                """,
                (executed_at.isoformat(), plugin_id)
            )

            # Record execution
            conn.execute(
                """
                INSERT INTO plugin_executions
                (plugin_id, executed_at, duration_ms, success, error_message)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    plugin_id,
                    executed_at.isoformat(),
                    duration_ms,
                    1 if success else 0,
                    error_message
                )
            )

    def get_plugin_stats(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """Get plugin statistics."""
        manifest = self._manifests.get(plugin_name)
        if not manifest:
            return None

        plugin_id = f"{manifest.name}_{manifest.version}"

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT execution_count, last_execution
                FROM plugins
                WHERE plugin_id = ?
                """,
                (plugin_id,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            cursor = conn.execute(
                """
                SELECT
                    AVG(duration_ms) as avg_duration,
                    SUM(success) as success_count,
                    COUNT(*) - SUM(success) as failure_count
                FROM plugin_executions
                WHERE plugin_id = ?
                """,
                (plugin_id,)
            )
            stats_row = cursor.fetchone()

            return {
                "plugin_name": plugin_name,
                "version": manifest.version,
                "execution_count": row[0],
                "last_execution": row[1],
                "avg_duration_ms": stats_row[0] or 0,
                "success_count": stats_row[1] or 0,
                "failure_count": stats_row[2] or 0
            }

    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all registered plugins."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT plugin_id, name, version, author,
                       installed_at, is_enabled, execution_count
                FROM plugins
                ORDER BY name
                """
            )

            plugins = []
            for row in cursor.fetchall():
                plugins.append({
                    "plugin_id": row[0],
                    "name": row[1],
                    "version": row[2],
                    "author": row[3],
                    "installed_at": row[4],
                    "is_enabled": bool(row[5]),
                    "execution_count": row[6],
                    "is_loaded": row[1] in self._plugins
                })

            return plugins
