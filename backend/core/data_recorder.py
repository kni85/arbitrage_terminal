"""
`core.data_recorder` – сервис фоновой записи котировок (bid/ask) в базу.

* Подписывается на стакан L2 по выбранным инструментам через `QuikConnector`.
* Раз в `period` секунд сохраняет последнюю котировку каждого инструмента в
  таблицу `Quote` (см. `db.models`).
* Может работать в несколько экземпляров – ключ подписки формируется из пары
  `class_code.sec_code`.

Использование из приложения FastAPI (в `backend.main` или другом месте):

```python
recorder = DataRecorder([("TQBR", "SBER"), ("SPBFUT", "SiM5")])
app.state.data_recorder = recorder
await recorder.start()
...
await recorder.stop()
```
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from core.quik_connector import QuikConnector
from db.database import AsyncSessionLocal
from db.models import Quote

logger = logging.getLogger(__name__)

InstrumentKey = Tuple[str, str]  # (class_code, sec_code)


class DataRecorder:
    """Фоновый сервис записи котировок."""

    def __init__(self, instruments: List[InstrumentKey], period: float = 1.0):
        self.instruments = instruments
        self.period = period
        self._connector = QuikConnector()
        self._running = False
        self._task: asyncio.Task | None = None
        # Храним последнюю котировку для каждой ноги
        self._latest: Dict[InstrumentKey, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True

        # Подписываемся на котировки
        for class_code, sec_code in self.instruments:
            self._connector.subscribe_quotes(class_code, sec_code, self._update_quote)

        # Запускаем фоновую задачу
        self._task = asyncio.create_task(self._loop(), name="data_recorder")
        logger.info("DataRecorder started (%d instruments)", len(self.instruments))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            await self._task
        for class_code, sec_code in self.instruments:
            self._connector.unsubscribe_quotes(class_code, sec_code, self._update_quote)
        logger.info("DataRecorder stopped")

    # ------------------------------------------------------------------
    # Callback от QuikConnector (может быть sync)
    # ------------------------------------------------------------------

    def _update_quote(self, data: Dict[str, Any]) -> None:  # noqa: D401
        key: InstrumentKey = (data["class_code"], data["sec_code"])
        self._latest[key] = data

    # ------------------------------------------------------------------
    # Основной цикл: раз в `period` сек пишет в базу
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.period)
            await self._flush_to_db()

    async def _flush_to_db(self) -> None:
        if not self._latest:
            return
        async with AsyncSessionLocal() as session:
            for (class_code, sec_code), q in list(self._latest.items()):
                quote = Quote(
                    timestamp=datetime.utcfromtimestamp(q["time"]).replace(tzinfo=timezone.utc),
                    instrument=f"{class_code}.{sec_code}",
                    bid=q["bid"],
                    ask=q["ask"],
                )
                session.add(quote)
            try:
                await session.commit()
            except Exception as exc:  # pragma: no cover
                await session.rollback()
                logger.exception("DB commit failed: %s", exc)


# ---------------------------------------------------------------------------
# Демонстрация работы DataRecorder с DummyQuikPy
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def _demo() -> None:
        # Создаём in-memory SQLite; перезаписываем фабрику сессий на лету
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from db.database import Base

        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
        global AsyncSessionLocal  # noqa: PLW0603 – переопределяем для демо
        AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        rec = DataRecorder([("TQBR", "SBER")], period=1)
        await rec.start()
        # Даём поработать 3 секунды
        await asyncio.sleep(3.2)
        await rec.stop()

        # Смотрим записанные котировки
        from sqlalchemy import select

        async with AsyncSessionLocal() as ses:
            rows = (await ses.execute(select(Quote))).scalars().all()
            print("\nQuotes saved:")
            for row in rows:
                print(row)

        await engine.dispose()

    asyncio.run(_demo())
    sys.exit(0)
