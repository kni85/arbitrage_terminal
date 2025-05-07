import asyncio
import json
import logging

import pytest

from backend.core.quik_connector import QuikConnector

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.asyncio


async def test_dump_account_info():
    """Интеграционный тест: вывод денежных лимитов и позиций по счёту."""

    ACCOUNT = "L01-00000F00"  # тот же счёт, что используется в других интеграционных тестах

    connector = QuikConnector()
    loop = asyncio.get_running_loop()

    # Денежные лимиты (остатки)
    money_resp: dict = await loop.run_in_executor(None, connector._qp.get_money_limits)  # type: ignore[attr-defined]
    money_limits = money_resp.get("data", [])
    money_filtered = [m for m in money_limits if m.get("trdaccid") == ACCOUNT or m.get("client_code")]

    # Позиции по инструментам
    depo_resp: dict = await loop.run_in_executor(None, connector._qp.get_all_depo_limits)  # type: ignore[attr-defined]
    depo_limits = depo_resp.get("data", [])
    depo_filtered = [d for d in depo_limits if d.get("trdaccid") == ACCOUNT or d.get("client_code")]

    print("\n===== MONEY LIMITS (", ACCOUNT, ") =====\n", json.dumps(money_filtered, ensure_ascii=False, indent=2))
    print("\n===== DEPO LIMITS (", ACCOUNT, ") =====\n", json.dumps(depo_filtered, ensure_ascii=False, indent=2))

    # Убедимся, что получили списки (пусть даже пустые)
    assert isinstance(money_filtered, list)
    assert isinstance(depo_filtered, list) 