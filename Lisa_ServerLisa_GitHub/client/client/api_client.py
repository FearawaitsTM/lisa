import threading

import requests
from requests.adapters import HTTPAdapter

from .constants import CURRENT_VERSION
from .utils import normalize_server_url, validate_date


class ApiClient:
    def __init__(self, server_url):
        self.server_url = normalize_server_url(server_url)
        self._thread_local = threading.local()

    def _session(self):
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update(
                {"Connection": "keep-alive", "User-Agent": f"LisaClient/{CURRENT_VERSION}"}
            )
            adapter = HTTPAdapter(pool_connections=4, pool_maxsize=8)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            self._thread_local.session = session
        return session

    def request(self, method, path, **kwargs):
        return self._session().request(method, f"{self.server_url}{path}", **kwargs)

    def update_server_url(self, server_url):
        self.server_url = normalize_server_url(server_url)

    def get_report_file(self, date_from, date_to):
        validate_date(date_from)
        validate_date(date_to)
        response = self.request(
            "GET",
            "/report",
            params={"date_from": date_from, "date_to": date_to},
            timeout=(10, 300),
        )
        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            try:
                error_message = response.json().get("error", response.text)
            except Exception:
                error_message = response.text
            raise RuntimeError(error_message)
        response.raise_for_status()
        if not response.content:
            raise RuntimeError("Сервер прислал пустой файл")
        return response.content

    def list_night_employees(self):
        response = self.request("GET", "/night-employees", timeout=20)
        response.raise_for_status()
        return response.json()

    def add_night_employee(self, name, tab_number="", valid_from="", valid_to=""):
        response = self.request(
            "POST",
            "/night-employees",
            json={
                "name": name,
                "tab_number": tab_number,
                "valid_from": valid_from,
                "valid_to": valid_to or None,
            },
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def delete_night_employee(self, employee_id):
        response = self.request(
            "DELETE",
            f"/night-employees/{employee_id}",
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def get_update_manifest(self):
        response = self.request(
            "GET",
            "/updates/version.json",
            timeout=15,
            headers={"Cache-Control": "no-cache"},
        )
        response.raise_for_status()
        return response.json()
