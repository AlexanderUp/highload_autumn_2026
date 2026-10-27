from grafana_foundation_sdk.builders.dashboard import Dashboard
from grafana_foundation_sdk.builders.prometheus import (
    Dataquery as PrometheusQuery,
)
from grafana_foundation_sdk.builders.timeseries import Panel as Timeseries
from grafana_foundation_sdk.cog.encoder import JSONEncoder
from grafana_foundation_sdk.models import units
from grafana_foundation_sdk.models.common import TimeZoneBrowser

GRAFANA_UID = "highload-service-dashboard"


def build_rps_panel(endpoint_name: str) -> Timeseries:
    prom_qs_fragments = [
        "sum(rate(http_requests_total{",
        f"endpoint='{endpoint_name}'",
        "}[$__rate_interval])) by (method, status_code)",
    ]
    rps_query = (
        PrometheusQuery()
        .expr("".join(prom_qs_fragments))
        .legend_format("{{method}} {{endpoint}} {{status_code}}")
    )
    return (
        Timeseries()
        .title(f"HTTP Requests Rate {endpoint_name}")
        .description(
            f"Number of total HTTP requests per second for endpoint {endpoint_name}"
        )
        .unit(units.RequestsPerSecond)
        .datasource({"type": "prometheus", "uid": "prometheus_datasource_v1"})
        .with_target(rps_query)
    )


def build_histogram_panel(endpoint_name: str) -> Timeseries:
    prom_qs_fragments_50 = [
        "histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket{",
        f"endpoint='{endpoint_name}'",
        "}[$__rate_interval])) by (le, method))",
    ]
    prom_qs_fragments_95 = [
        "histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{",
        f"endpoint='{endpoint_name}'",
        "}[$__rate_interval])) by (le, method))",
    ]
    prom_qs_fragments_99 = [
        "histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{",
        f"endpoint='{endpoint_name}'",
        "}[$__rate_interval])) by (le, method))",
    ]

    histo50_query = (
        PrometheusQuery()
        .expr("".join(prom_qs_fragments_50))
        .legend_format("p50 - {{method}} {{endpoint}}")
    )
    histo95_query = (
        PrometheusQuery()
        .expr("".join(prom_qs_fragments_95))
        .legend_format("p95 - {{method}} {{endpoint}}")
    )
    histo99_query = (
        PrometheusQuery()
        .expr("".join(prom_qs_fragments_99))
        .legend_format("p99 - {{method}} {{endpoint}}")
    )
    return (
        Timeseries()
        .title(f"Latency {endpoint_name}")
        .description(
            f"50th, 95th and 99th percentiles of request duration over $__rate_interval window {endpoint_name}"
        )
        .unit(units.Seconds)
        .datasource({"type": "prometheus", "uid": "prometheus_datasource_v1"})
        .with_target(histo50_query)
        .with_target(histo95_query)
        .with_target(histo99_query)
    )


def build_error_panel(endpoint_name: str) -> Timeseries:
    prom_qs_fragments_4xx = [
        "sum(rate(http_errors_4xx_total{",
        f"endpoint='{endpoint_name}'",
        "}[$__rate_interval])) by (method)",
    ]
    prom_qs_fragments_5xx = [
        "sum(rate(http_errors_5xx_total{",
        f"endpoint='{endpoint_name}'",
        "}[$__rate_interval])) by (method)",
    ]

    query_4xx = (
        PrometheusQuery()
        .ref_id("A")
        .expr("".join(prom_qs_fragments_4xx))
        .legend_format("4xx - {{method}} {{endpoint}}")
    )
    query_5xx = (
        PrometheusQuery()
        .ref_id("B")
        .expr("".join(prom_qs_fragments_5xx))
        .legend_format("5xx - {{method}} {{endpoint}}")
    )
    return (
        Timeseries()
        .title(f"HTTP Error Rates (4xx vs 5xx) {endpoint_name}")
        .description(
            f"Rate of 4xx and 5xx client/server errors per second averaged over $__rate_interval {endpoint_name}"
        )
        .unit(units.RequestsPerSecond)
        .datasource({"type": "prometheus", "uid": "prometheus_datasource_v1"})
        .with_target(query_4xx)
        .with_target(query_5xx)
    )


def generate_dashboard(endpoint_list: list[str]):
    dashboard = (
        Dashboard("Highload service dashboard")
        .id(None)
        .uid(GRAFANA_UID)
        .refresh("10s")
        .time("now-1h", "now")
        .timezone(TimeZoneBrowser)
    )

    for endpoint in endpoint_list:
        rps_panel = build_rps_panel(endpoint)
        dashboard.with_panel(rps_panel)

        histogram_panel = build_histogram_panel(endpoint)
        dashboard.with_panel(histogram_panel)

        errors_panel = build_error_panel(endpoint)
        dashboard.with_panel(errors_panel)

    dashboard_data = dashboard.build()
    return JSONEncoder(sort_keys=True, indent=2).encode(dashboard_data)
