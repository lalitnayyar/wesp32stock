"""Provider-independent AI interface (OpenAI, DeepSeek, Ollama).

Credentials are encrypted at rest and never returned or logged in full. The backend computes all
numbers; models only receive a concise verified fact sheet and must separate facts from
interpretation. No inference runs on the ESP32.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

import httpx

DEFAULT_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
    "ollama": "http://host.docker.internal:11434",
}
KINDS = tuple(DEFAULT_URLS)

SYSTEM_PROMPT = (
    "You are a cautious portfolio analysis assistant for the Lalit Stock Application. "
    "Use ONLY the JSON facts provided; never invent prices, holdings or news. "
    "Structure every answer with two headed sections: 'Facts' (restating figures from the data) and "
    "'Interpretation' (your observations, clearly labelled as opinion). Mention data staleness when present. "
    "This is not financial advice; do not recommend buying or selling specific securities."
)

TASKS = {
    "portfolio_summary": "Summarise the portfolio's current state: value, daily and unrealized P/L, allocation.",
    "daily_summary": "Give a short daily market summary for this portfolio and the benchmarks.",
    "contributors": "Explain which holdings contributed most positively and negatively to today's P/L.",
    "concentration": "Identify concentration risks by holding, sector and currency exposure.",
    "unusual_moves": "Point out unusually large daily moves (absolute daily change above 3%) and what the data shows.",
    "benchmark_comparison": "Compare today's portfolio move with the benchmark moves. Keep them separate.",
    "risk": "List risk observations (concentration, stale data, currency exposure, cash).",
    "question": "Answer the user's question using only the data.",
}


class AIError(Exception):
    pass


@dataclass
class AIConfig:
    kind: str
    base_url: str
    model: str
    api_key: str | None
    timeout_s: int = 60


def _client(cfg: AIConfig, transport: httpx.BaseTransport | None = None) -> httpx.Client:
    headers = {"Content-Type": "application/json"}
    if cfg.kind in ("openai", "deepseek"):
        if not cfg.api_key:
            raise AIError(f"{cfg.kind} requires an API key")
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    return httpx.Client(base_url=cfg.base_url.rstrip("/"), headers=headers, timeout=cfg.timeout_s, transport=transport)


def _err(resp: httpx.Response) -> AIError:
    try:
        body = resp.json()
        msg = body.get("error", {}).get("message") if isinstance(body.get("error"), dict) else body.get("error")
    except Exception:
        msg = None
    return AIError(f"HTTP {resp.status_code}: {(msg or resp.text)[:200]}")


def list_models(cfg: AIConfig, transport=None) -> list[str]:
    with _client(cfg, transport) as c:
        if cfg.kind == "ollama":
            r = c.get("/api/tags")
            if r.status_code != 200:
                raise _err(r)
            return [m.get("name", "") for m in r.json().get("models", [])]
        r = c.get("/models")
        if r.status_code != 200:
            raise _err(r)
        return [m.get("id", "") for m in r.json().get("data", [])]


def chat(cfg: AIConfig, system: str, user: str, max_tokens: int = 700, transport=None) -> str:
    with _client(cfg, transport) as c:
        if cfg.kind == "ollama":
            r = c.post("/api/chat", json={"model": cfg.model, "stream": False,
                                          "messages": [{"role": "system", "content": system},
                                                       {"role": "user", "content": user}],
                                          "options": {"num_predict": max_tokens}})
            if r.status_code != 200:
                raise _err(r)
            return r.json().get("message", {}).get("content", "")
        # OpenAI's current models (gpt-5, o-series) reject the legacy max_tokens and require
        # max_completion_tokens; DeepSeek and most compatible servers still expect max_tokens.
        # Start with the provider's preferred name and switch once if the server rejects it.
        param = "max_completion_tokens" if cfg.kind == "openai" else "max_tokens"
        budget = max_tokens
        for _ in range(3):
            r = c.post("/chat/completions", json={"model": cfg.model, param: budget,
                                                  "messages": [{"role": "system", "content": system},
                                                               {"role": "user", "content": user}]})
            if r.status_code == 400 and "unsupported parameter" in r.text.lower() and param in r.text:
                param = "max_tokens" if param == "max_completion_tokens" else "max_completion_tokens"
                continue
            if r.status_code != 200:
                raise _err(r)
            choice = r.json()["choices"][0]
            content = (choice.get("message") or {}).get("content") or ""
            # Reasoning models spend hidden tokens before answering; an empty reply cut off by the
            # limit means the budget went on reasoning, so retry once with room for an answer.
            if not content and choice.get("finish_reason") == "length" and budget < 4000:
                budget = max(4000, budget * 8)
                continue
            if not content:
                raise AIError(f"Model returned no text (finish_reason={choice.get('finish_reason')})")
            return content
        raise AIError("Model request failed after retries")


def test_connection(cfg: AIConfig, transport=None) -> dict:
    """Validate config, credentials, model availability; perform a tiny request; measure latency."""
    result = {"ok": False, "steps": [], "latency_ms": None, "message": ""}
    if cfg.kind not in KINDS:
        result["message"] = f"Unknown provider kind {cfg.kind}"
        return result
    if not cfg.base_url.startswith(("http://", "https://")):
        result["message"] = "Base URL must start with http:// or https://"
        return result
    if not cfg.model:
        result["message"] = "Model is required"
        return result
    result["steps"].append("config ok")
    try:
        models = list_models(cfg, transport)
        result["steps"].append(f"credentials ok ({len(models)} models listed)")
        if models and cfg.model not in models and f"{cfg.model}:latest" not in models:
            result["message"] = f"Model '{cfg.model}' not available. Available: {', '.join(models[:8])}"
            return result
        result["steps"].append("model available")
        t0 = time.perf_counter()
        reply = chat(cfg, "Reply with the single word OK.", "Connection test", max_tokens=5, transport=transport)
        result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        result["steps"].append(f"test request ok: {reply.strip()[:20]!r}")
        result["ok"] = True
        result["message"] = f"Connected to {cfg.kind} model {cfg.model} in {result['latency_ms']} ms"
    except AIError as exc:
        result["message"] = str(exc)
    except httpx.HTTPError as exc:
        result["message"] = f"Connection failed: {type(exc).__name__}: {str(exc)[:150]}"
    return result


def build_facts(summary: dict, bench: list[dict]) -> dict:
    """Concise, verified facts for the model (no secrets, no PII)."""
    return {
        "portfolio": summary["portfolio"],
        "totals": summary["totals"],
        "holdings": [{k: h[k] for k in ("ticker", "currency", "sector", "quantity", "price", "market_value_base",
                                         "unrealized_pct", "day_change_pct", "allocation_pct", "stale")}
                     for h in summary["holdings"]],
        "exposure": summary["exposure"],
        "best": summary["best"], "worst": summary["worst"],
        "freshness": summary["freshness"],
        "benchmarks": [{k: b.get(k) for k in ("name", "level", "day_change_pct", "ret_1m", "ret_ytd", "ret_1y", "stale")}
                       for b in bench],
        "warnings": summary["warnings"],
        "note": "Benchmark returns are index returns, separate from portfolio returns.",
    }


def insight(cfg: AIConfig, task: str, facts: dict, question: str | None = None, transport=None) -> str:
    if task not in TASKS:
        raise AIError(f"Unknown task {task}")
    if task == "question" and not (question or "").strip():
        raise AIError("A question is required")
    prompt = f"Task: {TASKS[task]}\n"
    if task == "question":
        prompt += f"Question: {question.strip()[:1000]}\n"
    prompt += "Data (JSON, authoritative):\n" + json.dumps(facts, separators=(",", ":"))
    return chat(cfg, SYSTEM_PROMPT, prompt, transport=transport)
