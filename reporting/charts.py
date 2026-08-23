"""
reporting/charts.py

Deterministic chart and HTML report generation from
DeliveryEvidence's numeric fields.

Charts are built server-side with matplotlib from numbers the
Data Retrieval Agent copied verbatim out of an Azure DevOps tool
result - the LLM never produces chart data itself, only the
narrative text. This keeps the visuals as trustworthy as the
deterministic sprint-health calculation they're drawn from.
"""

import base64
import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt


REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


def _fig_to_base64(fig) -> str:

    buffer = io.BytesIO()

    fig.savefig(
        buffer,
        format="png",
        bbox_inches="tight",
        dpi=120,
    )

    plt.close(fig)

    buffer.seek(0)

    return base64.b64encode(buffer.read()).decode("utf-8")


def build_status_pie_chart(evidence: dict) -> str | None:
    """
    Returns a base64-encoded PNG pie chart of work-item status
    (Completed / In Progress / New), or None if the evidence has
    no work-item status numbers to chart.
    """

    completed = evidence.get("completed_work_items")
    in_progress = evidence.get("in_progress_work_items")
    new = evidence.get("new_work_items")

    if completed is None and in_progress is None and new is None:
        return None

    labels = []
    values = []
    colors = []

    for label, value, color in [
        ("Completed", completed, "#2e7d32"),
        ("In Progress", in_progress, "#f9a825"),
        ("New", new, "#c62828"),
    ]:
        if value:
            labels.append(f"{label} ({value})")
            values.append(value)
            colors.append(color)

    if not values:
        return None

    fig, ax = plt.subplots(figsize=(4, 4))

    ax.pie(
        values,
        labels=labels,
        colors=colors,
        autopct="%1.0f%%",
        startangle=90,
    )

    title = evidence.get("iteration_name") or "Sprint"
    ax.set_title(f"{title} \u2014 Work Item Status")

    return _fig_to_base64(fig)


def build_effort_bar_chart(evidence: dict) -> str | None:
    """
    Returns a base64-encoded PNG bar chart of planned / completed /
    remaining effort hours, or None if the evidence has no effort
    numbers to chart.
    """

    planned = evidence.get("planned_hours")
    completed = evidence.get("completed_hours")
    remaining = evidence.get("remaining_hours")

    if planned is None and completed is None and remaining is None:
        return None

    labels = ["Original Estimate", "Logged", "Remaining (current)"]
    values = [planned or 0, completed or 0, remaining or 0]
    colors = ["#1565c0", "#2e7d32", "#c62828"]

    fig, ax = plt.subplots(figsize=(4, 4))

    bars = ax.bar(labels, values, color=colors)

    ax.set_ylabel("Hours")

    title = evidence.get("iteration_name") or "Sprint"
    ax.set_title(f"{title} \u2014 Effort Hours")

    # These three come from independently-maintained Azure DevOps
    # fields (Original Estimate, Completed Work, Remaining Work) and
    # are not derived from one another - they will not reliably sum
    # to the estimate. Caption this explicitly so the chart doesn't
    # read as broken math when they don't add up.
    fig.text(
        0.5,
        0.01,
        "Tracked independently in Azure DevOps - may not sum exactly.",
        ha="center",
        va="bottom",
        fontsize=7,
        color="#555555",
    )

    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{value:g}",
            ha="center",
            va="bottom",
        )

    fig.subplots_adjust(bottom=0.18)

    return _fig_to_base64(fig)


def save_chart_png(
    base64_data: str,
    report_id: str,
    name: str,
) -> Path:
    """
    Saves a base64 PNG to disk under REPORTS_DIR so it can be
    served as a direct image URL (e.g. for a Teams Adaptive Card
    Image element).
    """

    path = REPORTS_DIR / f"{report_id}_{name}.png"

    path.write_bytes(base64.b64decode(base64_data))

    return path


def build_html_report(
    *,
    question: str,
    answer: str,
    chart_pie_b64: str | None,
    chart_bar_b64: str | None,
    sources: list[str],
    report_id: str,
) -> Path:
    """
    Writes a self-contained HTML report (charts embedded as
    base64, no external requests needed to view it) to disk and
    returns its path.
    """

    charts_html = ""

    if chart_pie_b64:
        charts_html += (
            f'<img src="data:image/png;base64,{chart_pie_b64}" '
            'alt="Work item status" style="max-width:400px;margin:10px;">'
        )

    if chart_bar_b64:
        charts_html += (
            f'<img src="data:image/png;base64,{chart_bar_b64}" '
            'alt="Effort hours" style="max-width:400px;margin:10px;">'
        )

    answer_html = answer.replace("\n", "<br>")

    sources_text = ", ".join(sources) if sources else "None"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>MAQ Delivery Report</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; max-width: 900px;
          margin: 40px auto; color: #222; line-height: 1.5; }}
  h1 {{ color: #a4262c; }}
  .question {{ color: #555; font-style: italic; margin-bottom: 20px; }}
  .charts {{ display: flex; flex-wrap: wrap; justify-content: center; }}
  .sources {{ color: #555; font-size: 0.9em; margin-top: 24px;
              border-top: 1px solid #ddd; padding-top: 12px; }}
</style>
</head>
<body>
  <h1>MAQ Delivery Report</h1>
  <div class="question">{question}</div>
  <div>{answer_html}</div>
  <div class="charts">{charts_html}</div>
  <div class="sources"><strong>Sources:</strong> {sources_text}</div>
</body>
</html>
"""

    report_path = REPORTS_DIR / f"{report_id}.html"

    report_path.write_text(html, encoding="utf-8")

    return report_path