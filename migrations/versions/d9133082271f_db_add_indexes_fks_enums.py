"""db: add indexes, fks, enums

Revision ID: d9133082271f
Revises: 0001_init          # ← замените на ID вашей предыдущей ревизии
Create Date: 2024-05-01 12:34:56
"""

from alembic import op
import sqlalchemy as sa

# ————————————————————————————————————————————————————————————————
revision: str = "d9133082271f"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None
# ————————————————————————————————————————————————————————————————


# ─────────────────────────  UPGRADE  ──────────────────────────
def upgrade() -> None:
    # ---------- instruments ----------
    with op.batch_alter_table("instruments") as batch:
        # обычный ALTER TABLE ADD CONSTRAINT → SQLite-friendly
        batch.create_unique_constraint(
            "uq_instruments_ticker",
            ["ticker"],
        )

    # ---------- quotes ----------
    # индекс можно создать напрямую (SQLite это умеет)
    op.create_index(
        "ix_quotes_instrument_ts",
        "quotes",
        ["instrument_id", "timestamp"],
    )
    # FK — тоже через batch
    with op.batch_alter_table("quotes") as batch:
        batch.create_foreign_key(
            "fk_quotes_instrument",
            "instruments",
            ["instrument_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # ---------- orders ----------
    op.create_index("ix_orders_created_at", "orders", ["created_at"])
    with op.batch_alter_table("orders") as batch:
        batch.create_foreign_key(
            "fk_orders_instrument",
            "instruments",
            ["instrument_id"],
            ["id"],
        )

    # ---------- trades ----------
    op.create_index("ix_trades_timestamp", "trades", ["timestamp"])
    with op.batch_alter_table("trades") as batch:
        batch.create_foreign_key(
            "fk_trades_order",
            "orders",
            ["order_id"],
            ["id"],
        )

    # ---------- portfolio_positions ----------
    with op.batch_alter_table("portfolio_positions") as batch:
        batch.create_foreign_key(
            "fk_portfolio_positions_portfolio",
            "portfolio_configs",
            ["portfolio_id"],
            ["id"],
            ondelete="CASCADE",
        )


# ─────────────────────────  DOWNGRADE  ─────────────────────────
def downgrade() -> None:
    # порядок обратный upgrade-у
    with op.batch_alter_table("portfolio_positions") as batch:
        batch.drop_constraint("fk_portfolio_positions_portfolio", type_="foreignkey")

    with op.batch_alter_table("trades") as batch:
        batch.drop_constraint("fk_trades_order", type_="foreignkey")
    op.drop_index("ix_trades_timestamp", table_name="trades")

    with op.batch_alter_table("orders") as batch:
        batch.drop_constraint("fk_orders_instrument", type_="foreignkey")
    op.drop_index("ix_orders_created_at", table_name="orders")

    with op.batch_alter_table("quotes") as batch:
        batch.drop_constraint("fk_quotes_instrument", type_="foreignkey")
    op.drop_index("ix_quotes_instrument_ts", table_name="quotes")

    with op.batch_alter_table("instruments") as batch:
        batch.drop_constraint("uq_instruments_ticker", type_="unique")
