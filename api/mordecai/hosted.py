"""Hosted mode: a closed demo that runs one provider on the server's own key.

Off unless HOSTED_PROVIDER names a supported provider. The app assumes it is reachable only
through a gated address that the hosting setup provides; it has no invite mechanism of its own.
When on, every request counts one attempt against a per-visitor limit, whichever provider (the
hosted one, a provider with the caller's own key, or the demo): ATTEMPTS per WINDOW_SECONDS for
each IPv4 address or IPv6 /64, held in this process's memory (one uvicorn worker; a restart
resets it). The client address comes from X-Forwarded-For only
when the connecting peer is in TRUSTED_PROXIES. The server key is read from the environment
once (reload() re-reads it) and is never logged or returned.
"""
from __future__ import annotations

import ipaddress
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from . import providers

log = logging.getLogger(__name__)

NAME = "hosted"
SERVER_KEY_ENV = {"gemini": "GEMINI_API_KEY"}
ATTEMPTS = 3
WINDOW_SECONDS = 24 * 60 * 60
SWEEP_AT = 4096
HOSTED_MAX_BUCKETS = 10000


@dataclass(frozen=True)
class Config:
    provider: str = ""
    key: str = field(default="", repr=False)
    trusted: tuple = ()

    @property
    def on(self) -> bool:
        return bool(self.provider)


def _split(value: str) -> list[str]:
    return [p.strip() for p in value.split(",") if p.strip()]


def load() -> Config:
    name = os.environ.get("HOSTED_PROVIDER", "").strip().lower()
    if not name:
        return Config()
    if name not in SERVER_KEY_ENV:
        log.warning("hosted: HOSTED_PROVIDER is not a supported provider; hosted mode is off")
        return Config()
    trusted = []
    for c in _split(os.environ.get("TRUSTED_PROXIES", "")):
        try:
            trusted.append(ipaddress.ip_network(c, strict=False))
        except ValueError:
            log.warning("hosted: a TRUSTED_PROXIES entry is not a CIDR and is ignored")
    return Config(name, os.environ.get(SERVER_KEY_ENV[name], "").strip(), tuple(trusted))


_config: Config | None = None
_lock = threading.Lock()


def config() -> Config:
    global _config
    with _lock:
        if _config is None:
            _config = load()
        return _config


def reload() -> Config:
    global _config
    with _lock:
        _config = load()
        return _config


def describe(cfg: Config) -> str:
    """One startup line with counts only: never the key."""
    if not cfg.on:
        return "hosted: off"
    return (f"hosted: provider={cfg.provider} key={'set' if cfg.key else 'unset'} "
            f"trusted_proxies={len(cfg.trusted)}")


class HostedProvider:
    """The configured provider, run on the server's key: no key from the user."""
    name = NAME
    needs_key = False
    hosted = True

    def __init__(self, base):
        self.base = base
        self.label = f"{base.name} (hosted)"
        self.notice = getattr(base, "hosted_notice", base.notice)

    def default_model(self):
        return self.base.default_model()

    def models(self):
        d = self.default_model()
        return [d] if d else []

    def efforts(self, model):
        """The hosted model runs at its lowest level only; the page shows it read-only."""
        return self.base.efforts(model)[:1] if model == self.default_model() else ()

    def render(self, req, key, *, model=None, effort=None):
        return self.base.render(req, key, model=model, effort=effort)

    def complete(self, system, user, key, *, max_tokens=1024, temperature=None):
        return self.base.complete(system, user, key, max_tokens=max_tokens, temperature=temperature)


def provider() -> HostedProvider | None:
    cfg = config()
    return HostedProvider(providers.get(cfg.provider)) if cfg.on else None


def public_list() -> list[dict]:
    p = provider()
    if p is None:
        return []
    return [{"name": p.name, "label": p.label, "needs_key": False, "hosted": True, "notice": p.notice,
             "models": providers.models_list(p)}]


def _addr(s: str | None):
    try:
        a = ipaddress.ip_address((s or "").strip())
    except ValueError:
        return None
    if a.version == 6 and a.ipv4_mapped:
        return a.ipv4_mapped
    return a


def _is_trusted(a, trusted) -> bool:
    return any(a in n for n in trusted)


def client_key(peer: str | None, xff: str | None, trusted) -> str:
    """The limit bucket: an IPv4 address or an IPv6 /64. X-Forwarded-For counts only behind a
    trusted peer, read right to left, skipping trusted hops; a malformed entry ends the walk."""
    a = _addr(peer)
    if a is None:
        return "peer:" + (peer or "unknown")[:64]
    if xff and _is_trusted(a, trusted):
        for part in reversed(xff.split(",")):
            b = _addr(part)
            if b is None:
                break
            a = b
            if not _is_trusted(b, trusted):
                break
    if a.version == 4:
        return str(a)
    return str(ipaddress.ip_network(f"{a}/64", strict=False))


class Limiter:
    def __init__(self, attempts: int = ATTEMPTS, window: float = WINDOW_SECONDS, clock=time.monotonic):
        self.attempts, self.window, self._clock = attempts, window, clock
        self._hits: dict[str, deque] = {}
        self._swept_at = float("-inf")
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        """Count one attempt; False, with nothing counted, once the key has used them all."""
        now = self._clock()
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.attempts:
                return False
            q.append(now)
            if len(self._hits) > SWEEP_AT:
                self._sweep(now)
            if len(self._hits) > HOSTED_MAX_BUCKETS:
                self._evict_oldest()
            return True

    def _sweep(self, now: float) -> None:
        """Drop expired buckets; at an unchanged clock nothing new can have expired, so skip."""
        if now <= self._swept_at:
            return
        self._swept_at = now
        for k in [k for k, v in self._hits.items() if not v or now - v[-1] >= self.window]:
            del self._hits[k]

    def _evict_oldest(self) -> None:
        """Over the hard cap after the sweep: drop the buckets with the oldest window start, down
        to a tenth below the cap so the sort is paid once per batch (those clients start fresh)."""
        keep = HOSTED_MAX_BUCKETS - HOSTED_MAX_BUCKETS // 10
        oldest = sorted(self._hits, key=lambda k: self._hits[k][0] if self._hits[k] else float("-inf"))
        for k in oldest[:len(self._hits) - keep]:
            del self._hits[k]

    def __len__(self) -> int:
        return len(self._hits)


LIMITER = Limiter()
