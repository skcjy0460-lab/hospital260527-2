from __future__ import annotations

import json
import os
from dataclasses import dataclass

import streamlit as st

from .analytics import DiagnosticResult


@dataclass
class AIReport:
    final_report: str
    provider_notes: dict[str, str]
    errors: list[str]


def _config(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, os.getenv(name.upper(), default))
    except FileNotFoundError:
        value = os.getenv(name.upper(), default)
    return str(value or default)


def ai_availability() -> dict[str, bool]:
    return {
        "OpenAI GPT": bool(_config("openai_api_key")),
        "Google Gemini": bool(_config("gemini_api_key")),
    }


def _sanitized_payload(result: DiagnosticResult) -> str:
    monthly = result.monthly.reset_index().tail(12).copy()
    monthly["기준월"] = monthly["기준월"].dt.strftime("%Y-%m")
    fields = [
        "기준월", "총매출", "총인건비", "총고정비", "총구매비", "경영잉여", "경영잉여율",
        "총내원환자수", "신환수", "환자당매출", "삭감률", "미수금비율", "예약부도율",
    ]
    payload = {
        "기관": {key: value for key, value in result.hospital_info.items() if key not in {"대표자명", "전화번호"}},
        "월별지표": monthly[fields].to_dict(orient="records"),
        "목표판정": result.benchmark.to_dict(orient="records"),
        "우선조치": result.priority_actions,
        "주상병상위집계": result.top_diagnoses.to_dict(orient="records"),
        "해석제약": result.data_notes,
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


SYSTEM_INSTRUCTIONS = """당신은 병원 개원 및 경영 컨설턴트를 보조하는 경영분석 전문가입니다.
제공된 집계 수치만 사용하여 한국어로 전문 보고서를 작성하십시오.
환자 개인 정보, 의료적 진단의 적정성, 보험 청구 적법성은 추정하지 마십시오.
목표·벤치마크는 입력자가 제공한 기준임을 명확히 하고, 수치 근거가 없는 단정은 금지합니다.
출력은 다음 제목을 포함하십시오: 경영 요약, 핵심 수치 해석, 위험과 원인 가설, 30/90/180일 실행안, 추가로 받아야 할 데이터, 유의사항."""


def generate_ai_report(result: DiagnosticResult, selected: list[str]) -> AIReport:
    payload = _sanitized_payload(result)
    prompt = "아래 병원 집계 데이터에 기반하여 실행 가능한 경영진단 보고서를 작성하세요.\n\n" + payload
    notes: dict[str, str] = {}
    errors: list[str] = []
    if "OpenAI GPT" in selected:
        try:
            notes["OpenAI GPT"] = _openai_response(prompt)
        except Exception as exc:  # API failures should not erase deterministic analysis.
            errors.append(f"OpenAI GPT 분석 실패: {exc}")
    if "Google Gemini" in selected:
        try:
            notes["Google Gemini"] = _gemini_response(prompt)
        except Exception as exc:
            errors.append(f"Google Gemini 분석 실패: {exc}")

    if len(notes) > 1 and "OpenAI GPT" in notes:
        synthesis_prompt = (
            "다음은 동일 데이터에 대한 두 분석 초안입니다. 합의되는 위험은 우선 반영하고, "
            "의견이 갈리는 부분은 추가 확인사항으로 명시하여 최종 컨설팅 보고서를 작성하세요.\n\n"
            + "\n\n".join(f"[{provider}]\n{text}" for provider, text in notes.items())
        )
        try:
            final = _openai_response(synthesis_prompt)
        except Exception as exc:
            errors.append(f"교차검토 종합 실패: {exc}")
            final = notes["OpenAI GPT"]
    elif notes:
        final = next(iter(notes.values()))
    else:
        final = "AI API 키가 설정되지 않았거나 호출에 실패했습니다. 상단의 정량 진단 결과는 계속 사용할 수 있습니다."
    return AIReport(final, notes, errors)


def _openai_response(prompt: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=_config("openai_api_key"))
    response = client.responses.create(
        model=_config("openai_model", "gpt-5.5"),
        instructions=SYSTEM_INSTRUCTIONS,
        input=prompt,
    )
    return response.output_text


def _gemini_response(prompt: str) -> str:
    from google import genai

    client = genai.Client(api_key=_config("gemini_api_key"))
    response = client.models.generate_content(
        model=_config("gemini_model", "gemini-3.5-flash"),
        contents=SYSTEM_INSTRUCTIONS + "\n\n" + prompt,
    )
    return response.text

