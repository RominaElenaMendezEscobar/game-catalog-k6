"""Load test report generator (one run per report).

AWS Lambda:  event = {"bucket": "...", "scenario": "smoke",
                      "run_id": "2026-10-22--18-06-30"}   # optional, default: latest run of the scenario
Local:       python app.py --local-dir ./data --scenario smoke [--run-id ...] [--no-ai]

Writes report.pdf, metrics.json and ai-analysis.json to runs/<scenario>/<run_id>/.
"""

import argparse
import json
import os

import yaml

from reportgen import ai, metrics
from reportgen.charts import Charts
from reportgen.pdf import build_pdf
from reportgen.storage import LocalStore, S3Store, load_run

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")


def load_config():
    def read(name):
        with open(os.path.join(CONFIG_DIR, name), encoding="utf-8") as f:
            return yaml.safe_load(f)
    return read("style.yaml"), read("metrics.yaml"), read("report.yaml")


def resolve_run(store, scenario: str, run_id):
    runs = store.list_runs(scenario)
    if not runs:
        raise ValueError(f"No runs found for scenario '{scenario}'")
    run_id = run_id or runs[-1]
    if run_id not in runs:
        raise ValueError(f"Run '{run_id}' not found. Available: {runs}")
    return run_id


def generate(store, scenario: str, run_id=None, use_ai=True) -> dict:
    style, glossary, settings = load_config()
    run_id = resolve_run(store, scenario, run_id)
    run = metrics.compute_run(load_run(store, scenario, run_id), settings)
    notes = metrics.data_quality(run, settings)

    payload = ai.build_payload(metrics.export(run), notes, glossary["metrics"])
    if use_ai and settings["ai"]["enabled"]:
        try:
            analysis = ai.analyze(payload, settings)
        except Exception as e:  # the report is still produced without the AI section
            analysis = ai.fallback(notes, f"error: {type(e).__name__}: {e}")
    else:
        analysis = ai.fallback(notes, "disabled")

    pdf_bytes = build_pdf(style, glossary, run, notes, analysis, Charts(style))

    out = {
        "metrics.json": (json.dumps({"run": metrics.export(run), "data_quality": notes},
                                    indent=2, default=str).encode(), "application/json"),
        "ai-analysis.json": (json.dumps(analysis, indent=2, default=str).encode(), "application/json"),
        "report.pdf": (pdf_bytes, "application/pdf"),
    }
    for name, (data, ctype) in out.items():
        store.write_bytes(f"{run['prefix']}/{name}", data, ctype)

    return {"scenario": scenario, "run_id": run_id,
            "report": store.location(f"{run['prefix']}/report.pdf"),
            "ai_used": analysis.get("model_id") is not None}


def handler(event, context):
    store = S3Store(event.get("bucket") or os.environ["BUCKET"])
    return generate(store, event["scenario"], event.get("run_id"), use_ai=event.get("use_ai", True))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Generate a PDF load test report")
    p.add_argument("--local-dir", help="local folder with runs/<scenario>/<run_id>/")
    p.add_argument("--bucket", help="S3 bucket (instead of --local-dir)")
    p.add_argument("--scenario", required=True)
    p.add_argument("--run-id")
    p.add_argument("--no-ai", action="store_true")
    a = p.parse_args()
    store = LocalStore(a.local_dir) if a.local_dir else S3Store(a.bucket)
    print(json.dumps(generate(store, a.scenario, a.run_id, use_ai=not a.no_ai), indent=2))
