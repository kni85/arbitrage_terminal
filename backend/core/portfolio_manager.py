"""
Модуль `portfolio_manager` содержит диспетчер стратегий (портфелей).

* Поддерживает одновременный запуск нескольких стратегий.
* Предоставляет API для добавления, запуска и остановки портфелей.
* Является асинхронным: стратегии исполняются в виде задач `asyncio`.

> **Важно**: настоящая логика стратегий будет реализована в отдельном модуле
> `core.strategy`. На момент написания этого файла он может отсутствовать,
> поэтому предусмотрена заглушка `DummyStrategy`, чтобы файл можно было
> запускать и тестировать автономно.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Попытка импортировать базовый класс стратегии. Если ещё не создан – заглушка.
# ---------------------------------------------------------------------------
try:
    from core.strategy import BaseStrategy  # type: ignore
except ImportError:  # pragma: no cover – временно до появления real strategy

    class BaseStrategy:  # pylint: disable=too-few-public-methods
        """Заглушка, эмулирующая работу стратегии для автономного теста."""

        def __init__(self, config: dict[str, Any]):
            self.config = config
            self._running = False
            self._task: Optional[asyncio.Task] = None

        async def _loop(self) -> None:
            """Имитация торгового цикла: выводим сообщение раз в секунду."""
            while self._running:
                logger.info("[DummyStrategy] work… (config=%s)", self.config)
                await asyncio.sleep(1)

        async def start(self) -> None:
            """Запуск стратегии."""
            if self._running:
                return
            self._running = True
            self._task = asyncio.create_task(self._loop())

        async def stop(self) -> None:
            """Остановка стратегии."""
            self._running = False
            if self._task:
                await self._task

        @property
        def is_running(self) -> bool:  # noqa: D401
            """Возвращает `True`, если стратегия запущена."""
            return self._running


# ---------------------------------------------------------------------------
# Внутренняя структура для хранения данных о запущенном портфеле
# ---------------------------------------------------------------------------

@dataclass
class _PortfolioRecord:
    """Вспомогательная структура – хранит стратегию и связанную с ней задачу."""

    strategy: BaseStrategy
    task: asyncio.Task
    config: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Класс PortfolioManager
# ---------------------------------------------------------------------------

class PortfolioManager:
    """Диспетчер, управляющий жизненным циклом стратегий."""

    def __init__(self) -> None:
        self._portfolios: Dict[str, _PortfolioRecord] = {}
        self._lock = asyncio.Lock()
        self._running = False

    # ---------------------------- Публичный API ----------------------------

    async def start(self) -> None:
        """Вызывается при старте приложения FastAPI."""
        logger.info("PortfolioManager: старт.")
        self._running = True
        # (опционально) здесь можно загружать конфигурации из БД и автозапускать
        # сохранённые портфели. Пока пропускаем.

    async def stop(self) -> None:
        """Останавливает все запущенные портфели и завершает работу менеджера."""
        logger.info("PortfolioManager: остановка …")
        async with self._lock:
            # Останавливаем стратегии
            for pid, record in list(self._portfolios.items()):
                await self._stop_portfolio_nolock(pid)
        self._running = False
        logger.info("PortfolioManager: остановлен.")

    async def add_portfolio(self, config: dict[str, Any]) -> str:
        """Создать и запустить новый портфольный робот.

        :param config: конфигурация стратегии (формат будет уточнён позже)
        :return: идентификатор портфеля
        """
        async with self._lock:
            pid = str(uuid.uuid4())
            strategy = BaseStrategy(config)
            task = asyncio.create_task(strategy.start())  # type: ignore[arg-type]
            self._portfolios[pid] = _PortfolioRecord(
                strategy=strategy, task=task, config=config
            )
            logger.info("Portfolio %s добавлен и запущен.", pid)
            return pid

    async def stop_portfolio(self, pid: str) -> None:
        """Остановить запущенный портфель по идентификатору."""
        async with self._lock:
            await self._stop_portfolio_nolock(pid)

    async def list_portfolios(self) -> Dict[str, dict[str, Any]]:
        """Вернуть краткое состояние всех портфелей."""
        async with self._lock:
            summary: Dict[str, dict[str, Any]] = {}
            for pid, rec in self._portfolios.items():
                summary[pid] = {
                    "running": rec.strategy.is_running,
                    "config": rec.config,
                }
            return summary

    # ----------------------- Внутренние вспомогательные --------------------

    async def _stop_portfolio_nolock(self, pid: str) -> None:
        """Вспомогательный метод: остановка без захвата внешнего lock."""
        record = self._portfolios.get(pid)
        if not record:
            logger.warning("Портфеля %s не существует.", pid)
            return
        await record.strategy.stop()
        # Дожидаемся завершения фоновой задачи, если она ещё крутится
        if not record.task.done():
            await record.task
        del self._portfolios[pid]
        logger.info("Портфель %s остановлен и удалён.", pid)


# ---------------------------------------------------------------------------
# Тестирование модуля (запуск через `python core/portfolio_manager.py`)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """Небольшой тест: создаём менеджер, запускаем два заглушечных портфеля."""

    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def _demo() -> None:
        manager = PortfolioManager()
        await manager.start()

        # Добавляем два портфеля с разной конфигурацией
        pid1 = await manager.add_portfolio({"name": "Demo‑1", "legs": 2})
        pid2 = await manager.add_portfolio({"name": "Demo‑2", "legs": 3})

        # Работаем 5 секунд, смотрим логи
        await asyncio.sleep(5)

        # Выводим текущее состояние портфелей
        summary = await manager.list_portfolios()
        print("\nСостояние портфелей:")
        for pid, info in summary.items():
            print(f"{pid}: running={info['running']} config={info['config']}")

        # Останавливаем оба портфеля и менеджер
        await manager.stop_portfolio(pid1)
        await manager.stop_portfolio(pid2)
        await manager.stop()

    # Запуск демо‑корутины
    asyncio.run(_demo())

    # Для простоты завершаем процесс (если вдруг не все задачи остановились)
    sys.exit(0)
