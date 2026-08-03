# -*- coding: utf-8 -*-
"""
공유 인프라(common) — 여러 도메인 라우터/엔드포인트가 공통으로 쓰는 저수준 헬퍼.
app.py와 routers/*.py 가 여기서 import. (app.py 라우터 분리 1단계: 공유헬퍼 추출)
★app.py의 원본 정의와 100% 동일해야 함(복제). 엔드포인트 이동 시 라우터가 이걸 import.
"""
import os, sys, warnings
from datetime import datetime, timedelta
warnings.filterwarnings('ignore')
# ★경로는 이 파일(backend) 기준 상대경로 — 서버 어느 드라이브/폴더에 복사해도 동작
_HERE = os.path.dirname(os.path.abspath(__file__))                       # ...\NEW_ERP_1\PNC_ERP_Web\backend
sys.path.insert(0, os.path.join(_HERE, '..', '..', '..', 'New_ERP'))    # Projects\New_ERP (db_client)
sys.path.insert(0, os.path.join(_HERE, '..', '..', '_harness'))         # NEW_ERP_1\_harness (nx_cost_engine)
import db_client, pyodbc
try:
    from nx_cost_engine import NxCostEngine   # 검증완료 nx 원가엔진
except Exception:
    NxCostEngine = None

# ── 지속 원가엔진(캐시 유지) ── 매 요청 새 엔진=콜드캐시(느림). 엔진 재사용→웜캐시.
import threading as _threading
_COST_ENG = None
_COST_LOCK = _threading.RLock()
def _get_cost_engine(fresh=False):
    global _COST_ENG
    if fresh and _COST_ENG is not None:
        try: _COST_ENG.close()
        except Exception: pass
        _COST_ENG = None
    if _COST_ENG is None:
        _COST_ENG = NxCostEngine()
    return _COST_ENG
def _reset_cost_engine():
    """원가 입력(공정/BOM/단가) 변경 후 캐시 무효화 → 다음 계산은 최신 DB 반영."""
    global _COST_ENG
    with _COST_LOCK:
        if _COST_ENG is not None:
            try: _COST_ENG.close()
            except Exception: pass
            _COST_ENG = None

SP_SIL = 'SP_CS_견적서(실원가용)_250910'
SP_NAE = 'SP_CS_견적서(내부용)_250704'

import re as _re_guard
# ★라이브 PARTNER_ERP 쓰기 가드: DML 첫키워드 거부. 쓰기는 nx(_nx, PARTNER_ERP_TEST3)에서만.
_LIVE_DML = _re_guard.compile(r'^(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|DROP|ALTER|CREATE|GRANT|REVOKE)\b', _re_guard.IGNORECASE)

def _sql_lead(sql):
    """주석·공백·선행 세미콜론 제거 후 남은 문장 앞부분 반환(첫 키워드 판정용)."""
    s = str(sql or '')
    while True:
        s = s.lstrip(' \t\r\n;')
        if s[:2] == '--':
            i = s.find('\n'); s = '' if i < 0 else s[i + 1:]
        elif s[:2] == '/*':
            i = s.find('*/'); s = '' if i < 0 else s[i + 2:]
        else:
            return s

class _ROCursor:
    """라이브(PARTNER_ERP) 읽기전용 가드 커서 — DML 첫키워드 거부, 조회/EXEC/SET/DECLARE 허용."""
    def __init__(self, cur): object.__setattr__(self, '_cur', cur)
    def execute(self, sql, *a, **k):
        if _LIVE_DML.match(_sql_lead(sql)):
            raise PermissionError("라이브 PARTNER_ERP는 읽기전용입니다 — INSERT/UPDATE/DELETE/DDL 차단(쓰기는 nx=PARTNER_ERP_TEST3에서만).")
        return self._cur.execute(sql, *a, **k)
    def executemany(self, *a, **k):
        raise PermissionError("라이브 PARTNER_ERP는 읽기전용입니다 — executemany(쓰기) 차단.")
    def __iter__(self): return iter(self._cur)
    def __enter__(self): return self
    def __exit__(self, *a):
        c = getattr(self._cur, 'close', None)
        if c: c()
        return False
    def __getattr__(self, n): return getattr(self._cur, n)

class _ROConn:
    """라이브 읽기전용 가드 커넥션 — .cursor()가 가드 커서 반환. 그 외 위임."""
    def __init__(self, cn): object.__setattr__(self, '_cn', cn)
    def cursor(self): return _ROCursor(self._cn.cursor())
    def __enter__(self): return self
    def __exit__(self, *a):
        c = getattr(self._cn, 'close', None)
        if c: c()
        return False
    def __getattr__(self, n): return getattr(self._cn, n)

def _conn():
    cs = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
          f'DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD};ApplicationIntent=ReadOnly')
    return _ROConn(pyodbc.connect(cs, autocommit=True))

def _num(x):
    try: return round(float(x), 2)
    except Exception: return 0.0

def _run_sp(sp, item, ymd):
    """SP를 실행하고 마지막 결과셋(컬럼, 행)을 반환."""
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("SET NOCOUNT ON; EXEC [dbo].[" + sp + "] ?, ?", item, ymd)
        cols, rows = None, None
        while True:
            if cur.description:
                cols = [d[0] for d in cur.description]
                try: rows = cur.fetchall()
                except Exception: rows = []
            if not cur.nextset(): break
        return cols, (rows or [])
    finally:
        cn.close()

def _shape(cols, rows):
    if not cols:
        return {"rows": [], "agg": {}}
    ix = {c: i for i, c in enumerate(cols)}
    def g(r, c): return r[ix[c]] if c in ix else None
    grid, top = [], None
    for r in rows:
        lvl = int(g(r, 'C_ITEM_LEVEL') or 0)
        grid.append({
            "level": lvl,
            "part": str(g(r, 'C_ITEM_CODE') or '').strip(),
            "desc": str(g(r, 'C_ITEM_DESC') or '').strip(),
            "sgroup": str(g(r, 'ITEM_SGROUP') or '').strip(),
            "diam": _num(g(r, 'C_ITEM_DIAM')), "thick": _num(g(r, 'C_ITEM_THICK')), "length": _num(g(r, 'C_ITEM_LENGTH')),
            "metal": str(g(r, 'C_METAL_GUBUN') or '').strip(),
            "cust": str(g(r, 'CUST_DESC') or '').strip(),
            "unit_gubun": str(g(r, 'COST_GUBUN') or '').strip(),
            "use_qty": _num(g(r, 'USE_QTY')),
            "won_mat": _num(g(r, 'WON_MAT_COST')),
            "jai": _num(g(r, 'JAI_COST')),
        })
        if lvl == 0: top = r
    agg = {}
    if top is not None:
        for f in ['JAI_COST', 'GAGONG_AMT', 'ILBAN_AMT', 'UNBAN_AMT', 'PROFIT_AMT', 'TOT_AMT',
                  'LME_CHA_AMT', 'LG_COST', 'WON_JAI_AMT', 'BU_JAI_AMT', 'SA_JAI_AMT']:
            agg[f] = _num(g(top, f)) if f in ix else None
        agg['SONIK'] = (agg.get('LG_COST') or 0) - (agg.get('TOT_AMT') or 0)
    return {"rows": grid, "agg": agg}

# ===================== nx(쓰기=PARTNER_ERP_TEST3) 커넥션 =====================
def _nx():
    cs = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
          f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
    return pyodbc.connect(cs, autocommit=True)

def _nx_tx():
    """nx 쓰기 트랜잭션 커넥션(autocommit=False). ★그룹 단위 원자성 전용:
    호출측은 반드시 try:...commit() / except: rollback();raise / finally: close() 로 감쌀 것."""
    cs = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
          f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
    return pyodbc.connect(cs, autocommit=False)

def _b(x):  # 파이썬 truthy → BIT
    return 1 if x in (1, True, '1', 'Y', 'y', 'true', 'True') else 0

def _d6(s):
    d = ''.join(ch for ch in str(s or '') if ch.isdigit())
    if len(d) == 8: return d[2:8]      # yyyymmdd → yymmdd
    return d[-6:] if len(d) >= 6 else d

# 작업장코드 → 이름 (여러 도메인 공유: planinput·gagong·sourcing). app.py 원본과 동일.
_ITEM_WORK = {"": "", "P1": "용접", "P2": "가공", "D1": "직납"}

def _ym(ymd):  # MAINT_YMD(YYMMDD/YYYYMMDD) → 마감월 YYMM. 공유: sales(마감잠금)·salemagam.
    y = str(ymd or "").strip()
    return y[:4] if len(y) >= 6 else ""
