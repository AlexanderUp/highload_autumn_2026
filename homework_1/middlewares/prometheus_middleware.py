import time

from fastapi import Request
from starlette.routing import Match

from core.config import settings
from core.prometheus_metrics import (
    http_errors_4xx_total,
    http_errors_5xx_total,
    http_request_duration_seconds,
    http_requests_total,
)

EXCLUDED_ENDPOINTS_NAMES: list[str] = ["metrics_endpoint", "health_endpoint"]


class MetricsMiddleware:

    def __init__(self, excluded: list[str] | None = None):
        self.excluded: list[str] = excluded or EXCLUDED_ENDPOINTS_NAMES

    async def __call__(self, request: Request, call_next):
        start_time = time.time()

        response = await call_next(request)

        duration = time.time() - start_time
        route = request.scope.get("route")

        if route:
            path = route.path
            name = route.name
        else:
            path = request.scope["path"]
            name = "unknown"

        if name in self.excluded:
            return response

        http_requests_total.labels(
            pod_id=settings.pod_id,
            datacenter=settings.datacenter,
            method=request.method,
            endpoint=path,
            name=name,
            status_code=str(response.status_code),
        ).inc()

        http_request_duration_seconds.labels(
            pod_id=settings.pod_id,
            datacenter=settings.datacenter,
            method=request.method,
            endpoint=path,
            name=name,
        ).observe(duration)

        status_code = response.status_code

        if 400 <= status_code < 500:
            http_errors_4xx_total.labels(
                pod_id=settings.pod_id,
                datacenter=settings.datacenter,
                endpoint=path,
                name=name,
                status_code=str(status_code),
            ).inc()
        elif status_code >= 500:
            http_errors_5xx_total.labels(
                pod_id=settings.pod_id,
                datacenter=settings.datacenter,
                endpoint=path,
                name=name,
                status_code=str(status_code),
            ).inc()

        return response
