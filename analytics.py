from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class DiagnosticResult:
    hospital_info: dict[str, str]
    monthly: pd.DataFrame
    latest_metrics: dict[str, float]
    benchmark: pd.DataFrame
    priority_actions: list[dict[str, str]]
    top_diagnoses: pd.DataFrame
    purchase_mix: pd.DataFrame
    data_notes: list[str]


def _sum_by_month(df: pd.DataFrame, fields: list[str]) -> pd.DataFrame:
    return df.groupby("기준월", as_index=True)[fields].sum()


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator.div(denominator.replace(0, np.nan)).fillna(0)


def analyze_clinic(data: dict[str, pd.DataFrame]) -> DiagnosticResult:
    revenue = _sum_by_month(data["월간매출"], ["급여매출", "비급여매출", "기타매출"])
    revenue["총매출"] = revenue.sum(axis=1)
    labor = _sum_by_month(
        data["인건비"], ["세전급여", "사용자부담세금보험", "인센티브", "퇴직충당금"]
    )
    labor["총인건비"] = labor.sum(axis=1)
    fixed_fields = [col for col in data["고정비"].columns if col != "기준월"]
    fixed = _sum_by_month(data["고정비"], fixed_fields)
    fixed["총고정비"] = fixed.sum(axis=1)
    purchasing = _sum_by_month(data["구매비"], ["구매액"]).rename(columns={"구매액": "총구매비"})
    admin = _sum_by_month(
        data["원무지표"], ["신환수", "총내원환자수", "재진수", "급여청구건수", "비급여환자수"]
    )
    operations = _sum_by_month(
        data["운영지표"],
        ["진료일수", "의사수", "청구액", "삭감액", "미수금잔액", "마케팅비", "예약건수", "예약부도건수"],
    )

    monthly = revenue.join([labor[["총인건비"]], fixed[["총고정비"]], purchasing, admin, operations], how="outer")
    monthly = monthly.fillna(0).sort_index()
    monthly["비급여비중"] = _safe_divide(monthly["비급여매출"], monthly["총매출"])
    monthly["인건비율"] = _safe_divide(monthly["총인건비"], monthly["총매출"])
    monthly["고정비율"] = _safe_divide(monthly["총고정비"], monthly["총매출"])
    monthly["구매비율"] = _safe_divide(monthly["총구매비"], monthly["총매출"])
    monthly["경영잉여"] = (
        monthly["총매출"] - monthly["총인건비"] - monthly["총고정비"] - monthly["총구매비"] - monthly["마케팅비"]
    )
    monthly["경영잉여율"] = _safe_divide(monthly["경영잉여"], monthly["총매출"])
    monthly["환자당매출"] = _safe_divide(monthly["총매출"], monthly["총내원환자수"])
    monthly["의사1인당매출"] = _safe_divide(monthly["총매출"], monthly["의사수"])
    monthly["신환비율"] = _safe_divide(monthly["신환수"], monthly["총내원환자수"])
    monthly["삭감률"] = _safe_divide(monthly["삭감액"], monthly["청구액"])
    monthly["미수금비율"] = _safe_divide(monthly["미수금잔액"], monthly["총매출"])
    monthly["예약부도율"] = _safe_divide(monthly["예약부도건수"], monthly["예약건수"])

    latest = monthly.iloc[-1]
    metrics = {
        "revenue": float(latest["총매출"]),
        "payroll_ratio": float(latest["인건비율"]),
        "fixed_cost_ratio": float(latest["고정비율"]),
        "purchase_ratio": float(latest["구매비율"]),
        "surplus_margin": float(latest["경영잉여율"]),
        "revenue_per_visit": float(latest["환자당매출"]),
        "new_patient_ratio": float(latest["신환비율"]),
        "adjustment_ratio": float(latest["삭감률"]),
        "receivable_ratio": float(latest["미수금비율"]),
        "no_show_ratio": float(latest["예약부도율"]),
    }

    benchmark = _benchmark_assessment(data["목표벤치마크"], metrics)
    actions = _build_actions(metrics, monthly, benchmark)
    top_diagnoses = (
        data["주상병집계"]
        .loc[data["주상병집계"]["기준월"] == monthly.index[-1]]
        .sort_values("내원건수", ascending=False)
        .head(10)[["주상병코드", "주상병명", "내원건수"]]
    )
    purchase_mix = (
        data["구매비"]
        .loc[data["구매비"]["기준월"] == monthly.index[-1]]
        .groupby("구분", as_index=False)["구매액"]
        .sum()
        .sort_values("구매액", ascending=False)
    )
    info = {str(row["항목"]): str(row["값"]) for _, row in data["기관정보"].iterrows()}
    notes = _data_notes(monthly, data["목표벤치마크"])

    return DiagnosticResult(info, monthly, metrics, benchmark, actions, top_diagnoses, purchase_mix, notes)


def _benchmark_assessment(targets: pd.DataFrame, metrics: dict[str, float]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in targets.iterrows():
        key = str(row["지표키"]).strip()
        if key not in metrics:
            continue
        value = metrics[key]
        low = float(row["최소목표"])
        high = float(row["최대목표"])
        direction = str(row["비교방향"]).strip()
        if direction == "낮을수록양호":
            status = "양호" if value <= high else "주의"
            gap = value - high
        elif direction == "높을수록양호":
            status = "양호" if value >= low else "주의"
            gap = low - value
        else:
            status = "양호" if low <= value <= high else "주의"
            gap = 0 if status == "양호" else min(abs(value - low), abs(value - high))
        rows.append(
            {
                "지표키": key,
                "지표명": row["지표명"],
                "현재값": value,
                "최소목표": low,
                "최대목표": high,
                "상태": status,
                "목표격차": gap,
                "출처메모": row["출처메모"],
            }
        )
    return pd.DataFrame(rows)


def _build_actions(metrics: dict[str, float], monthly: pd.DataFrame, benchmark: pd.DataFrame) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    alerts = set(benchmark.loc[benchmark["상태"] == "주의", "지표키"]) if not benchmark.empty else set()
    if "payroll_ratio" in alerts:
        actions.append({"priority": "높음", "area": "인력 운영", "finding": "인건비율이 설정 목표 범위를 초과합니다.", "action": "직군별 생산성, 진료시간대별 배치, 인센티브 산식을 함께 점검하십시오."})
    if "adjustment_ratio" in alerts:
        actions.append({"priority": "높음", "area": "청구 심사", "finding": "삭감률이 목표 상한을 넘었습니다.", "action": "상위 삭감 사유와 주상병·행위 조합을 월별로 재분류하고 사전 점검 규칙을 수립하십시오."})
    if "receivable_ratio" in alerts:
        actions.append({"priority": "중간", "area": "수납/미수", "finding": "미수금 부담이 기준보다 높습니다.", "action": "보험·비급여·환자본인부담별 회수기간을 분리하여 수납 프로세스를 보완하십시오."})
    if "surplus_margin" in alerts or metrics["surplus_margin"] < 0:
        actions.append({"priority": "높음", "area": "손익 구조", "finding": "제출 비용 범위 내 경영잉여율이 목표에 미달합니다.", "action": "매출 믹스, 구매단가, 인력 및 고정비를 시나리오별로 조정해 손익분기 매출을 검토하십시오."})
    if len(monthly) >= 2:
        revenue_change = monthly["총매출"].pct_change().iloc[-1]
        visits_change = monthly["총내원환자수"].pct_change().iloc[-1]
        if revenue_change < -0.05 and visits_change < -0.05:
            actions.append({"priority": "중간", "area": "환자 흐름", "finding": "최근 월 매출과 내원환자수가 함께 감소했습니다.", "action": "신환 유입 경로와 재진 예약 이탈, 진료일수 변화를 분리해 점검하십시오."})
    if not actions:
        actions.append({"priority": "유지", "area": "모니터링", "finding": "입력된 목표 기준상 즉시 경보 지표가 없습니다.", "action": "월별 추세와 진료과·주상병별 변동을 지속 관찰하고 기준을 정기 갱신하십시오."})
    return actions


def _data_notes(monthly: pd.DataFrame, target: pd.DataFrame) -> list[str]:
    notes = [
        "경영잉여는 제출된 매출에서 인건비, 고정비, 구매비, 마케팅비를 차감한 관리지표이며 회계상 영업이익과 동일하지 않습니다.",
        "상병 분석은 집계 건수 기준이며 환자 단위 진료 적정성 평가나 의료적 판단을 의미하지 않습니다.",
    ]
    if len(monthly) < 12:
        notes.append("12개월 미만 데이터이므로 계절성·연간 추세 판단의 신뢰도가 제한됩니다.")
    if target.empty:
        notes.append("목표벤치마크가 비어 있어 목표 대비 판정은 제공되지 않습니다.")
    return notes

