"""macOS Keychain integration for secure credential storage."""

import subprocess
from dataclasses import dataclass

KEYCHAIN_KEYS = {
    "client_id": "zscaler-mcp-client-id",
    "client_secret": "zscaler-mcp-client-secret",
    "customer_id": "zscaler-mcp-customer-id",
    "vanity_domain": "zscaler-mcp-vanity-domain",
    "zia_cloud": "zscaler-mcp-zia-cloud",
}

LABELS = {
    "client_id": "Client ID",
    "client_secret": "Client Secret",
    "customer_id": "Customer ID (Zscaler Tenant)",
    "vanity_domain": "Vanity Domain",
    "zia_cloud": "ZIA Cloud Name",
}


@dataclass
class ZscalerCredentials:
    client_id: str = ""
    client_secret: str = ""
    customer_id: str = ""
    vanity_domain: str = ""
    zia_cloud: str = ""

    def is_complete(self) -> bool:
        return all([
            self.client_id,
            self.client_secret,
            self.customer_id,
            self.vanity_domain,
            self.zia_cloud,
        ])

    def as_env(self) -> dict[str, str]:
        return {
            "ZSCALER_CLIENT_ID": self.client_id,
            "ZSCALER_CLIENT_SECRET": self.client_secret,
            "ZSCALER_CUSTOMER_ID": self.customer_id,
            "ZSCALER_VANITY_DOMAIN": self.vanity_domain,
            "ZSCALER_CLOUD": self.zia_cloud,
        }


def read_keychain(service: str) -> str | None:
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-w"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def write_keychain(service: str, value: str) -> bool:
    try:
        # `-U` replaces an existing item without a delete/create gap.
        result = subprocess.run(
            [
                "security",
                "add-generic-password",
                "-s", service,
                "-a", "zsguardian",
                "-w", value,
                "-U",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def delete_keychain(service: str) -> bool:
    """Delete a saved item; a missing item is already the desired state."""
    try:
        result = subprocess.run(
            ["security", "delete-generic-password", "-s", service],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 or "could not be found" in result.stderr.lower()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def load_credentials() -> ZscalerCredentials:
    creds = ZscalerCredentials()
    for field, service in KEYCHAIN_KEYS.items():
        value = read_keychain(service)
        if value:
            setattr(creds, field, value)
    return creds


def save_credentials(creds: ZscalerCredentials) -> bool:
    success = True
    for field, service in KEYCHAIN_KEYS.items():
        value = getattr(creds, field)
        if value:
            if not write_keychain(service, value):
                success = False
        elif not delete_keychain(service):
            success = False
    return success
