"""
Скрипт для диагностики расхождений в exec_price (P&L).
Проверяет расчеты для всех пар и ордеров.

Формула: P&L = SUM(SHORT_price * SHORT_qty) - SUM(LONG_price * LONG_qty)
"""
import asyncio
from sqlalchemy import select
from db.database import AsyncSessionLocal
from db.models import Order, Pair, Side

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
            print(f"   БД: exec_price(P&L)={float(pair.exec_price):.2f}, exec_qty={pair.exec_qty}")
            
            # Получаем все ордера этой пары
            stmt_orders = select(Order).where(
                Order.pair_id == pair.id,
                Order.filled > 0
            )
            result_orders = await session.execute(stmt_orders)
            orders = result_orders.scalars().all()
            
            print(f"   Ордеров в паре: {len(orders)}")
            
            # Считаем P&L вручную
            short_value = 0.0
            long_value = 0.0
            
            for i, ord in enumerate(orders, 1):
                print(f"\n   Ордер #{i} (ID={ord.id}):")
                print(f"      filled={ord.filled}, exec_price={ord.exec_price}")
                print(f"      status={ord.status}, side={ord.side}")
                
                if ord.exec_price and ord.filled:
                    exec_price_float = float(ord.exec_price)
                    value = exec_price_float * ord.filled
                    
                    if ord.side == Side.SHORT:
                        short_value += value
                        print(f"      ✓ SHORT: +{value:.2f}")
                    else:
                        long_value += value
                        print(f"      ✓ LONG:  -{value:.2f}")
                else:
                    print(f"      ⚠️  НЕ учтен (exec_price или filled пустые!)")
            
            if short_value > 0 or long_value > 0:
                manual_pnl = short_value - long_value
                db_pnl = float(pair.exec_price or 0)
                diff = abs(manual_pnl - db_pnl)
                
                print(f"\n   {'─'*60}")
                print(f"   📈 Расчет P&L вручную:")
                print(f"      SHORT (продажи) = +{short_value:.2f}")
                print(f"      LONG  (покупки) = -{long_value:.2f}")
                print(f"      P&L = {short_value:.2f} - {long_value:.2f} = {manual_pnl:.2f}")
                print(f"\n   БД:             {db_pnl:.2f}")
                print(f"   Расчет вручную: {manual_pnl:.2f}")
                print(f"   Разница:        {diff:.2f}")
                
                if diff > 0.01:  # Погрешность округления
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
