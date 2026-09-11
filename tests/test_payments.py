import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest

import engine
from core.payments import (
    PaymentError,
    normalize_pix,
    normalize_stripe,
    verify_pix_signature,
    verify_stripe_signature,
)
from ui.web_dashboard import WebDashboardController


class PaymentTests(unittest.TestCase):
    def test_pix_normalization_uses_common_donation_shape(self):
        donation = normalize_pix({
            "id": "pix-123",
            "status": "confirmed",
            "streamerId": "local",
            "amount": "10.50",
            "currency": "BRL",
            "donor": {"name": "Alice"},
            "message": "Força!",
        }, "local")
        self.assertEqual(donation["provider"], "pix")
        self.assertEqual(donation["amountMinor"], 1050)
        self.assertEqual(donation["status"], "confirmed")
        self.assertEqual(donation["eventData"]["donationId"], "pix-123")

    def test_payment_normalizers_require_confirmed_status_and_streamer(self):
        with self.assertRaises(PaymentError):
            normalize_pix({"id": "pix-1", "status": "pending", "streamerId": "local", "amount": "1"}, "local")
        with self.assertRaises(PaymentError):
            normalize_pix({"id": "pix-1", "status": "confirmed", "amount": "1"}, "local")

    def test_pix_and_stripe_signatures(self):
        raw = b'{"id":"payment-1"}'
        pix_secret = "pix-secret"
        pix_signature = hmac.new(pix_secret.encode(), raw, hashlib.sha256).hexdigest()
        self.assertTrue(verify_pix_signature(raw, pix_signature, pix_secret))
        self.assertFalse(verify_pix_signature(raw, "invalid", pix_secret))

        stripe_secret = "stripe-secret"
        timestamp = int(time.time())
        signed = f"{timestamp}.".encode() + raw
        stripe_signature = hmac.new(stripe_secret.encode(), signed, hashlib.sha256).hexdigest()
        self.assertTrue(verify_stripe_signature(raw, f"t={timestamp},v1={stripe_signature}", stripe_secret))
        self.assertFalse(verify_stripe_signature(raw, f"t={timestamp - 1000},v1={stripe_signature}", stripe_secret))

    def test_webhook_confirms_once_and_publishes_common_event(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            overlay_path = os.path.join(temp_dir, "overlay.json")
            channels_path = os.path.join(temp_dir, "channels.json")
            controller = WebDashboardController(overlay_path, channels_path)
            previous = {key: os.environ.get(key) for key in (
                "NETRUNNER_PIX_WEBHOOK_SECRET", "NETRUNNER_STRIPE_WEBHOOK_SECRET", "NETRUNNER_STREAMER_ID"
            )}
            os.environ["NETRUNNER_PIX_WEBHOOK_SECRET"] = "pix-secret"
            os.environ["NETRUNNER_STREAMER_ID"] = "local"
            engine.set_dashboard_controller(controller)
            try:
                payload = {
                    "id": "pix-unique",
                    "status": "confirmed",
                    "streamerId": "local",
                    "amount": "12.00",
                    "currency": "BRL",
                    "donorName": "Alice",
                }
                raw = json.dumps(payload, separators=(",", ":")).encode()
                signature = hmac.new(b"pix-secret", raw, hashlib.sha256).hexdigest()
                client = engine.app.test_client()
                first = client.post(
                    "/api/v1/webhooks/pix",
                    data=raw,
                    content_type="application/json",
                    headers={"X-Netrunner-Signature": signature},
                )
                self.assertEqual(first.status_code, 200)
                self.assertTrue(first.json["accepted"])
                repeated = client.post(
                    "/api/v1/webhooks/pix",
                    data=raw,
                    content_type="application/json",
                    headers={"X-Netrunner-Signature": signature},
                )
                self.assertEqual(repeated.status_code, 200)
                self.assertTrue(repeated.json["duplicate"])
                self.assertEqual(controller.snapshot()["events"][-1]["platform"], "pix")
                self.assertEqual(controller.snapshot()["events"][-1]["type"], "donation")
                self.assertEqual(len(controller.donation_ledger.snapshot()), 1)
            finally:
                controller.shutdown()
                engine.set_dashboard_controller(None)
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_stripe_webhook_maps_payment_intent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = WebDashboardController(os.path.join(temp_dir, "overlay.json"), os.path.join(temp_dir, "channels.json"))
            previous = {key: os.environ.get(key) for key in ("NETRUNNER_STRIPE_WEBHOOK_SECRET", "NETRUNNER_STREAMER_ID")}
            os.environ["NETRUNNER_STRIPE_WEBHOOK_SECRET"] = "stripe-secret"
            os.environ["NETRUNNER_STREAMER_ID"] = "local"
            engine.set_dashboard_controller(controller)
            try:
                payload = {
                    "id": "evt_123",
                    "type": "payment_intent.succeeded",
                    "data": {"object": {
                        "id": "pi_123",
                        "amount_received": 2500,
                        "currency": "brl",
                        "metadata": {"streamer_id": "local", "donation_id": "don-123", "donor_name": "Bob"},
                    }},
                }
                raw = json.dumps(payload, separators=(",", ":")).encode()
                timestamp = int(time.time())
                signed = f"{timestamp}.".encode() + raw
                signature = hmac.new(b"stripe-secret", signed, hashlib.sha256).hexdigest()
                response = engine.app.test_client().post(
                    "/api/v1/webhooks/stripe",
                    data=raw,
                    content_type="application/json",
                    headers={"Stripe-Signature": f"t={timestamp},v1={signature}"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(controller.donation_ledger.snapshot()[0]["amountMinor"], 2500)
            finally:
                controller.shutdown()
                engine.set_dashboard_controller(None)
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
