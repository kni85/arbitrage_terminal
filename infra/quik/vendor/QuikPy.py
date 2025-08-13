"""Local vendor module for QuikPy.

Пытаемся импортировать библиотеку *QuikPy* из установленного окружения.
Если пакет отсутствует — возбуждаем ImportError, чтобы приложение явно
сообщило о необходимости установки, вместо тихого перехода в Dummy.
"""

try:
    from QuikPy import QuikPy  # type: ignore  # external dependency
except ImportError as exc:  # pragma: no cover – пакет не установлен
    raise ImportError(
        "QuikPy library is not installed. Install via 'pip install QuikPy' "
        "or place vendor/QuikPy.py in infra/quik/vendor."  # noqa: E501
    ) from exc
