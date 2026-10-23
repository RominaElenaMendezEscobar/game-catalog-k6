"""Builds the PDF report: scenario, test environment, results, metrics, analysis charts,
AI-generated summary and annex."""

import io
from datetime import datetime, timezone

from fpdf import FPDF
from fpdf.fonts import FontFace

from .metrics import describe_load, fmt_date, fmt_ms

REPLACE = {"→": "->", "≥": ">=", "≤": "<=", "•": "-", "–": "-", "—": "-", "…": "...",
           "’": "'", "‘": "'", "“": '"', "”": '"', "✔": "OK", "✖": "X", "×": "x"}


def clean(text) -> str:
    """Core PDF fonts (Helvetica) only support Latin-1 characters."""
    text = "" if text is None else str(text)
    for a, b in REPLACE.items():
        text = text.replace(a, b)
    return text.encode("latin-1", "replace").decode("latin-1")


def rgb(hex_color: str):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class ReportPDF(FPDF):
    def __init__(self, style: dict, footer_text: str):
        super().__init__(format=style["page"]["format"])
        self.c = style["colors"]
        self.font = style["fonts"]["family"]
        self.footer_text = footer_text
        m = style["page"]["margin_mm"]
        self.set_margins(m, m, m)
        self.set_auto_page_break(True, margin=m + 2)

    def footer(self):
        self.set_y(-11)
        self.set_draw_color(*rgb(self.c["rule"]))
        self.set_line_width(0.2)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_font(self.font, "", 7)
        self.set_text_color(*rgb(self.c["muted"]))
        self.cell(self.epw / 2, 6, clean(self.footer_text))
        self.cell(self.epw / 2, 6, f"Page {self.page_no()}", align="R")

    # ---------- text ----------

    def ensure_space(self, mm: float):
        if self.get_y() + mm > self.h - self.b_margin:
            self.add_page()

    def section(self, text: str, space=40):
        self.ensure_space(space)
        self.ln(3)
        y = self.get_y()
        self.set_fill_color(*rgb(self.c["text"]))
        self.rect(self.l_margin, y + 0.8, 1.6, 5.2, "F")
        self.set_x(self.l_margin + 4)
        self.set_font(self.font, "B", 12)
        self.set_text_color(*rgb(self.c["text"]))
        self.cell(0, 7, clean(text), new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def subtitle(self, text: str):
        self.set_font(self.font, "B", 10)
        self.set_text_color(*rgb(self.c["purple"]))
        self.cell(0, 6, clean(text), new_x="LMARGIN", new_y="NEXT")

    def numbered(self, text: str):
        self.ln(1)
        self.set_font(self.font, "B", 9)
        self.set_text_color(*rgb(self.c["purple"]))
        self.cell(0, 6, clean(text.upper()), new_x="LMARGIN", new_y="NEXT")

    def para(self, text: str, size=9, color=None, style=""):
        self.set_font(self.font, style, size)
        self.set_text_color(*rgb(color or self.c["text"]))
        self.multi_cell(0, size * 0.5, clean(text), new_x="LMARGIN", new_y="NEXT")
        self.ln(1.2)

    def bullet(self, text: str, label: str = None):
        self.set_x(self.l_margin + 2)
        self.set_font(self.font, "", 9)
        self.set_text_color(*rgb(self.c["purple"]))
        self.cell(4, 4.6, "-")
        self.set_text_color(*rgb(self.c["text"]))
        body = (f"**{clean(label)}** " if label else "") + clean(text)
        self.multi_cell(0, 4.6, body, markdown=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(0.6)

    def box(self, title: str, lines: list, fill: str, border: str, title_color: str):
        if not lines:
            return
        self.ensure_space(14 + 7 * len(lines))
        self.ln(2)
        y0 = self.get_y()
        self.set_fill_color(*rgb(fill))
        self.set_x(self.l_margin)
        self.set_font(self.font, "B", 9)
        self.set_text_color(*rgb(title_color))
        self.multi_cell(self.epw, 6, clean(title), fill=True, new_x="LMARGIN", new_y="NEXT", padding=(3, 4, 1, 5))
        self.set_font(self.font, "", 8.5)
        self.set_text_color(*rgb(self.c["text"]))
        for l in lines:
            self.multi_cell(self.epw, 4.6, "-  " + clean(l), fill=True, new_x="LMARGIN", new_y="NEXT",
                            padding=(0.8, 4, 0.8, 5))
        self.cell(self.epw, 2, "", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_fill_color(*rgb(border))
        self.rect(self.l_margin, y0, 1.4, self.get_y() - y0, "F")
        self.ln(3)

    # ---------- tables and tiles ----------

    def table_rows(self, header, rows, col_widths, status_col=None, font_size=8.3):
        head = FontFace(emphasis="BOLD", color=rgb("#FFFFFF"), fill_color=rgb(self.c["table_header"]))
        body = FontFace(color=rgb(self.c["text"]), fill_color=rgb(self.c["surface"]))
        first = FontFace(emphasis="BOLD", color=rgb(self.c["text"]), fill_color=rgb(self.c["surface"]))
        ok = FontFace(emphasis="BOLD", color=rgb(self.c["ok_text"]), fill_color=rgb(self.c["ok_fill"]))
        warn = FontFace(emphasis="BOLD", color=rgb(self.c["warn_text"]), fill_color=rgb(self.c["warn_fill"]))
        self.ensure_space(min(14 + 7 * len(rows), 90))
        self.set_font(self.font, "", font_size)
        self.set_draw_color(*rgb(self.c["rule"]))
        self.set_line_width(0.2)
        with self.table(col_widths=col_widths, headings_style=head, line_height=5.4,
                        borders_layout="ALL", text_align="LEFT", padding=(1.4, 2)) as t:
            r = t.row()
            for h in header:
                r.cell(clean(h))
            for row in rows:
                r = t.row()
                for i, v in enumerate(row):
                    v = "-" if v in (None, "") else clean(v)
                    if status_col is not None and i == status_col:
                        r.cell(v, style=ok if v.startswith("OK") else warn)
                    else:
                        r.cell(v, style=first if i == 0 else body)
        self.ln(3)

    def tiles(self, items: list, color: str, label_color: str):
        """items: list of (value, label). Four per row, like the reference layout."""
        per_row, h_val, h_lab = 4, 11, 7
        w = self.epw / per_row
        self.ensure_space(h_val + h_lab + 4)
        y = self.get_y()
        for i, (value, label) in enumerate(items[:per_row]):
            x = self.l_margin + i * w
            self.set_fill_color(*rgb(color))
            self.rect(x + 0.4, y, w - 0.8, h_val, "F")
            self.set_fill_color(*rgb(label_color))
            self.rect(x + 0.4, y + h_val, w - 0.8, h_lab, "F")
            self.set_xy(x, y + 1.5)
            self.set_font(self.font, "B", 14)
            self.set_text_color(255, 255, 255)
            self.cell(w, 8, clean(value), align="C")
            self.set_xy(x, y + h_val + 1.2)
            self.set_font(self.font, "", 7.2)
            self.cell(w, 4.6, clean(label), align="C")
        self.set_y(y + h_val + h_lab + 4)

    def chart(self, png: bytes, title: str, what: str, key_values: str, how_to_read: str, height_mm=62):
        self.ensure_space(height_mm + 30)
        self.subtitle(title)
        self.para(what, size=8.6)
        self.image(io.BytesIO(png), w=self.epw)
        self.ln(0.5)
        if key_values:
            self.para(key_values, size=8.2, color=self.c["purple"], style="B")
        self.para("How to read it: " + how_to_read, size=7.8, color=self.c["muted"])
        self.ln(3)


# ---------- the report ----------

def _p95_target(thresholds_cfg: dict):
    for rule in (thresholds_cfg or {}).get("http_req_duration", []):
        if rule.replace(" ", "").startswith("p(95)<"):
            return float(rule.split("<")[1])
    return None


def _bytes(v):
    if v is None:
        return "-"
    return f"{v / 1024:,.1f} KB" if v < 1024 * 1024 else f"{v / 1024 / 1024:,.2f} MB"


def build_pdf(style: dict, glossary: dict, run: dict, notes: list, analysis: dict, charts) -> bytes:
    c = style["colors"]
    pdf = ReportPDF(style, f"k6 load test report  ·  {run['scenario']} / {run['run_id']}")
    k, lat, cfg, setup = run["kpis"], run["kpis"].get("latency_ms", {}), run["scenario_config"], run["setup"]
    gm, gc = glossary["metrics"], glossary["charts"]
    target = _p95_target(cfg.get("thresholds"))

    # ---------- page 1: header, scenario, environment ----------
    pdf.add_page()
    pdf.set_font(pdf.font, "B", 20)
    pdf.set_text_color(*rgb(c["text"]))
    pdf.cell(0, 10, "Load Test Report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(pdf.font, "", 8.5)
    pdf.set_text_color(*rgb(c["muted"]))
    sub = (f"Game catalog search API  ·  Scenario: {run['scenario']}  ·  Run: {run['run_id']}"
           + (f"  ·  {run['label']}" if run["label"] else "")
           + f"  ·  Executed: {fmt_date(run['started_at'])}"
           + f"  ·  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    pdf.multi_cell(0, 4.4, clean(sub), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_draw_color(*rgb(c["purple"]))
    pdf.set_line_width(0.7)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + pdf.epw * 0.8, pdf.get_y())
    pdf.ln(4)

    pdf.section("Scenario")
    if cfg.get("description"):
        pdf.para(cfg["description"], size=9.2)
    started, finished = run["started_at"], run["finished_at"]
    duration = None
    try:
        duration = (datetime.fromisoformat(finished.replace("Z", "+00:00"))
                    - datetime.fromisoformat(started.replace("Z", "+00:00"))).total_seconds()
    except Exception:
        pass
    thresholds_cfg = cfg.get("thresholds") or {}
    pdf.table_rows(["Setting", "Value"], [
        ["Load profile", describe_load(cfg.get("executor"))],
        ["Duration", f"{duration:.0f} s ({fmt_date(started)} -> {fmt_date(finished)})" if duration else "-"],
        ["Think time", f"{cfg.get('think_time_seconds')} s between requests per user"
         if cfg.get("think_time_seconds") is not None else None],
        ["Request timeout", cfg.get("request_timeout")],
        ["Endpoint", f"POST {cfg.get('endpoint') or '-'}"],
        ["Test queries", cfg.get("queries_file")],
        ["Thresholds", "; ".join(f"{m}: {', '.join(r)}" for m, r in thresholds_cfg.items())],
        ["Authentication", "IAM (AWS Signature V4)" if setup.get("auth_mode") == "iam" else setup.get("auth_mode")],
        ["Scenario source", run["scenario_source"]],
    ], col_widths=(40, 138))

    pdf.section("Test environment and data sources")
    pdf.table_rows(["Item", "Value"], [
        ["k6 version", setup.get("k6_version") or "Not recorded"],
        ["Container image", setup.get("image")],
        ["Image ID", setup.get("image_id")],
        ["Task definition", setup.get("task_definition")],
        ["Compute", f"{setup.get('launch_type') or '-'} · {setup.get('cpu_vcpu') or '-'} vCPU · "
                    f"{setup.get('memory_mb') or '-'} MB · {setup.get('availability_zone') or '-'}"],
        ["Run folder", run["location"]],
        ["Files", ", ".join(f"{n}: {'yes' if ok else 'missing'}" for n, ok in run["files"].items())],
    ], col_widths=(40, 138))
    pdf.box("Data quality notes", notes, c["purple_soft"], c["purple"], c["purple"])

    # ---------- page 2: results and metrics ----------
    pdf.add_page()
    pdf.section("Results")
    pdf.tiles([(f"{k.get('requests', 0):,}", "Requests"),
               (f"{(k.get('throughput_rps') or 0):.2f}/s", "Throughput"),
               (f"{(k.get('error_rate') or 0) * 100:.2f} %", "Error rate"),
               (f"{(k.get('checks_rate') or 0) * 100:.1f} %" if k.get("checks_rate") is not None else "-", "Checks passed")],
              c["purple"], c["purple_light"])
    pdf.tiles([(fmt_ms(lat.get("med")), "Median (p50)"), (fmt_ms(lat.get("p95")), "p95"),
               (fmt_ms(lat.get("p99")), "p99"), (fmt_ms(lat.get("max")), "Max")],
              c["salmon"], c["salmon_light"])

    if k.get("thresholds"):
        values = {"http_req_duration": lat, "http_req_failed": {"rate": k.get("error_rate")}}
        rows = []
        for t in k["thresholds"]:
            name, rule = t["metric"], t["rule"]
            if name == "http_req_failed":
                v = f"{(k.get('error_rate') or 0) * 100:.2f} %"
            elif name == "http_req_duration" and rule.startswith("p("):
                key = {"p(95)": "p95", "p(99)": "p99", "p(90)": "p90"}.get(rule.split("<")[0], "p95")
                v = fmt_ms(lat.get(key))
            else:
                v = "-"
            rows.append([gm.get(name, {}).get("title", name), v, rule,
                         "OK" if t["ok"] else "Review: not met"])
        pdf.table_rows(["Threshold", "Value", "Rule", "Status"], rows, col_widths=(62, 36, 40, 40), status_col=3)

    pdf.section("Metrics")
    pdf.para("Latency metrics, in milliseconds. Each request is split into phases: blocked, connecting, "
             "TLS handshake, sending, waiting (server processing) and receiving.", size=8.4, color=c["muted"])
    order = ["http_req_duration", "http_req_waiting", "http_req_blocked", "http_req_connecting",
             "http_req_tls_handshaking", "http_req_sending", "http_req_receiving", "iteration_duration"]
    rows = []
    for name in order:
        t = run["trends"].get(name)
        if not t:
            continue
        g = gm.get(name, {})
        rows.append([g.get("title", name), g.get("short", ""), fmt_ms(t.get("avg")), fmt_ms(t.get("med")),
                     fmt_ms(t.get("p95")), fmt_ms(t.get("max"))])
    pdf.table_rows(["Metric", "What it measures", "Avg", "p50", "p95", "Max"], rows,
                   col_widths=(36, 66, 19, 19, 19, 19), font_size=7.6)

    rows = [
        ["http_reqs", f"{k.get('requests', 0):,} ({(k.get('throughput_rps') or 0):.2f} per second)"],
        ["http_req_failed", f"{(k.get('error_rate') or 0) * 100:.2f} %"],
        ["checks", f"{(k.get('checks_rate') or 0) * 100:.1f} %" if k.get("checks_rate") is not None else "-"],
        ["vus", f"{k.get('vus_max') or '-'} at most"],
        ["data_sent", _bytes(k.get("data_sent_bytes"))],
        ["data_received", _bytes(k.get("data_received_bytes"))],
    ]
    pdf.table_rows(["Metric", "What it measures", "Value"],
                   [[gm[n]["title"], gm[n]["short"], v] for n, v in rows],
                   col_widths=(36, 92, 50), font_size=7.6)

    if k.get("by_lang"):
        pdf.table_rows(["Query language", "Requests", "Error rate", "p50", "p95"],
                       [[lang, v.get("requests"), f"{(v.get('error_rate') or 0) * 100:.2f} %",
                         fmt_ms(v.get("med")), fmt_ms(v.get("p95"))] for lang, v in sorted(k["by_lang"].items())],
                       col_widths=(46, 33, 33, 33, 33), font_size=7.6)

    # ---------- analysis charts ----------
    pdf.section("Analysis charts", space=110)
    has_tl = run.get("_df") is not None and len(run["timeline"]) > 0

    def chart(key, png, key_values):
        pdf.chart(png, gc[key]["title"], gc[key]["what"], key_values, gc[key]["how_to_read"])

    if has_tl:
        chart("latency_timeline", charts.latency_timeline(run, target),
              f"Median {fmt_ms(lat.get('med'))} · p95 {fmt_ms(lat.get('p95'))} · max {fmt_ms(lat.get('max'))}.")
        chart("latency_percentiles_timeline", charts.latency_percentiles_timeline(run),
              f"Windows of {run['timeline'][1]['start_s'] - run['timeline'][0]['start_s'] if len(run['timeline']) > 1 else '-'} s.")
        chart("latency_distribution", charts.latency_distribution(run),
              f"{k.get('requests', 0)} requests between {fmt_ms(lat.get('min'))} and {fmt_ms(lat.get('max'))}.")
    chart("percentiles", charts.percentiles(run, target),
          f"p50 {fmt_ms(lat.get('med'))} · p90 {fmt_ms(lat.get('p90'))} · p95 {fmt_ms(lat.get('p95'))} · "
          f"p99 {fmt_ms(lat.get('p99'))}" + (f" · threshold p95 < {target:,.0f} ms." if target else "."))
    ph = k.get("phases_ms") or {}
    if ph:
        share = (ph.get("http_req_waiting") or 0) / (sum(v or 0 for v in ph.values()) or 1) * 100
        chart("phases", charts.phases(run),
              f"Waiting time (server processing) is {'>99.9' if share > 99.9 else f'{share:.1f}'} % of the request time.")
    if has_tl:
        chart("throughput", charts.throughput(run), f"Average {(k.get('throughput_rps') or 0):.2f} requests per second.")
        total_err = sum(r["errors"] for r in run["timeline"])
        chart("errors", charts.errors(run), f"{total_err} failed requests in total.")
        chart("vus", charts.vus(run), f"Up to {k.get('vus_max') or '-'} virtual users.")
    if k.get("by_lang"):
        chart("by_lang", charts.by_lang(run), None)
    if not has_tl:
        pdf.box("Charts over time not available",
                ["This run has no per-request results (k6-results.csv), so only aggregated charts are shown."],
                c["purple_soft"], c["purple"], c["purple"])

    # ---------- AI-generated summary ----------
    pdf.add_page()
    pdf.section("AI-generated summary")
    if analysis.get("model_id"):
        pdf.para(analysis.get("headline", ""), size=10.5, style="B")
        pdf.numbered("1. Overall assessment")
        pdf.para(analysis.get("summary", ""))
        n = 2
        if analysis.get("findings"):
            pdf.numbered(f"{n}. Key findings")
            n += 1
            for f in analysis["findings"]:
                pdf.bullet(f.get("detail", ""), label=f"{f.get('title', '')} ({f.get('severity', 'info')}):")
        if analysis.get("recommendations"):
            pdf.numbered(f"{n}. Recommendations")
            n += 1
            for r in analysis["recommendations"]:
                pdf.bullet(r)
        if analysis.get("caveats"):
            pdf.numbered(f"{n}. Caveats")
            for r in analysis["caveats"]:
                pdf.bullet(r)
        v = analysis.get("validation") or {}
        checks = [f"Response structure: {'valid' if v.get('structure_ok') else 'issues: ' + ', '.join(v.get('issues', []))}.",
                  f"Figures quoted by the model and checked against the computed metrics: {v.get('figures_checked', 0)}."]
        checks.append("Figures that could not be matched to a computed metric (review them): "
                      + ", ".join(f"{x:g}" for x in v["figures_not_traceable"]) + "."
                      if v.get("figures_not_traceable") else "All checked figures match the computed metrics.")
        checks.append(f"Confidence reported by the model: {analysis.get('confidence')}.")
        pdf.box("Validation of the AI answer", checks, c["purple_soft"], c["purple"], c["purple"])
    else:
        pdf.para(analysis.get("summary", ""))
    pdf.box("Please read before use", [
        f"This section is generated by Amazon Bedrock ({analysis.get('model_id') or 'not used'}) from the "
        "metrics computed in this report. The model interprets numbers; it does not measure anything.",
        "The tables and charts are the source of truth: always check the AI text against them.",
        "Causes suggested by the model are hypotheses consistent with the data, not confirmed diagnoses.",
    ], c["warn_fill"], c["warn_border"], c["warn_text"])

    # ---------- annex ----------
    pdf.add_page()
    pdf.section("Annex · Metric glossary")
    for name, g in gm.items():
        pdf.ensure_space(30)
        pdf.subtitle(f"{g['title']}  ({name}, {g['unit']})")
        pdf.para(g["what"], size=8.6)
        pdf.para(f"Calculation: {g['calculation']}", size=8, color=c["muted"])
        pdf.para(f"Example: {g['example']}", size=8, color=c["muted"])
        pdf.para(f"Why it matters: {g['why']}", size=8, color=c["text"])
        pdf.ln(1)

    return bytes(pdf.output())