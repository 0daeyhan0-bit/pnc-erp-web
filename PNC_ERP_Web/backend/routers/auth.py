# -*- coding: utf-8 -*-
"""★인증 · 소속 강제 (협력사 포털 1단계, 2026-08-29)

왜 (PARTNER_PORTAL_DESIGN.md §1 실측)
  · 로그인이 프론트 JavaScript 안에서 끝났다  →  `String(u.pw)!==String(pw)`
  · `GET /api/perm/users` 가 누구에게나 평문 비밀번호를 그대로 내줬다
  · 협력사 API 가 `cust` 를 쿼리 파라미터로 받아 **값만 바꾸면 남의 계획이 보였다**

원칙
  > 협력사에게 열기 전에 **서버가 거부**해야 한다. 화면에서 숨기는 것은 보안이 아니다.

정본
  nx.app_user     계정(행 단위·해시 저장·partner_code=거래처코드)
  nx.app_session  토큰 세션
  ※ nx.web_user(JSON 한 행)는 **은퇴 대상**이다. 계정 정본을 두 곳에 두면 드리프트가 난다.
"""
import json
import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Body, Request, HTTPException

from common import _nx

router = APIRouter()

ITER = 120000
TTL_HOURS = 12            # 토큰 수명. 만료되면 다시 로그인.
FAIL_MAX = 5              # 연속 실패 한도
LOCK_MIN = 10             # 잠금 시간(분)


# ===================== 비밀번호 =====================
def hash_pw(pw, salt=None):
    """PBKDF2-HMAC-SHA256. 표준 라이브러리만 쓴다(서버에 새 의존성을 올리지 않는다)."""
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', str(pw).encode('utf-8'), salt.encode('utf-8'), ITER)
    return f"pbkdf2_sha256${ITER}${salt}${dk.hex()}"


def verify_pw(pw, stored):
    """저장된 해시와 대조. 형식이 깨졌거나 비어 있으면 **거부**(폴백 금지)."""
    try:
        algo, it, salt, _h = str(stored or "").split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac('sha256', str(pw).encode('utf-8'), salt.encode('utf-8'), int(it))
        return secrets.compare_digest(dk.hex(), _h)      # 타이밍 공격 방지
    except Exception:
        return False


# ===================== 토큰 =====================
def _token_of(request):
    """Authorization: Bearer … 또는 X-Auth-Token 에서 토큰을 꺼낸다."""
    h = request.headers.get("authorization") or ""
    if h.lower().startswith("bearer "):
        return h[7:].strip()
    return (request.headers.get("x-auth-token") or "").strip()


def _load_user(cur, uid):
    cur.execute("""SELECT user_id,name,utype,dept,pos,roles,partner_code,email,tel,status
                     FROM nx.app_user WHERE user_id=?""", uid)
    r = cur.fetchone()
    if not r:
        return None
    try:
        roles = json.loads(r[5] or "[]")
    except Exception:
        roles = []
    return {"id": str(r[0]).strip(), "nm": (r[1] or "").strip(), "utype": (r[2] or "내부").strip(),
            "dept": (r[3] or "").strip(), "pos": (r[4] or "").strip(), "roles": roles,
            "partner_code": (r[6] or "").strip() or None, "email": (r[7] or "").strip(),
            "tel": (r[8] or "").strip(), "status": (r[9] or "사용").strip()}


def current_user(request):
    """토큰이 있으면 사용자를, 없거나 만료면 None. **거부하지 않는다**(선택 검사용)."""
    tok = _token_of(request)
    if not tok:
        return None
    cn = _nx()
    cur = cn.cursor()
    try:
        cur.execute("""SELECT user_id FROM nx.app_session
                        WHERE token=? AND revoked=0 AND expires_at > GETDATE()""", tok)
        r = cur.fetchone()
        if not r:
            return None
        u = _load_user(cur, str(r[0]).strip())
        if not u or u["status"] != "사용":
            return None
        cur.execute("UPDATE nx.app_session SET last_seen=GETDATE() WHERE token=?", tok)
        cn.commit()
        return u
    finally:
        cn.close()


def require_user(request):
    """토큰 없으면 401. **보호할 API 는 이걸 쓴다.**"""
    u = current_user(request)
    if not u:
        raise HTTPException(401, "로그인이 필요합니다.")
    return u


# ===================== ★소속 강제 (핵심) =====================
def scope_cust(user, req_cust=None):
    """협력사 계정이면 **자기 거래처코드로 고정**한다. 파라미터를 신뢰하지 않는다.

       협력사가 URL 의 cust 를 남의 코드로 바꿔도 자기 것만 나온다.
       ★거래처코드가 없는 협력사 계정은 **아무것도 못 본다**(빈 값이 전체 조회로 새면 안 된다).
    """
    if user and user.get("utype") == "협력사":
        return user.get("partner_code") or "__NONE__"
    return req_cust


def enforce_cust(request, req_cust=None, required=True):
    """라우터에서 한 줄로 쓰는 형태 — (사용자, 적용할 cust) 를 돌려준다.

       required=True  : 무토큰 401 (협력사에 열린 API)
       required=False : 무토큰 통과 (내부 전용 API 를 아직 안 막았을 때)
    """
    u = require_user(request) if required else current_user(request)
    return u, scope_cust(u, req_cust)


# ===================== 로그인 =====================
@router.post("/api/auth/login")
def auth_login(request: Request, payload: dict = Body(...)):
    """아이디·비밀번호 → 토큰. ★대조는 여기(서버)서만 한다."""
    uid = str(payload.get("id", "")).strip()
    pw = str(payload.get("pw", ""))
    if not uid or not pw:
        raise HTTPException(400, "아이디와 비밀번호를 입력하세요.")
    cn = _nx()
    cur = cn.cursor()
    try:
        cur.execute("""SELECT pw_hash, status, ISNULL(fail_cnt,0), locked_until
                         FROM nx.app_user WHERE user_id=?""", uid)
        r = cur.fetchone()
        # ★없는 계정과 틀린 비밀번호를 같은 문구로 답한다(계정 존재 여부를 흘리지 않는다).
        BAD = "아이디 또는 비밀번호가 올바르지 않습니다."
        if not r:
            raise HTTPException(401, BAD)
        pw_hash, status, fail, locked = r[0], (r[1] or "사용").strip(), int(r[2]), r[3]
        if status != "사용":
            raise HTTPException(403, f"사용할 수 없는 계정입니다({status}).")
        if locked and locked > datetime.now():
            raise HTTPException(423, f"연속 실패로 잠겼습니다 — {locked:%H:%M} 이후 다시 시도하세요.")
        if not verify_pw(pw, pw_hash):
            fail += 1
            if fail >= FAIL_MAX:
                cur.execute("""UPDATE nx.app_user SET fail_cnt=0,
                                 locked_until=DATEADD(minute,?,GETDATE()) WHERE user_id=?""", LOCK_MIN, uid)
                cn.commit()
                raise HTTPException(423, f"연속 {FAIL_MAX}회 실패로 {LOCK_MIN}분 잠깁니다.")
            cur.execute("UPDATE nx.app_user SET fail_cnt=? WHERE user_id=?", fail, uid)
            cn.commit()
            raise HTTPException(401, f"{BAD} (남은 시도 {FAIL_MAX - fail}회)")

        tok = secrets.token_urlsafe(32)
        cur.execute("""INSERT INTO nx.app_session(token,user_id,issued_at,expires_at,last_seen,ip,ua,revoked)
                       VALUES(?,?,GETDATE(),DATEADD(hour,?,GETDATE()),GETDATE(),?,?,0)""",
                    tok, uid, TTL_HOURS,
                    (request.client.host if request.client else "")[:45],
                    (request.headers.get("user-agent") or "")[:300])
        cur.execute("""UPDATE nx.app_user SET last_login=GETDATE(), fail_cnt=0, locked_until=NULL
                        WHERE user_id=?""", uid)
        # 만료·폐기 세션은 여기서 함께 정리한다(별도 배치를 만들지 않는다).
        cur.execute("DELETE FROM nx.app_session WHERE expires_at < DATEADD(day,-7,GETDATE())")
        cn.commit()
        u = _load_user(cur, uid)
        return {"ok": True, "token": tok, "expires_hours": TTL_HOURS, "user": u}
    finally:
        cn.close()


@router.get("/api/auth/me")
def auth_me(request: Request):
    """현재 사용자. 토큰이 없거나 만료면 401 — 프론트가 로그인 화면으로 되돌린다."""
    return {"ok": True, "user": require_user(request)}


@router.post("/api/auth/logout")
def auth_logout(request: Request):
    tok = _token_of(request)
    if not tok:
        return {"ok": True, "revoked": 0}
    cn = _nx()
    cur = cn.cursor()
    try:
        cur.execute("UPDATE nx.app_session SET revoked=1 WHERE token=?", tok)
        n = cur.rowcount
        cn.commit()
        return {"ok": True, "revoked": n}
    finally:
        cn.close()


@router.post("/api/auth/password")
def auth_password(request: Request, payload: dict = Body(...)):
    """본인 비밀번호 변경. 현재 비밀번호를 확인한다."""
    u = require_user(request)
    old = str(payload.get("old", ""))
    new = str(payload.get("new", ""))
    if len(new) < 4:
        raise HTTPException(400, "새 비밀번호는 4자 이상이어야 합니다.")
    cn = _nx()
    cur = cn.cursor()
    try:
        cur.execute("SELECT pw_hash FROM nx.app_user WHERE user_id=?", u["id"])
        r = cur.fetchone()
        if not r or not verify_pw(old, r[0]):
            raise HTTPException(401, "현재 비밀번호가 올바르지 않습니다.")
        cur.execute("""UPDATE nx.app_user SET pw_hash=?, upd_user=?, upd_dt=GETDATE()
                        WHERE user_id=?""", hash_pw(new), u["id"], u["id"])
        # 비밀번호를 바꾸면 **다른 기기의 세션을 모두 끊는다**(도난 대비).
        cur.execute("UPDATE nx.app_session SET revoked=1 WHERE user_id=? AND token<>?",
                    u["id"], _token_of(request))
        cn.commit()
        return {"ok": True, "msg": "비밀번호를 변경했습니다. 다른 기기의 로그인은 해제됩니다."}
    finally:
        cn.close()
