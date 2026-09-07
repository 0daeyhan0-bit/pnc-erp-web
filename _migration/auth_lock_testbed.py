# -*- coding: utf-8 -*-
"""로그인 보안 TestBed — 10회 잠금 · 관리자 초기화 · 초기비번 강제변경 (2026-09-07)

  ★안전: PARTNER_ERP_TEST3 단일 커넥션 · autocommit=False · commit 무력화 · 끝에서 rollback
         (flow_write_testbed.py 와 같은 방식) → DB 오염 0

  실행: python _migration/auth_lock_testbed.py
"""
import sys, os, io
BE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PNC_ERP_Web", "backend")
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
import common, db_client, pyodbc
from fastapi import HTTPException

CS = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
      f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
RAW = pyodbc.connect(CS, autocommit=False)


class NoCommit:
    def __init__(s, cn): object.__setattr__(s, '_cn', cn); object.__setattr__(s, '_c', [])
    def cursor(s):
        c = s._cn.cursor(); s._c.append(c); return c
    def commit(s): pass
    def rollback(s): pass
    def close(s):
        for c in s._c:
            try: c.close()
            except Exception: pass
        object.__setattr__(s, '_c', [])
    def __getattr__(s, k): return getattr(s._cn, k)


SH = NoCommit(RAW)
common._nx = lambda: SH
common._nx_tx = lambda: SH
import routers.auth as A
A._nx = lambda: SH
import routers.sales as S
S._nx = lambda: SH

cur = RAW.cursor()
OK, NG = [], []
UID = "__testbed_user__"
GOOD, NEW = "goodpw123", "newpw456"


def title(t):
    print("\n" + "=" * 80); print(" " + t); print("=" * 80)


def judge(n, c, d=""):
    (OK if c else NG).append(n)
    print(f"  {'PASS' if c else '★FAIL'}  {n}")
    if d:
        print(f"          {d}")


class Req:
    """current_user 가 보는 최소 요청객체 — 토큰과 경로."""
    def __init__(s, tok="", path="/api/whatever"):
        s.headers = {"authorization": f"Bearer {tok}"} if tok else {}
        s.client = type("C", (), {"host": "127.0.0.1"})()
        s.url = type("U", (), {"path": path})()


def login(pw):
    A._tok_forget()
    return A.auth_login(Req(), {"id": UID, "pw": pw})


def st():
    cur.execute("""SELECT ISNULL(fail_cnt,0), locked_until, ISNULL(must_change_pw,0)
                     FROM nx.app_user WHERE user_id=?""", UID)
    return cur.fetchone()


try:
    # ── 준비 ────────────────────────────────────────────────
    title("준비 — 시료 계정 생성 (롤백됨)")
    A._ensure_user_cols(cur)
    A._MCP_OK = None                      # 컬럼 캐시 리셋
    cur.execute("DELETE FROM nx.app_user WHERE user_id=?", UID)
    cur.execute("""INSERT INTO nx.app_user(user_id,pw_hash,name,utype,roles,status,fail_cnt,must_change_pw)
                   VALUES(?,?,N'테스트베드',N'내부',N'[]',N'사용',0,0)""", UID, A.hash_pw(GOOD))
    judge("시료 생성", True, f"{UID} · 비번 {GOOD} · FAIL_MAX={A.FAIL_MAX}")

    # ── ① 9회 실패 ──────────────────────────────────────────
    title("① 틀린 비번 9회 — 아직 잠기지 않아야 한다")
    for i in range(9):
        try: login("wrong")
        except HTTPException as e: last = e
    f, lk, _ = st()
    judge("9회 후 잠기지 않음", lk is None, f"fail_cnt={f} · locked_until={lk} · 마지막 status={last.status_code}")
    r = login(GOOD)
    judge("맞는 비번으로 로그인 성공", bool(r.get("ok")), f"must_change={r.get('must_change')}")
    f, lk, _ = st()
    judge("성공 시 실패횟수 초기화", f == 0 and lk is None, f"fail_cnt={f}")

    # ── ② 10회 실패 → 영구잠금 ──────────────────────────────
    title("② 틀린 비번 10회 — 잠기고, 맞는 비번으로도 못 들어간다")
    for i in range(10):
        try: login("wrong")
        except HTTPException as e: last = e
    f, lk, _ = st()
    judge("10회째 잠김(423)", last.status_code == 423, f"{last.detail}")
    judge("실패횟수가 보존됨", f >= A.FAIL_MAX, f"fail_cnt={f}  ← 종전엔 0으로 밀려 기록이 사라졌다")
    judge("영구잠금(먼 미래)", lk is not None and lk.year > 9000, f"locked_until={lk}")
    try:
        login(GOOD); judge("잠긴 뒤 맞는 비번 거부", False, "★로그인이 됐다")
    except HTTPException as e:
        judge("잠긴 뒤 맞는 비번도 거부", e.status_code == 423, f"{e.status_code} {e.detail}")

    # ── ③ 관리자 잠금해제 ───────────────────────────────────
    title("③ 관리자 잠금해제")
    cur.execute("SELECT TOP 1 user_id FROM nx.app_user WHERE roles LIKE N'%시스템관리자%' AND status=N'사용'")
    admin = str(cur.fetchone()[0]).strip()
    tok = "tb_admin_token"
    cur.execute("""INSERT INTO nx.app_session(token,user_id,issued_at,expires_at,last_seen,ip,ua,revoked)
                   VALUES(?,?,GETDATE(),DATEADD(hour,1,GETDATE()),GETDATE(),'','',0)""", tok, admin)
    A._tok_forget()
    r = A.auth_admin_unlock(Req(tok, "/api/auth/admin/unlock"), {"user_id": UID})
    f, lk, _ = st()
    judge("잠금해제 성공", bool(r.get("ok")) and lk is None, f"관리자={admin} · fail_cnt={f}")
    judge("해제 후 로그인 성공", bool(login(GOOD).get("ok")))

    # ── ④ 관리자 비번초기화 ─────────────────────────────────
    title("④ 관리자 비번초기화 — must_change_pw 가 서야 한다")
    A._tok_forget()
    r = A.auth_admin_resetpw(Req(tok, "/api/auth/admin/resetpw"), {"user_id": UID})
    f, lk, mc = st()
    judge("초기화 성공", bool(r.get("ok")), r.get("msg", "")[:70])
    judge("must_change_pw=1", mc == 1)
    cur.execute("SELECT COUNT(*) FROM nx.app_session WHERE user_id=? AND revoked=0", UID)
    judge("그 계정 세션 전부 해제", cur.fetchone()[0] == 0)

    # ── ⑤ 초기비번 로그인 → must_change ─────────────────────
    title("⑤ 초기비번 로그인 — 토큰은 주되 다른 API 는 막힌다")
    r = login(A.INIT_PW)
    utok = r.get("token")
    judge("초기비번으로 로그인됨", bool(r.get("ok")))
    judge("must_change=true 로 알려줌", r.get("must_change") is True, f"must_change={r.get('must_change')}")
    A._tok_forget()
    try:
        A.require_user(Req(utok, "/api/gagong/plan4w"))
        judge("다른 API 차단", False, "★통과해버렸다")
    except HTTPException as e:
        judge("다른 API 차단(403)", e.status_code == 403, f"{e.status_code} {e.detail}")
    try:
        A.require_user(Req(utok, "/api/auth/password"))
        judge("비번변경 경로는 허용", True)
    except HTTPException as e:
        judge("비번변경 경로는 허용", False, f"★막혔다 {e.detail}")

    # ── ⑥ 새 비번 규칙 ──────────────────────────────────────
    title("⑥ 새 비번 규칙 — 초기비번 재사용 금지")
    A._tok_forget()
    for bad, why in [(A.INIT_PW, "초기비번 그대로"), ("12", "4자 미만")]:
        try:
            A.auth_password(Req(utok, "/api/auth/password"), {"old": A.INIT_PW, "new": bad})
            judge(f"거부: {why}", False, "★통과해버렸다")
        except HTTPException as e:
            judge(f"거부: {why}", e.status_code == 400, f"{e.detail}")

    # ── ⑦ 정상 변경 → 해제 ─────────────────────────────────
    title("⑦ 새 비번 설정 → 강제변경 해제")
    A._tok_forget()
    r = A.auth_password(Req(utok, "/api/auth/password"), {"old": A.INIT_PW, "new": NEW})
    f, lk, mc = st()
    judge("비번 변경 성공", bool(r.get("ok")))
    judge("must_change_pw=0 으로 내려감", mc == 0, "이걸 빠뜨리면 계속 변경화면에 갇힌다")
    r2 = login(NEW)
    judge("새 비번으로 로그인", bool(r2.get("ok")) and r2.get("must_change") is False)
    A._tok_forget()
    try:
        A.require_user(Req(r2.get("token"), "/api/gagong/plan4w"))
        judge("이제 다른 API 도 통과", True)
    except HTTPException as e:
        judge("이제 다른 API 도 통과", False, f"★막혔다 {e.detail}")

    # ── ⑧ 비관리자 차단 ────────────────────────────────────
    title("⑧ 비관리자는 admin API 를 못 쓴다")
    A._tok_forget()
    for fn, nm in [(A.auth_admin_unlock, "unlock"), (A.auth_admin_resetpw, "resetpw")]:
        try:
            fn(Req(r2.get("token"), f"/api/auth/admin/{nm}"), {"user_id": UID})
            judge(f"비관리자 {nm} 차단", False, "★실행됐다")
        except HTTPException as e:
            judge(f"비관리자 {nm} 차단(403)", e.status_code == 403, f"{e.detail}")
    try:
        S.perm_save(Req(r2.get("token"), "/api/perm/save"), {"perms": {}})
        judge("비관리자 perm/save 차단", False, "★권한표가 지워졌다")
    except HTTPException as e:
        judge("비관리자 perm/save 차단(403)", e.status_code == 403, f"{e.detail}")

finally:
    title("정리 — 전량 롤백")
    try:
        RAW.rollback(); print("  ROLLBACK 완료 — DB 오염 0")
    except Exception as e:
        print("  ★롤백 실패:", str(e)[:150])
    print(f"\n  결과: PASS {len(OK)} · FAIL {len(NG)}")
    for n in NG:
        print("    ★", n)
    try: RAW.close()
    except Exception: pass
