# 병원 경영진단 PRO

병원 행정·청구심사 컨설팅 사이트의 유료 회원 전용 게시판에 삽입할 수 있는 `Streamlit` 진단 페이지입니다. 엑셀 집계자료를 업로드하면 재무, 원무, 청구 리스크, 설정한 목표 대비 격차를 분석하고 OpenAI GPT와 Google Gemini를 조합한 전문 보고서를 생성합니다.

## 제공 기능

- 월별 총매출, 급여/비급여 구성, 인건비율, 고정비율, 구매비율, 제출비용 기준 경영잉여율 분석
- 신환·내원환자, 환자당 매출, 청구 삭감률, 미수금 비율, 예약부도율 분석
- 주상병 및 구매유형 집계 표시. 환자 단위 개인정보는 수집하지 않음
- 사용자가 입력한 내부목표 또는 검증된 벤치마크와 비교하여 우선 실행과제 제시
- GPT, Gemini 단독 또는 두 모델 교차검토 보고서 생성
- HTML 전문 보고서 다운로드
- 라이선스 키 또는 상위 유료 사이트에서 발급한 만료 토큰으로만 접근

## Streamlit Cloud 업로드 최소 구성

현재 배포판은 import 오류를 방지하기 위해 `app.py` 단일 파일로 실행됩니다. GitHub 저장소 최상위에는 아래 파일만 올려도 앱이 실행됩니다.

```text
app.py
requirements.txt
outputs/
  hospital_management_diagnostic_sample.xlsx
.streamlit/
  config.toml
```

`clinic_diagnostic/` 및 `tools/` 폴더는 개발·확장용이므로 함께 올려도 되지만 실행에 필수는 아닙니다. `secrets.toml`은 GitHub에 올리지 말고 Streamlit Cloud의 Secrets 화면에서 직접 입력하십시오.

초기 화면 확인 및 고객 시연 단계에서는 별도의 라이선스 입력 없이 바로 이용하도록 구성되어 있습니다. 실제 유료 서비스로 오픈할 때 Streamlit Cloud Secrets에 아래 설정을 추가하면 회원 인증 화면이 활성화됩니다.

```toml
enable_paid_access = true
license_key_hashes = ["발급한_라이선스키의_SHA256_해시"]
```

`라이선스 키`는 향후 유료 결제를 완료한 병원 고객에게 운영자가 발급하는 접속 코드입니다. 현재 시연 단계에서는 입력할 필요가 없습니다.

## 실행

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .streamlit\secrets.toml.example .streamlit\secrets.toml
streamlit run app.py
```

최초 개발 확인 때만 `.streamlit/secrets.toml`의 `development_mode = true`로 설정하십시오. 운영 서비스에서는 반드시 `false`를 사용하고 유료 접근 설정을 완료해야 합니다.

## 엑셀 입력 양식

앱 좌측의 `작성 샘플 양식 다운로드` 버튼에서 양식을 제공합니다. 양식은 다음 시트를 포함합니다.

| 시트 | 내용 |
| --- | --- |
| 기관정보 | 기관명, 진료과, 지역, 작성 기준 |
| 월간매출 | 급여매출, 비급여매출, 기타매출 |
| 인건비 | 직군별 세전급여, 사용자부담 세금·보험, 인센티브, 퇴직충당금 |
| 고정비 | 렌탈, 유지보수, 임차료, 공과금, 통신, 이자, 보험, 전산 등 |
| 구매비 | 장비, 의료소모품, 약제 구매비 |
| 원무지표 | 신환수, 내원환자수, 재진수, 청구/비급여 집계 |
| 주상병집계 | 월별 주상병 코드·명칭별 내원건수 집계 |
| 운영지표 | 청구액, 삭감액, 미수금, 마케팅비, 예약부도 등 |
| 목표벤치마크 | 컨설턴트가 승인한 목표 범위와 근거 메모 |

샘플 입력값은 화면 동작을 확인하기 위한 가상 자료입니다. 공식 업계 평균 또는 의료기관 성과기준으로 사용하면 안 됩니다.

## 개인정보 및 판단 범위

- 환자 성명, 주민등록번호, 연락처, 차트번호 등의 개인정보를 업로드하지 마십시오.
- 상병 자료는 합계만 받으며 의료행위의 적정성 또는 청구 적법성을 자동 판정하지 않습니다.
- `경영잉여`는 제출한 비용 범위에 따른 관리지표이며 회계상 영업이익과 일치하지 않을 수 있습니다.
- AI 보고서는 컨설턴트 검토를 보조하며 최종 판단은 근거자료와 관련 규정을 확인하여 확정해야 합니다.

## 유료 회원 연동

### 라이선스 키

운영자가 고객별 키를 발급하고 SHA-256 해시만 `license_key_hashes`에 저장합니다.

```powershell
python -c "import hashlib; print(hashlib.sha256('발급할-키'.encode()).hexdigest())"
```

### 기존 사이트 게시판 iframe 연동

상위 사이트가 결제·로그인 검증 후 짧은 수명의 토큰을 발급해 iframe URL에 전달합니다. `embed_shared_secret`은 두 시스템의 서버에서만 보관해야 합니다.

```powershell
python tools\create_embed_token.py --user-id customer_001 --secret "긴-공유비밀" --minutes 30
```

```html
<iframe
  src="https://diagnostic.example.com/?access_token=발급된토큰"
  width="100%"
  height="1400"
  loading="lazy">
</iframe>
```

실서비스에서는 iframe 허용 도메인, HTTPS, API 키 비노출, 접속 로그, 결제 상태 재검증, 개인정보 처리방침 및 보유기간을 별도로 구성하십시오.

## AI API 설정

`.streamlit/secrets.toml`에서 다음 값을 설정합니다. 모델명은 운영 시 사용 가능한 모델 및 비용정책에 맞추어 변경할 수 있습니다.

```toml
openai_api_key = "..."
openai_model = "gpt-5.5"
gemini_api_key = "..."
gemini_model = "gemini-3.5-flash"
```

앱은 AI 호출 전에 집계된 지표와 목표 판정만 전송하고 개인식별정보가 의심되는 열이 포함된 업로드는 거부합니다.

## 공식 API 참고

- [OpenAI Text generation / Responses API](https://developers.openai.com/api/docs/guides/text)
- [OpenAI 최신 모델 가이드](https://developers.openai.com/api/docs/guides/latest-model)
- [Google Gemini API quickstart](https://ai.google.dev/gemini-api/docs/quickstart)
- [Streamlit secrets 관리](https://docs.streamlit.io/develop/api-reference/connections/st.secrets)
