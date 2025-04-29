"""
Smoke-тест: ORM-модели должны **импортироваться** и
регистрироваться в `Base.metadata` без исключений.

Запускается локально командой

    pytest -q tests/unit/db_models_import_test.py
"""

from importlib import import_module

import pytest


# путь к модулю моделей внутри вашего проекта  ─┐
MODELS_MODULE = "backend.db.models"             #│
DB_MODULE      = "backend.db.database"          #┘


@pytest.mark.parametrize("module_path", [MODELS_MODULE])
def test_models_importable(module_path: str) -> None:
    """
    1. Модуль с декларативными моделями импортируется без ошибок.
    2. После импорта в `Base.metadata.tables` появился
       хотя бы один объект — значит классы действительно
       «примонтировались» к declarative-base.
    """
    # --- шаг 1: сам факт импорта ---

    import_module(module_path)

    # --- шаг 2: в metadata есть таблицы ---

    Base = import_module(DB_MODULE).Base
    assert (
        Base.metadata.tables
    ), "После импорта моделей Base.metadata.tables пуст — проверьте декларативную регистрацию классов."
