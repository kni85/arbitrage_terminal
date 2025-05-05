import pytest

@pytest.fixture(autouse=True)
def close_quik_connector():
    """
    После каждого теста гарантированно закрывает singleton QuikConnector,
    чтобы завершить все фоновые потоки и ресурсы.
    """
    yield
    try:
        from backend.core.quik_connector import QuikConnector
        QuikConnector().close()
    except Exception:
        # Если QuikConnector не был создан — ничего не делаем
        pass 