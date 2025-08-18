"""allow nulls for draft rows

Revision ID: 20250818_allow_nulls
Revises: e8dfed7a75d4
Create Date: 2025-08-18
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250818_allow_nulls'
down_revision = 'e8dfed7a75d4'
branch_labels = None
depends_on = None


def upgrade():
    # Комментарии: снимаем NOT NULL с бизнес-полей
    with op.batch_alter_table('assets_table') as b:
        b.alter_column('code', existing_type=sa.String(), nullable=True)
        b.alter_column('class_code', existing_type=sa.String(), nullable=True)
        b.alter_column('sec_code', existing_type=sa.String(), nullable=True)
    with op.batch_alter_table('accounts_table') as b:
        b.alter_column('alias', existing_type=sa.String(), nullable=True)
        b.alter_column('account_number', existing_type=sa.String(), nullable=True)
        b.alter_column('client_code', existing_type=sa.String(), nullable=True)
    with op.batch_alter_table('pairs_table') as b:
        for col in [
            'asset_1','asset_2','account_1','account_2','side_1','side_2',
            'qty_ratio_1','qty_ratio_2','price_ratio_1','price_ratio_2',
            'price','target_qty','exec_price','exec_qty','leaves_qty',
            'strategy_name','price_1','price_2','hit_price','get_mdata','started','error'
        ]:
            b.alter_column(col, nullable=True)


def downgrade():
    # ВНИМАНИЕ: откат может быть невозможен, если в БД уже есть NULL
    with op.batch_alter_table('assets_table') as b:
        b.alter_column('code', existing_type=sa.String(), nullable=False)
        b.alter_column('class_code', existing_type=sa.String(), nullable=False)
        b.alter_column('sec_code', existing_type=sa.String(), nullable=False)
    with op.batch_alter_table('accounts_table') as b:
        b.alter_column('alias', existing_type=sa.String(), nullable=False)
        b.alter_column('account_number', existing_type=sa.String(), nullable=False)
        b.alter_column('client_code', existing_type=sa.String(), nullable=False)
    with op.batch_alter_table('pairs_table') as b:
        # возвращаем NOT NULL ровно на те колонки, что были до
        for col in [
            'asset_1','asset_2','account_1','account_2','side_1','side_2',
            'qty_ratio_1','qty_ratio_2','price_ratio_1','price_ratio_2'
        ]:
            b.alter_column(col, nullable=False)


