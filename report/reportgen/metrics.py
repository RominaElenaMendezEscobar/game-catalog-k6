"""Computes the report metrics with code (no AI): KPIs, timeline, breakdowns and data-quality notes.

The k6 summary is the reference for aggregated values. The per-request CSV is used for the
timeline and charts, and as a fallback when the summary is missing.
"""

from datetime import datetime, timezone

import numpy as np
import pandas as pd

PHASES = ["http_req_blocked", "http_req_connecting", "http_req_tls_handshaking",
          "http_req_sending", "http_req_waiting", "http_req_receiving"]
BREAKDOWN_RULES = {"max>=0", "rate>=0", "count>=0"}   # always-true thresholds used for breakdowns


def _parse_tags(value) -> dict:
    if not isinstance(value, str) or not value:
        return {}
    return dict(p.split("=", 1) for p in value.split("&") if "=" in p)


def _pct(values, q: float):
    return float(np.percentile(values, q)) if len(values) else None


def _latency_stats(values) -> dict:
    if not len(values):
        return {}
    return {"avg": float(values.mean()), "min": float(values.min()), "med": _pct(values, 50),
            "p90": _pct(values, 90), "p95": _pct(values, 95), "p99": _pct(values, 99),
            "max": float(values.max())}


def _from_summary_trend(values: dict) -> dict:
    return {"avg": values.get("avg"), "min": values.get("min"), "med": values.get("med"),
            "p90": values.get("p(90)"), "p95": values.get("p(95)"), "p99": values.get("p(99)"),
            "max": values.get("max")}


def prepare_results(df: pd.DataFrame) -> pd.DataFrame:
    """Adds parsed tags and elapsed seconds to the k6 CSV."""
    df = df.copy()
    df["tags"] = df["extra_tags"].apply(_parse_tags) if "extra_tags" in df else [{}] * len(df)
    df["lang"] = df["tags"].apply(lambda t: t.get("lang"))
    df["elapsed_s"] = df["timestamp"] - df["timestamp"].min()
    return df


def _kpis_from_results(df: pd.DataFrame) -> dict:
    dur = df[df.metric_name == "http_req_duration"]
    failed = df[df.metric_name == "http_req_failed"]
    values = dur.metric_value.to_numpy(dtype=float)
    span = max(float(df.timestamp.max() - df.timestamp.min()), 1.0)

    by_lang = {}
    for lang, g in dur.groupby("lang"):
        f = failed[failed.lang == lang].metric_value
        v = g.metric_value.to_numpy(dtype=float)
        by_lang[lang] = {"requests": int(len(v)), "error_rate": float(f.mean()) if len(f) else 0.0,
                         "med": _pct(v, 50), "p95": _pct(v, 95)}

    checks = df[df.metric_name == "checks"].metric_value
    vus = df[df.metric_name == "vus"].metric_value
    return {
        "requests": int(len(values)),
        "throughput_rps": len(values) / span,
        "error_rate": float(failed.metric_value.mean()) if len(failed) else 0.0,
        "latency_ms": _latency_stats(values),
        "phases_ms": {p: float(df[df.metric_name == p].metric_value.mean())
                      for p in PHASES if (df.metric_name == p).any()},
        "checks_rate": float(checks.mean()) if len(checks) else None,
        "vus_max": int(vus.max()) if len(vus) else None,
        "data_received_bytes": float(df[df.metric_name == "data_received"].metric_value.sum()),
        "data_sent_bytes": float(df[df.metric_name == "data_sent"].metric_value.sum()),
        "by_lang": by_lang,
    }


def _kpis_from_summary(summary: dict) -> dict:
    m = summary.get("metrics", {})
    val = lambda name: m.get(name, {}).get("values", {})

    by_lang = {}
    for name, metric in m.items():
        if name.startswith("http_req_duration{lang:"):
            lang = name.split(":", 1)[1].rstrip("}")
            failed = val(f"http_req_failed{{lang:{lang}}}")
            by_lang[lang] = {"requests": int(failed.get("passes", 0) + failed.get("fails", 0)),
                             "error_rate": failed.get("rate", 0.0),
                             "med": metric["values"].get("med"), "p95": metric["values"].get("p(95)")}

    thresholds = []
    for name, metric in m.items():
        for rule, result in (metric.get("thresholds") or {}).items():
            if rule not in BREAKDOWN_RULES:
                thresholds.append({"metric": name, "rule": rule, "ok": bool(result.get("ok"))})

    return {
        "requests": int(val("http_reqs").get("count", 0)),
        "throughput_rps": val("http_reqs").get("rate"),
        "error_rate": val("http_req_failed").get("rate", 0.0),
        "latency_ms": _from_summary_trend(val("http_req_duration")),
        "phases_ms": {p: val(p).get("avg") for p in PHASES if p in m},
        "checks_rate": val("checks").get("rate"),
        "vus_max": val("vus_max").get("max") or val("vus").get("max"),
        "data_received_bytes": val("data_received").get("count"),
        "data_sent_bytes": val("data_sent").get("count"),
        "by_lang": by_lang,
        "thresholds": thresholds,
    }


def _timeline(df: pd.DataFrame, bucket_s: int) -> list:
    dur = df[df.metric_name == "http_req_duration"]
    failed = df[df.metric_name == "http_req_failed"]
    vus = df[df.metric_name == "vus"]
    rows = []
    for b in sorted(set((df.elapsed_s // bucket_s).astype(int))):
        lo, hi = b * bucket_s, (b + 1) * bucket_s
        d = dur[(dur.elapsed_s >= lo) & (dur.elapsed_s < hi)].metric_value.to_numpy(dtype=float)
        f = failed[(failed.elapsed_s >= lo) & (failed.elapsed_s < hi)].metric_value
        v = vus[(vus.elapsed_s >= lo) & (vus.elapsed_s < hi)].metric_value
        rows.append({"start_s": int(lo), "requests": int(len(d)), "rps": len(d) / bucket_s,
                     "errors": int(f.sum()) if len(f) else 0,
                     "med_ms": _pct(d, 50), "p95_ms": _pct(d, 95),
                     "vus": int(v.max()) if len(v) else None})
    return rows


def _trends(summary, df) -> dict:
    """Every time metric (avg, med, p95, p99, max) for the metrics table."""
    out = {}
    if summary:
        for name, m in summary.get("metrics", {}).items():
            if m.get("type") == "trend" and m.get("contains") == "time" and "{" not in name:
                out[name] = _from_summary_trend(m["values"])
    elif df is not None:
        for name in df.metric_name.unique():
            if (name.startswith("http_req_") and name != "http_req_failed") or name == "iteration_duration":
                out[name] = _latency_stats(df[df.metric_name == name].metric_value.to_numpy(dtype=float))
    return out


def _csv_time(df, which: str):
    if df is None or df.empty:
        return None
    ts = getattr(df.timestamp, which)()
    return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_run(run: dict, settings: dict) -> dict:
    """Builds the metrics of one run from its summary and/or per-request results."""
    df = prepare_results(run["results"]) if run["results"] is not None else None
    summary, info = run["summary"], run["info"] or {}

    kpis = _kpis_from_results(df) if df is not None else {}
    if summary:
        for k, v in _kpis_from_summary(summary).items():
            if v not in (None, {}, []):
                kpis[k] = v
    kpis.setdefault("thresholds", [])

    ecs = info.get("ecs_task") or {}
    container = (ecs.get("Containers") or [{}])[0]
    scenario = run.get("scenario_config") or (summary or {}).get("config") or {}

    return {
        "scenario": run["scenario"],
        "run_id": run["run_id"],
        "location": run["location"],
        "prefix": run["prefix"],
        "files": run["files"],
        "label": info.get("label") or "",
        "started_at": info.get("started_at") or (summary or {}).get("started_at") or _csv_time(df, "min"),
        "finished_at": info.get("finished_at") or (summary or {}).get("finished_at") or _csv_time(df, "max"),
        "thresholds_passed": info.get("thresholds_passed",
                                      all(t["ok"] for t in kpis["thresholds"]) if kpis["thresholds"] else None),
        "scenario_config": scenario,
        "scenario_source": "copy saved with the run" if run.get("scenario_config") else
                           ("k6 summary" if scenario else "not available"),
        "setup": {
            "k6_version": info.get("k6_version"),
            "image": container.get("Image"),
            "image_id": container.get("ImageID"),
            "task_definition": f"{ecs['Family']}:{ecs['Revision']}" if ecs.get("Family") else None,
            "launch_type": ecs.get("LaunchType"),
            "cpu_vcpu": (ecs.get("Limits") or {}).get("CPU"),
            "memory_mb": (ecs.get("Limits") or {}).get("Memory"),
            "availability_zone": ecs.get("AvailabilityZone"),
            "auth_mode": (summary or {}).get("auth_mode"),
        },
        "kpis": kpis,
        "trends": _trends(summary, df),
        "timeline": _timeline(df, settings["timeline"]["bucket_seconds"]) if df is not None else [],
        "_df": df,   # used for charts, not exported
    }


def describe_load(executor: dict) -> str:
    """Human description of a k6 executor."""
    if not executor:
        return "-"
    kind = executor.get("executor")
    if kind == "constant-vus":
        return f"{executor.get('vus')} virtual user(s), constant, for {executor.get('duration')}"
    if kind == "ramping-vus":
        stages = " -> ".join(f"{s['target']} VUs in {s['duration']}" for s in executor.get("stages", []))
        return f"Ramping from {executor.get('startVUs', 0)} VUs: {stages}"
    if kind in ("shared-iterations", "per-vu-iterations"):
        return f"{executor.get('iterations')} iterations with {executor.get('vus')} virtual user(s)"
    return str(executor)


def data_quality(cur: dict, settings: dict) -> list:
    notes = []
    n = cur["kpis"].get("requests", 0)
    if n < settings["data_quality"]["min_requests_for_percentiles"]:
        notes.append(f"Small sample ({n} requests): p95 and p99 depend on very few requests and can "
                     f"change a lot between runs.")
    if not cur["files"]["k6-results.csv"]:
        notes.append("Per-request results (k6-results.csv) are missing: charts over time are not available.")
    if not cur["files"]["k6-summary.json"]:
        notes.append("k6-summary.json is missing: aggregated values were computed from the per-request results.")
    if cur["scenario_source"] != "copy saved with the run":
        notes.append("No copy of the scenario was saved with this run; its definition comes from the k6 summary.")
    if not cur["setup"].get("k6_version"):
        notes.append("The k6 version was not recorded for this run.")
    return notes


def export(run: dict) -> dict:
    """Run metrics without internal objects, for metrics.json and for the AI prompt."""
    return {k: v for k, v in run.items() if not k.startswith("_")}


def fmt_ms(v) -> str:
    if v is None:
        return "-"
    return f"{v:,.2f} ms" if v < 10 else f"{v:,.0f} ms"


def fmt_date(iso) -> str:
    if not iso:
        return "-"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        return iso
