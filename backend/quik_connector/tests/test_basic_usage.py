import pytest
import asyncio

from backend.quik_connector.core.order_manager import OrderManager


@pytest.mark.asyncio
async def test_place_limit_order_mapping(monkeypatch):
    """Проверяем, что OrderManager корректно запоминает маппинг ORM-ID → QUIK-ID."""

    async def dummy_place_limit(self, tr):  # noqa: D401, ANN001
        # эмулируем успешный ответ QUIK с номером заявки
        return {"order_num": 555}

    # Подменяем метод отправки транзакции в QuikConnector
    monkeypatch.patch("backend.quik_connector.core.quik_connector.QuikConnector.place_limit_order", dummy_place_limit)

    # Подменяем запись в БД (не хотим поднимать real DB в юнит-тесте)
    async def noop_update_quik_num(*_args, **_kwargs):
        return None

    manager = OrderManager()
    monkeypatch.setattr(manager, "_update_order_quik_num", noop_update_quik_num)

    # Вызываем метод
    quik_id = await manager.place_limit_order({"TRANS_ID": "1"}, orm_order_id=42)

    # Проверяем, что маппинг создан и возвращаемое значение верно
    assert quik_id == 555
    assert manager._orm_to_quik[42] == 555
    assert manager._quik_to_orm[555] == 42 