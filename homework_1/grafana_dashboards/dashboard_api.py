import json
import logging
import os

import requests
from metrics_dashboard import GRAFANA_UID, generate_dashboard

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# TODO: add retries and exception handling


def get_handlers_list(app_host: str) -> list[str]:
    response = requests.get(f"http://{app_host}:8000/handlers")
    return response.json()


class GrafanaDashboardAPI:
    def __init__(self, grafana_host: str, grafana_service_token: str) -> None:
        self.grafana_host = grafana_host
        self.grafana_service_token = grafana_service_token
        self._headers: dict[str] = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.grafana_service_token}",
        }

    def create_dashboard(
        self, dashboard_json: str, grafana_uid: str = GRAFANA_UID
    ) -> requests.Response:
        self.delete_dash_board(grafana_uid)

        url = f"http://{self.grafana_host}:3000/apis/dashboard.grafana.app/v1/namespaces/default/dashboards"
        payload = {
            "metadata": {
                "name": grafana_uid,
            },
            "spec": json.loads(dashboard_json),
            "overwrite": True,
        }
        return requests.post(url, headers=self._headers, json=payload)

    def delete_dash_board(
        self, grafana_uid: str = GRAFANA_UID
    ) -> requests.Response:
        url = f"http://{self.grafana_host}:3000/apis/dashboard.grafana.app/v1/namespaces/default/dashboards/{grafana_uid}"
        return requests.delete(url, headers=self._headers)


if __name__ == "__main__":
    logger.info("Start dashboard creation.")

    app_host: str = os.getenv("APP_HOST")
    grafana_host: str = os.getenv("GRAFANA_HOST")
    service_token = os.getenv("SERVICE_ACCOUNT_TOKEN")

    handlers_list = get_handlers_list(app_host)
    dashboard_stringified = generate_dashboard(handlers_list)

    dashboard_api = GrafanaDashboardAPI(grafana_host, service_token)
    response = dashboard_api.create_dashboard(dashboard_stringified)

    logger.info("Dashboard created.")
