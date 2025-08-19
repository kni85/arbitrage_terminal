"""remove_unique_constraints_for_nullable_fields

Revision ID: 4a5f58001d1f
Revises: b72ed1f9fbda
Create Date: 2025-08-19 15:52:16.521748

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a5f58001d1f'
down_revision: Union[str, None] = 'b72ed1f9fbda'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove UNIQUE constraints from nullable fields to allow multiple NULL values."""
    # For SQLite, recreate tables without UNIQUE constraints
    
    # Assets table
    with op.batch_alter_table('assets_table', recreate='always') as batch_op:
        batch_op.alter_column('code', existing_type=sa.VARCHAR(32), nullable=True, unique=False)
    
    # Accounts table  
    with op.batch_alter_table('accounts_table', recreate='always') as batch_op:
        batch_op.alter_column('alias', existing_type=sa.VARCHAR(64), nullable=True, unique=False)


def downgrade() -> None:
    """Restore UNIQUE constraints."""
    with op.batch_alter_table('assets_table', recreate='always') as batch_op:
        batch_op.alter_column('code', existing_type=sa.VARCHAR(32), nullable=True, unique=True)
    
    with op.batch_alter_table('accounts_table', recreate='always') as batch_op:
        batch_op.alter_column('alias', existing_type=sa.VARCHAR(64), nullable=True, unique=True)
