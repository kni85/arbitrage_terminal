"""add_exec_price_to_orders_and_pair_link

Revision ID: ce8b0e30fed1
Revises: 61082968c62d
Create Date: 2026-01-14 14:55:12.027669

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ce8b0e30fed1'
down_revision: Union[str, None] = '61082968c62d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add columns without foreign key constraint for SQLite compatibility
    op.add_column('orders', sa.Column('pair_id', sa.Integer(), nullable=True))
    op.add_column('orders', sa.Column('exec_price', sa.Numeric(precision=18, scale=6), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_column('exec_price')
        batch_op.drop_column('pair_id')
