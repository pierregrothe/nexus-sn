# scripts/smoke_anthropic.py
# Manual smoke test for AnthropicClient against the real Anthropic API.
# Author: Pierre Grothe
# Date: 2026-05-07

"""End-to-end smoke test for AnthropicClient.

Run with:
    NEXUS_CLAUDE_API_KEY=sk-... .venv/bin/python scripts/smoke_anthropic.py

Or store the key in macOS Keychain first:
    .venv/bin/python -c "from nexus.auth.keychain import KeychainClient; \
        KeychainClient().set('nexus-claude', 'api_key', 'sk-...')"

Then run without env var:
    .venv/bin/python scripts/smoke_anthropic.py

Validates:
  1. ClaudeAuth retrieves the API key from env or keychain
  2. AnthropicClient auto-discovers the newest Sonnet model via models.list()
  3. complete() makes a real API call with prompt caching on the system prompt
  4. Cache instrumentation logs token counts (in/out/cache_write/cache_read)
  5. Two consecutive calls with the same system prompt produce a cache_read > 0
"""

import logging
import sys

from nexus.api.client import AnthropicClient, ModelTier
from nexus.auth.claude import ClaudeAuth
from nexus.capabilities.registry import CapabilitySet


def main() -> int:
    """Run the smoke test and return an exit code."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s -- %(message)s",
    )
    log = logging.getLogger("smoke")

    auth = ClaudeAuth()
    if not auth.is_configured():
        print(
            "ERROR: No API key found.\n"
            "Set env var: export NEXUS_CLAUDE_API_KEY=sk-...\n"
            "Or store in keychain: .venv/bin/python -c "
            "\"from nexus.auth.keychain import KeychainClient; "
            "KeychainClient().set('nexus-claude', 'api_key', 'sk-...')\"",
            file=sys.stderr,
        )
        return 1

    api_key = auth.get_api_key()
    log.info("API key resolved (length=%d)", len(api_key))

    log.info("Constructing AnthropicClient (tier=STANDARD)...")
    client = AnthropicClient(
        api_key=api_key,
        capabilities=CapabilitySet.none(),
        tier=ModelTier.STANDARD,
    )
    # Resolved model is logged at INFO by AnthropicClient.__init__

    system_prompt = (
        "You are a terse assistant. Answer in one short sentence. "
        "If asked about NEXUS, say it is a ServiceNow AI architect tool."
    )

    log.info("Call 1: simple prompt, expect cache_creation_input_tokens > 0")
    msg1 = client.complete(
        messages=[{"role": "user", "content": "What is NEXUS?"}],
        system=system_prompt,
        max_tokens=200,
    )
    print("\n--- Response 1 ---")
    for block in msg1.content:
        if block.type == "text":
            print(block.text)
    print(f"stop_reason: {msg1.stop_reason}")
    print(f"usage: in={msg1.usage.input_tokens} out={msg1.usage.output_tokens}")
    print(f"  cache_write={getattr(msg1.usage, 'cache_creation_input_tokens', 0)}")
    print(f"  cache_read={getattr(msg1.usage, 'cache_read_input_tokens', 0)}")

    log.info("Call 2: same system, different question, expect cache_read > 0")
    msg2 = client.complete(
        messages=[{"role": "user", "content": "What is the capital of France?"}],
        system=system_prompt,
        max_tokens=200,
    )
    print("\n--- Response 2 ---")
    for block in msg2.content:
        if block.type == "text":
            print(block.text)
    print(f"stop_reason: {msg2.stop_reason}")
    print(f"usage: in={msg2.usage.input_tokens} out={msg2.usage.output_tokens}")
    print(f"  cache_write={getattr(msg2.usage, 'cache_creation_input_tokens', 0)}")
    print(f"  cache_read={getattr(msg2.usage, 'cache_read_input_tokens', 0)}")

    cache_read_2 = getattr(msg2.usage, "cache_read_input_tokens", 0)
    if cache_read_2 > 0:
        print(
            f"\nSUCCESS: prompt caching is working "
            f"(call 2 read {cache_read_2} cached tokens)."
        )
    else:
        print(
            "\nWARNING: cache_read_input_tokens = 0 on second call. "
            "Prompt caching may not be enabled for your account, or the system "
            "prompt is too short to qualify for caching."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
