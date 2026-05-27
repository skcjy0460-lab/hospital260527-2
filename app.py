from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from html import escape
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st


BASE_DIR = Path(__file__).parent
TEMPLATE_FILE = BASE_DIR / "outputs" / "hospital_management_diagnostic_sample.xlsx"
NO_PHI_WARNING = (
    "환자 성명, 주민등록번호, 차트번호, 전화번호 등 개인식별정보는 업로드하지 마십시오. "
    "본 프로그램은 월별 집계 및 주상병별 집계 데이터만 분석합니다."
)
REQUIRED_SHEETS = {
    "기관정보": ["항목", "값"],
    "월간매출": ["기준월", "급여매출", "비급여매출", "기타매출"],
    "인건비": ["기준월", "직군", "세전급여", "사용자부담세금보험", "인센티브", "퇴직충당금"],
    "고정비": ["기준월", "장비렌탈", "유지보수", "임차료", "전기료", "수도료", "통신비", "부채이자", "보험료", "전산서비스", "기타"],
    "구매비": ["기준월", "구분", "품목군", "구매액"],
    "원무지표": ["기준월", "신환수", "총내원환자수", "재진수", "급여청구건수", "비급여환자수"],
    "주상병집계": ["기준월", "주상병코드", "주상병명", "내원건수"],
    "운영지표": ["기준월", "진료일수", "의사수", "청구액", "삭감액", "미수금잔액", "마케팅비", "예약건수", "예약부도건수"],
    "목표벤치마크": ["지표키", "지표명", "최소목표", "최대목표", "비교방향", "출처메모"],
}


def config(name: str, default: object = "") -> object:
    try:
        return st.secrets.get(name, os.getenv(name.upper(), default))
    except FileNotFoundError:
        return os.getenv(name.upper(), default)


def require_paid_access() -> str | None:
    if str(config("enable_paid_access", "false")).lower() != "true":
        return "preview"
    if str(config("development_mode", "false")).lower() == "true":
        return "development"
    if "paid_user" in st.session_state:
        return st.session_state["paid_user"]

    token = st.query_params.get("access_token", "")
    secret = str(config("embed_shared_secret", "") or "")
    if token and secret:
        try:
            user_id, expires_at, supplied = token.split(".", 2)
            expected = hmac.new(secret.encode(), f"{user_id}.{expires_at}".encode(), hashlib.sha256).hexdigest()
            if int(expires_at) >= int(time.time()) and hmac.compare_digest(expected, supplied):
                st.session_state["paid_user"] = user_id
                return user_id
        except (ValueError, TypeError):
            pass

    st.subheader("구독 회원 전용 진단")
    st.caption("무료 체험 없이 유효한 구독 또는 게시판 연동 토큰이 있어야 이용할 수 있습니다.")
    with st.form("access_login"):
        user_id = st.text_input("가입 이메일 또는 기관 ID")
        license_key = st.text_input("라이선스 키", type="password")
        submitted = st.form_submit_button("접속")
    if submitted:
        digest = hashlib.sha256(license_key.strip().encode()).hexdigest()
        if digest in set(config("license_key_hashes", []) or []) and user_id.strip():
            st.session_state["paid_user"] = user_id.strip()
            st.rerun()
        st.error("유효한 구독 정보를 확인할 수 없습니다.")
    return None


def load_workbook(content: bytes) -> dict[str, pd.DataFrame]:
    sheets = pd.read_excel(BytesIO(content), sheet_name=None, header=3, engine="openpyxl")
    errors: list[str] = []
    data: dict[str, pd.DataFrame] = {}
    for sheet, required in REQUIRED_SHEETS.items():
        if sheet not in sheets:
            errors.append(f"`{sheet}` 시트가 없습니다.")
            continue
        frame = sheets[sheet].dropna(how="all").copy()
        missing = [column for column in required if column not in frame.columns]
        if missing:
            errors.append(f"`{sheet}` 시트에 필요한 열이 없습니다: {', '.join(missing)}")
            continue
        if sheet not in {"기관정보", "목표벤치마크"}:
            frame["기준월"] = pd.to_datetime(frame["기준월"], errors="coerce").dt.to_period("M").dt.to_timestamp()
            if frame["기준월"].isna().any():
                errors.append(f"`{sheet}` 시트의 기준월 형식을 확인하십시오.")
        data[sheet] = frame

    forbidden = ("환자명", "성명", "주민", "전화", "휴대폰", "주소", "차트번호", "환자번호")
    bad_columns = [str(c) for frame in sheets.values() for c in frame.columns if any(word in str(c) for word in forbidden)]
    if bad_columns:
        errors.append("개인식별정보로 해석될 수 있는 열이 있습니다: " + ", ".join(sorted(set(bad_columns))))
    if errors:
        raise ValueError("\n".join(errors))

    text_fields = {
        "인건비": {"기준월", "직군"},
        "구매비": {"기준월", "구분", "품목군"},
        "주상병집계": {"기준월", "주상병코드", "주상병명"},
        "목표벤치마크": {"지표키", "지표명", "비교방향", "출처메모"},
    }
    for sheet, frame in data.items():
        if sheet == "기관정보":
            continue
        for column in frame.columns:
            if column not in text_fields.get(sheet, {"기준월"}):
                frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    return data


def safe_divide(a: pd.Series, b: pd.Series) -> pd.Series:
    return a.div(b.replace(0, np.nan)).fillna(0)


def analyze(data: dict[str, pd.DataFrame]) -> dict[str, object]:
    revenue = data["월간매출"].groupby("기준월")[["급여매출", "비급여매출", "기타매출"]].sum()
    revenue["총매출"] = revenue.sum(axis=1)
    labor = data["인건비"].groupby("기준월")[["세전급여", "사용자부담세금보험", "인센티브", "퇴직충당금"]].sum()
    labor["총인건비"] = labor.sum(axis=1)
    fixed_cols = [c for c in data["고정비"].columns if c != "기준월"]
    fixed = data["고정비"].groupby("기준월")[fixed_cols].sum()
    fixed["총고정비"] = fixed.sum(axis=1)
    purchases = data["구매비"].groupby("기준월")[["구매액"]].sum().rename(columns={"구매액": "총구매비"})
    admin = data["원무지표"].groupby("기준월")[["신환수", "총내원환자수", "재진수", "급여청구건수", "비급여환자수"]].sum()
    ops = data["운영지표"].groupby("기준월")[["진료일수", "의사수", "청구액", "삭감액", "미수금잔액", "마케팅비", "예약건수", "예약부도건수"]].sum()
    monthly = revenue.join([labor[["총인건비"]], fixed[["총고정비"]], purchases, admin, ops], how="outer").fillna(0).sort_index()
    monthly["인건비율"] = safe_divide(monthly["총인건비"], monthly["총매출"])
    monthly["고정비율"] = safe_divide(monthly["총고정비"], monthly["총매출"])
    monthly["구매비율"] = safe_divide(monthly["총구매비"], monthly["총매출"])
    monthly["경영잉여"] = monthly["총매출"] - monthly["총인건비"] - monthly["총고정비"] - monthly["총구매비"] - monthly["마케팅비"]
    monthly["경영잉여율"] = safe_divide(monthly["경영잉여"], monthly["총매출"])
    monthly["환자당매출"] = safe_divide(monthly["총매출"], monthly["총내원환자수"])
    monthly["신환비율"] = safe_divide(monthly["신환수"], monthly["총내원환자수"])
    monthly["삭감률"] = safe_divide(monthly["삭감액"], monthly["청구액"])
    monthly["미수금비율"] = safe_divide(monthly["미수금잔액"], monthly["총매출"])
    monthly["예약부도율"] = safe_divide(monthly["예약부도건수"], monthly["예약건수"])

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
    rows = []
    for _, row in data["목표벤치마크"].iterrows():
        key = str(row["지표키"]).strip()
        if key not in metrics:
            continue
        value, low, high = metrics[key], float(row["최소목표"]), float(row["최대목표"])
        direction = str(row["비교방향"])
        good = value <= high if direction == "낮을수록양호" else value >= low if direction == "높을수록양호" else low <= value <= high
        rows.append({"지표키": key, "지표명": row["지표명"], "현재값": value, "최소목표": low, "최대목표": high, "상태": "양호" if good else "주의", "출처메모": row["출처메모"]})
    benchmark = pd.DataFrame(rows)
    alerts = set(benchmark.loc[benchmark["상태"] == "주의", "지표키"]) if not benchmark.empty else set()
    actions = []
    action_map = {
        "payroll_ratio": ("높음", "인력 운영", "인건비율이 목표 상한을 초과합니다.", "직군별 생산성과 진료시간대별 배치, 인센티브 산식을 점검하십시오."),
        "adjustment_ratio": ("높음", "청구 심사", "삭감률이 목표 상한을 초과합니다.", "상위 삭감 사유와 주상병·행위 조합을 분류해 사전점검 규칙을 마련하십시오."),
        "receivable_ratio": ("중간", "수납/미수", "미수금 부담이 기준보다 높습니다.", "회수기간을 부담 주체별로 나누어 수납 프로세스를 점검하십시오."),
        "surplus_margin": ("높음", "손익 구조", "경영잉여율이 목표에 미달합니다.", "매출 믹스와 주요 비용을 시나리오별로 조정해 손익분기 매출을 검토하십시오."),
    }
    for key in alerts:
        if key in action_map:
            priority, area, finding, proposal = action_map[key]
            actions.append({"우선순위": priority, "영역": area, "진단": finding, "실행제안": proposal})
    if not actions:
        actions = [{"우선순위": "유지", "영역": "모니터링", "진단": "설정된 목표 기준상 즉시 경보가 없습니다.", "실행제안": "월별 추세와 목표 기준을 정기 갱신하십시오."}]
    top_diagnoses = data["주상병집계"].loc[data["주상병집계"]["기준월"] == monthly.index[-1]].sort_values("내원건수", ascending=False).head(10)
    purchase_mix = data["구매비"].loc[data["구매비"]["기준월"] == monthly.index[-1]].groupby("구분", as_index=False)["구매액"].sum()
    info = {str(row["항목"]): str(row["값"]) for _, row in data["기관정보"].iterrows()}
    notes = [
        "경영잉여는 제출된 비용 항목을 차감한 관리지표이며 회계상 영업이익과 동일하지 않습니다.",
        "상병 분석은 집계 건수 기준이며 의료적 판단이나 청구 적법성 판정을 의미하지 않습니다.",
    ]
    if len(monthly) < 12:
        notes.append("12개월 미만 데이터이므로 계절성과 연간 추세 해석에는 제한이 있습니다.")
    return {"monthly": monthly, "metrics": metrics, "benchmark": benchmark, "actions": actions, "top_diagnoses": top_diagnoses, "purchase_mix": purchase_mix, "info": info, "notes": notes}


def money(value: float) -> str:
    return f"{value:,.0f} 원"


def pct(value: float) -> str:
    return f"{value:.1%}"


def generate_ai_report(result: dict[str, object], providers: list[str]) -> str:
    monthly = result["monthly"].reset_index().tail(12).copy()
    monthly["기준월"] = monthly["기준월"].dt.strftime("%Y-%m")
    payload = json.dumps(
        {"월별지표": monthly.to_dict(orient="records"), "목표판정": result["benchmark"].to_dict(orient="records"), "우선실행": result["actions"], "유의사항": result["notes"]},
        ensure_ascii=False,
        default=str,
    )
    instructions = "병원 경영 컨설팅 보조 전문가로서 제공된 집계 수치만 사용하십시오. 경영 요약, 위험, 30/90/180일 실행안, 추가 필요자료, 유의사항을 한국어로 작성하십시오. 의료적 판단이나 청구 적법성을 단정하지 마십시오."
    responses: list[str] = []
    if "OpenAI GPT" in providers:
        from openai import OpenAI

        response = OpenAI(api_key=str(config("openai_api_key"))).responses.create(model=str(config("openai_model", "gpt-5.5")), instructions=instructions, input=payload)
        responses.append("[OpenAI GPT]\n" + response.output_text)
    if "Google Gemini" in providers:
        from google import genai

        response = genai.Client(api_key=str(config("gemini_api_key"))).models.generate_content(model=str(config("gemini_model", "gemini-3.5-flash")), contents=instructions + "\n\n" + payload)
        responses.append("[Google Gemini]\n" + response.text)
    return "\n\n".join(responses)


def report_html(result: dict[str, object], ai_text: str = "") -> str:
    metrics, monthly = result["metrics"], result["monthly"]
    rows = "".join(f"<tr><td>{escape(a['우선순위'])}</td><td>{escape(a['영역'])}</td><td>{escape(a['진단'])}</td><td>{escape(a['실행제안'])}</td></tr>" for a in result["actions"])
    notes = "".join(f"<li>{escape(n)}</li>" for n in result["notes"])
    return f"""<!doctype html><meta charset="utf-8"><style>body{{font-family:Arial,sans-serif;margin:38px;color:#16243a}}h1,h2{{color:#123354}}.cards{{display:flex;gap:14px}}.card{{background:#f2f7f8;padding:15px;min-width:180px}}table{{border-collapse:collapse;width:100%}}td,th{{padding:8px;border:1px solid #d7e1e4}}th{{background:#123354;color:white}}pre{{white-space:pre-wrap;background:#f7f9fb;padding:18px}}</style><h1>{escape(result['info'].get('기관명','병원'))} 경영진단 보고서</h1><p>기준월: {monthly.index[-1].strftime('%Y-%m')}</p><div class="cards"><div class="card">총매출<br><strong>{money(metrics['revenue'])}</strong></div><div class="card">인건비율<br><strong>{pct(metrics['payroll_ratio'])}</strong></div><div class="card">경영잉여율<br><strong>{pct(metrics['surplus_margin'])}</strong></div></div><h2>우선 실행과제</h2><table><tr><th>우선순위</th><th>영역</th><th>진단</th><th>실행제안</th></tr>{rows}</table><h2>유의사항</h2><ul>{notes}</ul>{'<h2>AI 보고서</h2><pre>'+escape(ai_text)+'</pre>' if ai_text else ''}"""


st.set_page_config(page_title="병원 경영진단 PRO", layout="wide", initial_sidebar_state="expanded")
st.markdown("<style>.block-container{padding-top:2rem;max-width:1420px}</style>", unsafe_allow_html=True)
st.title("병원 경영진단 PRO")
st.caption("매출, 비용, 원무, 청구심사 지표를 한 화면에서 진단하고 실행계획까지 제시합니다.")
user_id = require_paid_access()
if not user_id:
    st.stop()

with st.sidebar:
    if user_id not in {"preview", "development"}:
        st.caption(f"접속: {user_id}")
    st.header("자료 업로드")
    st.warning(NO_PHI_WARNING)
    if TEMPLATE_FILE.exists():
        st.download_button("작성 샘플 양식 다운로드", TEMPLATE_FILE.read_bytes(), "병원경영진단_작성샘플양식.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    uploaded = st.file_uploader("작성 완료된 엑셀 업로드", type=["xlsx"])

if not uploaded:
    st.info("왼쪽에서 샘플 양식을 다운로드하여 작성한 뒤 업로드하면 상세 진단을 표시합니다.")
    st.stop()

try:
    result = analyze(load_workbook(uploaded.getvalue()))
except Exception as exc:
    st.error("업로드 파일을 분석하지 못했습니다.")
    st.code(str(exc))
    st.stop()

metrics = result["metrics"]
st.caption(f"분석 기준월: {result['monthly'].index[-1].strftime('%Y-%m')} | 업로드 집계자료 기반")
cards = st.columns(5)
cards[0].metric("총매출", money(metrics["revenue"]))
cards[1].metric("인건비율", pct(metrics["payroll_ratio"]))
cards[2].metric("경영잉여율", pct(metrics["surplus_margin"]))
cards[3].metric("환자당 매출", money(metrics["revenue_per_visit"]))
cards[4].metric("삭감률", pct(metrics["adjustment_ratio"]))

summary, finance, operations, ai_tab, export_tab = st.tabs(["종합진단", "재무분석", "원무/청구", "AI 전문보고서", "보고서 내보내기"])
with summary:
    st.subheader("우선 실행 과제")
    st.dataframe(result["actions"], hide_index=True, use_container_width=True)
    st.subheader("목표 대비 현황")
    st.dataframe(result["benchmark"], hide_index=True, use_container_width=True)
    for note in result["notes"]:
        st.caption("- " + note)
with finance:
    monthly = result["monthly"].reset_index()
    left, right = st.columns(2)
    left.plotly_chart(px.line(monthly, x="기준월", y=["총매출", "경영잉여"], markers=True, title="매출 및 경영잉여 추이"), use_container_width=True)
    right.plotly_chart(px.line(monthly, x="기준월", y=["인건비율", "고정비율", "구매비율"], markers=True, title="비용률 추이"), use_container_width=True)
    st.dataframe(monthly, hide_index=True, use_container_width=True)
with operations:
    left, right = st.columns(2)
    left.subheader("최근월 주상병 구성")
    left.dataframe(result["top_diagnoses"], hide_index=True, use_container_width=True)
    right.subheader("최근월 구매비 구성")
    right.dataframe(result["purchase_mix"], hide_index=True, use_container_width=True)
with ai_tab:
    options = []
    if config("openai_api_key"):
        options.append("OpenAI GPT")
    if config("gemini_api_key"):
        options.append("Google Gemini")
    selected = st.multiselect("분석 엔진 선택", options, default=options)
    if not options:
        st.info("Streamlit Secrets에 OpenAI 또는 Gemini API 키를 등록하면 AI 보고서를 생성합니다.")
    if st.button("AI 보고서 생성", disabled=not selected):
        with st.spinner("AI 보고서를 생성하는 중입니다..."):
            try:
                st.session_state["ai_text"] = generate_ai_report(result, selected)
            except Exception as exc:
                st.error(f"AI 보고서 생성에 실패했습니다: {exc}")
    if "ai_text" in st.session_state:
        st.markdown(st.session_state["ai_text"])
with export_tab:
    html = report_html(result, st.session_state.get("ai_text", ""))
    st.download_button("HTML 보고서 다운로드", html.encode("utf-8"), "병원경영진단_보고서.html", "text/html", type="primary")
