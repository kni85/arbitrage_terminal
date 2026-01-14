"""
Скрипт для диагностики расхождений в exec_price (P&L спреда).
Проверяет расчеты для всех пар и ордеров.

Формула: 
exec_price = SUM(price_1 * qty_1 / qty_ratio_1) * price_ratio_1
           - SUM(price_2 * qty_2 / qty_ratio_2) * price_ratio_2
"""
import asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload
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
            print(f"   БД: exec_price(P&L)={float(pair.exec_price):.2f}, exec_qty={pair.exec_qty}")
            
            # Коэффициенты
            qty_ratio_1 = float(pair.qty_ratio_1) if pair.qty_ratio_1 else 1.0
            qty_ratio_2 = float(pair.qty_ratio_2) if pair.qty_ratio_2 else 1.0
            price_ratio_1 = float(pair.price_ratio_1) if pair.price_ratio_1 else 1.0
            price_ratio_2 = float(pair.price_ratio_2) if pair.price_ratio_2 else 1.0
            print(f"   Коэффициенты: qty_ratio=({qty_ratio_1}, {qty_ratio_2}), price_ratio=({price_ratio_1}, {price_ratio_2})")
            
            # Получаем все ордера этой пары с инструментами
            stmt_orders = select(Order).options(selectinload(Order.instrument)).where(
                Order.pair_id == pair.id,
                Order.filled > 0
            )
            result_orders = await session.execute(stmt_orders)
            orders = result_orders.scalars().all()
            
            print(f"   Ордеров в паре: {len(orders)}")
            
            # Считаем по формуле
            sum_1 = 0.0
            sum_2 = 0.0
            
            for i, ord in enumerate(orders, 1):
                ticker = ord.instrument.ticker if ord.instrument else "?"
                print(f"\n   Ордер #{i} (ID={ord.id}):")
                print(f"      ticker={ticker}, filled={ord.filled}, exec_price={ord.exec_price}")
                print(f"      status={ord.status}, side={ord.side}")
                
                if ord.exec_price and ord.filled:
                    exec_price_float = float(ord.exec_price)
                    
                    if ticker == pair.asset_1:
                        normalized = (exec_price_float * ord.filled) / qty_ratio_1
                        sum_1 += normalized
                        print(f"      ✓ INSTR_1: ({exec_price_float}*{ord.filled})/{qty_ratio_1} = {normalized:.2f}")
                    elif ticker == pair.asset_2:
                        normalized = (exec_price_float * ord.filled) / qty_ratio_2
                        sum_2 += normalized
                        print(f"      ✓ INSTR_2: ({exec_price_float}*{ord.filled})/{qty_ratio_2} = {normalized:.2f}")
                    else:
                        print(f"      ⚠️  ticker не совпадает с asset_1/asset_2!")
                else:
                    print(f"      ⚠️  НЕ учтен (exec_price или filled пустые!)")
            
            if sum_1 > 0 or sum_2 > 0:
                manual_pnl = sum_1 * price_ratio_1 - sum_2 * price_ratio_2
                db_pnl = float(pair.exec_price or 0)
                diff = abs(manual_pnl - db_pnl)
                
                print(f"\n   {'─'*60}")
                print(f"   📈 Расчет P&L вручную:")
                print(f"      sum_1 (инстр.1) = {sum_1:.2f}")
                print(f"      sum_2 (инстр.2) = {sum_2:.2f}")
                print(f"      P&L = {sum_1:.2f}*{price_ratio_1} - {sum_2:.2f}*{price_ratio_2} = {manual_pnl:.2f}")
                print(f"\n   БД:             {db_pnl:.2f}")
                print(f"   Расчет вручную: {manual_pnl:.2f}")
                print(f"   Разница:        {diff:.2f}")
                
                if diff > 0.01:
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
