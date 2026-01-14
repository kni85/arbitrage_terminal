"""
Вручную пересчитываем exec_price для всех пар на основе реальных сделок
"""
import asyncio
from sqlalchemy import select
from db.database import AsyncSessionLocal
from db.models import Order, Pair

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
            
            # Считаем
            total_filled = 0
            total_cost = 0.0
            
            print(f"Пара ID={pair.id} ({pair.asset_1}/{pair.asset_2}):")
            for ord in orders:
                if ord.exec_price and ord.filled:
                    total_filled += ord.filled
                    total_cost += float(ord.exec_price) * ord.filled
                    print(f"  Order {ord.id}: exec_price={ord.exec_price}, filled={ord.filled}")
            
            if total_filled > 0:
                avg_exec_price = total_cost / total_filled
                
                # Обновляем
                pair.exec_qty = total_filled
                pair.exec_price = avg_exec_price
                
                print(f"  ✓ Обновлено: exec_qty={total_filled}, exec_price={avg_exec_price:.6f}\n")
        
        await session.commit()
        print("Готово!")

if __name__ == "__main__":
    asyncio.run(update_all_pairs())
