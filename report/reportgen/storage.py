"""Read and write run files from S3 or from a local folder with the same layout:

    runs/<scenario>/<run_id>/k6-summary.json
    runs/<scenario>/<run_id>/k6-results.csv
    runs/<scenario>/<run_id>/run-info.json
"""

import io
import json
import os

import pandas as pd


class S3Store:
    def __init__(self, bucket: str):
        import boto3
        self.bucket = bucket
        self.s3 = boto3.client("s3")

    def location(self, key: str) -> str:
        return f"s3://{self.bucket}/{key}"

    def list_runs(self, scenario: str) -> list:
        prefix = f"runs/{scenario}/"
        runs = []
        for page in self.s3.get_paginator("list_objects_v2").paginate(
                Bucket=self.bucket, Prefix=prefix, Delimiter="/"):
            for p in page.get("CommonPrefixes", []):
                runs.append(p["Prefix"][len(prefix):].strip("/"))
        return sorted(runs)

    def read_bytes(self, key: str):
        try:
            return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except self.s3.exceptions.NoSuchKey:
            return None

    def write_bytes(self, key: str, data: bytes, content_type: str):
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)


class LocalStore:
    def __init__(self, root: str):
        self.root = root

    def location(self, key: str) -> str:
        return os.path.join(self.root, key)

    def list_runs(self, scenario: str) -> list:
        path = os.path.join(self.root, "runs", scenario)
        if not os.path.isdir(path):
            return []
        return sorted(d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d)))

    def read_bytes(self, key: str):
        path = os.path.join(self.root, key)
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            return f.read()

    def write_bytes(self, key: str, data: bytes, content_type: str):
        path = os.path.join(self.root, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)


def run_prefix(scenario: str, run_id: str) -> str:
    return f"runs/{scenario}/{run_id}"


def load_run(store, scenario: str, run_id: str) -> dict:
    """Loads the three files of a run. Missing files are returned as None."""
    prefix = run_prefix(scenario, run_id)
    files = {}

    raw = store.read_bytes(f"{prefix}/k6-summary.json")
    files["summary"] = json.loads(raw) if raw else None

    raw = store.read_bytes(f"{prefix}/run-info.json")
    files["info"] = json.loads(raw) if raw else None

    # copy of the scenario used in this run (saved by the k6 container); fallback: k6 summary config
    raw = store.read_bytes(f"{prefix}/scripts/scenarios/{scenario}.json")
    files["scenario"] = json.loads(raw) if raw else None

    raw = store.read_bytes(f"{prefix}/k6-results.csv")
    files["results"] = pd.read_csv(io.BytesIO(raw), low_memory=False) if raw else None

    return {
        "scenario": scenario,
        "run_id": run_id,
        "prefix": prefix,
        "location": store.location(prefix),
        "files": {
            "k6-summary.json": files["summary"] is not None,
            "run-info.json": files["info"] is not None,
            "k6-results.csv": files["results"] is not None,
            "scripts/ (scenario copy)": files["scenario"] is not None,
        },
        "summary": files["summary"],
        "info": files["info"],
        "results": files["results"],
        "scenario_config": files["scenario"],
    }
