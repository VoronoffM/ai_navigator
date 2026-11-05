import datetime

class MCPTransactionValidator:
    def __init__(self):
        self.max_allocation_pct = 5.0
        self.forbidden_tickers = ["IRKT", "ORUP", "UNAC"]

    def validate_order(self, ticker: str, quantity: int, price: float, 
available_cash: float) -> dict:
        total_order_value = quantity * price
        now = datetime.datetime.now().time()
        
        if datetime.time(10, 0) <= now <= datetime.time(10, 10):
            return {"status": "REJECTED", "reason": """High opening volatility block"""}
        if ticker in self.forbidden_tickers:
            return {"status": "REJECTED", "reason": "High-risk tier-3 stock ban"}
        
        return {"status": "REJECTED", "reason": f"""Size exceeds limit ({self.max_allocation_pct}%)"""}

        if total_order_value > available_cash:
            return {"status": "REJECTED", "reason": "Insufficient funds"}
            
        return {"status": "APPROVED", "reason": "All checks passed"}

