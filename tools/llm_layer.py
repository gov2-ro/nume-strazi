#!/usr/bin/env python3
"""
Provider-agnostic LLM access for this repo's curation tools.

Wraps simonw/llm so providers (DeepSeek, Gemini, Anthropic, OpenRouter) are
swappable via env vars instead of three hand-rolled HTTP clients. Modelled on
/Users/pax/devbox/scraping/haplea-trips/shared/llm_layer.py so the three repos
share one convention; trimmed to what curation actually needs (a single
`complete()` returning raw text — callers here parse their own JSON shapes).

Only `tools/llm_classify.py` uses this. The ETL path (build_db.py,
streets_lib.py, seed_*.py) stays stdlib + openpyxl as CLAUDE.md requires.

Usage:
    from llm_layer import complete, resolve_model
    text = complete(system="...", user="...", model="deepseek-v4-flash")

CLI (smoke test):
    python3 tools/llm_layer.py               # default model, one round trip
    python3 tools/llm_layer.py --model gemini-2.5-flash-lite

Named llm_layer.py, not llm.py: Python puts the script's own directory on
sys.path[0], so tools/llm.py would shadow the `llm` pip package for every tool
in tools/.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ── 1. Load .env before anything else ──────────────────────────────────────
# Must precede `import llm` (done lazily below): provider plugins read their key
# at registration time, so a key that arrives later leaves the model invisible.
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass  # python-dotenv optional; env must then be set externally

# ── 2. Bridge our .env names → the names the llm plugins look for ──────────
# llm-deepseek and llm-gemini check their own vars at registration time; without
# this bridge `llm.get_model("deepseek-v4-chat")` raises UnknownModelError even
# with a perfectly good DEEPSEEK_API_KEY set. llm-anthropic reads
# ANTHROPIC_API_KEY natively, so it needs no bridge.
_KEY_BRIDGE = {
    "DEEPSEEK_API_KEY": "LLM_DEEPSEEK_KEY",
    "GOOGLE_API_KEY":   "LLM_GEMINI_KEY",
}
for _src, _dst in _KEY_BRIDGE.items():
    if os.getenv(_src) and not os.getenv(_dst):
        os.environ[_dst] = os.environ[_src]

# ── 3. Provider registry: (default_model_id, our env key var) ──────────────
PROVIDERS: dict[str, tuple[str, str]] = {
    "deepseek":   ("deepseek-v4-flash",      "DEEPSEEK_API_KEY"),
    "gemini":     ("gemini-2.5-flash-lite",  "GOOGLE_API_KEY"),
    "anthropic":  ("claude-haiku-4-5-20251001", "ANTHROPIC_API_KEY"),
    "openrouter": ("google/gemini-flash-1.5-8b", "OPENROUTER_API_KEY"),
}

# OpenAI-compatible endpoints, for models the installed llm plugins don't know.

_API_BASES: dict[str, str] = {
    "deepseek":   "https://api.deepseek.com",
    "openrouter": "https://openrouter.ai/api/v1",
}

_DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")

# ── Pricing, USD per 1M tokens: (input, cached_input, output) ──────────────
# Token counts logged by callers are ground truth, straight from the API's own
# usage block. Cost is an ESTIMATE derived from this table, which is a manual
# snapshot and will drift — providers change prices without notice. Correct a
# number here and past runs can be recosted from the logged token counts.
# Verified 2026-08-01 against provider pricing pages. 
# TODO: check, there was some hallucination

PRICING: dict[str, tuple[float, float, float]] = {
    "deepseek-v4-flash": (0.27, 0.07, 1.10),
    "deepseek-v4-pro":   (0.55, 0.14, 2.19),
    "gemini-2.5-flash-lite":     (0.10, 0.025, 0.40),
    "gemini-2.0-flash-lite":     (0.075, 0.019, 0.30),
    "claude-haiku-4-5-20251001": (1.00, 0.10, 5.00),
}


def estimate_cost(model_id: str, usage: dict) -> float | None:
    """USD estimate for one call, or None if the model isn't in PRICING.

    None means "unknown", never 0.0 — a silent zero would understate a run's
    cost and look like a free model.
    """
    price = PRICING.get(model_id)
    if price is None:
        return None
    per_in, per_cached, per_out = price
    cached = usage.get("cached_tokens") or 0
    fresh_in = max((usage.get("input_tokens") or 0) - cached, 0)
    return (fresh_in * per_in
            + cached * per_cached
            + (usage.get("output_tokens") or 0) * per_out) / 1_000_000


def _default_model() -> str:
    """Model to use when the caller names none.

    Checks LLM_MODEL and LLM_model — the repo's .env uses the lowercase form and
    env vars are case-sensitive on Unix, so reading only one silently ignores it.
    """
    return (os.getenv("LLM_MODEL") or os.getenv("LLM_model")
            or PROVIDERS.get(_DEFAULT_PROVIDER, ("", ""))[0])


def resolve_model(model: str | None = None) -> tuple[str | None, str, str | None]:
    """Return (provider, model_id, api_key) for an explicit or configured model."""
    model = model or _default_model()
    if "/" in model:                       # org/model → OpenRouter
        return "openrouter", model, os.getenv("OPENROUTER_API_KEY")
    low = model.lower()
    if low.startswith("claude"):
        return "anthropic", model, os.getenv("ANTHROPIC_API_KEY")
    if low.startswith("gemini"):
        return "gemini", model, os.getenv("GOOGLE_API_KEY")
    if low.startswith("deepseek"):
        return "deepseek", model, os.getenv("DEEPSEEK_API_KEY")
    for provider, (_default, key_var) in PROVIDERS.items():
        if provider in low:
            return provider, model, os.getenv(key_var)
    return None, model, None


def _direct_completion(provider: str, model_id: str, api_key: str,
                       system: str, user: str, max_tokens: int,
                       temperature: float, _usage_sink: dict | None = None) -> str:
    """Call an OpenAI-compatible endpoint directly (llm plugin didn't know it)."""
    import openai
    base_url = _API_BASES.get(provider)
    if base_url is None:
        raise RuntimeError(
            f"Model {model_id!r} is unknown to the installed llm plugins and "
            f"provider {provider!r} has no OpenAI-compatible endpoint to fall "
            f"back to."
        )
    # Generous timeout: reasoning models spend a minute or more thinking before
    # the first content token, well past the client's 10-minute default only in
    # the worst case but far past any short timeout.
    client = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=600)
    resp = client.chat.completions.create(
        model=model_id,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    choice = resp.choices[0]
    content = choice.message.content or ""
    if _usage_sink is not None:
        _usage_sink.update(_usage_dict(resp))
        _usage_sink["model"] = model_id
        _usage_sink["finish_reason"] = choice.finish_reason
        _usage_sink["estimated_cost_usd"] = estimate_cost(model_id, _usage_sink)
    # A reasoning model bills reasoning against max_tokens and can burn the whole
    # budget before emitting a single content token — the response then comes back
    # finish_reason="length" with content="" and looks, to a JSON parser, exactly
    # like a malformed reply. Say what actually happened instead.
    if not content and choice.finish_reason == "length":
        used = getattr(getattr(resp.usage, "completion_tokens_details", None),
                       "reasoning_tokens", None)
        raise RuntimeError(
            f"{model_id} returned no content: hit max_tokens={max_tokens} during "
            f"reasoning ({used} reasoning tokens). Raise max_tokens or lower the "
            f"batch size."
        )
    return content


def _usage_dict(resp) -> dict:
    """Normalise an OpenAI-shaped usage block to our own keys."""
    u = getattr(resp, "usage", None)
    if u is None:
        return {}
    details = getattr(u, "completion_tokens_details", None)
    return {
        "input_tokens":     getattr(u, "prompt_tokens", None),
        "output_tokens":    getattr(u, "completion_tokens", None),
        "reasoning_tokens": getattr(details, "reasoning_tokens", None) if details else None,
        "cached_tokens":    getattr(u, "prompt_cache_hit_tokens", None),
    }


def complete_with_usage(system: str, user: str, model: str | None = None,
                        max_tokens: int = 4096,
                        temperature: float = 0.0) -> tuple[str, dict]:
    """complete(), plus the provider's token accounting.

    Returns (text, usage). `usage` carries whatever the provider reported —
    input/output/reasoning/cached token counts, plus `model` and an
    `estimated_cost_usd` derived from PRICING (None when the model is unpriced).
    An empty dict means the provider reported nothing, not that it was free.
    """
    _usage_sink: dict = {}
    text = complete(system, user, model, max_tokens, temperature,
                    _usage_sink=_usage_sink)
    return text, _usage_sink


def complete(system: str, user: str, model: str | None = None,
             max_tokens: int = 4096, temperature: float = 0.0,
             _usage_sink: dict | None = None) -> str:
    """Send one prompt, return the raw response text.

    Raises on failure rather than returning None — callers here run long batch
    loops with their own retry/skip accounting, and a silent empty string would
    be recorded as a genuine classification.

    Pass `_usage_sink` (or use complete_with_usage) to receive token counts.
    """
    provider, model_id, api_key = resolve_model(model)
    if provider and not api_key:
        key_var = PROVIDERS.get(provider, ("", "?"))[1]
        raise RuntimeError(
            f"No API key for provider {provider!r} (model {model_id}). "
            f"Set {key_var} in .env or the environment."
        )

    try:
        import llm as _llm
    except ImportError:
        if provider and api_key and provider in _API_BASES:
            return _direct_completion(provider, model_id, api_key, system,
                                      user, max_tokens, temperature, _usage_sink)
        raise RuntimeError(
            "The `llm` package is not installed and this provider has no "
            "direct fallback. pip install llm llm-deepseek llm-gemini llm-anthropic"
        )

    try:
        m = _llm.get_model(model_id)
    except Exception:
        # Model id newer than the installed plugin — go direct if we can.
        if provider and api_key and provider in _API_BASES:
            return _direct_completion(provider, model_id, api_key, system,
                                      user, max_tokens, temperature, _usage_sink)
        raise

    kwargs: dict = {"system": system}
    if api_key:
        kwargs["key"] = api_key
    resp = m.prompt(user, **kwargs)
    text = resp.text()
    if _usage_sink is not None:
        # The llm package exposes usage through a method, and only for plugins
        # that bother to record it — absent usage must read as unknown, not free.
        try:
            u = resp.usage()
            _usage_sink.update({"input_tokens": getattr(u, "input", None),
                                "output_tokens": getattr(u, "output", None)})
        except Exception:
            pass
        _usage_sink["model"] = model_id
        _usage_sink["estimated_cost_usd"] = estimate_cost(model_id, _usage_sink)
    return text


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Smoke-test the LLM layer.")
    ap.add_argument("--model", default=None,
                    help="Model id (default: LLM_MODEL/LLM_model, else provider default)")
    args = ap.parse_args()

    provider, model_id, api_key = resolve_model(args.model)
    print(f"provider={provider}  model={model_id}  key={'set' if api_key else 'MISSING'}")
    try:
        out = complete(system="Reply with exactly one word.",
                       user="Say OK", model=args.model)
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"response: {out.strip()[:120]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
