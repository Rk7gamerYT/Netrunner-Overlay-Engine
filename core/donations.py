"""Durable idempotency ledger for confirmed external donations."""

import json
import os
import threading
import time

from core.sanitization import sanitize_text, sanitize_value


MAX_DONATION_RECORDS = 2000


class DonationLedger:
    def __init__(self, state_path, streamer_id="local", max_records=MAX_DONATION_RECORDS):
        self.state_path = os.path.abspath(state_path)
        self.streamer_id = sanitize_text(streamer_id or "local", 160)
        self.max_records = max(1, int(max_records))
        self._lock = threading.RLock()
        self._records = self._load()

    def _load(self):
        try:
            with open(self.state_path, "r", encoding="utf-8") as handle:
                state = json.load(handle)
            records = state.get("donations", []) if isinstance(state, dict) else []
            if not isinstance(records, list):
                raise ValueError("ledger inválido")
            return [sanitize_value(item) for item in records[-self.max_records:] if isinstance(item, dict)]
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return []

    def _persist(self, records):
        directory = os.path.dirname(self.state_path)
        os.makedirs(directory, exist_ok=True)
        temporary = self.state_path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(
                {"version": 1, "streamerId": self.streamer_id, "donations": records[-self.max_records:]},
                handle,
                ensure_ascii=False,
                indent=2,
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.state_path)

    def confirm(self, donation):
        donation = sanitize_value(donation or {})
        provider = sanitize_text(donation.get("provider"), 32).lower()
        external_id = sanitize_text(donation.get("externalId"), 200)
        streamer_id = sanitize_text(donation.get("streamerId"), 160)
        if not provider or not external_id:
            return {"ok": False, "accepted": False, "message": "Doação sem identificador externo."}
        if streamer_id != self.streamer_id:
            return {"ok": False, "accepted": False, "message": "Doação destinada a outro streamer."}
        key = f"{provider}:{external_id}"
        with self._lock:
            for record in self._records:
                if record.get("idempotencyKey") == key:
                    return {
                        "ok": True,
                        "accepted": False,
                        "duplicate": True,
                        "message": "Webhook já processado.",
                        "donation": dict(record),
                    }
            record = dict(donation)
            record["idempotencyKey"] = key
            record["confirmedAt"] = int(time.time() * 1000)
            records = (self._records + [record])[-self.max_records:]
            try:
                self._persist(records)
            except OSError:
                return {"ok": False, "accepted": False, "message": "Não foi possível persistir a confirmação."}
            self._records = records
            return {"ok": True, "accepted": True, "duplicate": False, "message": "Doação confirmada.", "donation": dict(record)}

    def snapshot(self):
        with self._lock:
            return list(self._records)
