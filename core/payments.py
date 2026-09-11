"""Provider-neutral payment webhook verification and normalization."""

import hashlib
import hmac
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from core.sanitization import sanitize_text, sanitize_value


MAX_DONATION_MINOR = 100_000_000
PIX_CONFIRMED_STATUSES = {"confirmed", "paid", "completed", "received", "settled", "concluida", "concluído"}
STRIPE_CONFIRMED_TYPES = {"payment_intent.succeeded", "checkout.session.completed", "charge.succeeded"}


class PaymentError(ValueError):
    pass


def _metadata(payload):
    value = payload.get("metadata") if isinstance(payload, dict) else None
    return value if isinstance(value, dict) else {}


def _first(*values):
    return next((value for value in values if value not in (None, "")), None)


def _amount_minor(value=None, amount_minor=None):
    if amount_minor not in (None, ""):
        try:
            result = int(amount_minor)
        except (TypeError, ValueError):
            raise PaymentError("Valor monetário inválido.")
    else:
        try:
            decimal_value = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            result = int(decimal_value * 100)
        except (InvalidOperation, TypeError, ValueError):
            raise PaymentError("Valor monetário inválido.")
    if result <= 0 or result > MAX_DONATION_MINOR:
        raise PaymentError("Valor da doação fora do limite permitido.")
    return result


def _currency(value):
    currency = sanitize_text(value or "BRL", 3).upper()
    if len(currency) != 3 or not currency.isalpha():
        raise PaymentError("Moeda inválida.")
    return currency


def _donor_name(payload, metadata):
    donor = _first(payload.get("donor"), payload.get("payer"), payload.get("customer"), payload.get("customer_details"), payload.get("billing_details"))
    if isinstance(donor, dict):
        donor = _first(donor.get("name"), donor.get("displayName"), donor.get("email"))
    return sanitize_text(_first(donor, payload.get("donorName"), metadata.get("donor_name"), "Apoiador"), 160)


def _common(provider, external_id, streamer_id, amount_minor, currency, donor_name, message, metadata=None):
    streamer_id = sanitize_text(streamer_id, 160)
    if not streamer_id:
        raise PaymentError("Streamer de destino ausente.")
    provider = sanitize_text(provider, 32).lower()
    external_id = sanitize_text(external_id, 200)
    if not provider or not external_id:
        raise PaymentError("Identificador externo ausente.")
    amount = f"{amount_minor / 100:.2f}"
    event_data = {
        "eventId": f"{provider}:{external_id}",
        "donationId": external_id,
        "provider": provider,
        "streamerId": streamer_id,
        "amount": amount,
        "amountMinor": amount_minor,
        "currency": currency,
        "user": donor_name,
        "displayName": donor_name,
        "title": "Doação recebida",
        "message": sanitize_text(message or f"{donor_name} enviou {amount} {currency}", 4000),
        "status": "confirmed",
        "priority": 100,
    }
    return {
        "provider": provider,
        "externalId": external_id,
        "streamerId": streamer_id,
        "amountMinor": amount_minor,
        "amount": amount,
        "currency": currency,
        "donorName": donor_name,
        "message": event_data["message"],
        "status": "confirmed",
        "metadata": sanitize_value(metadata or {}),
        "eventData": event_data,
    }


def normalize_pix(payload, streamer_id):
    if not isinstance(payload, dict):
        raise PaymentError("Payload Pix inválido.")
    status = sanitize_text(payload.get("status") or payload.get("situacao") or "", 32).lower()
    if status not in PIX_CONFIRMED_STATUSES:
        raise PaymentError("Pix ainda não está confirmado.")
    metadata = _metadata(payload)
    amount = payload.get("amount")
    if isinstance(amount, dict):
        amount_value = _first(amount.get("value"), amount.get("valor"))
        amount_minor = _first(amount.get("amountMinor"), amount.get("minor"))
        currency = _first(amount.get("currency"), payload.get("currency"), "BRL")
    else:
        amount_value = amount
        amount_minor = _first(payload.get("amountMinor"), payload.get("valorCentavos"))
        currency = _first(payload.get("currency"), "BRL")
    return _common(
        "pix",
        _first(payload.get("id"), payload.get("txid"), payload.get("transactionId"), payload.get("e2eId")),
        _first(payload.get("streamerId"), payload.get("streamer_id"), metadata.get("streamerId"), metadata.get("streamer_id")),
        _amount_minor(amount_value, amount_minor),
        _currency(currency),
        _donor_name(payload, metadata),
        _first(payload.get("message"), payload.get("description"), metadata.get("message")),
        metadata,
    )


def normalize_stripe(payload, streamer_id):
    if not isinstance(payload, dict):
        raise PaymentError("Payload Stripe inválido.")
    event_type = sanitize_text(payload.get("type"), 80).lower()
    if event_type not in STRIPE_CONFIRMED_TYPES:
        raise PaymentError("Evento Stripe não representa pagamento confirmado.")
    obj = ((payload.get("data") or {}).get("object"))
    if not isinstance(obj, dict):
        raise PaymentError("Objeto Stripe ausente.")
    metadata = _metadata(obj)
    currency = _currency(_first(obj.get("currency"), metadata.get("currency"), "BRL"))
    amount_minor = _first(obj.get("amount_received"), obj.get("amount_total"), obj.get("amount"))
    customer_details = obj.get("customer_details") if isinstance(obj.get("customer_details"), dict) else {}
    donor_payload = {"customer_details": customer_details}
    donor_payload.update(obj)
    return _common(
        "stripe",
        _first(metadata.get("donation_id"), obj.get("payment_intent"), obj.get("id"), payload.get("id")),
        _first(metadata.get("streamer_id"), metadata.get("streamerId"), payload.get("streamerId")),
        _amount_minor(None, amount_minor),
        currency,
        _donor_name(donor_payload, metadata),
        _first(metadata.get("message"), obj.get("description")),
        metadata,
    )


def verify_pix_signature(raw_body, signature, secret):
    if not raw_body or not signature or not secret:
        return False
    value = str(signature).strip()
    if value.lower().startswith("sha256="):
        value = value[7:]
    expected = hmac.new(str(secret).encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(value, expected)


def verify_stripe_signature(raw_body, signature, secret, tolerance_seconds=300):
    if not raw_body or not signature or not secret:
        return False
    timestamp = None
    signatures = []
    for item in str(signature).split(","):
        name, _, value = item.strip().partition("=")
        if name == "t":
            timestamp = value
        elif name == "v1" and value:
            signatures.append(value)
    try:
        timestamp_int = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(int(time.time()) - timestamp_int) > tolerance_seconds:
        return False
    signed_payload = f"{timestamp_int}.".encode("utf-8") + raw_body
    expected = hmac.new(str(secret).encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(item, expected) for item in signatures)
