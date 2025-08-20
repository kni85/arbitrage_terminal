"""create_trades_table

Revision ID: d22ea5f500de
Revises: 1d67ad887c0d
Create Date: 2025-08-20 17:57:56.536080

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd22ea5f500de'
down_revision: Union[str, None] = '1d67ad887c0d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create trades table for real trade execution logging
    op.create_table('trades',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pair_id', sa.Integer(), nullable=False),
        sa.Column('side', sa.String(length=4), nullable=False),
        sa.Column('qty', sa.Integer(), nullable=False),
        sa.Column('price', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('quik_trade_id', sa.String(length=64), nullable=True),
        sa.Column('asset_code', sa.String(length=32), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pair_id'], ['pairs_table.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for better performance
    op.create_index('ix_trades_pair_id', 'trades', ['pair_id'])
    op.create_index('ix_trades_timestamp', 'trades', ['timestamp'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes first
    op.drop_index('ix_trades_timestamp', table_name='trades')
    op.drop_index('ix_trades_pair_id', table_name='trades')
    
    # Drop trades table
    op.drop_table('trades')
