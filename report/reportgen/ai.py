"""Interpretation of the metrics with Amazon Bedrock.

The model receives numbers already computed by code and only interprets them.
Its answer is then validated: structure, allowed values and that every figure it
quotes can be traced back to the computed metrics.
"""

import json
import re

SYSTEM_PROMPT = """You are a performance engineer reviewing the results of a k6 load test against a
serverless search API (API Gateway -> AWS Lambda -> Amazon Bedrock, S3 Vectors and DynamoDB).

Rules:
- Use ONLY the numbers provided in the input. Never compute new statistics or invent values.
- When you quote a number, copy it as given (you may round to at most 1 decimal).
- Read every result against the scenario (load profile, think time and thresholds).
- Take the "data_quality" notes into account: with small samples, say that percentiles are not reliable.
- Explain causes only as hypotheses consistent with the data (for example: waiting time close to the
  total duration means the time is spent in the backend).
- Be concise and technical. Write in English.

Return ONLY valid JSON with this schema:
{
  "headline": "one sentence with the main conclusion",
  "summary": "a short paragraph (3-5 sentences)",
  "findings": [{"title": "...", "detail": "...", "severity": "info | warning | critical"}],
  "recommendations": ["..."],
  "caveats": ["..."],
  "confidence": "high | medium | low"
}"""

SEVERITIES = {"info", "warning", "critical"}
CONFIDENCE = {"high", "medium", "low"}


def build_payload(run: dict, notes: list, glossary: dict) -> dict:
    return {
        "run": {"run_id": run["run_id"], "scenario": run["scenario"], "label": run["label"],
                "started_at": run["started_at"], "finished_at": run["finished_at"],
                "scenario_definition": run["scenario_config"],
                "thresholds_passed": run["thresholds_passed"], "kpis": run["kpis"],
                "latency_metrics_ms": run["trends"], "timeline": run["timeline"]},
        "data_quality": notes,
        "metric_glossary": {k: v["short"] for k, v in glossary.items()},
    }


def _numbers_in(obj) -> list:
    out = []
    if isinstance(obj, dict):
        for v in obj.values():
            out += _numbers_in(v)
    elif isinstance(obj, list):
        for v in obj:
            out += _numbers_in(v)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out.append(float(obj))
    elif isinstance(obj, str):
        out += [float(n.replace(",", "")) for n in re.findall(r"(?<![A-Za-z(_])-?\d[\d,]*\.?\d*", obj)]
    return out


def _traceable(n: float, known: list) -> bool:
    n = abs(n)
    candidates = [abs(k) for k in known]
    candidates += [k * 100 for k in candidates] + [k / 1000 for k in candidates]
    return any(abs(n - k) <= max(0.5, k * 0.01) for k in candidates)


def validate(analysis: dict, payload: dict) -> dict:
    """Checks the structure and that the quoted figures come from the payload."""
    issues = []
    for key in ["headline", "summary", "findings", "recommendations", "caveats", "confidence"]:
        if key not in analysis:
            issues.append(f"missing field '{key}'")
    for f in analysis.get("findings", []):
        if f.get("severity") not in SEVERITIES:
            f["severity"] = "info"
    if analysis.get("confidence") not in CONFIDENCE:
        analysis["confidence"] = "low"

    known = _numbers_in(payload)
    text = {k: analysis.get(k) for k in ["headline", "summary", "findings", "recommendations"]}
    quoted = [n for n in _numbers_in(text) if abs(n) > 10]   # small integers are usually counts or labels
    untraceable = sorted({n for n in quoted if not _traceable(n, known)})

    analysis["validation"] = {
        "structure_ok": not issues,
        "issues": issues,
        "figures_checked": len(quoted),
        "figures_not_traceable": untraceable,
    }
    return analysis


def analyze(payload: dict, settings: dict) -> dict:
    import boto3
    ai = settings["ai"]
    client = boto3.client("bedrock-runtime")
    resp = client.converse(
        modelId=ai["model_id"],
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": json.dumps(payload, default=str)}]}],
        inferenceConfig={"temperature": ai["temperature"], "maxTokens": ai["max_tokens"]},
    )
    text = resp["output"]["message"]["content"][0]["text"].strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    analysis = json.loads(text)
    analysis["model_id"] = ai["model_id"]
    analysis["usage"] = resp.get("usage", {})
    return validate(analysis, payload)


def fallback(notes: list, reason: str) -> dict:
    """Used when Bedrock is not available: the report keeps the computed metrics only."""
    return {
        "headline": "AI analysis not available for this report.",
        "summary": f"Amazon Bedrock was not called ({reason}). All the values in this report are computed by code.",
        "findings": [],
        "recommendations": [],
        "caveats": notes,
        "confidence": None,
        "model_id": None,
        "validation": None,
    }
