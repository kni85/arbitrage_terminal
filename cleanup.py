"""
Скрипт для очистки старых ордеров без привязки к паре.
"""
import asyncio
from sqlalchemy import text
from db.database import AsyncSessionLocal

async def cleanup():
    async with AsyncSessionLocal() as session:
        # Удаляем ордера без pair_id
        result = await session.execute(
            text("DELETE FROM orders WHERE pair_id IS NULL")
        )
        await session.commit()
        print(f"✓ Удалено старых ордеров: {result.rowcount}")

if __name__ == "__main__":
    asyncio.run(cleanup())
