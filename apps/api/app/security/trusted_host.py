from __future__ import annotations

import ipaddress

from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import Receive, Scope, Send


class HealthCheckTrustedHostMiddleware(TrustedHostMiddleware):
    """Permit load-balancer target-IP host headers only on health probes."""

    _health_paths = frozenset({"/health", "/ready"})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] in {"http", "websocket"}
            and scope.get("path") in self._health_paths
            and self._host_is_ip_literal(scope)
        ):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)

    @staticmethod
    def _host_is_ip_literal(scope: Scope) -> bool:
        raw_host = next(
            (
                value.decode("latin-1")
                for name, value in scope.get("headers", [])
                if name.lower() == b"host"
            ),
            "",
        )
        if raw_host.startswith("["):
            closing_bracket = raw_host.find("]")
            candidate = raw_host[1:closing_bracket] if closing_bracket > 0 else ""
        else:
            candidate = raw_host.rsplit(":", 1)[0]
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            return False
        return True
