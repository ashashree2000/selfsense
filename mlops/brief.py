"""Owner's weekly brief.

Always builds a deterministic template version from the structured outputs.
If GEMINI_API_KEY is set, it asks Gemini (free tier) to REPHRASE that text only;
any failure (no key, quota exhausted, network, timeout) falls back to the template.
Latency and token counts are logged when the LLM path is used.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")


def template_brief(payload: dict) -> str:
    sug = [s for s in payload["reorder_suggestions"] if s["suggested_qty"] > 0]
    cats = payload["category_forecast"]
    top = sorted(cats, key=lambda c: -sum(c["yhat"]))[:3]
    q = payload["quality"]["counts"]
    lines = [f"Week of {payload['meta']['forecast_start']} (synthetic demo data).",
             "Expected sales next 7 days: " + ", ".join(
                 f"{c['category']} ~{round(sum(c['yhat'][:7]))} units" for c in top) + "."]
    if sug:
        lines.append(f"Reorder now: {len(sug)} products. Biggest: " + ", ".join(
            f"{s['productName']} ({s['suggested_qty']})" for s in sug[:3]) + ".")
    else:
        lines.append("No reorders needed today.")
    issues = {k: v for k, v in q.items() if v}
    if issues:
        lines.append("Data checks to review: " + ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in issues.items()) + ".")
    drift = payload.get("monitoring", {}).get("drift", {})
    if drift.get("alert"):
        lines.append("Sales pattern has shifted versus the training period; forecasts may be less reliable.")
    return " ".join(lines)


def llm_rephrase(text: str, timeout: float = 15.0) -> tuple[str | None, dict]:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None, {"used": False, "reason": "GEMINI_API_KEY not set"}
    prompt = ("Rewrite this shop summary as a short, friendly note to a shop owner. Keep every number exactly "
              "as given, add no new facts, max 90 words:\n\n" + text)
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
        out = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        usage = data.get("usageMetadata", {})
        return out, {"used": True, "model": GEMINI_MODEL, "latency_ms": round((time.perf_counter() - t0) * 1000),
                     "prompt_tokens": usage.get("promptTokenCount"), "output_tokens": usage.get("candidatesTokenCount")}
    except Exception as e:  # quota exhausted, network, schema change -> fall back
        return None, {"used": False, "reason": f"fallback to template: {type(e).__name__}",
                      "latency_ms": round((time.perf_counter() - t0) * 1000)}


def build_brief(payload: dict) -> dict:
    tmpl = template_brief(payload)
    llm, info = llm_rephrase(tmpl)
    return {"text": llm or tmpl, "template": tmpl, "source": "gemini" if llm else "template", "llm": info}
