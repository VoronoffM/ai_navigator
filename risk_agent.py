# Терминал: touch risk_agent.py && open -e risk_agent.py
class RiskAgent:
    """Агент проверки рисков. Блокирует небезопасные сделки."""
    def __init__(self, max_position_size_rub=50000):
        self.max_position_size_rub = max_position_size_rub

    def validate_buy_order(self, cash, shares_count, price, lot_size):
        # Запрещаем покупать, если уже есть позиция (защита от овертрейдинга)
        if shares_count > 0:
            return False, "Уже есть открытая позиция"
            
        # Считаем стоимость с учетом комиссии
        order_cost = price * lot_size * 1.001 
        if order_cost > cash:
            return False, f"Недостаточно средств (нужно {order_cost:.2f})"
            
        if order_cost > self.max_position_size_rub:
            return False, f"Превышен лимит на сделку ({self.max_position_size_rub} RUB)"
            
        return True, "OK"

    def validate_sell_order(self, shares_count, lot_size):
        # Запрещаем продавать, если нет акций
        if shares_count < lot_size:
            return False, "Недостаточно акций (меньше 1 лота)"
        return True, "OK"