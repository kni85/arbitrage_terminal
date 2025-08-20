"""change_pairs_column_width_to_float

Revision ID: 1d67ad887c0d
Revises: 1002f0ae27b1
Create Date: 2025-08-20 16:57:19.671715

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1d67ad887c0d'
down_revision: Union[str, None] = '1002f0ae27b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # SQLite doesn't support ALTER COLUMN type directly, so we recreate the table
    
    # Create new table with correct schema
    op.create_table('pairs_columns_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=32), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('width', sa.Float(), nullable=True),  # Changed from Integer to Float
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    
    # Copy data from old table to new table
    op.execute('INSERT INTO pairs_columns_new (id, name, position, width, updated_at) SELECT id, name, position, CAST(width AS REAL), updated_at FROM pairs_columns')
    
    # Drop old table
    op.drop_table('pairs_columns')
    
    # Rename new table to original name
    op.execute('ALTER TABLE pairs_columns_new RENAME TO pairs_columns')


def downgrade() -> None:
    """Downgrade schema."""
    # Recreate table with Integer width (reverse operation)
    op.create_table('pairs_columns_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=32), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('width', sa.Integer(), nullable=True),  # Back to Integer
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    
    op.execute('INSERT INTO pairs_columns_new (id, name, position, width, updated_at) SELECT id, name, position, CAST(width AS INTEGER), updated_at FROM pairs_columns')
    op.drop_table('pairs_columns')
    op.execute('ALTER TABLE pairs_columns_new RENAME TO pairs_columns')
