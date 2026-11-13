import uuid
import time
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API_SANDBOX
from t_tech.invest.schemas import OrderDirection, OrderType, OrderExecutionReportStatus
from t_tech.invest.exceptions import RequestError

class ExecutionAgent:
    """Агент исполнения заявок. Обрабатывает ошибки биржи (30079) и дубли.""" 
    def __init__(self, token):
        self.token = token

    def _get_price(self, q):
        return q.units + q.nano / 1e9 if q else 0

    def place_order(self, figi, acc_id, direction, qty_lots=1):
        """Отправляет рыночный ордер. Если ошибка 30079 (торги закрыты), делает ретрай."""
        # Генерируем UUID для идемпотентности (защита от случайных дублей при потере сети)
        req_id = str(uuid.uuid4()) 
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with Client(self.token, target=INVEST_GRPC_API_SANDBOX) as client:
                    resp = client.orders.post_order(
                        instrument_id=figi, quantity=qty_lots, account_id=acc_id, 
                        direction=direction, order_type=OrderType.ORDER_TYPE_MARKET, order_id=req_id
                    )
                
                # Проверяем реальный статус заявки
                if resp.execution_report_status == OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_FILL:
                    return self._get_price(resp.executed_order_price), resp.lots_executed, "FILLED"
                elif resp.execution_report_status == OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_REJECTED:
                    return None, 0, "REJECTED"
                else:
                    return None, resp.lots_executed, "PENDING"
                    
            except RequestError as e:
                error_str = str(e.details)
                # ОШИБКА 30079: Инструмент недоступен (торги закрыты)
                if "30079" in error_str and attempt < max_retries - 1:
                    time.sleep(2) # Ждем и пробуем снова
                    continue
                # ОШИБКА 429: Слишком много запросов
                elif "429" in error_str and attempt < max_retries - 1:
                    time.sleep(3)
                    continue
                return None, 0, f"ERROR: {error_str}"