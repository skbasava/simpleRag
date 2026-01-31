import time
import threading
import requests
from typing import Optional, Dict, Any


# =========================
# Exceptions
# =========================

class IPCatalogError(Exception):
    pass


class IPCatalogAuthError(IPCatalogError):
    pass


class IPCatalogRequestError(IPCatalogError):
    pass


# =========================
# Token Manager
# =========================

class TokenManager:
    """
    Thread-safe token cache with lazy refresh.
    """

    def __init__(
        self,
        client: "IPCatalogClient",
        username: Optional[str] = None,
        password: Optional[str] = None,
        ttl_seconds: int = 3600,
    ):
        self.client = client
        self.username = username
        self.password = password
        self.ttl_seconds = ttl_seconds

        self._token: Optional[str] = None
        self._expiry: float = 0
        self._lock = threading.Lock()

    def get_token(self) -> str:
        with self._lock:
            now = time.time()

            if self._token and now < self._expiry - 60:
                return self._token

            self._refresh_token()
            return self._token

    def _refresh_token(self):
        if not self.username or not self.password:
            raise IPCatalogAuthError("Username/password not provided for token refresh")

        token = self.client._fetch_token(self.username, self.password)

        self._token = token
        self._expiry = time.time() + self.ttl_seconds

        # attach token to client
        self.client.set_token(token)


# =========================
# IPCatalog Client
# =========================

class IPCatalogClient:
    """
    Production-grade IPCatalog API client.
    """

    def __init__(
        self,
        base_url: str,
        timeout: int = 15,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        verify_ssl: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.verify_ssl = verify_ssl

        self.session = requests.Session()
        self.token: Optional[str] = None
        self.token_manager: Optional[TokenManager] = None

    # -------------------------
    # Token handling
    # -------------------------

    def set_token(self, token: str):
        self.token = token

    def _fetch_token(self, username: str, password: str) -> str:
        """
        Calls: POST auth/token/login/
        """
        url = f"{self.base_url}/auth/token/login/"
        resp = self.session.post(
            url,
            json={"username": username, "password": password},
            timeout=self.timeout,
            verify=self.verify_ssl,
        )

        if resp.status_code != 200:
            raise IPCatalogAuthError(
                f"Token fetch failed ({resp.status_code}): {resp.text}"
            )

        data = resp.json()
        if "token" not in data:
            raise IPCatalogAuthError("Token missing in auth response")

        return data["token"]

    # -------------------------
    # Core request method
    # -------------------------

    def request(
        self,
        method: str,
        api: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        files: Any = None,
        response: str = "json",
    ):
        url = api if api.startswith("http") else f"{self.base_url}/{api.lstrip('/')}"

        headers = {}
        if self.token_manager:
            headers["Authorization"] = f"Token {self.token_manager.get_token()}"
        elif self.token:
            headers["Authorization"] = f"Token {self.token}"

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.request(
                    method=method.upper(),
                    url=url,
                    params=params if method.upper() == "GET" else None,
                    json=json_body if method.upper() != "GET" else None,
                    files=files,
                    headers=headers,
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                )

                if resp.status_code in (401, 403):
                    # force token refresh once
                    if self.token_manager:
                        self.token_manager._refresh_token()
                        continue
                    raise IPCatalogAuthError("Unauthorized")

                if resp.status_code >= 400:
                    raise IPCatalogRequestError(
                        f"HTTP {resp.status_code}: {resp.text}"
                    )

                if response == "raw":
                    return resp
                if response == "text":
                    return resp.text
                return resp.json()

            except (requests.RequestException, IPCatalogRequestError) as e:
                if attempt == self.max_retries:
                    raise

                sleep_time = self.backoff_base * (2 ** (attempt - 1))
                time.sleep(sleep_time)

    # -------------------------
    # Convenience wrappers
    # -------------------------

    def get(self, api: str, params=None, response="json"):
        return self.request("GET", api, params=params, response=response)

    def post(self, api: str, json_body=None, files=None, response="json"):
        return self.request("POST", api, json_body=json_body, files=files, response=response)

    def put(self, api: str, json_body=None, response="json"):
        return self.request("PUT", api, json_body=json_body, response=response)

    def delete(self, api: str, params=None, response="json"):
        return self.request("DELETE", api, params=params, response=response)


# =========================
# Example usage
# =========================
if __name__ == "__main__":
    client = IPCatalogClient(
        base_url="https://ipcatalog-api.qualcomm.com/api/1/",
    )

    token_manager = TokenManager(
        client=client,
        username="YOUR_USERNAME",
        password="YOUR_PASSWORD",
    )

    client.token_manager = token_manager

    # Example API call
    data = client.get("projects/")
    print(data)