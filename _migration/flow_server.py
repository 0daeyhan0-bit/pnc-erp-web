# -*- coding: utf-8 -*-
"""FLOW 검증 전용 백엔드 — **롤백 모드** (durable, 2026-08-28)

목적: **우리가 개발한 웹 화면을 실제로 작동시켜** 재고 flow 를 검증한다.
      (자재입고 → 키팅 → 생산실적 → 영업출고)

★일반 백엔드와 같은 앱을 띄우되, 기동 직전에 `_nx`/`_nx_tx` 를
  **no-commit 공유 커넥션**으로 몽키패치한다.
    · 화면 → HTTP → 라우터 → DB쓰기 **전 경로가 실제로 동작**한다
    · 그러나 commit() 이 no-op 이라 **DB 에 확정되지 않는다**
    · 검증이 끝나면 `/api/_flow/rollback` 으로 전부 되돌린다  ⟹ **오염 0**

추가 제어 엔드포인트(이 서버에만 존재):
    GET  /api/_flow/probe     현재 델타 관측(원장·수불장·재고)
    POST /api/_flow/mark      기준점 저장(라벨)
    POST /api/_flow/rollback  전체 롤백 + 오염 0 검증

사용:
    python _migration/flow_server.py            # 포트 8099
    python _migration/flow_server.py --port 8098
★운영/공유 DB 를 건드리지 않는다(커밋 안 함). 그래도 반드시 검증 목적으로만 사용할 것.
"""
import sys, os, io, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
BE = os.path.join(HERE, '..', 'PNC_ERP_Web', 'backend')
sys.path.insert(0, BE)
os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)

import common                     # db_client 경로를 sys.path 에 넣어준다
import pyodbc, db_client

CS = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
      f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')

RAW = pyodbc.connect(CS, autocommit=False)


class NoCommitConn:
    """공유 트랜잭션 커넥션 — 라우터가 commit/close 해도 트랜잭션은 유지한다.

       ★단, `close()` 는 **그 호출자가 받아 간 커서를 실제로 닫는다**(2026-08-30).
         앱의 계약은 `cn = _nx(); cur = cn.cursor(); ... finally: cn.close()` 이고,
         진짜 커넥션이면 close 로 커서가 함께 풀린다. 여기서 통째로 no-op 으로 두면
         **커서가 안 풀린 채 쌓여** MARS 꺼진 ODBC 에서 다음 요청이
         `HY000 다른 hstmt에 연결이 사용 중` 으로 터진다.
         실측: 스위트 첫 요청인 `/api/auth/login` 이 500 → 하네스가 통째로 로그인 실패 →
               뒤 40여 케이스가 SKIP 됐다.
       ⟹ 트랜잭션(commit/rollback)만 무력화하고, **커서 수명은 정상대로 지킨다.**
    """
    def __init__(self, cn):
        object.__setattr__(self, '_cn', cn)
        object.__setattr__(self, '_curs', [])
    def cursor(self):
        c = self._cn.cursor()
        self._curs.append(c)
        return c
    def commit(self): pass
    def close(self):
        # 내가 내준 커서만 닫는다(트랜잭션·커넥션은 그대로)
        for c in self._curs:
            try:
                c.close()
            except Exception:
                pass
        self._curs.clear()
    def rollback(self): pass       # 롤백은 제어 엔드포인트에서만
    def __enter__(self): return self
    def __exit__(self, *a): self.close(); return False
    def __getattr__(self, n): return getattr(self._cn, n)


SHARED = NoCommitConn(RAW)

# ★_nx() 는 **호출마다 새 래퍼**를 준다(트랜잭션은 RAW 하나로 공유).
#   싱글턴 하나를 돌려주면, 안쪽 함수가 `cn.close()` 할 때 **바깥 호출자의 커서까지** 닫힌다
#   (예: partner_my → partner_planstatus). 래퍼를 분리하면 각자 자기 커서만 정리한다.
def _shared_conn():
    return NoCommitConn(RAW)


# ── 몽키패치: common 먼저, 그 다음 app 임포트(라우터가 common 에서 가져감) ──
common._nx = _shared_conn
common._nx_tx = _shared_conn

# ★임포트 직전/직후 RAW 상태를 확인한다 — 모듈 레벨에서 커서를 잡고 안 놓는 코드를 찾기 위함
def _raw_ok(tag):
    try:
        c = RAW.cursor(); c.execute("SELECT 1"); c.fetchone(); c.close()
        print(f"[raw] {tag}: OK", flush=True)
    except Exception as e:
        print(f"[raw] {tag}: ★{type(e).__name__} {str(e)[:100]}", flush=True)


_raw_ok("app 임포트 전")
# ★워밍 스레드를 끄고 임포트한다 — 공유커넥션 하나를 스레드와 다투면 HY000.
os.environ["FLOW_TESTBED"] = "1"
import app as APP                 # ★여기서 라우터들이 임포트되며 패치된 _nx 를 가져간다
_raw_ok("app 임포트 후")

# 이미 임포트된 라우터 모듈에도 직접 주입(from common import _nx 형태 대비)
import importlib
_patched = 0
for name, mod in list(sys.modules.items()):
    if not name.startswith('routers.') and name not in ('live_api', 'common'):
        continue
    for attr in ('_nx', '_nx_tx'):
        if hasattr(mod, attr):
            setattr(mod, attr, _shared_conn); _patched += 1

# ★프로브는 **테스트 스코프(일자·품번)로 한정**한다.
#   전 테이블 COUNT(1.7M행)를 스텝마다 돌면 수십초 → 하네스가 못 돈다(2026-08-28 실측).
#   우리 테스트가 만든 델타만 보면 되므로 ymd/mat 로 좁히는 것이 더 정확하고 빠르다.
PROBES = [
    ("원장행",     "SELECT COUNT(*) FROM nx.stock_ledger WHERE MAINT_YMD=?"),
    ("원장MAT",    "SELECT ISNULL(SUM(CAST(MAINT_QTY AS float)),0) FROM nx.stock_ledger WHERE MAINT_YMD=? AND STOCK_POINT='MAT'"),
    ("원장RDY",    "SELECT ISNULL(SUM(CAST(MAINT_QTY AS float)),0) FROM nx.stock_ledger WHERE MAINT_YMD=? AND STOCK_POINT='RDY'"),
    ("원장PRD",    "SELECT ISNULL(SUM(CAST(MAINT_QTY AS float)),0) FROM nx.stock_ledger WHERE MAINT_YMD=? AND STOCK_POINT='PRD'"),
    ("원장ASY",    "SELECT ISNULL(SUM(CAST(MAINT_QTY AS float)),0) FROM nx.stock_ledger WHERE MAINT_YMD=? AND STOCK_POINT='ASY'"),
    ("자재수불장", "SELECT COUNT(*) FROM nx.PU_T_STOCK_MAINT WHERE MAINT_YMD=?"),
    ("수불장수량", "SELECT ISNULL(SUM(CAST(MAINT_QTY AS float)),0) FROM nx.PU_T_STOCK_MAINT WHERE MAINT_YMD=?"),
    ("공정실적수량", "SELECT ISNULL(SUM(CAST(PROD_QTY AS float)),0) FROM nx.proc_result WHERE PROD_YMD=?"),
    ("판매출고수량", "SELECT ISNULL(SUM(CAST(maint_qty AS float)),0) FROM nx.saleout_maint WHERE maint_ymd=?"),
]
# 품번 스코프(자재재고는 일자축이 없다)
PROBES_MAT = [
    ("자재재고", "SELECT ISNULL(SUM(CAST(STOCK_QTY AS float)),0) FROM nx.PU_T_MAT_STOCK_WH WHERE MAT_CODE=?"),
]

# ★기동 시점 행수 = 오염 0 판정 기준(쓰기 전에 잡아야 잠금에 안 걸린다)
ROLLBACK_TABS = ("nx.stock_ledger", "nx.PU_T_STOCK_MAINT", "nx.PU_T_MAT_STOCK_WH",
                 "nx.SA_T_STOCK_MAINT", "nx.SA_T_ITEM_STOCK",
                 "nx.proc_result", "nx.saleout_maint",
                 # 협력사 세트입고(2026-08-29) — 송장/입고거래도 오염 0 대상이다.
                 #   입고취소는 이 두 테이블을 지우므로, 여기 없으면 "깨끗하다"가 거짓말이 된다.
                 "nx.set_input_req", "nx.set_input_req_dtl", "nx.set_stock_maint",
                 # 인증(2026-08-29) — 하네스가 로그인하면 세션이 생기고 실패하면 잠금이 걸린다.
                 #   여기 없으면 "오염 0" 이 계정 테이블을 안 본 채로 통과한다.
                 "nx.app_user", "nx.app_session")
_ROWS0 = {}


def _snap_rows0():
    c = pyodbc.connect(CS, autocommit=True).cursor()
    for t in ROLLBACK_TABS:
        try:
            c.execute(f"SELECT COUNT(*) FROM {t}"); _ROWS0[t] = c.fetchone()[0]
        except Exception:
            _ROWS0[t] = None
    c.close()


_BASE = {}
_SCOPE = {"ymd": "260828", "mat": ""}


def _probe():
    """관측값 수집.

       ★커서를 **반드시 닫는다**(2026-08-30 실측). 안 닫으면 미처리 결과가 남아
         다음 요청이 같은 공유 커넥션에 커서를 열 때
         `HY000 다른 hstmt에 연결이 사용 중` 으로 터진다 — 실제로 스위트 첫 요청인
         `/api/auth/login` 이 500 을 맞아 하네스가 통째로 로그인을 못 했다.
       ★예외가 난 쿼리는 결과를 안 비운 채 남으므로 **except 안에서도 정리**한다.
    """
    cur = RAW.cursor(); out = {}
    try:
        for nm, q in PROBES + PROBES_MAT:
            arg = _SCOPE["mat"] if (nm, q) in [tuple(x) for x in PROBES_MAT] else _SCOPE["ymd"]
            try:
                cur.execute(q, arg); out[nm] = float(cur.fetchone()[0] or 0)
            except Exception as _e:
                out[nm] = None
                # ★예외를 삼키면 값이 null 로만 보여 원인을 못 찾는다(2026-08-30 실측)
                print(f"[probe] {nm} 실패 — {type(_e).__name__}: {str(_e)[:140]}", flush=True)
    finally:
        try:
            cur.close()
        except Exception:
            pass
    return out


from fastapi import Body


@APP.app.post("/api/_flow/scope")
def _flow_scope(payload: dict = Body(default={})):
    """관측 스코프(일자·품번) 지정. 이걸 좁혀야 하네스가 빠르게 돈다."""
    _SCOPE["ymd"] = str(payload.get("ymd") or _SCOPE["ymd"])
    _SCOPE["mat"] = str(payload.get("mat") or _SCOPE["mat"])
    return {"ok": True, "scope": _SCOPE}


@APP.app.get("/api/_flow/ping")
def _flow_ping():
    """★기동 확인 전용 — **DB 를 치지 않는다.**

       기동 대기를 `/api/_flow/probe` 로 하면 안 된다(2026-08-30 실측).
       probe 는 관측 쿼리 10여 개를 도는 무거운 엔드포인트라, **기동이 덜 끝난 상태에서
       반복 호출하면** 공유 커넥션에 미처리 상태가 남아 그 뒤 `/api/auth/login` 이
       `HY000 다른 hstmt에 연결이 사용 중` 으로 500 을 냈다
       → 하네스가 로그인을 못 해 40여 케이스가 통째로 SKIP.
       ⟹ 준비 확인은 이 엔드포인트로 한다.
    """
    return {"ok": True}


@APP.app.get("/api/_flow/probe")
def _flow_probe():
    """현재 관측값 + 기준점 대비 델타."""
    cur = _probe()
    return {"now": cur,
            "base": _BASE,
            "delta": {k: (round(cur[k] - _BASE[k], 4) if _BASE.get(k) is not None and cur[k] is not None else None)
                      for k in cur} if _BASE else {}}


@APP.app.post("/api/_flow/mark")
def _flow_mark(payload: dict = Body(default={})):
    """기준점 저장. label 로 구분."""
    global _BASE
    _BASE = _probe()
    return {"ok": True, "label": payload.get("label", ""), "base": _BASE}


@APP.app.post("/api/_flow/sql")
def _flow_sql(payload: dict = Body(default={})):
    """★공유(미커밋) 커넥션으로 SELECT — 하네스가 **자기가 방금 쓴 행**을 볼 수 있게 한다.
       별도 커넥션으로는 미커밋 행이 안 보여 수정/삭제 스텝을 검증할 수 없다(2026-08-28 교훈).
       SELECT 만 허용(쓰기는 화면 API 를 통해서만 — 하네스가 우회하면 검증 의미가 없다)."""
    q = str(payload.get("sql") or "").strip()
    if not q.lower().startswith("select"):
        return {"ok": False, "detail": "SELECT 만 허용"}
    cur = RAW.cursor()
    try:
        cur.execute(q, *(payload.get("args") or []))
        cols = [d[0] for d in cur.description]
        rows = [[(str(v) if not isinstance(v, (int, float, type(None))) else v) for v in r]
                for r in cur.fetchall()[:200]]
    finally:
        try:
            cur.close()        # ★안 닫으면 다음 요청이 HY000(다른 hstmt 사용중)으로 터진다
        except Exception:
            pass
    return {"ok": True, "cols": cols, "rows": rows}


@APP.app.post("/api/_flow/rollback")
def _flow_rollback():
    """전체 롤백 + 오염 0 검증.
       ★검증 기준은 **서버 기동 시점**에 잡아둔 행수(_ROWS0)다.
         롤백 전에 별도 커넥션으로 COUNT 하면 우리 자신의 미커밋 잠금에 걸려
         영원히 멈춘다(2026-08-28 실측 — 하네스가 멎던 진짜 원인)."""
    RAW.rollback()
    after = {}
    chk = pyodbc.connect(CS, autocommit=True).cursor()
    for t in ROLLBACK_TABS:
        chk.execute(f"SELECT COUNT(*) FROM {t}"); after[t] = chk.fetchone()[0]
    clean = all(_ROWS0.get(t) == after[t] for t in ROLLBACK_TABS)
    return {"ok": True, "rolled_back": True, "clean": clean,
            "rows_at_start": _ROWS0, "rows_after_rollback": after,
            "diff": {t: after[t] - _ROWS0.get(t, 0) for t in ROLLBACK_TABS
                     if after[t] != _ROWS0.get(t)}}


# ★app.mount("/", StaticFiles) 가 먼저 매칭되므로 제어 라우트를 **맨 앞으로** 옮긴다.
#   (CLAUDE.md §2 교훈: 마운트 뒤 등록 라우터는 openapi 에는 보여도 호출하면 404)
_ctrl = [r for r in APP.app.router.routes if getattr(r, 'path', '').startswith('/api/_flow/')]
for r in _ctrl:
    APP.app.router.routes.remove(r)
APP.app.router.routes[0:0] = _ctrl
print(f"  제어 라우트 {len(_ctrl)}개를 라우팅 테이블 맨 앞으로 이동")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8099)
    a = ap.parse_args()
    _snap_rows0()
    print(f"   기동시점 행수 스냅 완료(오염 0 기준)")
    print(f"★FLOW 검증 서버(롤백 모드) — 포트 {a.port} · 몽키패치 {_patched}곳")
    print("  커밋 무력화됨: 화면을 실제로 조작해도 DB 에 확정되지 않는다.")
    print(f"  제어: GET /api/_flow/probe · POST /api/_flow/mark · POST /api/_flow/rollback")
    import uvicorn
    uvicorn.run(APP.app, host="0.0.0.0", port=a.port, log_level="warning")
