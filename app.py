from __future__ import annotations

from pathlib import Path

import plotly.express as px
import streamlit as st

from clinic_diagnostic.ai_clients import ai_availability, generate_ai_report
from clinic_diagnostic.analytics import analyze_clinic
from clinic_diagnostic.auth import require_paid_access
from clinic_diagnostic.data_loader import WorkbookValidationError, load_and_validate_workbook
from clinic_diagnostic.reporting import display_monthly_table, money, pct, report_html
from clinic_diagnostic.schema import NO_PHI_WARNING


BASE_DIR = Path(__file__).parent
TEMPLATE_FILE = BASE_DIR / "outputs" / "hospital_management_diagnostic_sample.xlsx"

st.set_page_config(page_title="병원 경영진단 PRO", layout="wide", initial_sidebar_state="expanded")
st.markdown(
    """
<style>
.block-container {padding-top: 2rem; max-width: 1420px;}
.hero {padding: 1.4rem 1.6rem; border-radius: 12px; background: linear-gradient(110deg,#123354,#1f7088); color:white; margin-bottom:1rem;}
.hero h1 {margin:0 0 .35rem 0; font-size:2rem;}
.hero p {margin:0; opacity:.92;}
.notice {background:#fff5e8; padding:.8rem 1rem; border-left:4px solid #e59627; margin:.8rem 0 1rem 0;}
</style>
""",
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="hero"><h1>병원 경영진단 PRO</h1><p>매출, 비용, 원무, 청구심사 지표를 한 화면에서 진단하고 실행계획까지 제시합니다.</p></div>',
    unsafe_allow_html=True,
)

identity = require_paid_access()
if not identity:
    st.stop()

with st.sidebar:
    st.caption(f"접속: {identity.user_id} ({identity.method})")
    st.header("자료 업로드")
    st.warning(NO_PHI_WARNING)
    if TEMPLATE_FILE.exists():
        st.download_button(
            "작성 샘플 양식 다운로드",
            data=TEMPLATE_FILE.read_bytes(),
            file_name="병원경영진단_작성샘플양식.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    uploaded = st.file_uploader("작성 완료된 엑셀 업로드", type=["xlsx"], max_upload_size=30)

if uploaded is None:
    st.info("왼쪽에서 샘플 양식을 다운로드해 작성한 뒤 업로드하면 상세 진단이 표시됩니다.")
    st.markdown(
        '<div class="notice">수집 영역: 인건비, 고정비, 구매비, 매출, 원무, 주상병 집계, 청구 삭감·미수금·예약부도 및 목표 벤치마크</div>',
        unsafe_allow_html=True,
    )
    st.stop()

try:
    source = load_and_validate_workbook(uploaded)
    result = analyze_clinic(source)
except WorkbookValidationError as exc:
    st.error("업로드 양식을 확인해 주세요.")
    st.code(str(exc))
    st.stop()
except Exception as exc:
    st.error(f"파일을 분석하지 못했습니다: {exc}")
    st.stop()

latest_month = result.monthly.index[-1].strftime("%Y-%m")
st.caption(f"분석 기준월: {latest_month} | 업로드 자료의 입력 기준으로 산출")

metrics = result.latest_metrics
cols = st.columns(5)
cols[0].metric("총매출", money(metrics["revenue"]))
cols[1].metric("인건비율", pct(metrics["payroll_ratio"]))
cols[2].metric("경영잉여율", pct(metrics["surplus_margin"]))
cols[3].metric("환자당 매출", money(metrics["revenue_per_visit"]))
cols[4].metric("삭감률", pct(metrics["adjustment_ratio"]))

tab_summary, tab_finance, tab_operations, tab_ai, tab_export = st.tabs(
    ["종합진단", "재무분석", "원무/청구", "AI 전문보고서", "보고서 내보내기"]
)

with tab_summary:
    st.subheader("우선 실행 과제")
    st.dataframe(result.priority_actions, use_container_width=True, hide_index=True)
    st.subheader("입력 목표 대비 현황")
    if result.benchmark.empty:
        st.info("목표벤치마크 시트를 작성하면 목표 범위 대비 경보를 표시합니다.")
    else:
        table = result.benchmark.copy()
        for key in ["현재값", "최소목표", "최대목표", "목표격차"]:
            table[key] = table.apply(
                lambda row: pct(row[key]) if "ratio" in str(row["지표키"]) or "margin" in str(row["지표키"]) else money(row[key]),
                axis=1,
            )
        st.dataframe(table, use_container_width=True, hide_index=True)
    with st.expander("분석 전제 및 한계", expanded=True):
        for note in result.data_notes:
            st.write(f"- {note}")

with tab_finance:
    monthly_display = display_monthly_table(result.monthly)
    left, right = st.columns([1.3, 1])
    with left:
        chart_data = result.monthly.reset_index()
        fig = px.line(chart_data, x="기준월", y=["총매출", "경영잉여"], markers=True, title="총매출 및 경영잉여 추이")
        fig.update_layout(yaxis_title="원", legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)
    with right:
        ratio_data = result.monthly.reset_index()
        fig = px.line(ratio_data, x="기준월", y=["인건비율", "고정비율", "구매비율"], markers=True, title="비용률 추이")
        fig.update_layout(yaxis_tickformat=".0%", yaxis_title="비율", legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)
    st.dataframe(
        monthly_display.style.format(
            {"총매출": "{:,.0f}", "총인건비": "{:,.0f}", "총고정비": "{:,.0f}", "총구매비": "{:,.0f}", "경영잉여": "{:,.0f}", "경영잉여율": "{:.1%}", "총내원환자수": "{:,.0f}", "삭감률": "{:.1%}"}
        ),
        use_container_width=True,
        hide_index=True,
    )

with tab_operations:
    left, right = st.columns(2)
    with left:
        st.subheader("최근월 주상병 구성")
        st.dataframe(result.top_diagnoses, use_container_width=True, hide_index=True)
    with right:
        st.subheader("최근월 구매비 구성")
        st.dataframe(result.purchase_mix, use_container_width=True, hide_index=True)
    st.subheader("심사·수납·예약 점검 지표")
    op = result.monthly[["청구액", "삭감액", "삭감률", "미수금잔액", "미수금비율", "예약부도율"]].reset_index()
    op["기준월"] = op["기준월"].dt.strftime("%Y-%m")
    st.dataframe(op.style.format({"청구액": "{:,.0f}", "삭감액": "{:,.0f}", "삭감률": "{:.1%}", "미수금잔액": "{:,.0f}", "미수금비율": "{:.1%}", "예약부도율": "{:.1%}"}), use_container_width=True, hide_index=True)

with tab_ai:
    st.subheader("AI 교차검토 기반 전문 보고서")
    available = ai_availability()
    options = [name for name, ready in available.items() if ready]
    if not options:
        st.info("서버 설정에 OpenAI 또는 Gemini API 키를 등록하면 정량 진단에 기반한 전문 보고서를 생성할 수 있습니다.")
    else:
        selected = st.multiselect("분석 엔진 선택", options=options, default=options)
        if st.button("AI 보고서 생성", type="primary", disabled=not selected):
            with st.spinner("집계 지표를 검토하고 실행계획을 구성하는 중입니다..."):
                st.session_state["ai_report"] = generate_ai_report(result, selected)
        if "ai_report" in st.session_state:
            report = st.session_state["ai_report"]
            for error in report.errors:
                st.warning(error)
            st.markdown(report.final_report)
            if len(report.provider_notes) > 1:
                with st.expander("모델별 초안 비교"):
                    for provider, text in report.provider_notes.items():
                        st.markdown(f"**{provider}**")
                        st.markdown(text)

with tab_export:
    st.subheader("전문 보고서 저장")
    ai_text = st.session_state.get("ai_report").final_report if "ai_report" in st.session_state else None
    html = report_html(result, ai_text)
    st.download_button(
        "HTML 보고서 다운로드",
        data=html.encode("utf-8"),
        file_name=f"{result.hospital_info.get('기관명', '병원')}_{latest_month}_경영진단.html",
        mime="text/html",
        type="primary",
    )
    st.caption("현재 화면 보고서와 동일한 제출자료 기반 결과를 저장합니다. AI 보고서를 생성한 경우 함께 포함됩니다.")

