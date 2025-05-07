import asyncio
import json
import logging

import pytest

from backend.core.quik_connector import QuikConnector

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.asyncio


async def test_dump_sber_l2():
    """Интеграционный тест: вывод стакана котировок TQBR.SBER (L2)."""

    CLASS = "TQBR"
    SEC = "SBER"

    connector = QuikConnector()

    loop = asyncio.get_running_loop()
    resp: dict = await loop.run_in_executor(
        None,
        connector._qp.get_quote_level2,  # type: ignore[attr-defined]
        CLASS,
        SEC,
    )

    data = resp.get("data")
    assert data is not None, "Нет стакана от QUIK"

    print("\n===== L2 QUOTE TQBR.SBER =====\n", json.dumps(data, ensure_ascii=False, indent=2))

    # Данные должны содержать bid/offer списки
    assert "bid" in data and "offer" in data, "Формат стакана некорректен" 