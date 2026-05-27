from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass

import streamlit as st


@dataclass
class AccessIdentity:
    user_id: str
    method: str


def _secret(name: str, default: object = None) -> object:
    try:
        return st.secrets.get(name, os.getenv(name.upper(), default))
    except FileNotFoundError:
        return os.getenv(name.upper(), default)


def hash_license_key(value: str) -> str:
    return hashlib.sha256(value.strip().encode("utf-8")).hexdigest()


def validate_embed_token(token: str) -> AccessIdentity | None:
    shared_secret = str(_secret("embed_shared_secret", "") or "")
    if not shared_secret or not token:
        return None
    try:
        user_id, expires_at, supplied = token.split(".", 2)
        if int(expires_at) < int(time.time()):
            return None
        message = f"{user_id}.{expires_at}".encode("utf-8")
        expected = hmac.new(shared_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, supplied):
            return AccessIdentity(user_id=user_id, method="board_embed")
    except (ValueError, TypeError):
        return None
    return None


def require_paid_access() -> AccessIdentity | None:
    development_mode = str(_secret("development_mode", "false")).lower() == "true"
    if development_mode:
        return AccessIdentity("development", "local_development")
    if "paid_identity" in st.session_state:
        return st.session_state["paid_identity"]

    token = st.query_params.get("access_token", "")
    identity = validate_embed_token(token)
    if identity:
        st.session_state["paid_identity"] = identity
        return identity

    st.subheader("구독 회원 전용 진단")
    st.caption("이 페이지는 무료 체험 없이 유효한 구독 또는 게시판 연동 토큰이 있어야 이용할 수 있습니다.")
    with st.form("access_login"):
        user_id = st.text_input("가입 이메일 또는 기관 ID")
        license_key = st.text_input("라이선스 키", type="password")
        submitted = st.form_submit_button("접속")
    if submitted:
        allowed = set(_secret("license_key_hashes", []) or [])
        if hash_license_key(license_key) in allowed and user_id.strip():
            identity = AccessIdentity(user_id.strip(), "license")
            st.session_state["paid_identity"] = identity
            st.rerun()
        else:
            st.error("유효한 구독 정보를 확인할 수 없습니다.")
    return None

