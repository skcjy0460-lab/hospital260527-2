from __future__ import annotations

from dataclasses import dataclass


REQUIRED_SHEETS = {
    "기관정보": ["항목", "값"],
    "월간매출": ["기준월", "급여매출", "비급여매출", "기타매출"],
    "인건비": ["기준월", "직군", "세전급여", "사용자부담세금보험", "인센티브", "퇴직충당금"],
    "고정비": [
        "기준월",
        "장비렌탈",
        "유지보수",
        "임차료",
        "전기료",
        "수도료",
        "통신비",
        "부채이자",
        "보험료",
        "전산서비스",
        "기타",
    ],
    "구매비": ["기준월", "구분", "품목군", "구매액"],
    "원무지표": ["기준월", "신환수", "총내원환자수", "재진수", "급여청구건수", "비급여환자수"],
    "주상병집계": ["기준월", "주상병코드", "주상병명", "내원건수"],
    "운영지표": [
        "기준월",
        "진료일수",
        "의사수",
        "청구액",
        "삭감액",
        "미수금잔액",
        "마케팅비",
        "예약건수",
        "예약부도건수",
    ],
    "목표벤치마크": ["지표키", "지표명", "최소목표", "최대목표", "비교방향", "출처메모"],
}

NO_PHI_WARNING = (
    "환자 성명, 주민등록번호, 차트번호, 전화번호 등 개인식별정보는 업로드하지 마십시오. "
    "본 프로그램은 월별 집계 및 주상병별 집계 데이터만 분석합니다."
)


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    label: str
    format: str
    direction: str


METRICS = [
    MetricDefinition("revenue", "총매출", "currency", "higher"),
    MetricDefinition("payroll_ratio", "인건비율", "percent", "lower"),
    MetricDefinition("fixed_cost_ratio", "고정비율", "percent", "lower"),
    MetricDefinition("purchase_ratio", "구매비율", "percent", "lower"),
    MetricDefinition("surplus_margin", "제출비용 반영 경영잉여율", "percent", "higher"),
    MetricDefinition("revenue_per_visit", "내원환자 1인당 매출", "currency", "higher"),
    MetricDefinition("new_patient_ratio", "신환비율", "percent", "range"),
    MetricDefinition("adjustment_ratio", "청구 삭감률", "percent", "lower"),
    MetricDefinition("receivable_ratio", "미수금/매출 비율", "percent", "lower"),
    MetricDefinition("no_show_ratio", "예약부도율", "percent", "lower"),
]

