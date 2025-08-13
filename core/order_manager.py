"""Пакет `core` ещё находится в разработке.

Пока для обратной совместимости просто реэкспортируем OrderManager
из старого расположения.
Используйте `from core.order_manager import OrderManager` в новом коде –
после полного переноса реализация будет находиться именно здесь.
"""

from backend.quik_connector.core.order_manager import OrderManager  # type: ignore

__all__ = ["OrderManager"]
