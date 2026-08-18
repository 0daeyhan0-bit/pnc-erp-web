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
    elif not fresh:
        # ★커넥션 헬스체크: FastAPI 스레드풀 전환/유휴로 pyodbc 커넥션이 죽으면(10054) 커넥션만 재연결(메모캐시 보존).
        #   미적용 시 caller의 예외폴백 fresh=True가 엔진을 통째 버려 빈캐시 재적재(수초/요청) 발생 → 화면 열림 지연의 근본원인.
        with _COST_LOCK:
            try:
                if hasattr(_COST_ENG, 'alive'): _COST_ENG.alive()
            except Exception:
                try: _COST_ENG.close()
                except Exception: pass
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


# ── 도메인간 공유(app.py에서 추출) ──
def _closed(cur, ymd):
    cur.execute("SELECT close_flag FROM nx.stock_close WHERE ym=?", _ym(ymd))
    r = cur.fetchone()
    return bool(r and r[0])

# ===================== ★Phase5: nx 재고 월마감 스냅샷 (STOCK_POINT별 기초→기말=기초+ΣMAINT) =====================
# 기말 스냅샷=다음달 기초 연속성·마감후 파생 고정. 잠금=기존 nx.stock_close(ym) 플래그 재사용(옵션).
# ★사고 재발방지: stock_ledger 무삭제. 재계산은 자기생성 근거키(ym+point)의 stock_close_snap만 갱신.

# ── 도메인간 공유(app.py에서 추출) ──
def _validate_alloc(profs):
    """profs=[(af,at,alloc)] 활성 비내부 프로파일. 유효기간 겹치는 모든 구간에서 배분합=100% 강제.
       단독(그 구간에 1개, alloc=None)은 암묵 100%. 반환: 위반 메시지 리스트(빈=정상)."""
    FAR = "2099-12-31"
    norm = [(af, at or FAR, alloc) for (af, at, alloc) in profs]
    pts = sorted({p[0] for p in norm} | {p[1] for p in norm})
    errs = []
    for seg in pts:
        cover = [al for (af, at, al) in norm if af <= seg <= at]
        if not cover:
            continue
        if len(cover) == 1 and cover[0] is None:
            continue  # 단독=암묵 100%
        total = sum((al or 0) for al in cover)
        if abs(total - 100.0) > 0.01:
            errs.append(f"{seg} 시점 배분합 {total:g}% — 정확히 100%가 되어야 합니다 (활성 프로파일 {len(cover)}개)")
    return list(dict.fromkeys(errs))

# ── 도메인간 공유(app.py에서 추출) ──
def _ensure_modelbom(cur):
    cur.execute("""IF OBJECT_ID('nx.model_bom') IS NULL CREATE TABLE nx.model_bom(
        MODEL_NO varchar(30) NOT NULL, C_ITEM_CODE varchar(20) NOT NULL, USE_QTY decimal(18,4) DEFAULT 1,
        APPLY_FROM varchar(6) DEFAULT '000000', APPLY_TO varchar(6) DEFAULT '999999',
        REMARKS varchar(100), INS_USER varchar(20), INS_DT datetime DEFAULT getdate(),
        CONSTRAINT PK_nx_model_bom PRIMARY KEY(MODEL_NO,C_ITEM_CODE))""")

# ── 도메인간 공유(app.py에서 추출) ──
def _pur_src(win):
    """확정입고(매입) 원천: 9/S/C/G/H(검사통과) + 수입(_C DIVISION=P). 금액 양수. win=마감기준 조건(mg 참조)."""
    return f"""
    SELECT A.CUST_CODE cc, A.MAT_CODE mat, A.MAINT_COST cost, A.MAINT_YMD ymd, A.MAINT_QTY qty, A.MAINT_AMT amt, A.MAINT_VAT vat
     FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT A JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
     WHERE {win} AND A.MAINT_TAG IN ('9','S','C','G','H')
       AND ((ISNULL(A.INSP_FLAG,'N') IN ('','N')) OR (ISNULL(A.INSP_FLAG,'N') IN ('S','F') AND A.INSP_PROC_YMD >= ''))
    UNION ALL
    SELECT A.CUST_CODE, A.MAT_CODE, A.MAINT_COST, A.MAINT_YMD, A.MAINT_QTY, A.MAINT_AMT, ISNULL(A.TAXPAYERS,0)
     FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT_C A JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
     WHERE {win} AND A.DIVISION='P'"""


# ── 도메인간 공유(app.py에서 추출) ──
def _custnm_map(cur, codes):
    m = {}
    codes = sorted({str(c).strip() for c in codes if str(c or "").strip()})
    for i in range(0, len(codes), 900):
        ch = codes[i:i+900]; ph = ",".join("?" * len(ch))
        cur.execute(f"SELECT CUST_CODE, ISNULL(CUST_DESC,'') FROM PARTNER_ERP_TEST3.nx.CM_M_CUST WHERE CUST_CODE IN ({ph})", *ch)
        for r in cur.fetchall(): m[str(r[0]).strip()] = r[1]
    return m

# ── 도메인간 공유(app.py에서 추출) ──
def _kindmap(cur, kind):
    cur.execute("SELECT DETAIL_CODE, DETAIL_DESC FROM PARTNER_ERP_TEST3.nx.CM_M_MASTER_DETAIL WHERE KIND_CODE=?", kind)
    return {str(r[0]).strip(): str(r[1] or "").strip() for r in cur.fetchall()}


# ── 도메인간 공유(추출) ──
def _dig4(s):
    d = "".join(ch for ch in str(s or "") if ch.isdigit())
    return d[2:6] if len(d) == 6 else d[:4]   # YYYYMM→YYMM, YYMM→그대로(방어적)

# ── 도메인간 공유(추출) ──
def _cur_ym():
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("SELECT FORMAT(GETDATE(),'yyMM')"); return cur.fetchone()[0]
    finally:
        cn.close()

# ── 도메인간 공유(추출) ──
def _sale_win():
    return "A.MAINT_YMD > mg.JUN_YYMM+mg.JUN_MAGAM_DAY AND A.MAINT_YMD <= '{ym}'+mg.MAGAM_DAY"


# ── 도메인간 공유(문서저장/매출마감 SQL, app.py에서 이관) ──
import os as _os, hashlib as _hashlib, mimetypes as _mimetypes
from urllib.parse import quote as _urlquote
DOC_STORAGE_PATH = _os.getenv("DOC_STORAGE_PATH", r"F:\NEW_ERP_FILES")   # 배포시 NAS 마운트로 교체
_SALE_MAGAM = """WITH MAGAM(CUST_CODE,JUN_YYMM,JUN_MAGAM_DAY,MAGAM_DAY) AS (
  SELECT CUST_CODE, format(dateadd(MONTH,-1,convert(date,'{ym}'+'01',12)),'yyMM') JUN_YYMM,
    ISNULL((SELECT TOP 1 MAGAM_DAY FROM PARTNER_ERP_TEST3.nx.CM_M_CUST_MAGAM WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<=format(dateadd(MONTH,-1,convert(date,'{ym}'+'01',12)),'yyMM') ORDER BY APPLY_YYMM DESC),'31') JUN_MAGAM_DAY,
    ISNULL((SELECT TOP 1 MAGAM_DAY FROM PARTNER_ERP_TEST3.nx.CM_M_CUST_MAGAM WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<='{ym}' ORDER BY APPLY_YYMM DESC),'31') MAGAM_DAY
  FROM PARTNER_ERP_TEST3.nx.CM_M_CUST A)"""


# ── 도메인간 공유(추출) ──
def _valid_hhmm(s):
    d = str(s or "").strip()
    if not d: return True
    return len(d) == 4 and d.isdigit() and int(d[:2]) < 24 and int(d[2:]) < 60


# ── 도메인간 공유(추출) ──
def _d(s):  # 'yyyy-mm-dd' → date str or None
    s = str(s or "").strip()
    return s[:10] if len(s) >= 10 and s[4] == '-' else None

# -- 도메인간 공유 상수(품목 제작구분/성격) --
_ITEM_MAKE = {"": "", "1": "자체생산", "2": "외주가공", "3": "매입", "4": "사급가공", "5": "외주완성"}
_NATURE_ALL = ["1.원소재", "2.부자재/소모품", "3.사급자재", "4.가공품", "5.용접·조립품", "6.구매·부품"]


# ── 조달 배분: R01(현행) 경로 계수 (실발주비율 = route% × vendor% 의 route 축) ──
def _route01_ratio(ncur, item_codes):
    """품목별 R01(현행) 경로 배분율(nx.route_alloc, %). 미설정/단일=100. 실발주비율 = route01% × 업체비율.
       ★현재 R01=100%뿐이라 대개 100(업체비율 그대로) — R02 도입 대비 공용 배선. 자동발주·수동발주·협력사계획현황 공유.
       규칙 정본: _schema/PROCUREMENT_ALLOCATION_RULES.md §4·§5."""
    items = [str(c).strip() for c in item_codes if str(c).strip()]
    out = {c: 100.0 for c in items}
    if not items:
        return out
    try:
        if ncur.execute("SELECT COL_LENGTH('nx.route_alloc','alloc_ratio')").fetchone()[0] is None:
            return out
    except Exception:
        return out
    for i in range(0, len(items), 900):
        ch = items[i:i + 900]; ph = ",".join("?" * len(ch))
        try:
            ncur.execute(f"""SELECT LTRIM(RTRIM(a.item_code)), a.alloc_ratio
                FROM nx.route_alloc a JOIN nx.sourcing_route r ON r.route_id=a.route_id
                WHERE a.is_active=1 AND (r.current_flag=1 OR r.route_no=1)
                  AND a.alloc_ratio IS NOT NULL AND LTRIM(RTRIM(a.item_code)) IN ({ph})""", *ch)
            for ic, rt in ncur.fetchall():
                out[str(ic).strip()] = float(rt)
        except Exception:
            pass
    return out