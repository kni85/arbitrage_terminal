"""add_broker_field_to_accounts

Revision ID: 1002f0ae27b1
Revises: 3d0ee301447e
Create Date: 2025-08-20 16:16:17.642621

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1002f0ae27b1'
down_revision: Union[str, None] = '3d0ee301447e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add broker column to accounts_table
    op.add_column('accounts_table', sa.Column('broker', sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove broker column from accounts_table
    op.drop_column('accounts_table', 'broker')
