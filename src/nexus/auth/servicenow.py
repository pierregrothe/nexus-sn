# nexus/auth/servicenow.py
# ServiceNow instance credential storage per connection profile.
# Author: Pierre Grothe
# Date: 2026-05-07

"""SNAuth: store and retrieve ServiceNow credentials per instance profile."""

import logging
import os
import warnings

from nexus.auth.errors import AuthError
from nexus.auth.keychain import KeychainClient

log = logging.getLogger(__name__)

__all__ = ["SNAuth"]

_ENV_VAR_TEMPLATE = "NEXUS_SN_PASSWORD_{profile}"


class SNAuth:
    """Manage ServiceNow instance credentials.

    Resolution order for password:
      1. NEXUS_SN_PASSWORD_<PROFILE> environment variable (CI use)
      2. OS keychain under service "nexus-sn-<profile>"

    Args:
        keychain: KeychainClient instance. Defaults to a standard client.
    """

    def __init__(self, keychain: KeychainClient | None = None) -> None:
        """Initialize with optional keychain client."""
        warnings.warn(
            "SNAuth is deprecated. Use nexus.instances.SNOAuthClient instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._keychain = keychain or KeychainClient()

    def get_password(self, profile: str, username: str) -> str:
        """Return the password for a ServiceNow instance profile.

        Args:
            profile: Instance profile name, e.g. "dev12345".
            username: ServiceNow login username.

        Returns:
            The password string.

        Raises:
            AuthError: When no password is configured.
        """
        env_var = _ENV_VAR_TEMPLATE.format(profile=profile.upper())
        env_value = os.environ.get(env_var)
        if env_value:
            log.debug("SN password for profile=%s loaded from env", profile)
            return env_value

        return self._keychain.get(f"sn-{profile}", username)

    def store_password(self, profile: str, username: str, password: str) -> None:
        """Persist the password for a ServiceNow instance profile.

        Args:
            profile: Instance profile name.
            username: ServiceNow login username.
            password: Password to store. Never logged.
        """
        self._keychain.set(f"sn-{profile}", username, password)
        log.info("SN password stored for profile=%s username=%s", profile, username)

    def is_configured(self, profile: str, username: str) -> bool:
        """Return True if credentials are available for this profile.

        Args:
            profile: Instance profile name.
            username: ServiceNow login username.

        Returns:
            True when a password can be retrieved without raising AuthError.
        """
        env_var = _ENV_VAR_TEMPLATE.format(profile=profile.upper())
        if os.environ.get(env_var):
            return True
        try:
            self._keychain.get(f"sn-{profile}", username)
            return True
        except AuthError:
            return False
