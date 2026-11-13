# Терминал: touch execution_agent.py && open -e execution_agent.py
import uuid
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API_SANDBOX
from t_tech.invest.schemas import OrderDirection, OrderType, OrderExecutionReportStatus
from t_tech.invest.exceptions import RequestError

class ExecutionAgent:
    """Агент исполнения. Отправляет ордера и проверяет статус."""
    def __init__(self, token):
        self.token = token

    def _get_price(self, q):
        return q.units + q.nano / 1e9 if q else 0

    def place_order(self, figi, acc_id, direction, qty_lots=1):
        # Генерируем ID идемпотентности (защита от дублей)
        req_id = str(uuid.uuid4())
        try:
            with Client(self.token, target=INVEST_GRPC_API_SANDBOX) as client:
                resp = client.orders.post_order(
                    instrument_id=figi, quantity=qty_lots, account_id=acc_id, 
                    direction=direction, order_type=OrderType.ORDER_TYPE_MARKET, order_id=req_id
                )
            
            # Проверяем, исполнена ли заявка полностью
            if resp.execution_report_status == OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_FILL:
                return self._get_price(resp.executed_order_price), resp.lots_executed, "FILLED"
            elif resp.execution_report_status == OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_REJECTED:
                return None, 0, "REJECTED"
            else:
                return None, resp.lots_executed, "PENDING"
        except RequestError as e:
            return None, 0, f"ERROR: {e.details}"