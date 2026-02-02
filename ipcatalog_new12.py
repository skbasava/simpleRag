import requests
import time
from token_manager import TokenManager

class IPCatalogClient:
    """
    Thin API client with retry + backoff.
    """

    def __init__(self, base_url, token_manager):
        self.base_url = base_url.rstrip("/")
        self.token_manager = token_manager

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token_manager.get_token()}",
            "Accept": "application/json"
        }

    def request(self, method, path, retries=3):
        url = f"{self.base_url}{path}"
        for attempt in range(retries):
            resp = requests.request(
                method,
                url,
                headers=self._headers(),
                timeout=30
            )
            if resp.status_code == 401:
                self.token_manager._refresh()
                continue
            if resp.ok:
                return resp.json()
            time.sleep(2 ** attempt)
        resp.raise_for_status()

    def list_chips(self):
        return self.request("GET", "/chip/")

    def list_xpu_policies(self, chip_id, version):
        return self.request(
            "GET",
            f"/xpu/policy/?chip={chip_id}&version={version}"
        )

    def export_policy(self, policy_id):
        return self.request(
            "POST",
            f"/xpu/policy/{policy_id}/export"
        )