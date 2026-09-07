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
FAIL_MAX = 10             # 연속 실패 한도 (2026-09-07 대표확정: 5 → 10)
INIT_PW = "1111"          # 관리자 비번초기화 기본값. 이 값으로는 **새 비번을 정할 수 없다**.
# ★LOCK_MIN(시간잠금)은 폐지했다(2026-09-07). 종전엔 5회 실패 시 10분 뒤 저절로 풀렸다.
#   대표확정 = "10회 틀리면 미접속, 관리자가 초기화해야 재접속".
#   시간이 지나 저절로 열리면 무차별 대입을 10분마다 재개할 수 있어 잠금의 의미가 없다.
#   구현 = locked_until 에 먼 미래값(LOCK_FOREVER)을 넣어 기존 잠금검사를 그대로 재사용한다.
LOCK_FOREVER = "9999-12-31"

# 비번변경 전에도 허용할 경로 — 그 외는 must_change_pw=1 이면 전부 403(아래 require_user).
_MUSTCHG_ALLOW = ("/api/auth/password", "/api/auth/me", "/api/auth/logout")


def _ensure_user_cols(cur):
    """★must_change_pw 컬럼 멱등 보장 (2026-09-07 신설).

       관리자가 비번을 초기화하면 1 이 되고, 사용자가 새 비번을 정하면 0 으로 내린다.
       "비번이 1111 인가"로 판정하지 않는 이유 —
         ① 사용자가 새 비번을 또 1111 로 정하면 무한 반복된다
         ② 관리자가 다른 초기비번을 쓰면 판정이 안 먹는다
       기본값 0 — 기존 계정이 갑자기 못 들어오면 안 된다.
    """
    try:
        cur.execute("""IF COL_LENGTH('PARTNER_ERP_TEST3.nx.app_user','must_change_pw') IS NULL
                         ALTER TABLE PARTNER_ERP_TEST3.nx.app_user
                           ADD must_change_pw bit NOT NULL CONSTRAINT DF_app_user_mcp DEFAULT 0""")
    except Exception:
        pass   # 권한 등으로 실패해도 로그인 자체는 막지 않는다(아래 ISNULL 로 방어)


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

_MCP_OK = None            # must_change_pw 컬럼 존재여부 캐시(매 요청 COL_LENGTH 하지 않는다)


def _has_mcp(cur):
    global _MCP_OK
    if _MCP_OK is None:
        try:
            cur.execute("SELECT COL_LENGTH('PARTNER_ERP_TEST3.nx.app_user','must_change_pw')")
            _MCP_OK = cur.fetchone()[0] is not None
        except Exception:
            _MCP_OK = False
    return _MCP_OK


def _load_user(cur, uid):
    # ★must_change_pw 는 컬럼이 없을 수도 있다(신설 전 구버전 DB) → ISNULL+COL_LENGTH 방어.
    #   여기서 실어야 require_user 가 비번변경 강제를 판정할 수 있다.
    _mcp = "ISNULL(must_change_pw,0)" if _has_mcp(cur) else "0"
    cur.execute(f"""SELECT user_id,name,utype,dept,pos,roles,partner_code,email,tel,status,{_mcp}
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
            "must_change": bool(r[10]),
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
    "/api/pref",                          # 내 화면설정(항목보기 등) — 본인 것만(user_id 파라미터 없음)
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
    "/api/plan/basedate",                 # 계획 공통 기준일(=마지막 업로드 일자축 첫날). 거래처 정보 없음·읽기전용
    "/api/partner/workcenters",           # 작업처 드롭다운 — ★소속강제 넣고 개방(자기 1건만)
    "/api/sagubledger/list",              # 사급 수불장 — 목록 (읽기)
    "/api/sagubledger/detail",            # 〃 상세 (읽기)
    "/api/delivedit/list",                # 거래명세표 수정 — 목록 (읽기·scope_cust 강제)
    "/api/delivedit/custs",               # 〃 거래처(자기 1건)
    "/api/delivedit/items",               # 〃 도번·자도번 목록
    "/api/delivedit/update",              # 〃 수량수정 (쓰기·_guard 가 출발20 이후 차단)
    "/api/delivedit/delete",              # 〃 삭제   (쓰기·동상)

    # ── 매입/매출 마감현황 (2026-09-06) ────────────────────────────────────
    #   레거시 협력사 메뉴의 「매입마감현황」·「매출마감현황」에 해당한다.
    #   내부 화면(SCREEN.purmagam/salemagam)을 그대로 쓰고 **조회 API 만** 연다.
    #   ★소속강제 = purmagam.py/salemagam.py 의 lines() 가 scope_cust 로 cust_code 를
    #     자기 코드로 덮는다(파라미터 불신). list 는 거래처별 집계라 협력사도 자기 행만 보인다.
    #   ★단가 재계산·저장·마감확정은 **열지 않는다** — 협력사는 조회만 한다.
    #     (화면의 재계산 버튼·체크박스는 core.js `canW`(PERM.canEdit) 게이트로 이미 숨는다)
    "/api/purmagam/list",                 # 매입마감 — 거래처별 집계 (읽기)
    "/api/purmagam/lines",                # 〃 P/No 상세 (읽기·scope_cust 강제)
    "/api/salemagam/list",                # 매출마감 — 거래처별 집계 (읽기)
    "/api/salemagam/lines",               # 〃 P/No 상세 (읽기·scope_cust 강제)
    "/api/salemagam/weight_quote",        # 〃 LME 중량정산(매출 화면이 함께 부름·읽기)

    # ── 협력사자재계획현황 (2026-09-06) ───────────────────────────────────
    #   레거시 w_pr_outside_040. 읽기 전용이고 scope_cust 로 거래처가 강제된다
    #   (coopplan.coopmatplan_list — 협력사는 cust 파라미터를 넣어도 자기 코드로 덮인다).
    "/api/coopmatplan/list",
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
    """토큰 없으면 401. **보호할 API 는 이걸 쓴다.**

       ★비번변경 강제(2026-09-07) — must_change=1 이면 비번변경·내정보·로그아웃 외
         **전부 403**. 화면에서 숨기는 게 아니라 서버가 거부한다(이 파일 머리말 원칙).
         관리자가 초기화한 계정이 초기비번 그대로 시스템을 쓰는 것을 막는다.
    """
    u = current_user(request)
    if not u:
        raise HTTPException(401, "로그인이 필요합니다.")
    if u.get("must_change"):
        try:
            path = request.url.path
        except Exception:
            path = ""
        if path not in _MUSTCHG_ALLOW:
            raise HTTPException(403, "비밀번호를 변경해야 계속 사용할 수 있습니다.")
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
        _ensure_user_cols(cur)
        cur.execute("""SELECT pw_hash, status, ISNULL(fail_cnt,0), locked_until,
                              ISNULL(must_change_pw,0)
                         FROM nx.app_user WHERE user_id=?""", uid)
        r = cur.fetchone()
        # ★없는 계정과 틀린 비밀번호를 같은 문구로 답한다(계정 존재 여부를 흘리지 않는다).
        BAD = "아이디 또는 비밀번호가 올바르지 않습니다."
        if not r:
            raise HTTPException(401, BAD)
        pw_hash, status, fail, locked = r[0], (r[1] or "사용").strip(), int(r[2]), r[3]
        must_chg = bool(r[4])
        if status != "사용":
            raise HTTPException(403, f"사용할 수 없는 계정입니다({status}).")
        # ★잠금은 시간이 지나도 안 풀린다 — 관리자만 해제한다(2026-09-07).
        LOCKED_MSG = (f"연속 {FAIL_MAX}회 실패로 잠긴 계정입니다. "
                      f"시스템관리자에게 비밀번호 초기화를 요청하세요.")
        if locked and locked > datetime.now():
            raise HTTPException(423, LOCKED_MSG)
        if not verify_pw(pw, pw_hash):
            fail += 1
            if fail >= FAIL_MAX:
                # ★fail_cnt 는 그대로 둔다 — 종전엔 0 으로 밀어 "몇 회 틀렸는지"가 사라졌다.
                #   관리자 화면이 실패횟수를 보여주려면 기록이 남아야 한다.
                cur.execute("""UPDATE nx.app_user SET fail_cnt=?, locked_until=?
                                WHERE user_id=?""", fail, LOCK_FOREVER, uid)
                cn.commit()
                _tok_forget()          # ★잠근 계정이 캐시된 토큰으로 계속 살면 안 된다
                raise HTTPException(423, LOCKED_MSG)
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
        # ★비번변경이 필요한 계정 — 토큰은 주되 서버가 다른 API 를 전부 막는다(require_user).
        #   임시토큰을 따로 두면 토큰 종류가 둘이 되어 fetch 래퍼·게이트를 전부 손봐야 한다.
        #   화면에서 숨기는 게 아니라 **서버가 거부**하므로 이 파일 머리말의 원칙에 맞는다.
        return {"ok": True, "token": tok, "expires_hours": TTL_HOURS, "user": u,
                "must_change": must_chg}
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


# ===================== ★사용자별 화면설정 (nx.user_pref, 2026-09-03) =====================
# 왜 — 항목보기(컬럼 순서·숨김) 같은 개인 설정을 브라우저 localStorage 에만 두면
#      ① 다른 PC 로 가면 기본값 ② 캐시를 지우면 사라짐 ③ 한 PC 를 여러 명이 쓰면 섞임.
#      로그인 계정에 붙여 서버에 둔다. 화면이 늘어나도 scope 만 다르게 쓰면 되는 범용 저장소.
# 구조 — (user_id, scope, pref_key) → pref_val(JSON 문자열).
#      예) ('TEST4','pp410','hidecols') → '["upper","lgh"]'
# ★본인 것만 읽고 쓴다 — user_id 를 파라미터로 받지 않는다(남의 설정을 건드릴 수 없다).


@router.get("/api/pref")
def pref_get(request: Request, scope: str = ""):
    """내 화면설정 조회. scope 미지정이면 전체. → {prefs:{key:파싱된값}}"""
    u = require_user(request)
    sc = (scope or "").strip()
    cn = _nx()
    cur = cn.cursor()
    try:
        if sc:
            cur.execute("""SELECT pref_key, pref_val FROM nx.user_pref
                            WHERE user_id=? AND scope=?""", u["id"], sc)
        else:
            cur.execute("""SELECT pref_key, pref_val FROM nx.user_pref
                            WHERE user_id=?""", u["id"])
        out = {}
        for k, v in cur.fetchall():
            try:
                out[str(k).strip()] = json.loads(v) if v else None
            except Exception:
                out[str(k).strip()] = v          # JSON 이 아니면 원문 그대로
        return {"ok": True, "prefs": out}
    finally:
        cn.close()


@router.post("/api/pref")
def pref_save(request: Request, payload: dict = Body(...)):
    """내 화면설정 저장. body {scope:'pp410', prefs:{key:value,...}}
       ★value=null 이면 그 키를 삭제한다(기본값으로 되돌리기 = '초기화')."""
    u = require_user(request)
    sc = str(payload.get("scope", "")).strip()
    if not sc:
        raise HTTPException(400, "scope 가 필요합니다.")
    prefs = payload.get("prefs")
    if not isinstance(prefs, dict):
        raise HTTPException(400, "prefs 는 객체여야 합니다.")
    cn = _nx()
    cur = cn.cursor()
    try:
        n = 0
        for k, v in prefs.items():
            k = str(k).strip()[:60]
            if not k:
                continue
            if v is None:
                cur.execute("""DELETE FROM nx.user_pref
                                WHERE user_id=? AND scope=? AND pref_key=?""", u["id"], sc, k)
            else:
                val = json.dumps(v, ensure_ascii=False)
                # MERGE 대신 UPDATE→없으면 INSERT (드라이버 호환·가독)
                cur.execute("""UPDATE nx.user_pref SET pref_val=?, upd_dt=GETDATE()
                                WHERE user_id=? AND scope=? AND pref_key=?""",
                            val, u["id"], sc, k)
                if cur.rowcount == 0:
                    cur.execute("""INSERT INTO nx.user_pref(user_id,scope,pref_key,pref_val,upd_dt)
                                   VALUES(?,?,?,?,GETDATE())""", u["id"], sc, k, val)
            n += 1
        cn.commit()
        return {"ok": True, "saved": n}
    finally:
        cn.close()


@router.post("/api/auth/password")
def auth_password(request: Request, payload: dict = Body(...)):
    """본인 비밀번호 변경. 현재 비밀번호를 확인한다."""
    u = require_user(request)
    old = str(payload.get("old", ""))
    new = str(payload.get("new", ""))
    # ★새 비번 규칙(2026-09-07 대표확정) — 4자 이상 + 초기비번 금지.
    #   초기비번을 그대로 다시 정하면 강제변경이 아무 의미가 없다.
    if len(new) < 4:
        raise HTTPException(400, "새 비밀번호는 4자 이상이어야 합니다.")
    if new == INIT_PW:
        raise HTTPException(400, f"초기 비밀번호({INIT_PW})는 사용할 수 없습니다. 다른 비밀번호를 정하세요.")
    if new == old:
        raise HTTPException(400, "현재 비밀번호와 다른 비밀번호를 정하세요.")
    cn = _nx()
    cur = cn.cursor()
    try:
        _ensure_user_cols(cur)
        cur.execute("SELECT pw_hash FROM nx.app_user WHERE user_id=?", u["id"])
        r = cur.fetchone()
        if not r or not verify_pw(old, r[0]):
            raise HTTPException(401, "현재 비밀번호가 올바르지 않습니다.")
        # ★must_change_pw 를 내린다 — 이걸 빠뜨리면 비번을 바꿔도 계속 변경화면에 갇힌다.
        cur.execute("""UPDATE nx.app_user SET pw_hash=?, must_change_pw=0,
                          upd_user=?, upd_dt=GETDATE()
                        WHERE user_id=?""", hash_pw(new), u["id"], u["id"])
        # 비밀번호를 바꾸면 **다른 기기의 세션을 모두 끊는다**(도난 대비).
        cur.execute("UPDATE nx.app_session SET revoked=1 WHERE user_id=? AND token<>?",
                    u["id"], _token_of(request))
        cn.commit()
        _tok_forget()                     # ★다른 기기 세션을 끊었으므로 캐시 전체를 버린다
        return {"ok": True, "msg": "비밀번호를 변경했습니다. 다른 기기의 로그인은 해제됩니다."}
    finally:
        cn.close()


# ===================== 관리자 전용 — 잠금해제 · 비번초기화 (2026-09-07 신설) =====================
#   ★시스템관리자만. 협력사는 COOP_ALLOW 에 넣지 않았으므로 전역 게이트가 먼저 403 을 준다.
#   ★세션 revoke + _tok_forget() 을 빠뜨리면 잠근/초기화한 계정이 옛 토큰으로 계속 돌아다닌다.

def _admin_only(request):
    """계정 보안조작은 시스템관리자만. sales._is_admin 과 같은 기준(roles 에 '시스템관리자')."""
    u = require_user(request)
    if "시스템관리자" not in (u.get("roles") or []):
        raise HTTPException(403, "계정 잠금해제·비밀번호 초기화는 시스템관리자만 할 수 있습니다.")
    return u


@router.post("/api/auth/admin/unlock")
def auth_admin_unlock(request: Request, payload: dict = Body(...)):
    """잠금 해제 — 실패횟수와 잠금표시를 지운다. 비밀번호는 건드리지 않는다."""
    adm = _admin_only(request)
    uid = str(payload.get("user_id") or payload.get("id") or "").strip()
    if not uid:
        raise HTTPException(400, "대상 아이디가 필요합니다.")
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM nx.app_user WHERE user_id=?", uid)
        if not cur.fetchone()[0]:
            raise HTTPException(404, f"계정을 찾을 수 없습니다({uid}).")
        cur.execute("""UPDATE nx.app_user SET fail_cnt=0, locked_until=NULL,
                          upd_user=?, upd_dt=GETDATE() WHERE user_id=?""", adm["id"], uid)
        cn.commit()
        _tok_forget()
        return {"ok": True, "user_id": uid, "msg": f"{uid} 계정의 잠금을 해제했습니다."}
    finally:
        cn.close()


@router.post("/api/auth/admin/resetpw")
def auth_admin_resetpw(request: Request, payload: dict = Body(...)):
    """비밀번호 초기화 — 초기비번으로 되돌리고 **다음 로그인 시 새 비번을 강제**한다.

       · pw 를 주면 그 값으로, 없으면 INIT_PW('1111')
       · must_change_pw=1 → require_user 가 비번변경 외 전부 403
       · 잠금·실패횟수도 함께 푼다(초기화했는데 잠긴 채면 못 들어온다)
       · ★그 계정의 세션을 전부 끊는다 — 안 그러면 옛 토큰으로 계속 쓴다
    """
    adm = _admin_only(request)
    uid = str(payload.get("user_id") or payload.get("id") or "").strip()
    newpw = str(payload.get("pw") or "").strip() or INIT_PW
    if not uid:
        raise HTTPException(400, "대상 아이디가 필요합니다.")
    cn = _nx(); cur = cn.cursor()
    try:
        _ensure_user_cols(cur)
        cur.execute("SELECT COUNT(*) FROM nx.app_user WHERE user_id=?", uid)
        if not cur.fetchone()[0]:
            raise HTTPException(404, f"계정을 찾을 수 없습니다({uid}).")
        cur.execute("""UPDATE nx.app_user SET pw_hash=?, must_change_pw=1,
                          fail_cnt=0, locked_until=NULL, upd_user=?, upd_dt=GETDATE()
                        WHERE user_id=?""", hash_pw(newpw), adm["id"], uid)
        cur.execute("UPDATE nx.app_session SET revoked=1 WHERE user_id=?", uid)
        cn.commit()
        _tok_forget()
        return {"ok": True, "user_id": uid, "init_pw": newpw,
                "msg": f"{uid} 계정의 비밀번호를 초기화했습니다. "
                       f"초기비번 {newpw} 로 접속하면 새 비밀번호를 정하게 됩니다."}
    finally:
        cn.close()
