"""0001 init schema

Revision ID: 9c8437210af5
Revises: 
Create Date: 2025-04-29 18:29:49.023863

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = '9c8437210af5'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('instruments',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('ticker', sa.String(length=32), nullable=False),
    sa.Column('board', sa.String(length=16), nullable=False),
    sa.Column('lot_size', sa.Integer(), nullable=False),
    sa.Column('price_precision', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('ticker')
    )
    op.create_table('portfolio_configs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('pid', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('config_json', sqlite.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('pid', name='uq_portfolio_pid')
    )
    op.create_index('ix_portfolio_active', 'portfolio_configs', ['active'], unique=False)
    op.create_table('orders',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('quik_num', sa.Integer(), nullable=True),
    sa.Column('portfolio_id', sa.Integer(), nullable=False),
    sa.Column('instrument_id', sa.Integer(), nullable=False),
    sa.Column('side', sa.Enum('LONG', 'SHORT', name='side'), nullable=False),
    sa.Column('price', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('qty', sa.Integer(), nullable=False),
    sa.Column('filled', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('NEW', 'ACTIVE', 'PARTIAL', 'FILLED', 'CANCELLED', 'REJECTED', name='orderstatus'), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('executed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], ),
    sa.ForeignKeyConstraint(['portfolio_id'], ['portfolio_configs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_orders_portfolio_status', 'orders', ['portfolio_id', 'status'], unique=False)
    op.create_table('portfolio_positions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('portfolio_id', sa.Integer(), nullable=False),
    sa.Column('instrument_id', sa.Integer(), nullable=False),
    sa.Column('side', sa.Enum('LONG', 'SHORT', name='side'), nullable=False),
    sa.Column('qty', sa.Integer(), nullable=False),
    sa.Column('avg_price', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], ),
    sa.ForeignKeyConstraint(['portfolio_id'], ['portfolio_configs.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('portfolio_id', 'instrument_id', name='uq_position_portfolio_instrument')
    )
    op.create_table('quotes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('instrument_id', sa.Integer(), nullable=False),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.Column('bid', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('bid_qty', sa.Integer(), nullable=False),
    sa.Column('ask', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('ask_qty', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_quotes_inst_ts', 'quotes', ['instrument_id', 'ts'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('ix_quotes_inst_ts', table_name='quotes')
    op.drop_table('quotes')
    op.drop_table('portfolio_positions')
    op.drop_index('ix_orders_portfolio_status', table_name='orders')
    op.drop_table('orders')
    op.drop_index('ix_portfolio_active', table_name='portfolio_configs')
    op.drop_table('portfolio_configs')
    op.drop_table('instruments')
    # ### end Alembic commands ###
