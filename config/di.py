"""DI-контейнер приложения на базе dependency-injector."""

from __future__ import annotations

from dependency_injector import containers, providers

# Низкоуровневый коннектор QUIK и высокоуровневый адаптер Broker
from backend.quik_connector.core.quik_connector import QuikConnector  # type: ignore
from infra.quik_adapter import QuikBrokerAdapter
from core.order_manager import OrderManager
from core.broker import Broker  # noqa: F401 for typing
from .settings import settings


class AppContainer(containers.DeclarativeContainer):
    """Описание провайдеров приложения."""

    # Настройки доступны как singleton
    config = providers.Object(settings)

    # --- Низкоуровневый коннектор (singleton) ---------------------------------
    _quik_connector = providers.Singleton(
        QuikConnector,
        host=config.provided.QUIK_HOST,
        requests_port=config.provided.QUIK_PORT,
    )

    # --- Высокоуровневый адаптер, удовлетворяющий интерфейсу Broker ----------
    broker: providers.Provider[Broker] = providers.Singleton(
        QuikBrokerAdapter,
        connector=_quik_connector,
    )

    # OrderManager — зависит от broker (пока OrderManager внутри сам берёт QuikConnector, но на будущее)
    order_manager = providers.Singleton(OrderManager)


# Экземпляр контейнера, который можно импортировать
container = AppContainer()
