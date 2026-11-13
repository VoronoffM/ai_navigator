class RiskAgent:
    def __init__(self, max_position_size_rub=50000):
        self.max_position_size_rub = max_position_size_rub

    def validate_buy_order(self, cash, shares_count, price, lot_size):
        # Защита от овертрейдинга (уже в позиции)
        if shares_count > 0:
            return False, "Уже есть открытая позиция"
            
        # Защита от нехватки средств (с учетом комиссии)
        order_cost = price * lot_size * 1.001 
        if order_cost > cash:
            return False, f"Недостаточно средств (нужно {order_cost:.2f})"
            
        # Защита от превышения лимита на сделку
        if order_cost > self.max_position_size_rub:
            return False, f"Превышен лимит на сделку ({self.max_position_size_rub} RUB)"
            
        return True, "OK"

    def validate_sell_order(self, shares_count, lot_size):
        # Защита от продажи того, чего нет
        if shares_count < lot_size:
            return False, "Недостаточно акций (меньше 1 лота)"
        return True, "OK"