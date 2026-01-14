"""
Вручную пересчитываем exec_price (P&L) для всех пар на основе реальных сделок

Формула: P&L = SUM(SHORT_price * SHORT_qty) - SUM(LONG_price * LONG_qty)
"""
import asyncio
from sqlalchemy import select
from db.database import AsyncSessionLocal
from db.models import Order, Pair, Side

async def update_all_pairs():
    async with AsyncSessionLocal() as session:
        # Получаем все пары
        stmt_pairs = select(Pair)
        result = await session.execute(stmt_pairs)
        pairs = result.scalars().all()
        
        print(f"Найдено пар: {len(pairs)}\n")
        
        for pair in pairs:
            # Получаем ордера этой пары
            stmt_orders = select(Order).where(
                Order.pair_id == pair.id,
                Order.filled > 0,
                Order.exec_price.isnot(None)
            )
            result_orders = await session.execute(stmt_orders)
            orders = result_orders.scalars().all()
            
            if not orders:
                print(f"Пара ID={pair.id} ({pair.asset_1}/{pair.asset_2}): нет исполненных ордеров")
                continue
            
            # Считаем P&L: SHORT - LONG
            short_value = 0.0
            long_value = 0.0
            
            print(f"Пара ID={pair.id} ({pair.asset_1}/{pair.asset_2}):")
            for ord in orders:
                if ord.exec_price and ord.filled:
                    value = float(ord.exec_price) * ord.filled
                    if ord.side == Side.SHORT:
                        short_value += value
                        print(f"  Order {ord.id}: SHORT {ord.filled} @ {ord.exec_price} = +{value:.2f}")
                    else:
                        long_value += value
                        print(f"  Order {ord.id}: LONG  {ord.filled} @ {ord.exec_price} = -{value:.2f}")
            
            pnl = short_value - long_value
            
            # exec_qty = количество SHORT ордеров
            short_orders = [o for o in orders if o.side == Side.SHORT and o.filled > 0]
            exec_qty = sum(o.filled for o in short_orders)
            
            # Обновляем
            pair.exec_qty = exec_qty
            pair.exec_price = pnl
            
            print(f"  ✓ P&L = {short_value:.2f} - {long_value:.2f} = {pnl:.2f}")
            print(f"  ✓ exec_qty={exec_qty}, exec_price(P&L)={pnl:.2f}\n")
        
        await session.commit()
        print("Готово!")

if __name__ == "__main__":
    asyncio.run(update_all_pairs())
