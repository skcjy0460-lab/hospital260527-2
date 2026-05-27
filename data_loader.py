from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pandas as pd

from .schema import REQUIRED_SHEETS


class WorkbookValidationError(ValueError):
    """Raised when uploaded clinic data does not conform to the template."""


def _read_workbook(source: str | Path | BinaryIO | bytes) -> dict[str, pd.DataFrame]:
    if isinstance(source, bytes):
        source = BytesIO(source)
    return pd.read_excel(source, sheet_name=None, header=3, engine="openpyxl")


def load_and_validate_workbook(source: str | Path | BinaryIO | bytes) -> dict[str, pd.DataFrame]:
    raw = _read_workbook(source)
    errors: list[str] = []
    cleaned: dict[str, pd.DataFrame] = {}

    for sheet, columns in REQUIRED_SHEETS.items():
        if sheet not in raw:
            errors.append(f"`{sheet}` 시트가 없습니다.")
            continue
        df = raw[sheet].dropna(how="all").copy()
        missing = [col for col in columns if col not in df.columns]
        if missing:
            errors.append(f"`{sheet}` 시트에 필요한 열이 없습니다: {', '.join(missing)}")
            continue
        if sheet not in {"기관정보", "목표벤치마크"}:
            df["기준월"] = pd.to_datetime(df["기준월"], errors="coerce").dt.to_period("M").dt.to_timestamp()
            if df["기준월"].isna().any():
                errors.append(f"`{sheet}` 시트의 기준월에 올바르지 않은 날짜가 있습니다.")
        cleaned[sheet] = df

    if errors:
        raise WorkbookValidationError("\n".join(errors))

    finance_sheets = ["월간매출", "인건비", "고정비", "구매비", "원무지표", "운영지표"]
    if any(cleaned[name].empty for name in finance_sheets):
        raise WorkbookValidationError("재무 및 운영 시트에는 최소 1개월의 데이터가 필요합니다.")

    _coerce_numeric(cleaned)
    _validate_privacy_columns(raw)
    return cleaned


def _coerce_numeric(data: dict[str, pd.DataFrame]) -> None:
    text_columns = {
        "기관정보": {"항목", "값"},
        "인건비": {"기준월", "직군"},
        "구매비": {"기준월", "구분", "품목군"},
        "주상병집계": {"기준월", "주상병코드", "주상병명"},
        "목표벤치마크": {"지표키", "지표명", "비교방향", "출처메모"},
    }
    for name, df in data.items():
        excluded = text_columns.get(name, {"기준월"})
        for col in df.columns:
            if col not in excluded:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)


def _validate_privacy_columns(raw: dict[str, pd.DataFrame]) -> None:
    forbidden = ("환자명", "성명", "주민", "전화", "휴대폰", "주소", "차트번호", "환자번호")
    columns = [str(col) for df in raw.values() for col in df.columns]
    detected = [col for col in columns if any(keyword in col for keyword in forbidden)]
    if detected:
        raise WorkbookValidationError(
            "개인식별정보로 해석될 수 있는 열이 발견되었습니다. 집계 자료만 업로드하십시오: "
            + ", ".join(sorted(set(detected)))
        )
