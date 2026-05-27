from __future__ import annotations

from html import escape

import pandas as pd

from .analytics import DiagnosticResult


def money(value: float) -> str:
    return f"{value:,.0f} 원"


def pct(value: float) -> str:
    return f"{value:.1%}"


def report_html(result: DiagnosticResult, ai_text: str | None = None) -> str:
    latest_month = result.monthly.index[-1].strftime("%Y-%m")
    metrics = result.latest_metrics
    action_rows = "".join(
        f"<tr><td>{escape(a['priority'])}</td><td>{escape(a['area'])}</td>"
        f"<td>{escape(a['finding'])}</td><td>{escape(a['action'])}</td></tr>"
        for a in result.priority_actions
    )
    benchmark_html = result.benchmark.to_html(index=False, border=0, classes="table") if not result.benchmark.empty else "<p>입력된 목표가 없습니다.</p>"
    notes = "".join(f"<li>{escape(note)}</li>" for note in result.data_notes)
    ai_section = f"<h2>AI 교차검토 의견</h2><pre>{escape(ai_text)}</pre>" if ai_text else ""
    hospital = escape(result.hospital_info.get("기관명", "병원"))
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>{hospital} 경영진단</title>
<style>
body {{ font-family: Arial, sans-serif; color:#16243a; margin:40px; }}
h1 {{ color:#123354; border-bottom:3px solid #1f7088; padding-bottom:12px; }}
h2 {{ margin-top:30px; color:#123354; }}
.cards {{ display:flex; gap:12px; flex-wrap:wrap; }}
.card {{ background:#f2f7f8; border:1px solid #c8dadd; padding:12px 16px; min-width:180px; }}
.card strong {{ display:block; font-size:20px; margin-top:6px; }}
.table {{ border-collapse:collapse; width:100%; font-size:13px; }}
.table th,.table td {{ border:1px solid #d7e1e4; padding:8px; text-align:left; }}
.table th {{ background:#123354; color:white; }}
pre {{ white-space:pre-wrap; background:#f7f9fb; padding:18px; border:1px solid #d7e1e4; }}
</style></head><body>
<h1>{hospital} 월간 경영진단 보고서</h1>
<p>기준월: {latest_month} | 제출 자료 기반 관리 분석</p>
<div class="cards">
<div class="card">총매출<strong>{money(metrics['revenue'])}</strong></div>
<div class="card">인건비율<strong>{pct(metrics['payroll_ratio'])}</strong></div>
<div class="card">경영잉여율<strong>{pct(metrics['surplus_margin'])}</strong></div>
<div class="card">삭감률<strong>{pct(metrics['adjustment_ratio'])}</strong></div>
</div>
<h2>우선 실행 과제</h2>
<table class="table"><thead><tr><th>우선순위</th><th>영역</th><th>관찰 결과</th><th>실행 제안</th></tr></thead><tbody>{action_rows}</tbody></table>
<h2>목표 대비 판정</h2>{benchmark_html}
<h2>분석 유의사항</h2><ul>{notes}</ul>
{ai_section}
</body></html>"""


def display_monthly_table(monthly: pd.DataFrame) -> pd.DataFrame:
    columns = ["총매출", "총인건비", "총고정비", "총구매비", "경영잉여", "경영잉여율", "총내원환자수", "삭감률"]
    output = monthly[columns].reset_index()
    output["기준월"] = output["기준월"].dt.strftime("%Y-%m")
    return output

