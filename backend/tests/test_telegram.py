import json
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.main import app
from backend.replay import gazprom_signal
from backend.telegram import TelegramError


class TelegramTests(unittest.TestCase):
    def setUp(self):
        self.client = self.enterContext(TestClient(app))
        self.send = self.enterContext(patch("backend.main.send_message", new_callable=AsyncMock))
        self.event_id = gazprom_signal().event_id
        self.analysis_url = f"/api/analysis/{self.event_id}"
        self.delivery = {"run_id": str(uuid4()), "scenario_id": "gazp", "name": "Падение Газпрома"}
        self.profile = {"checks": ["market"], "telegram": self.delivery}

    def connect(self):
        response = self.client.post("/api/studio/telegram/test", json={"token": "123:test", "chat_id": "42"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertEqual(self.client.get("/api/studio/telegram").json(), {"chat_id": "42"})

    def status(self, job_id):
        return self.client.get(f"/api/analysis/jobs/{job_id}", params={
            "run_id": self.delivery["run_id"], "scenario_id": self.delivery["scenario_id"],
        }).json()

    def test_finished_report_sent_once_per_run_for_connected_browser(self):
        self.connect()
        self.client.post(self.analysis_url, json={"checks": ["market"]})
        self.send.assert_awaited_once()
        job = self.client.post(self.analysis_url, json=self.profile).json()
        self.assertEqual(self.status(job["id"])["telegram"], "sent")
        message = self.send.await_args.args[1]
        self.assertIn("Падение Газпрома", message)
        self.assertIn("GAZP", message)
        self.assertIn("IMOEX", message)

        self.client.post(self.analysis_url, json=self.profile)
        self.assertEqual(self.send.await_count, 2)
        self.delivery["run_id"] = str(uuid4())
        self.client.post(self.analysis_url, json=self.profile)
        self.assertEqual(self.send.await_count, 3)

        disconnected = self.client.delete("/api/studio/telegram")
        self.assertEqual(disconnected.status_code, 204)
        self.assertEqual(self.client.get("/api/studio/telegram").json(), {"chat_id": None})
        self.delivery["run_id"] = str(uuid4())
        job = self.client.post(self.analysis_url, json=self.profile).json()
        self.assertEqual(job["telegram"], "unconnected")
        self.assertEqual(self.send.await_count, 3)

    def test_failed_delivery_preserves_completed_analysis(self):
        self.connect()
        self.send.side_effect = TelegramError("Не удалось получить ответ от Telegram.")
        job = self.client.post(self.analysis_url, json=self.profile).json()
        result = self.status(job["id"])
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["telegram"], "failed")
        self.assertIn("comparison", result["checks"]["market"]["facts"])

    def test_report_includes_analysis_and_source(self):
        self.connect()
        analysis = app.state.analysis
        provider_response = json.dumps({
            "summary": "Компания объявила рекомендацию по дивидендам.",
            "facts": [{"text": "Совет рекомендовал не выплачивать дивиденды.", "materialIds": ["interfax-1027187"]}],
            "hypotheses": [],
            "questions": [],
        })
        with patch.object(analysis.provider, "generate", new=AsyncMock(return_value=provider_response)):
            job = self.client.post(self.analysis_url, json={**self.profile, "checks": ["news"]}).json()
        result = self.status(job["id"])
        self.assertEqual(result["llm"], "ready")
        self.assertEqual(result["telegram"], "sent")
        message = self.send.await_args.args[1]
        self.assertIn("Компания объявила рекомендацию по дивидендам.", message)
        self.assertIn("https://www.interfax.ru/business/1027187", message)
