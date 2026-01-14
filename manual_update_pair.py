"""
Вручную пересчитываем exec_price (P&L спреда) для всех пар на основе реальных сделок

Формула: 
exec_price = SUM(price_1 * qty_1 / qty_ratio_1) * price_ratio_1
           - SUM(price_2 * qty_2 / qty_ratio_2) * price_ratio_2

Нога определяется через справочник assets_table: sec_code (ticker) -> code (alias)
"""
import asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from db.database import AsyncSessionLocal
from db.models import Order, Pair, Asset

async def update_all_pairs():
    async with AsyncSessionLocal() as session:
        # Загружаем справочник алиасов: sec_code -> code
        stmt_assets = select(Asset).where(Asset.sec_code.isnot(None), Asset.code.isnot(None))
        result_assets = await session.execute(stmt_assets)
        assets = result_assets.scalars().all()
        ticker_to_alias = {a.sec_code: a.code for a in assets}
        
        print(f"📚 Справочник алиасов: {ticker_to_alias}\n")
        
        # Получаем все пары
        stmt_pairs = select(Pair)
        result = await session.execute(stmt_pairs)
        pairs = result.scalars().all()
        
        print(f"Найдено пар: {len(pairs)}\n")
        
        for pair in pairs:
            # Получаем ордера этой пары с инструментами
            stmt_orders = select(Order).options(selectinload(Order.instrument)).where(
                Order.pair_id == pair.id,
                Order.filled > 0,
                Order.exec_price.isnot(None)
            )
            result_orders = await session.execute(stmt_orders)
            orders = result_orders.scalars().all()
            
            if not orders:
                print(f"Пара ID={pair.id} ({pair.asset_1}/{pair.asset_2}): нет исполненных ордеров")
                continue
            
            # Коэффициенты
            qty_ratio_1 = float(pair.qty_ratio_1) if pair.qty_ratio_1 else 1.0
            qty_ratio_2 = float(pair.qty_ratio_2) if pair.qty_ratio_2 else 1.0
            price_ratio_1 = float(pair.price_ratio_1) if pair.price_ratio_1 else 1.0
            price_ratio_2 = float(pair.price_ratio_2) if pair.price_ratio_2 else 1.0
            
            print(f"Пара ID={pair.id} ({pair.asset_1}/{pair.asset_2}):")
            print(f"  qty_ratio=({qty_ratio_1}, {qty_ratio_2}), price_ratio=({price_ratio_1}, {price_ratio_2})")
            
            # Считаем по формуле
            sum_1 = 0.0
            sum_2 = 0.0
            exec_qty = 0
            
            for ord in orders:
                if ord.exec_price and ord.filled:
                    ticker = ord.instrument.ticker if ord.instrument else "?"
                    alias = ticker_to_alias.get(ticker, ticker)  # Fallback на ticker
                    exec_price_float = float(ord.exec_price)
                    
                    if alias == pair.asset_1:
                        normalized = (exec_price_float * ord.filled) / qty_ratio_1
                        sum_1 += normalized
                        exec_qty += ord.filled
                        print(f"  Order {ord.id}: LEG_1 ({ticker}->{alias}) {ord.filled} @ {exec_price_float} / {qty_ratio_1} = {normalized:.2f}")
                    elif alias == pair.asset_2:
                        normalized = (exec_price_float * ord.filled) / qty_ratio_2
                        sum_2 += normalized
                        print(f"  Order {ord.id}: LEG_2 ({ticker}->{alias}) {ord.filled} @ {exec_price_float} / {qty_ratio_2} = {normalized:.2f}")
                    else:
                        print(f"  Order {ord.id}: ⚠️ alias={alias} не совпадает!")
            
            pnl = sum_1 * price_ratio_1 - sum_2 * price_ratio_2
            
            # Обновляем
            pair.exec_qty = exec_qty
            pair.exec_price = pnl
            
            print(f"  ✓ P&L = {sum_1:.2f}*{price_ratio_1} - {sum_2:.2f}*{price_ratio_2} = {pnl:.2f}")
            print(f"  ✓ exec_qty={exec_qty}, exec_price={pnl:.2f}\n")
        
        await session.commit()
        print("Готово!")

if __name__ == "__main__":
    asyncio.run(update_all_pairs())
