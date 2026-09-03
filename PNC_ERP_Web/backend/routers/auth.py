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


# ★국내 절삭협력사(사용자 지정 명단, 2026-08-31) — 이 협력사들은 '협력사 발주현황(일반)'을 보지 않고
#   '협력사 계획현황'을 사용한다(포털 발주현황 탭 숨김). 나머지 협력사 = 일반 = 발주현황 노출.
#   코드 = CM_M_CUST.CUST_CODE. 대원2148·명진2306·미래정밀2096·세광2142·수테크2250·썬텍코리아233·
#   이젠터2068·중앙정밀2048·케이비2266·MTS2067·SKNT2030.
CUTTING_COOP_CODES = {"2148", "2306", "2096", "2142", "2250", "233",
                      "2068", "2048", "2266", "2067", "2030"}

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
    _pc = (r[6] or "").strip() or None
    return {"id": str(r[0]).strip(), "nm": (r[1] or "").strip(), "utype": (r[2] or "내부").strip(),
            "dept": (r[3] or "").strip(), "pos": (r[4] or "").strip(), "roles": roles,
            "partner_code": _pc, "email": (r[7] or "").strip(),
            "tel": (r[8] or "").strip(), "status": (r[9] or "사용").strip(),
            "is_cutting": bool(_pc and _pc in CUTTING_COOP_CODES)}


# ★토큰 캐시 — 인증을 **모든 요청**에 걸면 요청마다 SELECT×2 + UPDATE 가 된다.
#   그대로 두면 화면이 눈에 띄게 느려진다(측정 없이 넣지 말 것). 60초 캐시로 흡수한다.
#   로그아웃·비밀번호 변경·계정 저장은 즉시 무효화한다(stale 로 남으면 끊은 세션이 살아 있다).
_TOK_CACHE = {}          # token -> (user, expire_ts)
_TOK_TTL = 60.0


def _tok_forget(token=None):
    """캐시 무효화. token 없으면 전부 버린다(계정 일괄 저장 등)."""
    if token:
        _TOK_CACHE.pop(token, None)
    else:
        _TOK_CACHE.clear()


def current_user(request):
    """토큰이 있으면 사용자를, 없거나 만료면 None. **거부하지 않는다**(선택 검사용)."""
    tok = _token_of(request)
    if not tok:
        return None
    import time as _t
    hit = _TOK_CACHE.get(tok)
    if hit and hit[1] > _t.time():
        return hit[0]
    cn = _nx()
    cur = cn.cursor()
    try:
        cur.execute("""SELECT user_id FROM nx.app_session
                        WHERE token=? AND revoked=0 AND expires_at > GETDATE()""", tok)
        r = cur.fetchone()
        if not r:
            _TOK_CACHE.pop(tok, None)
            return None
        u = _load_user(cur, str(r[0]).strip())
        if not u or u["status"] != "사용":
            _TOK_CACHE.pop(tok, None)
            return None
        cur.execute("UPDATE nx.app_session SET last_seen=GETDATE() WHERE token=?", tok)
        cn.commit()
        _TOK_CACHE[tok] = (u, _t.time() + _TOK_TTL)
        if len(_TOK_CACHE) > 5000:            # 폭주 방지(로그인 폭주 시 메모리)
            _TOK_CACHE.clear()
        return u
    finally:
        cn.close()


# ===================== ★경로 정책 (미들웨어가 쓴다) =====================
# 무인증 허용 — 로그인 자체·정적자원·헬스체크. 그 외 /api/** 는 전부 토큰 필수.
OPEN_PATHS = {
    "/api/auth/login",
    "/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect",
}
OPEN_PREFIX = (
    "/api/_flow/",        # TestBed 제어(롤백서버에만 존재)
    # ★바코드·QR 이미지 생성(2026-08-31 추가) — 인쇄물의 <img src> 로 로드된다.
    #   08-29 전역 인증게이트 도입 때 예외에서 빠져 401 → 가간판·라벨·전표의 바코드/QR 이
    #   전부 **깨진 이미지 아이콘**으로 출력됐다(그 전에는 정상 출력, 실물 확인 2026-08-31).
    #   ※인쇄 팝업의 <img> 요청은 쿠키가 실리지 않는 경우가 있어 인증을 요구하면 안 된다.
    #   ※입력값(text)을 그대로 그림으로 만들 뿐 DB 를 읽지 않으므로 정보노출 위험 없음.
    "/api/barcode/",
)

# ★협력사 계정이 부를 수 있는 경로 — 여기 없는 것은 403.
#   deny by default. 새 협력사 화면을 만들면 **여기 한 줄 추가**한다(의식적으로).
COOP_ALLOW = {
    "/api/auth/me", "/api/auth/logout", "/api/auth/password",
    "/api/perm/users",                    # GET=본인 1건 / POST 는 라우터가 403
    "/api/partner/my",                    # 홈 요약(내 계획·내 송장·할 일)
    "/api/partner/qr",                    # 내 송장 QR (자기 것만)
    "/api/partner/depart",                # 송장 출발 처리(10→20)
    "/api/partner/planstatus",            # 내 계획
    "/api/partner/deliv420",              # 거래명세서 조회
    "/api/partner/deliv420/issue",        # 발행
    "/api/partner/deliv420/cancel",       # 발행취소
    "/api/partner/deliv420/invoice",      # 명세표 출력
    "/api/setin/list", "/api/setin/detail",
    "/api/setin/issue", "/api/setin/invoice",
    "/api/setstock/list",                 # 내 납품이 입고됐는지 확인(읽기전용·소속강제됨)
    "/api/coopporder/items",              # 협력사 발주현황(내 계획·재고·기발주·순소요, 읽기전용·소속강제됨)

    # ── 내부 ERP 「협력사」 폴더 개방 (2026-09-03) ──────────────────────────────
    #   협력사 계정이 index.html 로 들어와 자기 것만 보게 한다(core.js ROLE_MOD['협력사']).
    #   ★전부 scope_cust() 로 소속강제됨 — 자기 거래처 외 데이터는 못 본다.
    "/api/partner/workcenters",           # 작업처 드롭다운 — ★소속강제 넣고 개방(자기 1건만)
    "/api/sagubledger/list",              # 사급 수불장 — 목록 (읽기)
    "/api/sagubledger/detail",            # 〃 상세 (읽기)
    "/api/delivedit/custs",               # 거래명세표 수정 — 거래처(자기 1건)
    "/api/delivedit/items",               # 〃 도번·자도번 목록
    "/api/delivedit/update",              # 〃 수량수정 (쓰기·_guard 가 출발20 이후 차단)
    "/api/delivedit/delete",              # 〃 삭제   (쓰기·동상)
}
# ★★협력사에게 **열지 않은 것** — 뺀 이유를 남긴다(나중에 무심코 추가하지 않도록).
#   · /api/sagub/* 전부 (holding/list · adjust/list · adjust/save · adjust/delete)
#       사급은 **사급 수불장(/api/sagubledger/*)** 하나로 본다 — 같은 원장(nx.sagub_maint)을
#       보는 중복 화면이라 포털에서 「협력사사급재고관리」를 뺐다(2026-09-03).
#       특히 adjust/save·delete 는 열면 안 된다: 원장에 maint_tag='B' 를 직접 넣고
#       **음수를 허용**해, 협력사가 "실사 보정"으로 분실·과소비한 사급자재를 스스로
#       장부에서 지울 수 있다. 아무도 실물을 확인하지 않는다
#       → staff_only() 의 논리와 정확히 같은 상황.
#   ※/api/partner/workcenters 는 **소속강제를 넣은 뒤** 열었다(위 목록).
#     종전엔 request 파라미터조차 없어 인증을 걸 수 없었고 전 협력사 코드·이름·계획물량(n)을
#     그대로 줬다 — 그 상태로 열었으면 경쟁사 목록이 샜다. coopplan.py 에서 scope_cust 로
#     자기 1건만 남기도록 고친 뒤 개방. 직원은 종전대로 전체.
#   ※ scan/receive/cancel 은 staff_only — 담당자만


def path_policy(path):
    """(무인증 허용?, 경로) — 미들웨어에서 쓴다."""
    p = (path or "").split("?")[0].rstrip("/") or "/"
    if not p.startswith("/api/"):
        return True, p                     # 정적자원·프론트
    if p in OPEN_PATHS or path in OPEN_PATHS:
        return True, p
    if any(p.startswith(x) for x in OPEN_PREFIX):
        return True, p
    return False, p


def coop_allowed(path):
    p = (path or "").split("?")[0].rstrip("/") or "/"
    return p in COOP_ALLOW


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


def staff_only(request, what="이 작업"):
    """★우리 담당자 전용. 협력사 계정은 거부한다.

       입고 스캔·입고취소·장부수정은 **우리가 받는 행위**다. 협력사가 자기 송장을
       스스로 입고 처리하면 아무도 물건을 확인하지 않은 채 재고가 늘어난다.
    """
    u = require_user(request)
    if u.get("utype") == "협력사":
        raise HTTPException(403, f"{what}은(는) 담당자만 할 수 있습니다.")
    return u


def assert_own_barcode(cur, user, barcode, table="nx.set_input_req", col="barcode_no", cust_col="in_cust_code"):
    """★바코드가 그 협력사 것인지 확인한다.

       cust 파라미터가 없는 API(바코드만 받는 것)는 소속 강제를 걸 자리가 없다.
       그래서 **바코드의 주인**을 직접 확인한다 — 남의 송장 번호를 넣어도 열리면 안 된다.
    """
    if not user or user.get("utype") != "협력사":
        return
    mine = user.get("partner_code") or "__NONE__"
    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col}=? AND {cust_col}=?", str(barcode), mine)
    if not cur.fetchone()[0]:
        raise HTTPException(403, "다른 협력사의 문서입니다.")


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
        _tok_forget(tok)                  # ★캐시에 남아 있으면 끊은 세션이 계속 산다
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
        _tok_forget()                     # ★다른 기기 세션을 끊었으므로 캐시 전체를 버린다
        return {"ok": True, "msg": "비밀번호를 변경했습니다. 다른 기기의 로그인은 해제됩니다."}
    finally:
        cn.close()
