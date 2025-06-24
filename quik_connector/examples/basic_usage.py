import sys, os
# Добавляем путь к родительской директории
sys.path.append(
    os.path.dirname(               # …/arbitrage_terminal/quik_connector/examples
        os.path.dirname(           # …/arbitrage_terminal/quik_connector
            os.path.dirname(os.path.abspath(__file__))  # …/arbitrage_terminal
        )
    )
)

import asyncio
from quik_connector.core.quik_connector import QuikConnector
from quik_connector.core.order_manager import OrderManager

async def main():
    # Создаём коннектор
    connector = QuikConnector()
    
    # Создаём менеджер ордеров
    order_manager = OrderManager()
    
    # Выставляем ордер
    order_data = {
        "ACTION": "NEW_ORDER",
        "CLASSCODE": "TQBR",
        "SECCODE": "SBER",
        "ACCOUNT": "L01-00000F00",
        "CLIENT_CODE": "1360W2",
        "OPERATION": "B",
        "PRICE": "290.50",
        "QUANTITY": "1",
        "TRANS_ID": "12345"
    }
    
    quik_id = await order_manager.place_limit_order(order_data, orm_order_id=1)
    print(f"Order placed with QUIK ID: {quik_id}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        # аккуратно гасим соединение и поток CallbackThread
        from quik_connector.core.quik_connector import QuikConnector
        QuikConnector().close()          # закроет DummyQuikPy/QuikPy