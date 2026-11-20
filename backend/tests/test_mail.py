import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.main import app
from backend.mail import MailError, MailSettings, _send
from backend.replay import gazprom_signal


SETTINGS = dict(host="smtp.example.com", port=465, security="ssl", username="sender@example.com",
                password="private-app-password", sender="sender@example.com", recipient="reports@example.com")


class MailTests(unittest.TestCase):
    def setUp(self):
        self.client = self.enterContext(TestClient(app))
        self.send = self.enterContext(patch("backend.main.send_mail", new_callable=AsyncMock))
        self.delivery = dict(run_id=str(uuid4()), scenario_id="gazp", name="Падение Газпрома")
        self.url = f"/api/analysis/{gazprom_signal().event_id}"
        self.profile = {"checks": ["market"], "mail": self.delivery}

    def connect(self):
        result = self.client.post("/api/studio/mail/test", json=SETTINGS)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIn("HttpOnly", result.headers["set-cookie"])
        data = self.client.get("/api/studio/mail").json()
        self.assertEqual(data["settings"]["recipient"], SETTINGS["recipient"])
        self.assertNotIn("password", data["settings"])
        self.assertNotIn(SETTINGS["password"], result.text)

    def status(self, job):
        return self.client.get(f"/api/analysis/jobs/{job['id']}", params={
            "run_id": self.delivery["run_id"], "scenario_id": self.delivery["scenario_id"], "channel": "mail",
        }).json()

    def test_delivery_once_per_run_and_disconnect(self):
        self.connect()
        job = self.client.post(self.url, json=self.profile).json()
        self.assertEqual(self.status(job)["mail"], "sent")
        self.assertIn("GAZP", self.send.await_args.args[2])
        self.assertIn("IMOEX", self.send.await_args.args[2])
        self.assertIn(self.delivery["name"], self.send.await_args.args[1])
        self.client.post(self.url, json=self.profile)
        self.assertEqual(self.send.await_count, 2)  # test + report
        self.delivery["run_id"] = str(uuid4())
        self.client.post(self.url, json=self.profile)
        self.assertEqual(self.send.await_count, 3)
        self.assertEqual(self.client.delete("/api/studio/mail").status_code, 204)
        self.assertIsNone(self.client.get("/api/studio/mail").json()["settings"])
        job = self.client.post(self.url, json=self.profile).json()
        self.assertEqual(job["mail"], "unconnected")
        self.assertEqual(self.send.await_count, 3)

    def test_failure_keeps_report(self):
        self.connect()
        self.send.side_effect = MailError("SMTP недоступен")
        job = self.client.post(self.url, json=self.profile).json()
        result = self.status(job)
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["mail"], "failed")
        self.assertIn("comparison", result["checks"]["market"]["facts"])

    def test_no_report_action_no_mail(self):
        self.connect()
        self.send.reset_mock()
        job = self.client.post(self.url, json={**self.profile, "workflow": {"actions": ["mcp"]}}).json()
        self.send.assert_not_awaited()
        self.assertNotIn("mail", job)

    def test_failed_setup_does_not_replace_working_connection(self):
        self.connect()
        self.send.side_effect = MailError("Проверьте пароль приложения")
        result = self.client.post("/api/studio/mail/test", json={**SETTINGS, "recipient": "new@example.com"})
        self.assertEqual(result.status_code, 502)
        self.assertEqual(self.client.get("/api/studio/mail").json()["settings"]["recipient"], SETTINGS["recipient"])

    def test_invalid_settings_never_echo_password(self):
        for patch_settings in ({"port": 0}, {"recipient": "bad"}, {"password": ""},
                               {"sender": "x@example.com\r\nBcc: other@example.com"}, {"security": "none"}):
            result = self.client.post("/api/studio/mail/test", json={**SETTINGS, **patch_settings})
            self.assertEqual(result.status_code, 422)
            self.assertNotIn(SETTINGS["password"], result.text)
        self.send.assert_not_awaited()

    def test_other_browser_cannot_use_connection(self):
        self.connect()
        # Use the same server lifespan with a separate browser cookie jar.
        other = TestClient(app)
        try:
            job = other.post(self.url, json=self.profile).json()
            self.assertEqual(job["mail"], "unconnected")
            self.assertEqual(self.client.get("/api/studio/mail").json()["settings"]["recipient"], SETTINGS["recipient"])
        finally:
            other.close()


class SmtpTransportTests(unittest.TestCase):
    def test_ssl_and_starttls_login_and_message(self):
        for security, constructor in (("ssl", "SMTP_SSL"), ("starttls", "SMTP")):
            with self.subTest(security=security), patch(f"backend.mail.smtplib.{constructor}") as factory:
                smtp = factory.return_value
                _send(MailSettings(**{**SETTINGS, "security": security}), "Отчёт", "Полный отчёт")
                smtp.login.assert_called_once_with(SETTINGS["username"], SETTINGS["password"])
                message = smtp.send_message.call_args.args[0]
                self.assertEqual(message["To"], SETTINGS["recipient"])
                self.assertIn("Полный отчёт", message.get_content())
                if security == "starttls":
                    smtp.starttls.assert_called_once()
                else:
                    smtp.starttls.assert_not_called()
