from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests


class SpacetimeError(Exception):
    """Raised when the SpacetimeDB server returns an error."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _hex(value: Any) -> str | None:
    """Normalise identities/hashes: ``{"__identity__": "0xabc"}`` / ``"0xabc"`` -> ``"abc"``."""
    if value is None:
        return None
    if isinstance(value, dict):
        value = next(iter(value.values()), None)
        if value is None:
            return None
    s = str(value)
    return s[2:] if s.startswith("0x") else s


def _tag(value: Any) -> str | None:
    """Normalise unit enums: ``{"Js": []}`` -> ``"Js"``."""
    if isinstance(value, dict) and value:
        return next(iter(value.keys()))
    return None if value is None else str(value)


@dataclass
class DatabaseInfo:
    identity: str
    owner_identity: str | None = None
    host_type: str | None = None
    initial_program: str | None = None
    names: list[str] | None = None

    @property
    def display_name(self) -> str:
        if self.names:
            return self.names[0]
        return self.short_identity

    @property
    def short_identity(self) -> str:
        return f"{self.identity[:8]}…{self.identity[-6:]}" if len(self.identity) > 16 else self.identity

    @property
    def ref(self) -> str:
        """Best identifier to use in URLs."""
        return self.names[0] if self.names else self.identity


class SpacetimeClient:
    def __init__(self, host: str, token: str | None = None, timeout: float = 15.0):
        self.host = host.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._session = requests.Session()

    # ----------------------------------------------------------- plumbing
    def _headers(self, auth: bool = True, extra: dict | None = None) -> dict:
        h: dict[str, str] = {}
        if auth and self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if extra:
            h.update(extra)
        return h

    def _request(self, method: str, path: str, *, auth: bool = True, **kw) -> requests.Response:
        url = f"{self.host}{path}"
        kw.setdefault("timeout", self.timeout)
        kw["headers"] = self._headers(auth, kw.pop("headers", None))
        try:
            resp = self._session.request(method, url, **kw)
        except requests.ConnectionError as e:
            raise SpacetimeError(f"Could not connect to SpacetimeDB at {self.host}: {e}") from e
        except requests.Timeout as e:
            raise SpacetimeError(f"Request to {url} timed out") from e
        if resp.status_code >= 400:
            body = resp.text.strip()
            try:
                parsed = resp.json()
                body = json.dumps(parsed) if not isinstance(parsed, str) else parsed
            except ValueError:
                pass
            raise SpacetimeError(body or f"HTTP {resp.status_code} {resp.reason}", resp.status_code)
        return resp

    # ------------------------------------------------------------- server
    def ping(self) -> bool:
        try:
            self._request("GET", "/v1/ping", auth=False, timeout=3)
            return True
        except SpacetimeError:
            return False

    def create_identity(self) -> dict:
        return self._request("POST", "/v1/identity", auth=False).json()

    def verify_identity(self, identity: str) -> bool:
        try:
            self._request("GET", f"/v1/identity/{identity}/verify")
            return True
        except SpacetimeError:
            return False

    def public_key(self) -> str:
        return self._request("GET", "/v1/identity/public-key", auth=False).text

    # ---------------------------------------------------------- databases
    def databases_owned_by(self, identity: str) -> list[str]:
        data = self._request("GET", f"/v1/identity/{identity}/databases").json()
        # Older servers returned {"addresses": [...]}.
        return [_hex(i) for i in (data.get("identities") or data.get("addresses") or []) if _hex(i)]

    def database_info(self, name_or_identity: str) -> DatabaseInfo:
        data = self._request("GET", f"/v1/database/{name_or_identity}").json()
        info = DatabaseInfo(
            identity=_hex(data.get("database_identity") or data.get("identity")) or name_or_identity,
            owner_identity=_hex(data.get("owner_identity")),
            host_type=_tag(data.get("host_type")),
            initial_program=_hex(data.get("initial_program")),
        )
        try:
            info.names = self.database_names(info.identity)
        except SpacetimeError:
            info.names = []
        return info

    def database_names(self, name_or_identity: str) -> list[str]:
        data = self._request("GET", f"/v1/database/{name_or_identity}/names", auth=False).json()
        return list(data.get("names") or [])

    def add_database_name(self, name_or_identity: str, new_name: str) -> dict:
        return self._request(
            "POST", f"/v1/database/{name_or_identity}/names", data=new_name,
            headers={"Content-Type": "text/plain"},
        ).json()

    def set_database_names(self, name_or_identity: str, names: list[str]) -> dict:
        return self._request("PUT", f"/v1/database/{name_or_identity}/names", json=names).json()

    def delete_database(self, name_or_identity: str) -> None:
        self._request("DELETE", f"/v1/database/{name_or_identity}")

    def publish(self, program: bytes, name: str | None = None, clear: bool = False,
                host_type: str = "Wasm") -> dict:
        """Publish a module. ``host_type`` is ``"Wasm"`` or ``"Js"`` (TypeScript bundles)."""
        headers = {"Content-Type": "application/octet-stream"}
        params: dict[str, str] = {"host_type": host_type}
        if name:
            if clear:
                params["clear"] = "true"
            resp = self._request("PUT", f"/v1/database/{name}", params=params, data=program, headers=headers, timeout=120)
        else:
            resp = self._request("POST", "/v1/database", params=params, data=program, headers=headers, timeout=120)
        return resp.json()

    def schema(self, name_or_identity: str, version: int = 9) -> dict:
        return self._request(
            "GET", f"/v1/database/{name_or_identity}/schema", params={"version": version}
        ).json()

    def logs(self, name_or_identity: str, num_lines: int = 200) -> list[dict]:
        text = self._request(
            "GET", f"/v1/database/{name_or_identity}/logs", params={"num_lines": num_lines}
        ).text
        out: list[dict] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if not isinstance(entry, dict):
                    entry = {"message": str(entry)}
            except ValueError:
                entry = {"message": line}
            out.append(entry)
        return out

    def sql(self, name_or_identity: str, query: str) -> list[dict]:
        resp = self._request(
            "POST", f"/v1/database/{name_or_identity}/sql", data=query.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"}, timeout=60,
        )
        data = resp.json()
        return data if isinstance(data, list) else [data]

    def call_reducer(self, name_or_identity: str, reducer: str, args: list[Any]) -> Any:
        resp = self._request("POST", f"/v1/database/{name_or_identity}/call/{reducer}", json=args, timeout=60)
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text
