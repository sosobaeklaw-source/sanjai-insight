"""
Multi-tenancy Manager with DB schema isolation and RBAC.

Features:
- Tenant-specific database schemas
- Role-Based Access Control (RBAC)
- API key management per tenant
- Tenant lifecycle management
"""

import os
import secrets
import hashlib
import sqlite3
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class Role(Enum):
    """User roles for RBAC."""
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class Permission(Enum):
    """Granular permissions."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    MANAGE_USERS = "manage_users"
    MANAGE_API_KEYS = "manage_api_keys"
    MANAGE_BILLING = "manage_billing"


@dataclass
class TenantPermission:
    """Permission mapping for roles."""
    role: Role
    permissions: Set[Permission]

    @classmethod
    def get_role_permissions(cls, role: Role) -> Set[Permission]:
        """Get permissions for a role."""
        role_map = {
            Role.OWNER: {
                Permission.READ, Permission.WRITE, Permission.DELETE,
                Permission.MANAGE_USERS, Permission.MANAGE_API_KEYS,
                Permission.MANAGE_BILLING
            },
            Role.ADMIN: {
                Permission.READ, Permission.WRITE, Permission.DELETE,
                Permission.MANAGE_USERS, Permission.MANAGE_API_KEYS
            },
            Role.EDITOR: {
                Permission.READ, Permission.WRITE
            },
            Role.VIEWER: {
                Permission.READ
            }
        }
        return role_map.get(role, set())


@dataclass
class APIKey:
    """API key for tenant authentication."""
    key: str
    tenant_id: str
    name: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    is_active: bool = True
    last_used: Optional[datetime] = None
    usage_count: int = 0


@dataclass
class User:
    """User within a tenant."""
    user_id: str
    tenant_id: str
    email: str
    role: Role
    created_at: datetime
    is_active: bool = True


@dataclass
class Tenant:
    """Tenant entity."""
    tenant_id: str
    name: str
    schema_name: str
    created_at: datetime
    owner_email: str
    is_active: bool = True
    max_users: int = 10
    max_api_keys: int = 5
    metadata: Dict = field(default_factory=dict)


class TenantManager:
    """
    Manages multi-tenancy with schema isolation and RBAC.

    Features:
    - Schema-per-tenant isolation
    - API key generation and validation
    - User and permission management
    - Tenant quota enforcement
    """

    def __init__(self, db_path: str = "data/tenants.db"):
        """Initialize tenant manager."""
        self.db_path = db_path
        self._ensure_db()
        self._tenants_cache: Dict[str, Tenant] = {}
        self._api_keys_cache: Dict[str, APIKey] = {}

    def _ensure_db(self):
        """Create tenant management database."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tenants (
                    tenant_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    schema_name TEXT UNIQUE NOT NULL,
                    owner_email TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    max_users INTEGER DEFAULT 10,
                    max_api_keys INTEGER DEFAULT 5,
                    metadata TEXT DEFAULT '{}'
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    email TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id),
                    UNIQUE(tenant_id, email)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    key_hash TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    is_active INTEGER DEFAULT 1,
                    last_used TEXT,
                    usage_count INTEGER DEFAULT 0,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_tenant
                ON users(tenant_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_keys_tenant
                ON api_keys(tenant_id)
            """)

    def create_tenant(
        self,
        name: str,
        owner_email: str,
        max_users: int = 10,
        max_api_keys: int = 5
    ) -> Tenant:
        """
        Create a new tenant with isolated schema.

        Args:
            name: Tenant name
            owner_email: Owner email
            max_users: Maximum users allowed
            max_api_keys: Maximum API keys allowed

        Returns:
            Created tenant
        """
        tenant_id = f"tenant_{secrets.token_hex(8)}"
        schema_name = f"schema_{tenant_id}"

        tenant = Tenant(
            tenant_id=tenant_id,
            name=name,
            schema_name=schema_name,
            owner_email=owner_email,
            created_at=datetime.utcnow(),
            max_users=max_users,
            max_api_keys=max_api_keys
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO tenants
                (tenant_id, name, schema_name, owner_email, created_at,
                 max_users, max_api_keys)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant.tenant_id,
                    tenant.name,
                    tenant.schema_name,
                    tenant.owner_email,
                    tenant.created_at.isoformat(),
                    tenant.max_users,
                    tenant.max_api_keys
                )
            )

        # Create owner user
        owner_id = f"user_{secrets.token_hex(8)}"
        self._create_user(
            user_id=owner_id,
            tenant_id=tenant_id,
            email=owner_email,
            role=Role.OWNER
        )

        # Initialize tenant schema
        self._initialize_tenant_schema(schema_name)

        self._tenants_cache[tenant_id] = tenant
        logger.info(f"Created tenant {tenant_id}: {name}")

        return tenant

    def _initialize_tenant_schema(self, schema_name: str):
        """Initialize isolated database schema for tenant."""
        schema_db_path = f"data/{schema_name}.db"

        with sqlite3.connect(schema_db_path) as conn:
            # Create tenant-specific tables
            conn.execute("""
                CREATE TABLE IF NOT EXISTS insights (
                    insight_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    category TEXT,
                    metadata TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS crawl_results (
                    result_id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    content TEXT,
                    crawled_at TEXT NOT NULL,
                    status TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS proposals (
                    proposal_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT DEFAULT 'draft'
                )
            """)

    def _create_user(
        self,
        user_id: str,
        tenant_id: str,
        email: str,
        role: Role
    ) -> User:
        """Create user in tenant."""
        user = User(
            user_id=user_id,
            tenant_id=tenant_id,
            email=email,
            role=role,
            created_at=datetime.utcnow()
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO users
                (user_id, tenant_id, email, role, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user.user_id,
                    user.tenant_id,
                    user.email,
                    user.role.value,
                    user.created_at.isoformat()
                )
            )

        return user

    def add_user(
        self,
        tenant_id: str,
        email: str,
        role: Role,
        requester_user_id: str
    ) -> User:
        """
        Add user to tenant (requires MANAGE_USERS permission).

        Args:
            tenant_id: Target tenant
            email: User email
            role: User role
            requester_user_id: User making the request

        Returns:
            Created user

        Raises:
            PermissionError: If requester lacks permission
            ValueError: If tenant quota exceeded
        """
        # Check permission
        if not self.check_permission(
            requester_user_id,
            Permission.MANAGE_USERS
        ):
            raise PermissionError("Insufficient permissions")

        # Check quota
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT max_users FROM tenants WHERE tenant_id = ?",
                (tenant_id,)
            )
            max_users = cursor.fetchone()[0]

            cursor = conn.execute(
                "SELECT COUNT(*) FROM users WHERE tenant_id = ? AND is_active = 1",
                (tenant_id,)
            )
            current_count = cursor.fetchone()[0]

            if current_count >= max_users:
                raise ValueError(f"Tenant user limit reached ({max_users})")

        user_id = f"user_{secrets.token_hex(8)}"
        return self._create_user(user_id, tenant_id, email, role)

    def generate_api_key(
        self,
        tenant_id: str,
        name: str,
        requester_user_id: str,
        expires_days: Optional[int] = None
    ) -> str:
        """
        Generate API key for tenant.

        Args:
            tenant_id: Target tenant
            name: Key name/description
            requester_user_id: User making request
            expires_days: Days until expiration (None = no expiry)

        Returns:
            API key (only time it's shown)

        Raises:
            PermissionError: If requester lacks permission
            ValueError: If quota exceeded
        """
        # Check permission
        if not self.check_permission(
            requester_user_id,
            Permission.MANAGE_API_KEYS
        ):
            raise PermissionError("Insufficient permissions")

        # Check quota
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT max_api_keys FROM tenants WHERE tenant_id = ?",
                (tenant_id,)
            )
            max_keys = cursor.fetchone()[0]

            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM api_keys
                WHERE tenant_id = ? AND is_active = 1
                """,
                (tenant_id,)
            )
            current_count = cursor.fetchone()[0]

            if current_count >= max_keys:
                raise ValueError(f"API key limit reached ({max_keys})")

        # Generate key
        api_key = f"sk_{tenant_id}_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        created_at = datetime.utcnow()
        expires_at = None
        if expires_days:
            expires_at = created_at + timedelta(days=expires_days)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO api_keys
                (key_hash, tenant_id, name, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    key_hash,
                    tenant_id,
                    name,
                    created_at.isoformat(),
                    expires_at.isoformat() if expires_at else None
                )
            )

        logger.info(f"Generated API key '{name}' for tenant {tenant_id}")
        return api_key

    def validate_api_key(self, api_key: str) -> Optional[str]:
        """
        Validate API key and return tenant_id.

        Args:
            api_key: API key to validate

        Returns:
            tenant_id if valid, None otherwise
        """
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT tenant_id, expires_at, is_active
                FROM api_keys
                WHERE key_hash = ?
                """,
                (key_hash,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            tenant_id, expires_at_str, is_active = row

            if not is_active:
                return None

            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str)
                if datetime.utcnow() > expires_at:
                    return None

            # Update usage stats
            conn.execute(
                """
                UPDATE api_keys
                SET last_used = ?, usage_count = usage_count + 1
                WHERE key_hash = ?
                """,
                (datetime.utcnow().isoformat(), key_hash)
            )

        return tenant_id

    def check_permission(
        self,
        user_id: str,
        permission: Permission
    ) -> bool:
        """
        Check if user has permission.

        Args:
            user_id: User to check
            permission: Required permission

        Returns:
            True if permitted
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT role FROM users WHERE user_id = ? AND is_active = 1",
                (user_id,)
            )
            row = cursor.fetchone()

            if not row:
                return False

            role = Role(row[0])
            permissions = TenantPermission.get_role_permissions(role)
            return permission in permissions

    def get_tenant_schema(self, tenant_id: str) -> str:
        """Get database path for tenant schema."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")
        return f"data/{tenant.schema_name}.db"

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Get tenant by ID."""
        if tenant_id in self._tenants_cache:
            return self._tenants_cache[tenant_id]

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT tenant_id, name, schema_name, owner_email,
                       created_at, is_active, max_users, max_api_keys
                FROM tenants
                WHERE tenant_id = ?
                """,
                (tenant_id,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            tenant = Tenant(
                tenant_id=row[0],
                name=row[1],
                schema_name=row[2],
                owner_email=row[3],
                created_at=datetime.fromisoformat(row[4]),
                is_active=bool(row[5]),
                max_users=row[6],
                max_api_keys=row[7]
            )

            self._tenants_cache[tenant_id] = tenant
            return tenant

    def delete_tenant(
        self,
        tenant_id: str,
        requester_user_id: str
    ):
        """
        Soft-delete tenant (requires OWNER role).

        Args:
            tenant_id: Tenant to delete
            requester_user_id: User making request

        Raises:
            PermissionError: If not owner
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT role FROM users WHERE user_id = ? AND tenant_id = ?",
                (requester_user_id, tenant_id)
            )
            row = cursor.fetchone()

            if not row or Role(row[0]) != Role.OWNER:
                raise PermissionError("Only tenant owner can delete tenant")

            conn.execute(
                "UPDATE tenants SET is_active = 0 WHERE tenant_id = ?",
                (tenant_id,)
            )

            conn.execute(
                "UPDATE users SET is_active = 0 WHERE tenant_id = ?",
                (tenant_id,)
            )

            conn.execute(
                "UPDATE api_keys SET is_active = 0 WHERE tenant_id = ?",
                (tenant_id,)
            )

        if tenant_id in self._tenants_cache:
            del self._tenants_cache[tenant_id]

        logger.info(f"Deleted tenant {tenant_id}")

    def list_tenant_users(self, tenant_id: str) -> List[User]:
        """List all users in tenant."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT user_id, tenant_id, email, role, created_at, is_active
                FROM users
                WHERE tenant_id = ?
                ORDER BY created_at
                """,
                (tenant_id,)
            )

            users = []
            for row in cursor.fetchall():
                users.append(User(
                    user_id=row[0],
                    tenant_id=row[1],
                    email=row[2],
                    role=Role(row[3]),
                    created_at=datetime.fromisoformat(row[4]),
                    is_active=bool(row[5])
                ))

            return users
