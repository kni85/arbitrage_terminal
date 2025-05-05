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

from .quik_connector import QuikConnector
from ..db.database import AsyncSessionLocal
from ..db.models import Quote, Trade, Instrument, PortfolioConfig

logger = logging.getLogger(__name__)

InstrumentKey = Tuple[str, str]  # (class_code, sec_code)


class DataRecorder:
    """Фоновый сервис записи котировок и сделок."""

    def __init__(self, instruments: List[InstrumentKey], period: float = 1.0):
        self.instruments = instruments
        self.period = period
        self._connector = QuikConnector()
        self._running = False
        self._task: asyncio.Task | None = None
        # Храним последнюю котировку для каждой ноги
        self._latest: Dict[InstrumentKey, Dict[str, Any]] = {}
        # Буфер новых сделок
        self._trades: list[Dict[str, Any]] = []
        # Кэш сопоставления (class_code, sec_code) -> instrument_id
        self._instrument_id_cache: Dict[InstrumentKey, int] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True

        # Инициализируем кэш instrument_id для всех инструментов
        await self._init_instrument_id_cache()

        # Подписываемся на котировки и сделки
        for class_code, sec_code in self.instruments:
            self._connector.subscribe_quotes(class_code, sec_code, self._update_quote)
            self._connector.subscribe_trades(class_code, sec_code, self._on_trade)

        # Запускаем фоновую задачу
        self._task = asyncio.create_task(self._loop(), name="data_recorder")
        logger.info("DataRecorder started (%d instruments)", len(self.instruments))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            await self._task
        for class_code, sec_code in self.instruments:
            self._connector.unsubscribe_quotes(class_code, sec_code, self._update_quote)
            self._connector.unsubscribe_trades(class_code, sec_code, self._on_trade)
        # Закрываем QuikConnector, чтобы фоновые потоки завершились
        self._connector.close()
        logger.info("DataRecorder stopped")

    # ------------------------------------------------------------------
    # Callback от QuikConnector (может быть sync)
    # ------------------------------------------------------------------

    def _update_quote(self, data: Dict[str, Any]) -> None:  # noqa: D401
        key: InstrumentKey = (data["class_code"], data["sec_code"])
        self._latest[key] = data

    # Callback от QuikConnector для сделок
    def _on_trade(self, data: Dict[str, Any]) -> None:
        self._trades.append(data)

    # ------------------------------------------------------------------
    # Основной цикл: раз в `period` сек пишет в базу
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.period)
            await self._flush_to_db()

    async def _init_instrument_id_cache(self) -> None:
        """Заполняет кэш сопоставления (class_code, sec_code) -> instrument_id из БД."""
        async with AsyncSessionLocal() as session:
            for class_code, sec_code in self.instruments:
                # Ищем инструмент по тикеру и board (class_code)
                result = await session.execute(
                    Instrument.__table__.select().where(
                        (Instrument.ticker == sec_code) & (Instrument.board == class_code)
                    )
                )
                row = result.first()
                if row:
                    instrument_id = row[0]
                    self._instrument_id_cache[(class_code, sec_code)] = instrument_id
                else:
                    logger.warning(f"Instrument not found in DB: {class_code}.{sec_code}")

    async def _flush_to_db(self) -> None:
        if not self._latest and not self._trades:
            return
        async with AsyncSessionLocal() as session:
            # Котировки
            for (class_code, sec_code), q in list(self._latest.items()):
                # Получаем instrument_id из кэша, если нет — пропускаем котировку
                instrument_id = self._instrument_id_cache.get((class_code, sec_code))
                if instrument_id is None:
                    logger.warning(f"Instrument not found in DB: {class_code}.{sec_code}")
                    continue
                # Сохраняем котировку (используем только реальные поля модели)
                quote = Quote(
                    ts=datetime.fromtimestamp(q["time"], tz=timezone.utc),
                    instrument_id=instrument_id,
                    bid=q["bid"],
                    ask=q["ask"],
                    bid_qty=q.get("bid_qty", 0),
                    ask_qty=q.get("ask_qty", 0),
                )
                session.add(quote)
            # Сделки
            for t in self._trades:
                instrument_id = self._instrument_id_cache.get((t["class_code"], t["sec_code"]))
                if instrument_id is None:
                    logger.warning(f"Unknown instrument for trade: {t['class_code']}.{t['sec_code']}")
                    continue
                trade = Trade(
                    ts=datetime.fromtimestamp(t["time"], tz=timezone.utc),
                    price=t["price"],
                    qty=t["qty"],
                    side=t.get("side", ""),
                    instrument_id=instrument_id,
                )
                session.add(trade)
            self._trades.clear()
            try:
                await session.commit()
            except Exception as exc:  # pragma: no cover
                await session.rollback()
                logger.exception("DB commit failed: %s", exc)

    @classmethod
    async def from_active_portfolios(cls, period: float = 1.0) -> "DataRecorder":
        """
        Создаёт DataRecorder, автоматически собирая список инструментов из активных портфелей (PortfolioConfig).
        """
        instruments: set[InstrumentKey] = set()
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                PortfolioConfig.__table__.select().where(PortfolioConfig.active == True)
            )
            for row in result:
                # Ожидаем, что config_json содержит список ног с class_code и sec_code
                config = row[3]  # config_json
                if not config:
                    continue
                try:
                    legs = config.get("legs") or []
                    for leg in legs:
                        instruments.add((leg["class_code"], leg["sec_code"]))
                except Exception as exc:
                    logger.warning(f"Некорректный config_json в портфеле: {exc}")
        return cls(list(instruments), period=period)

    async def update_instruments(self, new_instruments: list[InstrumentKey]) -> None:
        """
        Динамически обновляет список инструментов: подписывается на новые, отписывается от неактуальных.
        """
        to_add = set(new_instruments) - set(self.instruments)
        to_remove = set(self.instruments) - set(new_instruments)
        for class_code, sec_code in to_remove:
            self._connector.unsubscribe_quotes(class_code, sec_code, self._update_quote)
            self._connector.unsubscribe_trades(class_code, sec_code, self._on_trade)
            self._latest.pop((class_code, sec_code), None)
        for class_code, sec_code in to_add:
            self._connector.subscribe_quotes(class_code, sec_code, self._update_quote)
            self._connector.subscribe_trades(class_code, sec_code, self._on_trade)
        self.instruments = list(new_instruments)
        await self._init_instrument_id_cache()
        logger.info(f"DataRecorder instruments обновлены: {self.instruments}")


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
        from ..db.database import Base

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
