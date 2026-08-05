"""Add agents.session_token_hash - closes the header-forgery gap where
/agent/v1/* endpoints (other than /register) trusted raw X-Org-ID/X-Agent-ID
headers with no secret. See tenant/middleware.py's _verify_agent_session_token.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_agent_session_token"
down_revision: str | None = "001_initial_saas_multitenant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("session_token_hash", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "session_token_hash")
