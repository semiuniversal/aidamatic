import os
import sys
import time
from typing import Optional

from dotenv import load_dotenv

try:
	import anthropic
except Exception as exc:  # pragma: no cover
	print("Anthropic SDK not installed. Run: pip install anthropic", file=sys.stderr)
	raise


def get_env(name: str) -> Optional[str]:
	value = os.environ.get(name)
	return value.strip() if value else None


def main() -> int:
	# Load .env if present
	load_dotenv()

	api_key = get_env("ANTHROPIC_API_KEY")
	if not api_key:
		print("Missing ANTHROPIC_API_KEY in environment.", file=sys.stderr)
		print("Add it to your shell or a .env file.", file=sys.stderr)
		return 2

	# Allow model override via env; require explicit model for reliability
	model = get_env("ANTHROPIC_MODEL")
	if not model:
		print(
			"ANTHROPIC_MODEL not set. Set it to a deployed model in your account (e.g., 'claude-3-7-sonnet').",
			file=sys.stderr,
		)
		return 2

	client = anthropic.Anthropic(api_key=api_key)

	elapsed_s = None
	try:
		start_time = time.perf_counter()
		resp = client.messages.create(
			model=model,
			max_tokens=128,
			messages=[{"role": "user", "content": "Reply with 'pong'."}],
		)
		elapsed_s = time.perf_counter() - start_time
	except Exception as exc:  # pragma: no cover
		print(f"API call failed: {exc}", file=sys.stderr)
		return 1

	# Print the first text block, if present
	text = None
	for block in resp.content:
		if hasattr(block, "type") and getattr(block, "type") == "text":
			text = getattr(block, "text", None)
			if text:
				break

	print(text or "<no text content>")
	# Optionally show token usage if available
	usage = getattr(resp, "usage", None)
	if usage:
		in_tokens = getattr(usage, "input_tokens", None)
		out_tokens = getattr(usage, "output_tokens", None)
		if in_tokens is not None and out_tokens is not None:
			print(f"tokens: input={in_tokens} output={out_tokens}")

	if elapsed_s is not None:
		print(f"latency: {elapsed_s:.3f} s")

	return 0


if __name__ == "__main__":
	sys.exit(main())
