"""Local capability-token management for the dashboard and Browser Source URLs."""

import hmac
import json
import os
import secrets
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


OVERLAY_KINDS = ("chat", "events")
TOKEN_BYTES = 32


def _new_token():
    return secrets.token_urlsafe(TOKEN_BYTES)


def _timestamp():
    return int(time.time())


class SecurityManager:
    """Persisted local capabilities with atomic updates and constant-time checks."""

    def __init__(self, config_path):
        self.config_path = os.path.abspath(config_path)
        self._lock = threading.RLock()
        self._state = self._load_or_create()

    def _default_state(self):
        created_at = _timestamp()
        return {
            "version": 1,
            "adminToken": _new_token(),
            "overlays": {
                kind: {"token": _new_token(), "createdAt": created_at, "revokedAt": None}
                for kind in OVERLAY_KINDS
            },
        }

    def _load_or_create(self):
        try:
            with open(self.config_path, "r", encoding="utf-8") as handle:
                state = json.load(handle)
            if not isinstance(state, dict) or not isinstance(state.get("adminToken"), str):
                raise ValueError("security state inválido")
            overlays = state.get("overlays")
            if not isinstance(overlays, dict):
                raise ValueError("tokens de overlay inválidos")
            for kind in OVERLAY_KINDS:
                item = overlays.get(kind)
                if not isinstance(item, dict) or not isinstance(item.get("token"), str):
                    raise ValueError("token de overlay inválido")
            state["version"] = 1
            return state
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            state = self._default_state()
            self._persist(state)
            return state

    def _persist(self, state=None):
        payload = state if state is not None else self._state
        directory = os.path.dirname(self.config_path)
        os.makedirs(directory, exist_ok=True)
        temporary = self.config_path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.config_path)

    @staticmethod
    def _candidate_tokens(request, allow_query=False):
        candidates = []
        header = request.headers.get("X-Netrunner-Admin-Token")
        if header:
            candidates.append(header)
        authorization = request.headers.get("Authorization", "")
        if authorization.lower().startswith("bearer "):
            candidates.append(authorization[7:].strip())
        cookie = request.cookies.get("netrunner_admin")
        if cookie:
            candidates.append(cookie)
        if allow_query:
            query_token = request.args.get("admin")
            if query_token:
                candidates.append(query_token)
        return candidates

    @staticmethod
    def _overlay_candidates(request):
        candidates = []
        query_token = request.args.get("token")
        if query_token:
            candidates.append(query_token)
        header = request.headers.get("X-Netrunner-Overlay-Token")
        if header:
            candidates.append(header)
        authorization = request.headers.get("Authorization", "")
        if authorization.lower().startswith("bearer "):
            candidates.append(authorization[7:].strip())
        return candidates

    @staticmethod
    def _matches(candidates, expected):
        if not expected or not isinstance(expected, str):
            return False
        return any(
            isinstance(candidate, str) and hmac.compare_digest(candidate, expected)
            for candidate in candidates
        )

    def authenticate_admin(self, request, allow_query=False):
        with self._lock:
            expected = self._state.get("adminToken", "")
        return self._matches(self._candidate_tokens(request, allow_query), expected)

    def authenticate_overlay(self, kind, request):
        if kind not in OVERLAY_KINDS:
            return False
        return self.authenticate_overlay_token(kind, self._overlay_candidates(request))

    def authenticate_overlay_token(self, kind, candidates):
        if kind not in OVERLAY_KINDS:
            return False
        with self._lock:
            record = self._state["overlays"].get(kind, {})
            expected = record.get("token", "") if not record.get("revokedAt") else ""
        if isinstance(candidates, str):
            candidates = [candidates]
        return self._matches(candidates, expected)

    def authenticate_any_overlay(self, request):
        return any(self.authenticate_overlay(kind, request) for kind in OVERLAY_KINDS)

    def admin_token(self):
        with self._lock:
            return self._state["adminToken"]

    def overlay_token(self, kind):
        if kind not in OVERLAY_KINDS:
            raise ValueError("overlay desconhecido")
        with self._lock:
            record = self._state["overlays"][kind]
            return record["token"] if not record.get("revokedAt") else ""

    @staticmethod
    def _with_query(url, values):
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.update(values)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    def overlay_url(self, kind, base_url):
        token = self.overlay_token(kind)
        return self._with_query(base_url, {"token": token}) if token else ""

    def admin_access_url(self, base_url):
        return self._with_query(base_url, {"admin": self.admin_token()})

    def rotate_overlay(self, kind):
        if kind not in OVERLAY_KINDS:
            return {"ok": False, "message": "Overlay desconhecido."}
        with self._lock:
            record = self._state["overlays"][kind]
            record["token"] = _new_token()
            record["createdAt"] = _timestamp()
            record["revokedAt"] = None
            self._persist()
            return {"ok": True, "kind": kind, "message": "Token rotacionado. O link anterior foi invalidado."}

    def revoke_overlay(self, kind):
        if kind not in OVERLAY_KINDS:
            return {"ok": False, "message": "Overlay desconhecido."}
        with self._lock:
            record = self._state["overlays"][kind]
            record["token"] = ""
            record["revokedAt"] = _timestamp()
            self._persist()
            return {"ok": True, "kind": kind, "message": "Token revogado. Gere um novo link para reativar o overlay."}

    def snapshot(self, base_urls):
        with self._lock:
            overlays = {}
            for kind in OVERLAY_KINDS:
                record = self._state["overlays"][kind]
                token = record.get("token", "")
                overlays[kind] = {
                    "active": bool(token) and not record.get("revokedAt"),
                    "createdAt": record.get("createdAt"),
                    "revokedAt": record.get("revokedAt"),
                    "url": self._with_query(base_urls[kind], {"token": token}) if token else "",
                    "tokenHint": (token[:6] + "…") if token else None,
                }
            admin_token = self._state.get("adminToken", "")
            return {
                "admin": {"active": bool(admin_token), "tokenHint": (admin_token[:6] + "…") if admin_token else None},
                "overlays": overlays,
            }
