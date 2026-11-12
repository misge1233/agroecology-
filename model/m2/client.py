"""The cached, counted and capped chat client of Methodology 2 (E6 ground rules, Part 5).

* **Cached**: every answer is stored under ``model/m2/cache/<model>/<prompt version>/<hash>.json``
  keyed by the model, the messages, the schema, the sampling parameters and an optional
  ``repeat`` tag (the stability check's fresh calls get their own keys, so the check itself
  reruns from the cache). A rerun of a cached prompt costs nothing and makes no request.
* **Counted**: every paid request (chat or embedding) is appended to
  ``model/m2/cache/ledger.jsonl`` with its tokens and cost from ``prices.yaml``.
* **Capped**: before a request the client reserves its worst-case cost (input tokens counted
  with ``tiktoken`` plus the output allowance); when the phase total in the ledger plus the
  open reservations plus this one would exceed ``budget_usd`` it raises
  :class:`BudgetExceeded` and sends nothing.

The API is called with ``httpx`` as the backend does (no SDK). Temperature 0 and a fixed
seed where the model accepts them (reasoning models accept neither; recorded). Structured
output (``json_schema``, strict) is used, with JSON mode as the recorded fallback when a
model rejects it. The key comes from the environment or ``app/backend/.env`` and is never
logged or written.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import random
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

from model.m2 import CACHE_DIR, PRICES_PATH
from model.m2.knowledge import n_tokens
from model.m2.prompt import PROMPT_VERSION

logger = logging.getLogger(__name__)

API = "https://api.openai.com/v1"
SEED = 0
MAX_OUT = 2000
MAX_OUT_REASONING = 8000
DEFAULT_BUDGET = 100.0


class BudgetExceeded(RuntimeError):
    pass


def load_prices(path: Path = PRICES_PATH) -> dict[str, dict[str, Any]]:
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("models", {})


def price_of(model: str, prices: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Prices of a model id (dated ids such as ``gpt-4o-mini-2024-07-18`` match their base)."""
    if model in prices:
        return prices[model]
    for base in sorted(prices, key=len, reverse=True):
        if model.startswith(base + "-"):
            return prices[base]
    raise KeyError(f"no price for model {model!r} in prices.yaml; add it (the owner checks prices) before a paid run")


def is_reasoning(model: str, prices: dict[str, dict[str, Any]]) -> bool:
    try:
        return bool(price_of(model, prices).get("reasoning"))
    except KeyError:
        return model.startswith(("o1", "o3", "o4", "gpt-5"))


def cost_usd(model: str, n_in: int, n_out: int, prices: dict[str, dict[str, Any]]) -> float:
    p = price_of(model, prices)
    return (n_in * float(p["input"]) + n_out * float(p.get("output", 0.0))) / 1e6


def chat_tokens(messages: list[dict[str, str]]) -> int:
    """Input tokens of a chat request (content tokens plus the per-message overhead)."""
    return sum(n_tokens(m["content"]) + 4 for m in messages) + 3


class Ledger:
    """Append-only record of paid requests; the phase total is the budget base.

    Several processes run at once (one variant per process), so each process appends only to
    its own file ``<stem>.<pid>.jsonl`` beside ``path`` (no interleaved lines); the total sums
    ``path`` and every per-process file, ignoring another process's unfinished last line.
    """

    def __init__(self, path: Path = CACHE_DIR / "ledger.jsonl") -> None:
        import os

        self.path = Path(path)
        self.own = self.path.with_name(f"{self.path.stem}.{os.getpid()}.jsonl")
        self._lock = threading.Lock()
        self._reserved = 0.0

    def files(self) -> list[Path]:
        return sorted(p for p in self.path.parent.glob(f"{self.path.stem}*.jsonl") if p.is_file())

    def total(self) -> float:
        tot = 0.0
        for p in self.files():
            text = p.read_text(encoding="utf-8")
            lines = text.split("\n")
            if not text.endswith("\n"):
                lines = lines[:-1]  # a record still being written by another process
            for l in lines:
                if l.strip():
                    tot += float(json.loads(l)["cost_usd"])
        return tot

    def reserve(self, amount: float, budget: float) -> None:
        with self._lock:
            spent = self.total()
            if spent + self._reserved + amount > budget:
                raise BudgetExceeded(f"budget {budget:.2f} USD: spent {spent:.4f}, reserved {self._reserved:.4f}, "
                                     f"this request up to {amount:.4f}; nothing sent")
            self._reserved += amount

    def settle(self, reserved: float, record: dict[str, Any]) -> None:
        with self._lock:
            self._reserved = max(0.0, self._reserved - reserved)
            self.own.parent.mkdir(parents=True, exist_ok=True)
            with self.own.open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(record, sort_keys=True) + "\n")

    def release(self, reserved: float) -> None:
        with self._lock:
            self._reserved = max(0.0, self._reserved - reserved)


def find_api_key() -> str:
    from rag.retrieve import _find_api_key

    return _find_api_key()


class ChatClient:
    def __init__(self, model: str, budget_usd: float = DEFAULT_BUDGET, cache_dir: Path = CACHE_DIR,
                 ledger: Ledger | None = None, prices: dict[str, dict[str, Any]] | None = None,
                 api_key: str | None = None, transport: httpx.BaseTransport | None = None,
                 timeout: float = 120.0, offline: bool = False, max_attempts: int = 7) -> None:
        self.model = model
        self.budget_usd = float(budget_usd)
        self.cache_dir = Path(cache_dir)
        self.ledger = ledger or Ledger(self.cache_dir / "ledger.jsonl")
        self.prices = prices if prices is not None else load_prices()
        self._key = api_key
        self._transport = transport
        self.timeout = timeout
        #: offline: answer from the cache only; a miss raises (reruns, determinism checks)
        self.offline = offline
        #: transport/HTTP attempts per request (evaluation 7 with backoff; serving 1, E7 Part D)
        self.max_attempts = max(1, int(max_attempts))
        self.reasoning = is_reasoning(model, self.prices)
        self.stats = {"calls": 0, "cache_hits": 0, "cost_usd": 0.0}
        self._client: httpx.Client | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------ plumbing
    def _http(self) -> httpx.Client:
        if self._client is None:
            key = self._key or find_api_key()
            if not key:
                raise RuntimeError("OPENAI_API_KEY is not configured (env var or app/backend/.env)")
            self._client = httpx.Client(base_url=API, headers={"Authorization": f"Bearer {key}"},
                                        timeout=self.timeout, transport=self._transport)
        return self._client

    def params(self) -> dict[str, Any]:
        """The sampling parameters sent (and part of the cache key)."""
        if self.reasoning:
            return {"max_completion_tokens": MAX_OUT_REASONING}
        return {"temperature": 0, "seed": SEED, "max_completion_tokens": MAX_OUT}

    def max_out(self) -> int:
        return MAX_OUT_REASONING if self.reasoning else MAX_OUT

    def cache_key(self, messages: list[dict[str, str]], schema: dict[str, Any] | None, repeat: str | None) -> str:
        blob = json.dumps({"model": self.model, "messages": messages, "schema": schema, "params": self.params(),
                           "prompt_version": PROMPT_VERSION, "repeat": repeat}, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def cache_path(self, key: str) -> Path:
        return self.cache_dir / self.model / PROMPT_VERSION / f"{key}.json"

    def cached(self, messages: list[dict[str, str]], schema: dict[str, Any] | None, repeat: str | None = None) -> dict[str, Any] | None:
        p = self.cache_path(self.cache_key(messages, schema, repeat))
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def estimate(self, messages: list[dict[str, str]]) -> float:
        """Worst-case cost of one request (input counted, output at its allowance)."""
        return cost_usd(self.model, chat_tokens(messages), self.max_out(), self.prices)

    # ------------------------------------------------------------ call
    def chat(self, messages: list[dict[str, str]], schema: dict[str, Any] | None = None, repeat: str | None = None) -> dict[str, Any]:
        """The cached record ``{content, parsed, usage, latency_s, model, ...}`` for one request."""
        key = self.cache_key(messages, schema, repeat)
        path = self.cache_path(key)
        if path.exists():
            with self._lock:
                self.stats["cache_hits"] += 1
            rec = json.loads(path.read_text(encoding="utf-8"))
            rec["from_cache"] = True
            return rec
        if self.offline:
            raise LookupError(f"offline: no cached answer for {key[:12]}")
        reserved = self.estimate(messages)
        self.ledger.reserve(reserved, self.budget_usd)
        try:
            rec = self._send(messages, schema)
        except BaseException:
            self.ledger.release(reserved)
            raise
        usage = rec.get("usage") or {}
        n_in, n_out = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
        rec["cost_usd"] = cost_usd(self.model, n_in, n_out, self.prices)
        rec.update({"key": key, "repeat": repeat, "prompt_version": PROMPT_VERSION, "params": self.params(),
                    "request_model": self.model, "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                    "messages": messages})
        self.ledger.settle(reserved, {"ts": rec["created_utc"], "kind": "chat", "model": self.model, "key": key,
                                      "prompt_tokens": n_in, "completion_tokens": n_out, "cost_usd": rec["cost_usd"]})
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, indent=1), encoding="utf-8")
        tmp.replace(path)
        with self._lock:
            self.stats["calls"] += 1
            self.stats["cost_usd"] += rec["cost_usd"]
        rec["from_cache"] = False
        return rec

    def _send(self, messages: list[dict[str, str]], schema: dict[str, Any] | None) -> dict[str, Any]:
        body: dict[str, Any] = {"model": self.model, "messages": messages, **self.params()}
        fmt = "json_schema" if schema is not None else "json_object"
        body["response_format"] = {"type": "json_schema", "json_schema": schema} if schema is not None else {"type": "json_object"}
        delay = 2.0
        last = self.max_attempts - 1
        for attempt in range(self.max_attempts):
            t0 = time.time()
            try:
                r = self._http().post("/chat/completions", json=body)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == last:
                    raise
                logger.warning("transport error (%s); retrying in %.0f s", type(exc).__name__, delay)
                time.sleep(delay + random.random())
                delay = min(delay * 2, 60)
                continue
            latency = time.time() - t0
            if r.status_code == 400 and fmt == "json_schema" and "response_format" in r.text:
                logger.warning("%s rejects json_schema output; JSON mode (recorded)", self.model)
                body["response_format"] = {"type": "json_object"}
                fmt = "json_object"
                continue
            if r.status_code in (429, 500, 502, 503, 504) and attempt < last:
                logger.warning("HTTP %s; retrying in %.0f s", r.status_code, delay)
                time.sleep(delay + random.random())
                delay = min(delay * 2, 60)
                continue
            if r.status_code == 401:
                raise RuntimeError("OpenAI rejected the API key (401)")
            r.raise_for_status()
            j = r.json()
            choice = j["choices"][0]
            content = choice["message"].get("content") or ""
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                parsed = None
            return {"content": content, "parsed": parsed, "usage": j.get("usage"), "latency_s": round(latency, 3),
                    "model": j.get("model"), "system_fingerprint": j.get("system_fingerprint"),
                    "finish_reason": choice.get("finish_reason"), "response_format": fmt}
        raise RuntimeError(f"no answer after {self.max_attempts} attempt(s)")

    def list_models(self) -> list[str]:
        r = self._http().get("/models")
        r.raise_for_status()
        return sorted(m["id"] for m in r.json().get("data", []))

    def record_embedding(self, text: str, model: str = "text-embedding-3-small") -> None:
        """Ledger entry for one query embedding (called by the retrieval cache on a miss)."""
        n = n_tokens(text)
        c = cost_usd(model, n, 0, self.prices)
        self.ledger.settle(0.0, {"ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"), "kind": "embedding",
                                 "model": model, "prompt_tokens": n, "completion_tokens": 0, "cost_usd": c})
