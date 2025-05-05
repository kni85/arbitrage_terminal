"""
`core.portfolio_manager` – диспетчер портфелей (стратегий).

* Хранит запущенные стратегии в памяти.
* Сохраняет/деактивирует конфигурации в таблице `PortfolioConfig`.
* Поддерживает фабрику стратегий через `STRATEGY_REGISTRY`.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, Optional, Type
from sqlalchemy import select

from ..db.database import AsyncSessionLocal, ensure_tables_exist
from ..db.models import PortfolioConfig
from .strategy import BaseStrategy, PairArbitrageStrategy, StrategyConfig, LegConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Реестр доступных стратегий
# ---------------------------------------------------------------------------

STRATEGY_REGISTRY: Dict[str, Type[BaseStrategy]] = {
    "pair": PairArbitrageStrategy,
    # "triangular": TriangularArbStrategy,  # задел на будущее
}

# ---------------------------------------------------------------------------
# Вспомогательная структура – хранит задачу и стратегию
# ---------------------------------------------------------------------------

class _PortfolioRecord:
    def __init__(self, strategy: BaseStrategy, task: asyncio.Task, config: dict[str, Any]):
        self.strategy = strategy
        self.task = task
        self.config = config


class PortfolioManager:
    """Управляет жизненным циклом стратегий (портфелей)."""

    def __init__(self) -> None:
        # Гарантируем создание таблиц один раз при первом запуске
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                # Если уже есть цикл – выполняем init_db в нём
                loop.create_task(ensure_tables_exist())
            else:
                loop.run_until_complete(ensure_tables_exist())
        except RuntimeError:
            # Нет активного цикла – создаём временный
            asyncio.run(ensure_tables_exist())

        self._portfolios: Dict[str, _PortfolioRecord] = {}
        self._lock = asyncio.Lock()
        self._running = False

    # ------------------------------------------------------------------
    # Внутреннее: построение стратегии
    # ------------------------------------------------------------------

    def _build_strategy(self, cfg: dict[str, Any]) -> BaseStrategy:
        stype = cfg.get("type")
        if stype not in STRATEGY_REGISTRY:
            raise ValueError(f"Неизвестный тип стратегии: {stype}")
        cls = STRATEGY_REGISTRY[stype]

        if stype == "pair":
            s_cfg = StrategyConfig(
                name=cfg.get("name", f"Pair-{uuid.uuid4().hex[:4]}"),
                leg1=LegConfig(**cfg["leg1"]),
                leg2=LegConfig(**cfg["leg2"]),
                entry_levels=cfg.get("entry_levels", [0.5]),
                exit_level=cfg.get("exit_level", 0.1),
                poll_interval=cfg.get("poll_interval", 0.5),
            )
            return cls(s_cfg)  # type: ignore[arg-type]

        # fallback: передаём raw‑dict, если стратегия умеет разбирать сама
        return cls(cfg)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._running = True
        logger.info("PortfolioManager started")
        # --- Восстанавливаем активные портфели из БД ---
        async with AsyncSessionLocal() as ses:
            result = await ses.execute(select(PortfolioConfig).where(PortfolioConfig.active == True))
            for row in result.scalars():
                pid = row.pid
                config = row.config_json
                # Запускаем стратегию с восстановленным конфигом
                await self._start_portfolio_from_config(pid, config)

    async def stop(self) -> None:
        async with self._lock:
            for pid in list(self._portfolios):
                await self._stop_portfolio_nolock(pid)
        self._running = False
        logger.info("PortfolioManager stopped")

    async def add_portfolio(self, config: dict[str, Any]) -> str:
        await ensure_tables_exist()
        async with self._lock:
            pid = str(uuid.uuid4())
            strategy = self._build_strategy(config)
            task = asyncio.create_task(strategy.start())
            # Добавляем обработчик для рестарта при падении
            task.add_done_callback(lambda t: asyncio.create_task(self._on_strategy_done(pid, config, t)))
            self._portfolios[pid] = _PortfolioRecord(strategy, task, config)
            logger.info("Portfolio %s of type %s started", pid, config.get("type"))
            await self._save_config(pid, config)
            return pid

    async def stop_portfolio(self, pid: str) -> None:
        async with self._lock:
            await self._stop_portfolio_nolock(pid)

    async def list_portfolios(self) -> Dict[str, dict[str, Any]]:
        async with self._lock:
            return {
                pid: {"running": rec.strategy.is_running, "config": rec.config}
                for pid, rec in self._portfolios.items()
            }

    async def update_portfolio(self, pid: str, new_config: dict[str, Any]) -> None:
        """
        Обновляет конфиг портфеля и перезапускает стратегию.
        """
        async with self._lock:
            await self._stop_portfolio_nolock(pid)
            await self._start_portfolio_from_config(pid, new_config)
            await self._save_config(pid, new_config)
            logger.info("Portfolio %s обновлён и перезапущен", pid)

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    async def _stop_portfolio_nolock(self, pid: str) -> None:
        rec = self._portfolios.get(pid)
        if not rec:
            logger.warning("Portfolio %s not found", pid)
            return
        await rec.strategy.stop()
        if not rec.task.done():
            await rec.task
        del self._portfolios[pid]
        logger.info("Portfolio %s stopped", pid)
        await self._deactivate_config(pid)

    async def _save_config(self, pid: str, cfg: dict[str, Any]) -> None:
        async with AsyncSessionLocal() as ses:
            ses.add(PortfolioConfig(pid=pid, name=cfg.get("name", pid), config_json=cfg))
            await ses.commit()

    async def _deactivate_config(self, pid: str) -> None:
        async with AsyncSessionLocal() as ses:
            stmt = select(PortfolioConfig).where(PortfolioConfig.pid == pid)
            result = await ses.execute(stmt)
            row = result.scalar_one_or_none()
            if row:
                row.active = False  # type: ignore[attr-defined]
                await ses.commit()

    async def _start_portfolio_from_config(self, pid: str, config: dict[str, Any]) -> None:
        async with self._lock:
            strategy = self._build_strategy(config)
            task = asyncio.create_task(strategy.start())
            # Добавляем обработчик для рестарта при падении
            task.add_done_callback(lambda t: asyncio.create_task(self._on_strategy_done(pid, config, t)))
            self._portfolios[pid] = _PortfolioRecord(strategy, task, config)
            logger.info("Portfolio %s of type %s started (restore)", pid, config.get("type"))

    async def _on_strategy_done(self, pid: str, config: dict[str, Any], task: asyncio.Task) -> None:
        """
        Обработчик завершения задачи стратегии. Если завершилась с ошибкой — рестарт.
        """
        try:
            exc = task.exception()
            if exc:
                logger.error(f"Стратегия {pid} завершилась с ошибкой: {exc}. Перезапуск...")
                await self._start_portfolio_from_config(pid, config)
        except asyncio.CancelledError:
            pass


# ---------------------------------------------------------------------------
# Демонстрация
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    async def _demo() -> None:
        mgr = PortfolioManager()
        await mgr.start()
        pid = await mgr.add_portfolio(
            {
                "type": "pair",
                "name": "DemoPair",
                "leg1": {"ticker": "A", "price_ratio": 1, "qty_ratio": 1},
                "leg2": {"ticker": "B", "price_ratio": 1, "qty_ratio": 1},
            }
        )
        await asyncio.sleep(3)
        await mgr.stop_portfolio(pid)
        await mgr.stop()

    asyncio.run(_demo())
    sys.exit(0)
