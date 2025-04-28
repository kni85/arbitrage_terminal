"""
`core.strategy` – базовые классы стратегий арбитража.

* **BaseStrategy** – абстрактный класс, описывающий общий жизненный цикл.
* **PairArbitrageStrategy** – пример реализации парного арбитража
  (2‑ногий спред) с фиксированными коэффициентами и уровнями.

> Настоящая торговля через QUIK будет добавлена позднее (через QuikConnector).
> Сейчас мы эмулируем поток котировок случайными числами для демонстрации.
"""

from __future__ import annotations

import abc
import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Конфигурационные структуры
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class LegConfig:
    """Описывает одну ногу арбитража."""

    ticker: str  # тикер инструмента в QUIK
    price_ratio: float = 1.0  # коэффициент для цены
    qty_ratio: float = 1.0  # коэффициент объёма (кол-во лотов)


@dataclass(slots=True)
class StrategyConfig:
    """Конфигурация парного арбитража."""

    name: str
    leg1: LegConfig
    leg2: LegConfig
    entry_levels: List[float] = field(default_factory=lambda: [0.5])  # отклонение спреда
    exit_level: float = 0.1  # возвращение спреда к 0 для выхода
    poll_interval: float = 0.5  # сек между проверками рынка


# ---------------------------------------------------------------------------
# Абстрактный базовый класс стратегии
# ---------------------------------------------------------------------------

class BaseStrategy(abc.ABC):
    """Абстрактная стратегия со стандартным жизненным циклом."""

    def __init__(self, config: StrategyConfig):
        self.cfg = config
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None

    # ---------------------- Методы, вызываемые менеджером ------------------

    async def start(self) -> None:
        """Запуск фонового цикла."""
        if self._running:
            logger.warning("Стратегия %s уже запущена", self.cfg.name)
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name=f"strategy:{self.cfg.name}")

    async def stop(self) -> None:
        """Остановка цикла."""
        self._running = False
        if self._task:
            await self._task

    @property
    def is_running(self) -> bool:  # noqa: D401
        return self._running

    # ------------------------ Абстрактные методы ---------------------------

    @abc.abstractmethod
    async def _loop(self) -> None:
        """Основной цикл стратегии (как coroutine)."""


# ---------------------------------------------------------------------------
# Простейшая реализация парного арбитража (имитация котировок)
# ---------------------------------------------------------------------------

class PairArbitrageStrategy(BaseStrategy):
    """Демонстрационная стратегия: покупаем/продаём спред между двумя ценами."""

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.position_open = False
        self.entry_side: Optional[int] = None  # 1 если long leg1/short leg2, -1 наоборот

    async def _loop(self) -> None:
        """Имитация торгового цикла: случайные котировки и логика вход/выход."""
        logger.info("Стратегия %s запущена", self.cfg.name)
        while self._running:
            # 1. Получаем (эмулируем) цены
            price1 = self._simulate_price(self.cfg.leg1.ticker)
            price2 = self._simulate_price(self.cfg.leg2.ticker)

            # 2. Рассчитываем спред (базис)
            spread = price1 * self.cfg.leg1.price_ratio - price2 * self.cfg.leg2.price_ratio
            logger.debug("[%s] price1=%s price2=%s spread=%.4f", self.cfg.name, price1, price2, spread)

            # 3. Логика входа
            if not self.position_open:
                for level in sorted(self.cfg.entry_levels):
                    if spread >= level:
                        await self._enter_position(side=-1, spread=spread)  # short spread
                        break
                    if spread <= -level:
                        await self._enter_position(side=1, spread=spread)  # long spread
                        break
            else:
                # 4. Логика выхода
                if self.entry_side == 1 and spread >= -self.cfg.exit_level:
                    await self._exit_position(spread)
                elif self.entry_side == -1 and spread <= self.cfg.exit_level:
                    await self._exit_position(spread)

            await asyncio.sleep(self.cfg.poll_interval)
        logger.info("Стратегия %s остановлена", self.cfg.name)

    # ------------------------ Вспомогательные методы -----------------------

    async def _enter_position(self, side: int, spread: float) -> None:
        """Открытие позиции.

        side =  1 → long leg1 / short leg2
        side = -1 → short leg1 / long leg2
        """
        self.position_open = True
        self.entry_side = side
        logger.info(
            "[%s] >>> ОТКРЫТА позиция side=%s (spread=%.4f)", self.cfg.name, side, spread
        )
        # Здесь будет логика выставления ордеров через QuikConnector

    async def _exit_position(self, spread: float) -> None:
        """Закрытие позиции."""
        logger.info("[%s] <<< ЗАКРЫТА позиция (spread=%.4f)", self.cfg.name, spread)
        self.position_open = False
        self.entry_side = None
        # Здесь будет реальное закрытие через QUIK

    # --------------------- Служебная эмуляция цен --------------------------

    _price_state: Dict[str, float] = {}

    @classmethod
    def _simulate_price(cls, ticker: str) -> float:
        """Генерирует псевдо‑цены: случайное блуждание."""
        base = cls._price_state.get(ticker, random.uniform(100, 110))
        base += random.uniform(-0.5, 0.5)
        cls._price_state[ticker] = base
        return round(base, 4)


# ---------------------------------------------------------------------------
# Демонстрационный запуск модуля
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def _demo() -> None:
        cfg = StrategyConfig(
            name="DemoPair",
            leg1=LegConfig(ticker="A", price_ratio=1.0, qty_ratio=1),
            leg2=LegConfig(ticker="B", price_ratio=1.0, qty_ratio=1),
            entry_levels=[1.0, 1.5],
            exit_level=0.2,
            poll_interval=0.5,
        )
        strat = PairArbitrageStrategy(cfg)
        await strat.start()

        # Даём поработать 10 секунд
        await asyncio.sleep(10)
        await strat.stop()

    asyncio.run(_demo())
    sys.exit(0)
