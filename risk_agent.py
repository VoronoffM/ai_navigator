class RiskAgent:
    """
    Агент контроля рисков.
    Проверяет достаточность средств и лимиты на сделку.
    """
    def __init__(self, max_position_size_rub=100000): 
        self.max_position_size_rub = max_position_size_rub

    def validate_buy_order(self, cash, shares_count, price, lot_size):
        """Проверяет, можно ли купить лот. Лотность берется динамически."""
        # Запрещаем покупать, если уже есть позиция (защита от овертрейдинга)
        if shares_count > 0:
            return False, "Уже есть открытая позиция"
            
        # Считаем реальную стоимость лота с учетом комиссии (0.1%)
        order_cost = price * lot_size * 1.001 
        
        if order_cost > cash:
            return False, f"Недостаточно средств (нужно {order_cost:.2f} RUB)"
            
        if order_cost > self.max_position_size_rub:
            return False, f"Сделка превышает лимит риска ({self.max_position_size_rub} RUB)"
            
        return True, "OK"

    def validate_sell_order(self, shares_count, lot_size):
        """Проверяет, достаточно ли акций для продажи одного лота."""
        if shares_count < lot_size:
            return False, "Недостаточно акций (меньше 1 лота)"
        return True, "OK"