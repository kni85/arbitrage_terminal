"""
Скрипт для диагностики расхождений в exec_price.
Проверяет расчеты для всех пар и ордеров.
"""
import asyncio
from sqlalchemy import select
from db.database import AsyncSessionLocal
from db.models import Order, Pair

async def check_exec_price():
    async with AsyncSessionLocal() as session:
        # Получаем все пары с exec_price
        stmt_pairs = select(Pair).where(Pair.exec_price.isnot(None))
        result = await session.execute(stmt_pairs)
        pairs = result.scalars().all()
        
        print(f"\n{'='*80}")
        print(f"Найдено пар с exec_price: {len(pairs)}")
        print(f"{'='*80}\n")
        
        for pair in pairs:
            print(f"\n📊 Пара ID={pair.id}: {pair.asset_1}/{pair.asset_2}")
            print(f"   БД: exec_price={pair.exec_price:.6f}, exec_qty={pair.exec_qty}")
            
            # Получаем все ордера этой пары
            stmt_orders = select(Order).where(
                Order.pair_id == pair.id,
                Order.filled > 0
            )
            result_orders = await session.execute(stmt_orders)
            orders = result_orders.scalars().all()
            
            print(f"   Ордеров в паре: {len(orders)}")
            
            # Считаем вручную
            total_filled = 0
            total_cost = 0.0
            
            for i, ord in enumerate(orders, 1):
                print(f"\n   Ордер #{i} (ID={ord.id}):")
                print(f"      filled={ord.filled}, exec_price={ord.exec_price}")
                print(f"      status={ord.status}, side={ord.side}")
                
                if ord.exec_price and ord.filled:
                    total_filled += ord.filled
                    total_cost += ord.exec_price * ord.filled
                    print(f"      ✓ Учтен: вклад={ord.exec_price * ord.filled:.6f}")
                else:
                    print(f"      ⚠️  НЕ учтен (exec_price или filled пустые!)")
            
            if total_filled > 0:
                manual_avg = total_cost / total_filled
                diff = abs(manual_avg - (pair.exec_price or 0))
                
                print(f"\n   {'─'*60}")
                print(f"   📈 Расчет вручную:")
                print(f"      total_filled = {total_filled}")
                print(f"      total_cost   = {total_cost:.6f}")
                print(f"      avg_price    = {manual_avg:.6f}")
                print(f"\n   БД:             {pair.exec_price:.6f}")
                print(f"   Расчет вручную: {manual_avg:.6f}")
                print(f"   Разница:        {diff:.6f}")
                
                if diff > 0.000001:  # Погрешность округления
                    print(f"   ❌ РАСХОЖДЕНИЕ!")
                else:
                    print(f"   ✅ Совпадает")
            else:
                print(f"\n   ⚠️  Нет исполненных ордеров для расчета")
        
        print(f"\n{'='*80}\n")
        
        # Проверяем ордера без pair_id
        stmt_orphan = select(Order).where(
            Order.pair_id.is_(None),
            Order.filled > 0
        )
        result_orphan = await session.execute(stmt_orphan)
        orphan_orders = result_orphan.scalars().all()
        
        if orphan_orders:
            print(f"⚠️  ВНИМАНИЕ: Найдено {len(orphan_orders)} ордеров без привязки к паре:")
            for ord in orphan_orders:
                print(f"   Order ID={ord.id}: filled={ord.filled}, exec_price={ord.exec_price}, status={ord.status}")
            print()

if __name__ == "__main__":
    asyncio.run(check_exec_price())
