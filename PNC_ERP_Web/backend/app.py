# -*- coding: utf-8 -*-
"""
PNC ERP 원가/손익 백엔드 API (FastAPI, 읽기전용 PARTNER_ERP)
- 견적원가조회(w_cs_esti_010) + 손익분석(w_cs_esti_020) 데이터를 라이브 SP로 산출
- 실원가용 SP_CS_견적서(실원가용)_250910, 내부용 SP_CS_견적서(내부용)_250704
- 엔진(engine_full.py)이 이 SP와 일치함을 검증완료 → 향후 신DB 전환 시 엔진으로 교체
실행(내부망):  uvicorn app:app --host 0.0.0.0 --port 8010   → 직원 PC 브라우저: http://<서버IP>:8010/
실행(단독):    uvicorn app:app --host 127.0.0.1 --port 8010
"""
import os, sys, warnings
from datetime import datetime, timedelta
warnings.filterwarnings('ignore')
# ★경로는 이 파일(backend) 기준 상대경로 — 서버 어느 드라이브/폴더에 복사해도 동작(트리만 유지: Projects\{New_ERP, NEW_ERP_1})
_HERE = os.path.dirname(os.path.abspath(__file__))                       # ...\NEW_ERP_1\PNC_ERP_Web\backend
sys.path.insert(0, os.path.join(_HERE, '..', '..', '..', 'New_ERP'))    # Projects\New_ERP (db_client)
sys.path.insert(0, os.path.join(_HERE, '..', '..', '_harness'))         # NEW_ERP_1\_harness (nx_cost_engine)
import db_client, pyodbc
from fastapi import FastAPI, Query, HTTPException, Body, Response, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
try:
    from nx_cost_engine import NxCostEngine   # 검증완료 nx 원가엔진(재료·가공·일반/운반/이윤·손익)
except Exception as _e:
    NxCostEngine = None

# ── 지속 원가엔진(캐시 유지) ── 매 요청 새 엔진=콜드캐시(느림, 3~6초). 엔진 재사용→웜캐시(수십ms).
#    pyodbc 커서 스레드 비안전 → _COST_LOCK 안에서만 사용. 공정/BOM/단가 변경 시 _reset_cost_engine()으로 무효화.
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

app = FastAPI(title="PNC ERP 원가/손익 API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
from fastapi.middleware.gzip import GZipMiddleware   # data.js(25MB)·대용량 응답 gzip 압축 → 초기로딩 가속
app.add_middleware(GZipMiddleware, minimum_size=1024)

# 라이브 조회 API(읽기전용 PARTNER_ERP) — 스냅샷 화면 승격용
from live_api import live_router
app.include_router(live_router)
from routers import prod as _r_prod   # 생산실적 도메인 라우터(app.py 분리)
app.include_router(_r_prod.router)
from routers import cost as _r_cost   # 원가 도메인 라우터
app.include_router(_r_cost.router)
from routers import qc as _r_qc   # 품질 도메인 라우터
app.include_router(_r_qc.router)
from routers import esticost as _r_esti   # 견적원가+납품 도메인 라우터
app.include_router(_r_esti.router)
from routers import planinput as _r_pi   # 생산계획입력 도메인 라우터
app.include_router(_r_pi.router)
from routers import sales as _r_sales   # 사급+매출+권한 도메인 라우터
app.include_router(_r_sales.router)
from routers import setin as _r_setin   # 협력사 세트입고 도메인 라우터
app.include_router(_r_setin.router)
from routers import bom as _r_bom
app.include_router(_r_bom.router)
from routers import stock as _r_stock
app.include_router(_r_stock.router)
from routers import salemagam as _r_salemagam
app.include_router(_r_salemagam.router)
from routers import doc as _r_doc
app.include_router(_r_doc.router)
from routers import prodsheet as _r_prodsheet
app.include_router(_r_prodsheet.router)
from routers import ready as _r_ready
app.include_router(_r_ready.router)
from routers import partmaster as _r_partmaster
app.include_router(_r_partmaster.router)
from routers import kitting as _r_kitting
app.include_router(_r_kitting.router)
from routers import backflush as _r_backflush
app.include_router(_r_backflush.router)
from routers import gagong as _r_gagong
app.include_router(_r_gagong.router)
from routers import scrap as _r_scrap
app.include_router(_r_scrap.router)
from routers import gagongmove as _r_gagongmove
app.include_router(_r_gagongmove.router)
from routers import procbc as _r_procbc
app.include_router(_r_procbc.router)
from routers import purmagam as _r_purmagam
app.include_router(_r_purmagam.router)
from routers import manorder as _r_manorder
app.include_router(_r_manorder.router)
from routers import order as _r_order
app.include_router(_r_order.router)
from routers import partplan as _r_partplan
app.include_router(_r_partplan.router)
from routers import soyo as _r_soyo
app.include_router(_r_soyo.router)
from routers import modelbom as _r_modelbom
app.include_router(_r_modelbom.router)
from routers import coopplan as _r_coopplan
app.include_router(_r_coopplan.router)
from routers import partplandtl as _r_partplandtl
app.include_router(_r_partplandtl.router)
from routers import profile as _r_profile
app.include_router(_r_profile.router)
from routers import prodwrite as _r_prodwrite
app.include_router(_r_prodwrite.router)
from routers import sourcing as _r_sourcing
app.include_router(_r_sourcing.router)
from routers import price as _r_price
app.include_router(_r_price.router)
from routers import item as _r_item
app.include_router(_r_item.router)
from routers import rawmat as _r_rawmat
app.include_router(_r_rawmat.router)
from routers import lglme as _r_lglme
app.include_router(_r_lglme.router)
from routers import dtrade as _r_dtrade
app.include_router(_r_dtrade.router)
from routers import coopquote as _r_coopquote
app.include_router(_r_coopquote.router)
from routers import coopquote2 as _r_coopquote2
app.include_router(_r_coopquote2.router)
from routers import stockval as _r_stockval
app.include_router(_r_stockval.router)
from routers import basemaster as _r_basemaster
app.include_router(_r_basemaster.router)
from routers import cust as _r_cust
app.include_router(_r_cust.router)
from routers import prodinfo as _r_prodinfo
app.include_router(_r_prodinfo.router)
from routers import prodplan as _r_prodplan
app.include_router(_r_prodplan.router)
from routers import gongsu as _r_gongsu
app.include_router(_r_gongsu.router)
from routers import daycheck as _r_daycheck
app.include_router(_r_daycheck.router)
# autoorder 폐기(2026-08-26): 미사용(프론트/타백엔드 소비 0)·AI개발본. 라우팅 해제+파일제거. 복구=git. 대체=자재예상매입(MRP, 설계단계) [[newerp-matexpect-initiative]]
from routers import lgsagub as _r_lgsagub
app.include_router(_r_lgsagub.router)
from routers import sagubledger as _r_sagubledger   # 협력사 사급부품 수불장(신규)
app.include_router(_r_sagubledger.router)
from routers import rawmatledger as _r_rawmatledger   # 협력사 원소재(동관) 수불장(규격별·신규)
app.include_router(_r_rawmatledger.router)
from routers import dopip as _r_dopip
app.include_router(_r_dopip.router)
from routers import pricemgmt as _r_pricemgmt
app.include_router(_r_pricemgmt.router)
from routers import salesplan as _r_salesplan
app.include_router(_r_salesplan.router)
from routers import prodstockadj as _r_prodstockadj
app.include_router(_r_prodstockadj.router)
from routers import assywork as _r_assywork  # 체결 매트릭스(품목별 체결 공정횟수 입력→가공비)
app.include_router(_r_assywork.router)
from routers import setstock as _r_setstock  # 가공세트재고관리(w_pu_stock_280 + 조정 285)
app.include_router(_r_setstock.router)
from routers import setstockio as _r_setstockio  # 자재세트재고입출고현황(w_pu_stock_070)
app.include_router(_r_setstockio.router)
from routers import setinstat as _r_setinstat  # 자재세트입고현황(w_pr_input_130_part)
app.include_router(_r_setinstat.router)
from routers import dragprod as _r_dragprod  # 파트별 생산계획 드래그 실적처리
app.include_router(_r_dragprod.router)
from routers import qareview as _r_qareview  # 품질 반성회일지(w_pr_input_590 + 등록 595)
app.include_router(_r_qareview.router)
# ★생산계획업로드(검토) — soyo.py 파이프라인 사본 + 레거시식 단계별 실행(/api/planrev/*).
#   현행 soyo.py·screens.prod.js 무변경. 검증 후 승격 여부 결정. (2026-08-26)
from routers import close as _r_close
from routers import planrev as _r_planrev
app.include_router(_r_close.router)
app.include_router(_r_planrev.router)
from routers import muldong as _r_muldong  # LG 물동량(영업) 업로드+조회 → nx.lg_muldong (자재예상매입 4주초과 소요원)
app.include_router(_r_muldong.router)
from routers import delivedit as _r_delivedit  # 거래명세표 수정(협력사) — 레거시 w_pr_outside_030_new
app.include_router(_r_delivedit.router)
from routers import matinput as _r_matinput    # 자재입고진행현황 — 레거시 w_pr_input_010_part
app.include_router(_r_matinput.router)
# ★인증·소속 강제 (협력사 포털 1단계, 2026-08-29) — PARTNER_PORTAL_DESIGN.md §1~2
#   협력사에게 열기 전에 서버가 거부해야 한다. 화면에서 숨기는 것은 보안이 아니다.
from routers import auth as _r_auth
app.include_router(_r_auth.router)


# ★★내부 API 전면 인증 게이트 (2026-08-29) — PARTNER_PORTAL_DESIGN.md §13
#   실측: 전체 530개 중 인증 결선 21개뿐. 협력사 토큰으로 cust/list·item/list·close/ledger·
#         partner/workcenters·perm/all 이 그대로 열렸다.
#   라우터 44개에 하나씩 붙이면 반드시 하나는 빠지고 공유파일을 44번 만진다.
#   ⟹ 여기 한 곳에서 막는다. **앞으로 만들 엔드포인트도 자동 보호**된다.
@app.middleware("http")
async def _auth_gate(request, call_next):
    from fastapi.responses import JSONResponse
    from routers.auth import path_policy, coop_allowed, current_user
    is_open, path = path_policy(request.url.path)
    if is_open:
        return await call_next(request)
    u = current_user(request)
    if not u:
        return JSONResponse({"detail": "로그인이 필요합니다."}, status_code=401)
    # 협력사는 화이트리스트만 — deny by default
    if u.get("utype") == "협력사" and not coop_allowed(path):
        return JSONResponse(
            {"detail": "협력사 계정으로는 접근할 수 없는 기능입니다."}, status_code=403)
    request.state.user = u
    return await call_next(request)
import weight_calc  # 무게정산(중량조정) 계산
# 도메인간 공유헬퍼 — 로컬 def가 있으면 그게 shadow, 해당 도메인 라우터 이동 후엔 common판 사용(잔류 엔드포인트 보호)
from common import _closed, _validate_alloc, _ensure_modelbom, _pur_src, _ym, _ITEM_WORK, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win
from common import _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes, _urlquote

import re as _re_guard
# ★라이브 PARTNER_ERP 쓰기 가드: DML(INSERT/UPDATE/DELETE/MERGE/TRUNCATE/DROP/ALTER/CREATE/GRANT/REVOKE) 첫키워드 거부.
#   허용: SELECT·WITH·SET·DECLARE·EXEC/EXECUTE(조회SP). 쓰기는 nx(_nx, PARTNER_ERP_TEST3)에서만. _nx엔 가드 미적용.
_LIVE_DML = _re_guard.compile(r'^(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|DROP|ALTER|CREATE|GRANT|REVOKE)\b', _re_guard.IGNORECASE)

def _sql_lead(sql):
    """주석(-- , /* */)·공백·선행 세미콜론 제거 후 남은 문장 앞부분 반환(첫 키워드 판정용)."""
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
        c = getattr(self._cur, 'close', None);
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
    # ApplicationIntent=ReadOnly: 테스트 연결·SELECT 1 성공 확인됨(2026-07-29). AG 미사용 시 무해(라우팅 힌트).
    #   실질 쓰기차단은 _ROConn/_ROCursor 코드가드. 쓰기는 _nx(PARTNER_ERP_TEST3)에서만 허용.
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

@app.get("/api/health")
def health():
    return {"ok": True, "sp_sil": SP_SIL, "sp_nae": SP_NAE}

# ===================== 품목 BOM 관리 (nx.bom, 쓰기=TEST3) =====================
def _nx():
    cs = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
          f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
    return pyodbc.connect(cs, autocommit=True)

def _nx_tx():
    """nx 쓰기 트랜잭션 커넥션(autocommit=False). ★그룹 단위 원자성 전용:
    호출측은 반드시 try:...commit() / except: rollback();raise / finally: close() 로 감쌀 것.
    멀티행 그룹(이동 2행·백플러시 다건+log·재키 delete+insert)이 부분실패로 net-0/멱등 불변식을 깨지 않게 함."""
    cs = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
          f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
    return pyodbc.connect(cs, autocommit=False)

def _b(x):  # 파이썬 truthy → BIT
    return 1 if x in (1, True, '1', 'Y', 'y', 'true', 'True') else 0

# ============ 생산 ③④: 생산실적현황(w_pr_list_010) / 파트별생산실적현황(w_pr_list_090) — PR_T_PROD_DTL ============
def _pivot_prod(raw, keyname, extra):
    dates = sorted({r["PROD_YMD"] for r in raw})
    keyed = {}
    for r in raw:
        k = r[keyname]; g = keyed.get(k)
        if not g:
            g = dict(extra(r)); g["days"] = {}; g["tot"] = 0; keyed[k] = g
        q = float(r["q"] or 0); g["days"][r["PROD_YMD"]] = g["days"].get(r["PROD_YMD"], 0) + q; g["tot"] += q
    return dates, list(keyed.values())

# ===== 시작 워밍(첫 조회 콜드 지연 완화) =====
# 무거운 첫 조회(자재수불장 등)는 플랜 컴파일 + 콜드 버퍼로 느림 → 기동 직후 백그라운드로 예열.
# 데몬 스레드(비차단). 실패해도 무시(가용성 우선). 인덱스(nx 복제본, _migration/r_add_indexes.py)와 병행.
@app.on_event("startup")
def _warmup_heavy_queries():
    import threading, time as _t
    def _run():
        _t.sleep(3)   # 기동 안정 후
        warm = [
            # 자재수불장 일/월 최신 — 실제 조인·집계 플랜 예열
            """select t.mat_code, max(m.item_name), isnull(max(c.cust_desc),''), sum(t.stock_qty)
                 from PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH_DAILY t
                 join PARTNER_ERP_TEST3.nx.item m on t.mat_code=m.item_code
                 join PARTNER_ERP_TEST3.nx.pr_m_proc_gagong g on t.gagong_proc_code=g.gagong_proc_code
                 left join PARTNER_ERP_TEST3.nx.cm_m_cust c on m.in_cust=c.cust_code
                 where t.cust_code='Z99990' and t.STOCK_YMD=(SELECT MAX(STOCK_YMD) FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH_DAILY WHERE cust_code='Z99990')
                 group by t.mat_code""",
            """select t.mat_code, max(m.item_name), sum(t.stock_qty)
                 from PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH t
                 join PARTNER_ERP_TEST3.nx.item m on t.mat_code=m.item_code
                 where t.cust_code='Z99990' and t.STOCK_YYMM=(SELECT MAX(STOCK_YYMM) FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH WHERE cust_code='Z99990')
                 group by t.mat_code""",
        ]
        try:
            cn = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
                                f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
            cur = cn.cursor()
            for q in warm:
                try: cur.execute(q); cur.fetchall()
                except Exception: pass
            cn.close()
        except Exception: pass
        # ★원가엔진 예열 — 재시작 후 첫 조달경로 '수정'(실체화)/원가 조회 콜드지연(수초) 제거.
        #   공유캐시(임율·공정마스터·품목마스터)를 미리 채움. 대표 품목 1개 walk로 엔진 상주 활성화.
        try:
            from common import _get_cost_engine, _COST_LOCK as _CL
            with _CL:
                eng = _get_cost_engine()
                try: eng.labor_rate("2026" + "06")
                except Exception: pass
                for _wi in ("AJR75563402",):
                    try: eng.naewon_nodes(_wi, "260630")
                    except Exception: pass
        except Exception: pass
    # ★TestBed(FLOW_TESTBED=1)는 예열을 **동기로** 한다 — 하네스는 커넥션이 하나라
    #   예열 스레드가 본 스레드와 다투면 HY000 이 나고, 그렇다고 끄면 엔진이 차가워
    #   생산재고조회가 타임아웃한다(실측 600s 초과). 요청을 받기 전에 끝낸다.
    import os as _os
    if _os.environ.get("FLOW_TESTBED"):
        _run()
    else:
        threading.Thread(target=_run, daemon=True).start()

# ===== 프론트엔드 정적 서빙 (내부망 단일 포트 운영) =====
# ★반드시 모든 API 라우트 정의 이후(파일 최하단)에 위치. /api/* · /live/* 가 먼저 매칭되고 나머지는 정적파일로.
# 프론트도 8010에서 서빙 → 브라우저 API_BASE=location.origin 자동일치(직원 PC 어디서 열어도 동작).
import os as _os
from fastapi.staticfiles import StaticFiles as _StaticFiles

# ★index.html / *.js 는 브라우저 캐시 금지.
#   index.html이 캐시되면 그 안의 ?v=… 캐시버스팅이 통째로 무력화되어, JS를 고쳐도 화면이 안 바뀜
#   (2026-08-19: 준비실적처리 수정분이 여러 번 반영 안 되는 문제의 원인). ?v= 는 그대로 두되 보험으로 헤더도 no-store.
@app.middleware("http")
async def _no_cache_front(request, call_next):
    resp = await call_next(request)
    p = request.url.path.lower()
    if p.endswith((".html", ".js", ".css")) or p in ("/", ""):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        # ★charset 명시(2026-08-21). StaticFiles 는 .js 에 charset 을 안 붙인다.
        #   소스가 BOM 없는 UTF-8 이라 브라우저가 시스템 기본(CP949)으로 읽으면
        #   한글 주석·문자열이 깨져 따옴표 짝이 어긋나고 파싱이 중단된다.
        #   → 파일 뒤쪽에 있는 화면(예: SCREEN.salesplan)이 등록되지 않는 원인.
        ct = resp.headers.get("content-type", "")
        if ct and "charset" not in ct.lower():
            resp.headers["Content-Type"] = ct.split(";")[0] + "; charset=utf-8"
    return resp

_FRONT_DIR = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))   # backend의 상위 = PNC_ERP_Web
app.mount("/", _StaticFiles(directory=_FRONT_DIR, html=True), name="front")
