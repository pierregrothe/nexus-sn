# scripts/smoke_anthropic.py
# Manual smoke test for AnthropicClient against the real Anthropic API.
# Author: Pierre Grothe
# Date: 2026-05-07

"""End-to-end smoke test for AnthropicClient with default auth providers.

Run with:
    .venv/bin/python scripts/smoke_anthropic.py

Picks up auth automatically:
  - ClaudeCodeOAuthProvider (uses ~/.claude/.credentials.json or Keychain)
  - AnthropicAPIKeyProvider (uses NEXUS_CLAUDE_API_KEY or nexus keychain)

Validates:
  1. Default provider chain resolves to an authenticated client
  2. AnthropicClient auto-discovers the newest Sonnet via models.list()
  3. complete() makes a real API call with prompt caching on system prompt
  4. Two consecutive calls with the same system prompt produce cache_read > 0
"""

import logging
import sys

from nexus.api.client import AnthropicClient, ModelTier
from nexus.auth.errors import AuthError
from nexus.auth.providers import get_default_providers
from nexus.capabilities.registry import CapabilitySet


def main() -> int:
    """Run the smoke test and return an exit code."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s -- %(message)s",
    )

    try:
        client = AnthropicClient(
            auth_providers=get_default_providers(),
            capabilities=CapabilitySet.none(),
            tier=ModelTier.STANDARD,
        )
    except AuthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(
            "\nEnsure one of the following:\n"
            "  - Claude Code is authenticated ('claude login')\n"
            "  - CLAUDE_CODE_OAUTH_TOKEN env var is set\n"
            "  - NEXUS_CLAUDE_API_KEY env var is set\n"
            "  - API key is in keychain (service='nexus-claude', user='api_key')",
            file=sys.stderr,
        )
        return 1

    system_prompt = (
        "You are a terse assistant. Answer in one short sentence. "
        "If asked about NEXUS, say it is a ServiceNow AI architect tool."
    )

    msg1 = client.complete(
        messages=[{"role": "user", "content": "What is NEXUS?"}],
        system=system_prompt,
        max_tokens=200,
    )
    print("\n--- Response 1 ---")
    for block in msg1.content:
        if block.type == "text":
            print(block.text)
    print(
        f"usage: in={msg1.usage.input_tokens} out={msg1.usage.output_tokens} "
        f"cache_write={getattr(msg1.usage, 'cache_creation_input_tokens', 0)} "
        f"cache_read={getattr(msg1.usage, 'cache_read_input_tokens', 0)}"
    )

    msg2 = client.complete(
        messages=[{"role": "user", "content": "What is the capital of France?"}],
        system=system_prompt,
        max_tokens=200,
    )
    print("\n--- Response 2 ---")
    for block in msg2.content:
        if block.type == "text":
            print(block.text)
    print(
        f"usage: in={msg2.usage.input_tokens} out={msg2.usage.output_tokens} "
        f"cache_write={getattr(msg2.usage, 'cache_creation_input_tokens', 0)} "
        f"cache_read={getattr(msg2.usage, 'cache_read_input_tokens', 0)}"
    )

    cache_read_2 = getattr(msg2.usage, "cache_read_input_tokens", 0)
    if cache_read_2 > 0:
        print(f"\nSUCCESS: prompt caching working (call 2 read {cache_read_2} cached tokens).")
    else:
        print(
            "\nWARNING: cache_read_input_tokens = 0 on second call. "
            "Prompt caching may not be enabled, or system prompt is too short."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
