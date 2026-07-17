from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

TenantAuthSource = Literal["jwt", "mtls", "internal"]


@dataclass(frozen=True, slots=True)
class TenantContext:
    org_id: UUID
    auth_source: TenantAuthSource
    user_id: UUID | None = None
    agent_id: UUID | None = None
    permissions: frozenset[str] = frozenset()


_tenant_context: ContextVar[TenantContext | None] = ContextVar("tenant_context", default=None)


def get_tenant_context() -> TenantContext | None:
    return _tenant_context.get()


def require_tenant_context() -> TenantContext:
    ctx = get_tenant_context()
    if ctx is None:
        raise RuntimeError("Tenant context not set")
    return ctx


def set_tenant_context(ctx: TenantContext) -> None:
    _tenant_context.set(ctx)


def clear_tenant_context() -> None:
    _tenant_context.set(None)
