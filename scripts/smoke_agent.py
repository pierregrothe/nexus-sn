# scripts/smoke_agent.py
# End-to-end smoke test for AgentClient against the real Anthropic API.
# Author: Pierre Grothe
# Date: 2026-05-08
"""End-to-end smoke test for AgentClient backed by claude-agent-sdk.

Run with:
    .venv/bin/python scripts/smoke_agent.py

Auth is handled automatically by claude-agent-sdk:
  - ANTHROPIC_API_KEY env var
  - Claude Code stored credentials (env var, file, or macOS Keychain)

Validates:
  1. Real API call via claude-agent-sdk works (no API key required)
  2. Two consecutive calls succeed
"""

import asyncio
import logging
import sys

from nexus.api.agent_client import AgentClient


async def main() -> int:
    """Run the smoke test and return an exit code."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s -- %(message)s",
    )
    log = logging.getLogger("smoke-agent")

    client = AgentClient()
    system_prompt = (
        "You are a terse assistant. Answer in one short sentence. "
        "If asked about NEXUS, say it is a ServiceNow AI architect tool."
    )

    log.info("Sending first call...")
    msg1 = await client.complete("What is NEXUS?", system=system_prompt)
    print("Response 1:", msg1)

    log.info("Sending second call...")
    msg2 = await client.complete("What is the capital of France?", system=system_prompt)
    print("Response 2:", msg2)

    print("\nSUCCESS: both calls completed.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
