import asyncio
import json
import logging

import pytest

from backend.core.quik_connector import QuikConnector

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.asyncio


async def test_dump_quik_orders():
    """Интеграционный тест: печатает все заявки из таблицы QUIK (активные и снятые)."""

    connector = QuikConnector()

    # Вызов get_all_orders у QuikPy может быть блокирующим ⇒ run_in_executor
    loop = asyncio.get_running_loop()
    orders_resp: dict = await loop.run_in_executor(None, connector._qp.get_all_orders)  # type: ignore[attr-defined]

    data = orders_resp.get("data")
    assert data is not None, "Нет данных об ордерах от QUIK"

    # Красиво выводим JSON-сериализацию
    dump = json.dumps(data, ensure_ascii=False, indent=2)
    print("\n===== QUIK ORDERS DUMP =====\n", dump)

    # Тест считается пройденным, если мы успешно получили список (может быть пустым)
    assert isinstance(data, (list, tuple)), "Формат ответа некорректен" 