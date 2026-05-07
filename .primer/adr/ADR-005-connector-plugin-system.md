# ADR-005: Connector plugin system

**Status:** accepted
**Date:** 2026-05-07
**Enforcement:** agent

## Context

ServiceNow is the first and primary connector, but future connectors (JIRA,
GitHub, Confluence) were anticipated in the JARVIS analysis. Hard-coding
ServiceNow throughout the codebase would make adding connectors require
invasive changes.

## Decision

Connectors are defined via ConnectorProtocol. ConnectorRegistry discovers
registered connectors by class name. ServiceNow REST is built-in; enterprise
MCP connectors are optional. New connectors can be added without modifying
core code -- they inherit ConnectorProtocol and register themselves.

## Consequences

ServiceNowClient must not be imported directly outside the connectors/ layer.
All tool calls go through ConnectorRegistry.get(). This is enforced by the
layer-order agent rule. Future connectors contribute a Protocol implementation
and a registration call; no changes to api/, agents/, or cli.py are required.
The ConnectorRegistry must be initialized before any layer-5 code runs.
