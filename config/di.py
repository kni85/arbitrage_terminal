"""DI-контейнер приложения на базе dependency-injector."""

from __future__ import annotations

from dependency_injector import containers, providers

from backend.quik_connector.core.quik_connector import QuikConnector  # type: ignore
from core.order_manager import OrderManager
from .settings import settings


class AppContainer(containers.DeclarativeContainer):
    """Описание провайдеров приложения."""

    wiring_config = containers.WiringConfiguration(packages=[
        "backend.api",
    ])

    # Настройки доступны как singleton
    config = providers.Object(settings)

    # Брокер (QUIK) — singleton
    broker = providers.Singleton(QuikConnector, host=settings.QUIK_HOST, port=settings.QUIK_PORT)

    # OrderManager — зависит от broker (пока OrderManager внутри сам берёт QuikConnector, но на будущее)
    order_manager = providers.Singleton(OrderManager)


# Экземпляр контейнера, который можно импортировать
container = AppContainer()
