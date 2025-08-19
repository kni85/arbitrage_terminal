"""recreate_tables_without_unique

Revision ID: 3d0ee301447e
Revises: 4a5f58001d1f
Create Date: 2025-08-19 15:59:42.327945

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3d0ee301447e'
down_revision: Union[str, None] = '4a5f58001d1f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Recreate tables without UNIQUE constraints."""
    # Drop and recreate assets_table without UNIQUE(code)
    op.drop_table('assets_table')
    op.create_table('assets_table',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.VARCHAR(length=32), nullable=True),
        sa.Column('name', sa.VARCHAR(length=128), nullable=True),
        sa.Column('class_code', sa.VARCHAR(length=16), nullable=True),
        sa.Column('sec_code', sa.VARCHAR(length=32), nullable=True),
        sa.Column('price_step', sa.NUMERIC(precision=18, scale=6), nullable=True),
        sa.Column('updated_at', sa.DATETIME(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Drop and recreate accounts_table without UNIQUE(alias)
    op.drop_table('accounts_table')
    op.create_table('accounts_table',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('alias', sa.VARCHAR(length=64), nullable=True),
        sa.Column('account_number', sa.VARCHAR(length=32), nullable=True),
        sa.Column('client_code', sa.VARCHAR(length=32), nullable=True),
        sa.Column('updated_at', sa.DATETIME(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Restore tables with UNIQUE constraints."""
    # Drop and recreate assets_table with UNIQUE(code)
    op.drop_table('assets_table')
    op.create_table('assets_table',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.VARCHAR(length=32), nullable=True),
        sa.Column('name', sa.VARCHAR(length=128), nullable=True),
        sa.Column('class_code', sa.VARCHAR(length=16), nullable=True),
        sa.Column('sec_code', sa.VARCHAR(length=32), nullable=True),
        sa.Column('price_step', sa.NUMERIC(precision=18, scale=6), nullable=True),
        sa.Column('updated_at', sa.DATETIME(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )
    
    # Drop and recreate accounts_table with UNIQUE(alias)
    op.drop_table('accounts_table')
    op.create_table('accounts_table',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('alias', sa.VARCHAR(length=64), nullable=True),
        sa.Column('account_number', sa.VARCHAR(length=32), nullable=True),
        sa.Column('client_code', sa.VARCHAR(length=32), nullable=True),
        sa.Column('updated_at', sa.DATETIME(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('alias')
    )
