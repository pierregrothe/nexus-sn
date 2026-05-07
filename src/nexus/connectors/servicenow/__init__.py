# nexus/connectors/servicenow/__init__.py
# ServiceNow REST connector public exports.
# Author: Pierre Grothe
# Date: 2026-05-07

"""ServiceNow REST API connector -- the built-in NEXUS connector."""

from nexus.connectors.servicenow.client import ServiceNowClient
from nexus.connectors.servicenow.connector import ServiceNowConnector
from nexus.connectors.servicenow.errors import SNAuthError, SNClientError, SNNotFoundError

__all__ = [
    "ServiceNowClient",
    "ServiceNowConnector",
    "SNAuthError",
    "SNClientError",
    "SNNotFoundError",
]
