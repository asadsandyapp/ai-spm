"""Legacy revision placeholder — applied on older dev DBs via Docker patches.

The database may already be stamped at ``002_saas_plans_entitlements`` while
schema objects came from an earlier in-container migration. This no-op keeps
Alembic history resolvable so ``002_commercial_saas_plans`` can run next.
"""

from collections.abc import Sequence

revision: str = "002_saas_plans_entitlements"
down_revision: str | None = "001_initial_saas_multitenant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
