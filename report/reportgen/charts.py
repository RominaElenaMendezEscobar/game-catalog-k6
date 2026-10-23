"""Charts rendered with matplotlib as PNG images for the PDF.

Rules: one y-axis per chart, thin marks, recessive grid, purple as the main series and
salmon as the second one, a legend whenever there are two series.
"""

import io
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .metrics import PHASES

PHASE_NAMES = {"http_req_blocked": "Blocked", "http_req_connecting": "Connecting",
               "http_req_tls_handshaking": "TLS handshake", "http_req_sending": "Sending",
               "http_req_waiting": "Waiting (server)", "http_req_receiving": "Receiving"}


class Charts:
    def __init__(self, style: dict):
        self.c = style["colors"]
        self.main = style["series"]["main"]
        self.second = style["series"]["second"]
        self.size = (style["charts"]["width_in"], style["charts"]["height_in"])
        self.dpi = style["charts"]["dpi"]
        plt.rcParams.update({
            "font.family": "DejaVu Sans", "font.size": 8,
            "axes.facecolor": "#FBFBFD", "axes.edgecolor": self.c["rule"],
            "axes.labelcolor": self.c["muted"], "xtick.color": self.c["muted"],
            "ytick.color": self.c["muted"], "axes.grid": True, "grid.color": self.c["rule"],
            "grid.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False,
            "legend.frameon": True, "legend.edgecolor": self.c["rule"], "legend.fontsize": 7,
        })

    def _fig(self, height=None):
        fig, ax = plt.subplots(figsize=(self.size[0], height or self.size[1]))
        ax.set_axisbelow(True)
        return fig, ax

    def _png(self, fig) -> bytes:
        buf = io.BytesIO()
        fig.tight_layout()
        fig.savefig(buf, format="png", dpi=self.dpi, facecolor="white")
        plt.close(fig)
        return buf.getvalue()

    @staticmethod
    def _metric(df, name):
        d = df[df.metric_name == name].sort_values("timestamp")
        return d.elapsed_s.to_numpy(dtype=float), d.metric_value.to_numpy(dtype=float)

    def latency_timeline(self, run, p95_target=None) -> bytes:
        fig, ax = self._fig()
        x, y = self._metric(run["_df"], "http_req_duration")
        ax.scatter(x, y, s=22, color=self.c["purple_light"], alpha=0.8, linewidths=0, label="Request")
        window = max(3, len(y) // 10)
        med = np.array([np.median(y[max(0, i - window + 1):i + 1]) for i in range(len(y))])
        ax.plot(x, med, color=self.main, linewidth=2, label="Rolling median")
        if p95_target:
            ax.axhline(p95_target, color=self.second, linewidth=1, linestyle=":",
                       label=f"p95 threshold ({p95_target:,.0f} ms)")
        ax.set_xlabel("Elapsed time (s)")
        ax.set_ylabel("Duration (ms)")
        ax.set_ylim(bottom=0)
        ax.legend(loc="upper right")
        return self._png(fig)

    def latency_percentiles_timeline(self, run) -> bytes:
        fig, ax = self._fig()
        tl = [r for r in run["timeline"] if r["med_ms"] is not None]
        x = [r["start_s"] for r in tl]
        ax.plot(x, [r["med_ms"] for r in tl], color=self.main, linewidth=2, marker="o", markersize=4, label="p50 (median)")
        ax.plot(x, [r["p95_ms"] for r in tl], color=self.second, linewidth=2, marker="o", markersize=4, label="p95")
        ax.fill_between(x, [r["med_ms"] for r in tl], [r["p95_ms"] for r in tl], color=self.c["purple_soft"])
        ax.set_xlabel("Elapsed time (s)")
        ax.set_ylabel("Duration (ms)")
        ax.set_ylim(bottom=0)
        ax.legend(loc="upper right")
        return self._png(fig)

    def latency_distribution(self, run) -> bytes:
        fig, ax = self._fig()
        _, y = self._metric(run["_df"], "http_req_duration")
        ax.hist(y, bins=np.linspace(0, max(y.max(), 1), 25), color=self.main, rwidth=0.88)
        ax.set_xlabel("Duration (ms)")
        ax.set_ylabel("Requests")
        return self._png(fig)

    def percentiles(self, run, p95_target=None) -> bytes:
        lat = run["kpis"]["latency_ms"]
        keys, labels = ["med", "p90", "p95", "p99", "max"], ["p50", "p90", "p95", "p99", "max"]
        vals = [lat.get(k) or 0 for k in keys]
        fig, ax = self._fig()
        bars = ax.bar(labels, vals, width=0.55, color=self.main)
        for b, v in zip(bars, vals):
            ax.annotate(f"{v:,.0f} ms", (b.get_x() + b.get_width() / 2, v), xytext=(0, 2),
                        textcoords="offset points", ha="center", fontsize=7, color=self.c["text"])
        if p95_target:
            ax.axhline(p95_target, color=self.second, linewidth=1, linestyle=":",
                       label=f"p95 threshold ({p95_target:,.0f} ms)")
            ax.legend(loc="upper left")
        ax.set_ylabel("Duration (ms)")
        ax.grid(axis="x", visible=False)
        return self._png(fig)

    def phases(self, run) -> bytes:
        items = [(PHASE_NAMES[p], run["kpis"]["phases_ms"].get(p) or 0) for p in PHASES]
        fig, ax = self._fig(height=2.3)
        y = np.arange(len(items))
        bars = ax.barh(y, [v for _, v in items], height=0.6, color=self.main)
        for b, (_, v) in zip(bars, items):
            ax.annotate(f"{v:,.2f} ms" if v < 10 else f"{v:,.0f} ms", (v, b.get_y() + b.get_height() / 2),
                        xytext=(3, 0), textcoords="offset points", va="center", fontsize=7, color=self.c["text"])
        ax.set_yticks(y, [n for n, _ in items])
        ax.invert_yaxis()
        ax.set_xlabel("Average time per request (ms)")
        ax.grid(axis="y", visible=False)
        ax.set_xlim(0, (max(v for _, v in items) or 1) * 1.18)
        return self._png(fig)

    def throughput(self, run) -> bytes:
        fig, ax = self._fig()
        tl = run["timeline"]
        x, y = [r["start_s"] for r in tl], [r["rps"] for r in tl]
        ax.step(x, y, where="post", color=self.main, linewidth=2)
        ax.fill_between(x, y, step="post", color=self.c["purple_soft"])
        ax.set_xlabel("Elapsed time (s)")
        ax.set_ylabel("Requests per second")
        ax.set_ylim(bottom=0)
        return self._png(fig)

    def errors(self, run) -> bytes:
        fig, ax = self._fig(height=2.2)
        tl = run["timeline"]
        ax.bar([r["start_s"] for r in tl], [r["errors"] for r in tl], width=8, align="edge", color=self.second)
        ax.set_xlabel("Elapsed time (s)")
        ax.set_ylabel("Failed requests")
        ax.set_ylim(0, max(1, max(r["errors"] for r in tl) * 1.2))
        ax.grid(axis="x", visible=False)
        return self._png(fig)

    def vus(self, run) -> bytes:
        fig, ax = self._fig(height=2.2)
        x, y = self._metric(run["_df"], "vus")
        ax.step(x, y, where="post", color=self.main, linewidth=2)
        ax.fill_between(x, y, step="post", color=self.c["purple_soft"])
        ax.set_xlabel("Elapsed time (s)")
        ax.set_ylabel("Virtual users")
        ax.set_ylim(0, max(1, y.max() * 1.2))
        return self._png(fig)

    def by_lang(self, run) -> bytes:
        langs = sorted(run["kpis"]["by_lang"].items())
        fig, ax = self._fig(height=2.4)
        x = np.arange(len(langs))
        for i, (key, label, color) in enumerate([("med", "p50 (median)", self.main), ("p95", "p95", self.second)]):
            vals = [v.get(key) or 0 for _, v in langs]
            bars = ax.bar(x + (i - 0.5) * 0.36, vals, width=0.33, color=color, label=label)
            for b, v in zip(bars, vals):
                ax.annotate(f"{v:,.0f}", (b.get_x() + b.get_width() / 2, v), xytext=(0, 2),
                            textcoords="offset points", ha="center", fontsize=7, color=self.c["text"])
        ax.set_xticks(x, [f"{l} ({v['requests']} req.)" for l, v in langs])
        ax.set_ylabel("Duration (ms)")
        ax.grid(axis="x", visible=False)
        ax.legend(loc="upper right")
        return self._png(fig)
