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
def _new_cost_engine():
    """persistent 원가엔진 생성 + ★글로벌 벌크예열(warm_all): silwon 즉시화(16~96ms)·naewon 구조전개 in-memory화
       (per-node DB왕복 N+1 제거). warm_all은 diff0 검증됨(값 불변)·실패 시 lazy 폴백(무해). one-time ~4.7s.
       미적용 시 신규 품목 조회마다 ~3.5s(품목BOM 조회 지연의 근본)."""
    e = NxCostEngine()
    try: e.warm_all()
    except Exception: pass
    return e
def _get_cost_engine(fresh=False):
    global _COST_ENG
    if fresh and _COST_ENG is not None:
        try: _COST_ENG.close()
        except Exception: pass
        _COST_ENG = None
    if _COST_ENG is None:
        _COST_ENG = _new_cost_engine()
    elif not fresh:
        # ★커넥션 헬스체크: FastAPI 스레드풀 전환/유휴로 pyodbc 커넥션이 죽으면(10054) 커넥션만 재연결(메모캐시 보존).
        #   미적용 시 caller의 예외폴백 fresh=True가 엔진을 통째 버려 빈캐시 재적재(수초/요청) 발생 → 화면 열림 지연의 근본원인.
        with _COST_LOCK:
            try:
                if hasattr(_COST_ENG, 'alive'): _COST_ENG.alive()
            except Exception:
                try: _COST_ENG.close()
                except Exception: pass
                _COST_ENG = _new_cost_engine()
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
def _closed(cur, ymd, domain="MAT"):
    """마감 여부(bool). ★공용 게이트 `_lock_msg` 에 위임한다.

       ★2026-08-28 결함수정: 종전엔 구 전역 월잠금 `nx.stock_close` 만 봤다.
         우리 마감은 `nx.period_close` 에 기록되므로 **마감된 달의 전표가 그대로 저장**됐다
         (TestBed 확장이 발견 — 생산파트재고조정·발주입고이 마감월 2607 로 통과).
         게이팅 캐논 §0-★ = 예외 없음 → 마감잠금도 전 화면이 같은 판정을 써야 한다.
       `_lock_msg` 는 ① 일마감 ② 월마감 ③ 구 stock_close(하위호환) 순으로 보므로
       종전 동작을 포함하면서 우리 마감까지 잡는다."""
    return bool(_lock_msg(cur, ymd, domain))

# ===== 전 도메인 공통 가드 (마감 일자 잠금 + 재고 가용성 게이팅) — 정본 _schema/STOCK_GATING_CLOSE_LOCK_RULES.md =====
def _lock_msg(cur, ymd, domain="MAT"):
    """★마감 일자 잠금 (전 도메인 공통). 마감된 기간이면 사유메시지, 아니면 None.
       (비발생형 — 호출측이 return/raise 결정)

       판정 순서 (정본 = nx.period_close, 마감관리 화면이 기록):
         ① 일마감  nx.period_close(domain, 'D', YYMMDD)   ← 그 날이 잠겼는가
         ② 월마감  nx.period_close(domain, 'M', YYMM)     ← 일마감 ⊂ 월마감
         ③ 하위호환 nx.stock_close(ym)                     ← 구 전역 월잠금(기존 동작 보존)
       domain = MAT 자재 / PRD 생산 / SAL 영업. 미지정이면 MAT.
       정본 = _schema/STOCK_GATING_CLOSE_LOCK_RULES.md 규칙B · nextgen-erp-close-settlement(일마감⊂월마감)."""
    ymd = str(ymd or "").strip()
    if len(ymd) < 6:
        return None
    d = str(domain or "MAT").strip().upper() or "MAT"
    ym = _ym(ymd)
    try:
        cur.execute("""SELECT ptype FROM nx.period_close
                       WHERE domain=? AND close_flag=1 AND ((ptype='D' AND period=?) OR (ptype='M' AND period=?))
                       ORDER BY ptype""", d, ymd[:6], ym)
        r = cur.fetchone()
        if r:
            return (f"{ymd[:6]} 일마감된 일자입니다 — 생성/수정/삭제 불가" if r[0] == "D"
                    else f"{ym} 마감된 월입니다 — 생성/수정/삭제 불가")
    except Exception:
        pass          # period_close 미생성 환경(구 배포본) → 하위호환 경로로
    # ③ 하위호환 = 구 전역 월잠금. ★_closed() 를 부르면 안 된다 —
    #   _closed 가 다시 _lock_msg 로 위임하므로 **무한 재귀**가 된다(2026-08-28 실측).
    #   여기서는 원천을 직접 읽는다.
    try:
        cur.execute("SELECT close_flag FROM nx.stock_close WHERE ym=?", ym)
        r = cur.fetchone()
        if r and r[0]:
            return f"{ym} 마감된 월입니다 — 생성/수정/삭제 불가"
    except Exception:
        pass
    return None

# ===== 자재 현재고 정본 — 실시간 승격 (G-1, 2026-08-28) =====
# ★종전: nx.mat_stock_daily(일 스냅샷) 최신일 값.
#   그 테이블을 채우는 빌더(_migration/sub_norm/matclose_movavg_build.py)는 **사람이 손으로 돌린다.**
#   자동 실행 지점이 설계상 정의된 적이 없어(백엔드·배치·스케줄러·SQL Agent 전부 없음)
#   실제로 8/25 에 멈춰 있었고, **133품목이 "재고 있음" 으로 오판**되어 음수재고를 통과시켰다.
#   (5210A22409A — 게이트 2,241 vs 실제 −2,659)
# ★지금: **확정 스냅샷 + 그 이후 전표** = 마감·수불장과 **같은 엔진**으로 계산한다.
#   - 빌더 의존이 사라진다(누가 언제 돌리는지 문제 자체가 없어진다).
#   - 컷오버 항목 5번(실시간 자재정본 승격)이 미리 끝난다.
#   - 실측: 3,694품목 0.75초 · 음수 40(실시간) vs 139(구방식) — 구방식이 과소평가하고 있었다.
# ★게이트 전용 SQL 을 새로 짜지 않는다. 손으로 다시 짜면 반드시 하나를 빠뜨린다 —
#   실제로 검산용 SQL 이 **수입 전표(PU_T_STOCK_MAINT_C)를 놓쳐** 수불장과 56건 갈렸다
#   (AJR30057201: 기초 376 + 수입 2,000 = 2,376 인데 376 으로 계산). CUTOVER_CHECKLIST G-4.
_AVAIL_MAP = {"key": None, "map": {}, "at": 0.0}
_AVAIL_TTL = 60.0    # 초


def _mat_avail_map(cur, force=False):
    """자재 현재고 맵 {품번: 수량} — 확정 스냅샷 기초 + 그 이후 전표(오늘까지).
       ★프로세스 캐시(산출 약 1.2초). 두 겹으로 낡지 않게 지킨다:
         ① 웹에서 재고를 바꾸는 쓰기 → stock_changed() 가 즉시 버린다.
         ② 웹 밖에서 DB 가 바뀌는 경우(매일 7:30 마이그 r_delta_sync 등) → TTL 60초.
            ①만 두면 마이그가 직접 쓴 뒤 게이트가 **하루 종일 낡은 값**을 본다.
       ★워커 1개 전제(uvicorn app:app, --workers 없음). 다중 워커로 가면 이 캐시는 못 쓴다
         — 한 워커의 무효화가 다른 워커에 가지 않기 때문. 그때는 공용 캐시로 옮길 것."""
    import datetime as _dt, time as _t
    today = _dt.date.today().strftime("%y%m%d")
    if (not force and _AVAIL_MAP["key"] == today and _AVAIL_MAP["map"]
            and (_t.time() - _AVAIL_MAP["at"]) < _AVAIL_TTL):
        return _AVAIL_MAP["map"]
    try:
        from routers.close import _mv_base, _mv_moves, _mv_step, _mv_scope, _next_ymd
    except Exception:
        return _AVAIL_MAP["map"] or {}
    state, base_ymd, _src = _mv_base(cur, today)
    scope = _mv_scope(cur)
    start = _next_ymd(base_ymd)
    if start <= today:
        moves = _mv_moves(cur, start, today)
        for y in sorted(moves):
            _mv_step(state, moves[y], scope)
    m = {k: float(v[0]) for k, v in state.items()}
    import time as _t2
    _AVAIL_MAP["key"], _AVAIL_MAP["map"], _AVAIL_MAP["at"] = today, m, _t2.time()
    return m


def _mat_avail(cur, item):
    """자재 현재고(가용) — 실시간 정본. 없으면 0.
       ★음수재고 차단(§0-★)의 판정 기준. 정본 = STOCK_GATING_CLOSE_LOCK_RULES §0-★★★."""
    item = str(item or "").strip().upper()
    if not item:
        return 0.0
    try:
        return float(_mat_avail_map(cur).get(item, 0.0))
    except Exception:
        # 엔진 호출 실패 시에도 **폴백하지 않는다**(하드룰 §1-9-1) — 판정 불가는 통과가 아니라 0.
        return 0.0

def _mat_short_msg(cur, item, need, label="출고"):
    """자재 재고 가용 게이트(정본=실시간 자재정본 _mat_avail). 부족하면 사유메시지, 아니면 None. 마이너스 원천차단."""
    item = str(item or "").strip(); need = float(need or 0)
    if not item or need <= 0:
        return None
    avail = _mat_avail(cur, item)
    if need > avail + 1e-6:
        return f"재고부족 ({item} 가용 {avail:g} < {label} {need:g})"
    return None

def _finished_avail(cur, item, asof=None):
    """완성/제품 현재고 정본(ASY 게이트 source) = 제품재고조회(salesstock) recipe 단일품목 압축.
       = 2502기말 snap + Σ sa_t_stock_maint[P(무in_part)/B/V/J/8/R/2].maint_qty − Σ 직납(pu out_wh_gubun=2).maint_qty, maint_ymd≤asof(기본 오늘).
       ★2026-08-19 레거시 w_pr_stock_040 diff0 검증(총 55,296). nx 병행운영중 테스트오염 주의 — 컷오버 후 정본. 정본 §4-C."""
    item = str(item or "").strip().upper()
    if not item:
        return 0.0
    if not asof:
        cur.execute("SELECT FORMAT(GETDATE(),'yyMMdd')"); asof = cur.fetchone()[0]
    # ★2026-08-29 화면(제품재고조회 `live_api.salesstock`) recipe 와 **버킷까지 동일**하게 정렬.
    #   화면 항등식 = 기초 + 입고 − 출고 − 조정
    #     입고 = 완성 P(in_part='') + (B,V)  +  **직납 자재출고(pu out_wh='2') 의 −qty**
    #     출고 = 완성 (J,8,R) 의 −qty
    #     조정 = 완성 (2) 의 −qty
    #   ★직납이 '입고' 인 이유: 협력사 차량이 LG 에 못 들어가서 **우리 창고를 거쳐** 나간다.
    #     (대표 확인 2026-08-29). 그래서 자재축 직납 출고가 곧 제품 입고다.
    #   ★부호 함정: 조정은 ×(−1) 로 담긴다. 가용에 더하려면 **빼야** 한다.
    #     (MJU63357501 8/10 조정 +1,500 을 반대로 넣었더니 가용이 −1,498 로 나와 정상출고가 막혔다)
    cur.execute("""SELECT
        (SELECT ISNULL(SUM(stock_qty),0) FROM PARTNER_ERP_TEST3.nx.sa_t_month_stock
          WHERE stock_yymm='2502' AND UPPER(item_code)=?)
      + (SELECT ISNULL(SUM(maint_qty),0) FROM PARTNER_ERP_TEST3.nx.sa_t_stock_maint
          WHERE UPPER(item_code)=? AND maint_ymd BETWEEN '250299' AND ?
            AND ((maint_tag='P' AND ISNULL(in_part_code,'')='') OR maint_tag IN ('B','V','J','8','R','2')))
      - (SELECT ISNULL(SUM(maint_qty),0) FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint
          WHERE UPPER(mat_code)=? AND maint_ymd BETWEEN '250299' AND ? AND ISNULL(out_wh_gubun,'1')='2')
    """, item, item, asof, item, asof)
    r = cur.fetchone()
    return float(r[0] or 0)

def _finished_short_msg(cur, item, need, label="출고"):
    """완성/제품 재고 가용 게이트(ASY, 정본=_finished_avail). 부족하면 사유메시지, 아니면 None."""
    item = str(item or "").strip(); need = float(need or 0)
    if not item or need <= 0:
        return None
    avail = _finished_avail(cur, item)
    if need > avail + 1e-6:
        # ★왜 안 되는지 밝힌다(§0-★). 완성재고 = 제품재고조회 화면과 같은 계산.
        return (f"재고부족 — {item}: {label} {need:g} > 완성재고 {avail:g}"
                f" (제품재고조회 기준: 기초+입고−출고−조정. 부족 {need-avail:g})")
    return None

# 생산재고조회(_prodstock, dw_pr_stock_480) recipe U — 단일품목 현재고용(라인=P0001 가공/그외 용접). live_api와 동일 정본, {asof}까지 누적.
def _prod_avail(cur, mat, line="P0001", asof=None):
    """생산 현재고 정본(PRD 게이트 source) = 생산재고조회(_prodstock) recipe 단일품목. line='P0001'=가공(기본)·그외=용접 라인코드.
       ★2026-08-19 레거시 w_pr_stock_480 가공창고 18일 diff0 검증. nx 병행운영중 테스트오염 주의 — 컷오버 후 정본. 정본 §4-C."""
    mat = str(mat or "").strip().upper()
    if not mat:
        return 0.0
    if not asof:
        cur.execute("SELECT FORMAT(GETDATE(),'yyMMdd')"); asof = cur.fetchone()[0]
    T3 = "PARTNER_ERP_TEST3.nx."
    U = f"""
SELECT a.gagong_proc_code gpc, A.MAT_CODE mat, A.STOCK_QTY q FROM {T3}PR_T_MONTH_STOCK_WH A WHERE A.STOCK_YYMM='2502'
UNION ALL SELECT a.to_gagong_proc_code,A.MAT_CODE,-A.MAINT_QTY FROM {T3}PU_T_STOCK_MAINT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{asof}' AND a.maint_tag='B' AND isnull(a.out_wh_gubun,'1')='1'
UNION ALL SELECT A.gagong_proc_code,a.mat_code,a.cut_QTY FROM PARTNER_ERP.dbo.pu_t_cut_dtl a WHERE A.cut_ymd>'250299' and A.cut_ymd<='{asof}'
UNION ALL SELECT a.to_gagong_proc_code,A.MAT_CODE,a.MAINT_QTY FROM {T3}PU_T_STOCK_MAINT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{asof}' AND a.maint_tag='T' and isnull(a.out_wh_gubun,'3')='3'
UNION ALL SELECT a.to_gagong_proc_code,A.MAT_CODE,-a.MAINT_QTY FROM {T3}PU_T_STOCK_MAINT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{asof}' AND a.maint_tag='C'
UNION ALL SELECT A.stock_part_code,a.item_code,a.prod_qty FROM {T3}pr_t_prod_dtl a WHERE A.prod_ymd>'250299' and A.prod_ymd<='{asof}' and a.stock_part_code>'' and not exists (select 1 from {T3}sa_t_stock_maint where maint_ymd=a.prod_ymd and item_code=a.item_code and in_part_code=a.stock_part_code)
UNION ALL SELECT A.IN_PART_CODE,a.item_code,a.MAINT_QTY FROM {T3}sa_t_stock_maint a WHERE A.maint_ymd>'250299' and A.MAINT_YMD<='{asof}' and a.in_part_code>''
UNION ALL SELECT A.PART_CODE,A.MAT_CODE,a.MAINT_QTY FROM {T3}PR_T_STOCK_MAINT_MAT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{asof}' AND A.MAINT_TAG='3'
UNION ALL SELECT A.PART_CODE,A.MAT_CODE,a.MAINT_QTY FROM {T3}PR_T_STOCK_MAINT_MAT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{asof}' AND A.MAINT_TAG in ('2','1')
UNION ALL SELECT A.PART_CODE,A.MAT_CODE,a.MAINT_QTY FROM {T3}PR_T_STOCK_MAINT_MAT A JOIN {T3}item M ON A.MAT_CODE=M.ITEM_CODE WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{asof}' AND A.MAINT_TAG='4'
"""
    cur.execute(f"""SELECT ISNULL(SUM(t.q),0) FROM ({U}) t
        WHERE ISNULL(LTRIM(RTRIM(t.gpc)),'')=? AND UPPER(LTRIM(RTRIM(t.mat)))=?""", line, mat)
    r = cur.fetchone()
    return float(r[0] or 0)

def _prod_short_msg(cur, mat, need, line="P0001", label="사용"):
    """생산 재고 가용 게이트(PRD, 정본=_prod_avail). 부족하면 사유메시지, 아니면 None."""
    mat = str(mat or "").strip(); need = float(need or 0)
    if not mat or need <= 0:
        return None
    avail = _prod_avail(cur, mat, line)
    if need > avail + 1e-6:
        return f"재고부족 ({mat} 생산재고 {avail:g} < {label} {need:g})"
    return None

def _stock_short_msg(cur, item, need, points=("MAT",), label="출고"):
    """재고 가용성 게이팅. item(MAT_CODE 또는 ITEM_CODE)의 지정 재고점 가용(원장 SUM) < need면 부족메시지, 아니면 None.
       points: MAT(자재)·RDY(준비)·PRD(생산/가공)·ASY(완성)·SAG(사급). 마이너스 원천차단용."""
    item = str(item or "").strip(); need = float(need or 0)
    if not item or need <= 0:
        return None
    ph = ",".join("?" * len(points))
    cur.execute(f"""SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger
        WHERE STOCK_POINT IN ({ph}) AND (MAT_CODE=? OR ITEM_CODE=?)""", *points, item, item)
    avail = float(cur.fetchone()[0] or 0)
    if need > avail + 1e-6:
        return f"재고부족 ({item} 가용 {avail:g} < {label} {need:g})"
    return None

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
# nx 전용 확장 코드(라이브 코드마스터엔 없고 우리가 추가한 클린 분류) — 미러 재복사(r_bulk_copy)에도 코드로 보존.
_KINDMAP_EXT = {'PR006': {'240': '용접봉'}}  # 소분류 240=용접봉(재고평가 대상), 2026-08-27 신설
def _kindmap(cur, kind):
    cur.execute("SELECT DETAIL_CODE, DETAIL_DESC FROM PARTNER_ERP_TEST3.nx.CM_M_MASTER_DETAIL WHERE KIND_CODE=?", kind)
    m = {str(r[0]).strip(): str(r[1] or "").strip() for r in cur.fetchall()}
    for k, v in _KINDMAP_EXT.get(kind, {}).items():
        m[k] = v   # 우리 소유 코드(240 등) — 우리 라벨이 정본
    return m


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


# ── ★2026-08-25 웹 전용 SEQ 대역 (라이브와 키 충돌 방지) ──────────────────
#   문제: MAINT_SEQ 는 일자별 채번인데 라이브·nx 가 독립 증가한다.
#         같은 (MAINT_YMD, MAINT_SEQ) 가 서로 다른 행이 되어, 두 DB 를 합쳐 조회할 때
#         중복배제가 불가능하다. 실측 260825 seq646 = 라이브 EAD62115301 / nx AJR30027704-12-1.
#         이 때문에 nx 648행이 통째로 배제돼 웹 실적이 화면에서 사라졌다.
#   해법: 웹이 쓰는 행은 WEB_SEQ_BASE(20000) 이상으로만 채번한다.
#         → 레거시(1~19,999)와 절대 겹치지 않으므로 (YMD,SEQ) 만으로 출처 판별·중복배제 가능.
#   ※ MAINT_SEQ 가 smallint(최대 32,767) 라 20000 대역이 한계다(일자별 웹 12,767건 수용).
#     레거시 일자별 최대는 7,791 이라 19,999 안에서 충분하다.
WEB_SEQ_BASE = 20000

def _web_seq(cur, table, ymd, col="MAINT_SEQ", ymd_col="MAINT_YMD"):
    """레거시 공유 테이블에 웹이 쓸 때 쓰는 다음 SEQ. 항상 WEB_SEQ_BASE 이상.
       table 은 'nx.PR_T_STOCK_MAINT_MAT' 처럼 스키마 포함 문자열(호출부 상수)."""
    cur.execute(f"SELECT ISNULL(MAX({col}),0) FROM {table} WHERE {ymd_col}=? AND {col}>=?",
                ymd, WEB_SEQ_BASE)
    mx = int(cur.fetchone()[0] or 0)
    return max(mx + 1, WEB_SEQ_BASE)


# ── ★2026-08-25 생산창고 재고 = '이력 기준' 공용 계산 ─────────────────────
#   왜 잔액 테이블을 못 쓰나:
#     nx 잔액은 '라이브 미러 + 웹실적' 이 아니라, 미러가 늦으면 웹실적만 담긴 반쪽 값이 된다.
#     실측 AJR30027704-SUB6 → 라이브 25(미러본) / nx 0(미러 못 받고 웹 -2만 적용) / 정답 23.
#     라이브·nx 잔액을 어떻게 조합해도(합·최댓값·최신본) 두 케이스를 동시에 못 맞춘다.
#       · 라이브+원장델타 = 이중계상 (웹이 잔액도 갱신하므로) → SUB1 -2 (정답 0)
#       · nx 잔액 단독    = 미러 미반영분 누락        → SUB6 0  (정답 23)
#   해법: 2502 마감 스냅샷 + 그 이후 모든 이동을 누적한다(라이브 ∪ nx, 중복배제).
#         생산입출고현황(live_api._prodinout)이 이 방식으로 SUB1=0·SUB6=23·12-1=62 를 정확히 낸다.
#   ※반드시 (MAT_CODE, PART_CODE) 파트 단위로 집계할 것. 파트를 빼고 합치면 값이 무너진다.

def _u_tbl(tbl, keys):
    """라이브 ∪ nx — nx 행 중 라이브에 같은 키가 없는 것만 얹는 인라인뷰."""
    on = " AND ".join(f"ISNULL(l.{k},'')=ISNULL(n.{k},'')" for k in keys)
    return (f"(SELECT * FROM PARTNER_ERP.dbo.{tbl} UNION ALL SELECT n.* FROM PARTNER_ERP_TEST3.nx.{tbl} n"
            f" WHERE NOT EXISTS(SELECT 1 FROM PARTNER_ERP.dbo.{tbl} l WHERE {on}))")


def _prod_stock_sql():
    """생산창고(파트창고) 재고를 이력으로 계산하는 SQL. 컬럼 = mat, part, q.
       원천·부호는 live_api._prodinout(생산입출고현황, 검증완료)과 1:1 동일하게 유지할 것.
       하나라도 빠지면 값이 통째로 어긋난다(실측: 자재창고입고 누락 시 1,493/1,582행 불일치)."""
    PUSM = _u_tbl("PU_T_STOCK_MAINT", ["MAINT_YMD", "MAINT_SEQ", "MAT_CODE", "MAINT_QTY", "MAINT_TAG"])
    PRPD = _u_tbl("PR_T_PROD_DTL", ["PROD_YMD", "PROD_HMS", "ITEM_CODE", "WORK_ORDER", "SPLIT_WORK_ORDER"])
    PRSM = _u_tbl("PR_T_STOCK_MAINT_MAT", ["MAINT_YMD", "MAINT_SEQ", "MAT_CODE", "PART_CODE", "MAINT_QTY"])
    SASM = _u_tbl("SA_T_STOCK_MAINT", ["MAINT_YMD", "MAINT_SEQ", "ITEM_CODE", "MAINT_QTY"])
    CUT = ("(SELECT * FROM PARTNER_ERP.dbo.pu_t_cut_dtl UNION ALL SELECT n.* FROM PARTNER_ERP_TEST3.nx.pu_t_cut_dtl n"
           " WHERE NOT EXISTS(SELECT 1 FROM PARTNER_ERP.dbo.pu_t_cut_dtl l"
           " WHERE l.BOX_NO=n.BOX_NO AND l.CUT_YMD=n.CUT_YMD AND l.CUT_HMS=n.CUT_HMS))")
    INSP = "NOT(ISNULL(a.insp_flag,'N') IN ('S','F') AND ISNULL(a.insp_proc_flag,'0')<>'1')"
    return f"""
 SELECT mat, part, SUM(q) q FROM (
   -- 2502 마감 스냅샷
   SELECT UPPER(a.mat_code) mat, a.gagong_proc_code part, a.stock_qty q
     FROM PARTNER_ERP.dbo.PR_T_MONTH_STOCK_WH a WITH(NOLOCK) WHERE a.stock_yymm='2502'
   -- 자재창고→생산창고 입고 (maint_qty 가 음수로 적재되어 부호 반전)
   UNION ALL
   SELECT UPPER(a.mat_code), a.TO_GAGONG_PROC_CODE, a.maint_qty*-1
     FROM {PUSM} a WHERE a.maint_ymd>'250299' AND a.maint_tag='B'
      AND ISNULL(a.out_wh_gubun,'1')='1' AND {INSP} AND ISNULL(a.TO_GAGONG_PROC_CODE,'')>''
   -- 자재창고 반품(출고)
   UNION ALL
   SELECT UPPER(a.mat_code), a.TO_GAGONG_PROC_CODE, a.maint_qty
     FROM {PUSM} a WHERE a.maint_ymd>'250299' AND a.maint_tag='T'
      AND ISNULL(a.out_wh_gubun,'3')='3' AND ISNULL(a.TO_GAGONG_PROC_CODE,'')>''
   -- 가공부품이동(출고)
   UNION ALL
   SELECT UPPER(a.mat_code), a.TO_GAGONG_PROC_CODE, a.maint_qty*-1
     FROM {PUSM} a WHERE a.maint_ymd>'250299' AND a.maint_tag='C'
      AND ISNULL(a.TO_GAGONG_PROC_CODE,'')>''
   -- 가공생산입고
   UNION ALL
   SELECT UPPER(a.mat_code), a.gagong_proc_code, a.cut_qty
     FROM {CUT} a WHERE a.cut_ymd>'250299' AND ISNULL(a.gagong_proc_code,'')>'' AND a.cut_qty<>0
   -- SUB생산실적(바코드) — 같은 건이 sa_t_stock_maint 에도 있으면 제외
   UNION ALL
   SELECT UPPER(a.item_code), a.STOCK_PART_CODE, a.prod_qty
     FROM {PRPD} a
    WHERE a.prod_ymd>'250299' AND ISNULL(a.STOCK_PART_CODE,'')>''
      AND NOT EXISTS(SELECT 1 FROM PARTNER_ERP_TEST3.nx.sa_t_stock_maint s WITH(NOLOCK)
                      WHERE s.maint_ymd=a.prod_ymd AND s.item_code=a.item_code
                        AND (s.in_part_code=a.stock_part_code
                             -- ★최종품(ASSY) 실적은 in_part_code 가 비어 있다. 520 바코드가
                             --   PR_T_PROD_DTL 에도 STOCK_PART_CODE 를 채우므로, 이 조건이
                             --   없으면 같은 실적이 ASSY재고 + 생산재고로 두 번 잡힌다
                             --   (실측 AEG74589807: ASSY 22 인데 생산재고에도 22).
                             OR (ISNULL(s.in_part_code,'')='' AND s.maint_tag='P')))
   -- 생산실적(제품수불 경유분)
   UNION ALL
   SELECT UPPER(a.ITEM_CODE), a.IN_PART_CODE, a.MAINT_QTY
     FROM {SASM} a WHERE a.MAINT_YMD>'250299' AND ISNULL(a.IN_PART_CODE,'')>''
   -- 생산사용(출고)·재고조정·기초 — PR_T_STOCK_MAINT_MAT 전 태그
   UNION ALL
   SELECT UPPER(a.MAT_CODE), a.PART_CODE, a.MAINT_QTY
     FROM {PRSM} a WHERE a.MAINT_YMD>'250299' AND ISNULL(a.PART_CODE,'')>''
 ) t GROUP BY mat, part"""


def _latest_stock_map(cur, tbl, key, where="", extra_on=()):
    """잔액 테이블을 'nx 우선, 없으면 라이브' 로 읽는다. {키: 재고}.

       nx 가 정본이다 — 웹 실적/조정은 nx 에만 쌓이므로 라이브를 보면 웹에서 한 작업이
       화면에 안 나타나고 프로세스 검증이 불가능하다.
       미러가 늦어 nx 에 행이 아직 없는 품목만 라이브 값으로 채운다(목록 누락 방지).

       ★갱신시각(UPDATE_DATETIME) 비교는 쓰지 않는다 — 레거시가 계속 가동돼
         라이브가 거의 항상 더 최신이라(실측 라이브 16:36 vs nx 11:42) 그 규칙으로는
         웹 실적이 통째로 묻힌다.
       ※생산창고(PR_T_MAT_STOCK_WH)만 예외 — 거긴 nx 잔액이 미러 지연 시 웹실적만 담긴
         반쪽 값이 되므로 _prod_stock_map(이력기준)을 써야 한다."""
    w = (" WHERE " + where) if where else ""
    on = " AND ".join([f"l.{key}=n.{key}"] + [f"ISNULL(l.{c},'')=ISNULL(n.{c},'')" for c in extra_on])
    sql = f"""
 SELECT k, SUM(q) q FROM (
   SELECT ISNULL(n.{key}, l.{key}) k,
          CASE WHEN n.{key} IS NULL THEN l.STOCK_QTY ELSE n.STOCK_QTY END q
     FROM (SELECT * FROM PARTNER_ERP_TEST3.nx.{tbl} WITH(NOLOCK){w}) n
     FULL JOIN (SELECT * FROM PARTNER_ERP.dbo.{tbl} WITH(NOLOCK){w}) l ON {on}
 ) u GROUP BY k"""
    out = {}
    try:
        cur.execute(sql)
        for r in cur.fetchall():
            out[str(r[0] or "").strip()] = float(r[1] or 0)
    except Exception:
        pass
    return out


def _prod_stock_map(cur, by_part=False):
    """생산창고 재고 맵. by_part=False → {mat: 합계} / True → {(mat,part): 재고}."""
    out = {}
    try:
        cur.execute(_prod_stock_sql())
        for r in cur.fetchall():
            m = str(r[0] or "").strip(); p = str(r[1] or "").strip(); v = float(r[2] or 0)
            if by_part:
                out[(m, p)] = out.get((m, p), 0.0) + v
            else:
                out[m] = out.get(m, 0.0) + v
    except Exception:
        pass
    return out


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

# ── 원소재 기하중량 (레거시 f_get_weight3 정합) ─────────────────────────────
_METAL_DENS = {'고강도': 8.94, 'CU': 8.94, 'AL': 2.7, 'FE': 7.85, 'STS': 7.93}  # CM_M_MASTER_DETAIL PR019 비중

def _geom_weight(metal_gubun, diam, thick, length):
    """원소재 기하중량 = π(D−T)·T·L·비중(재질별)/1e6. 레거시 f_get_weight3(PR019 비중)와 정합.
       cg='3' 원소재는 SP가 저장 중량 무시하고 항상 기하계산 → 편집/sync 시 이 값으로 재계산.
       비중 미상·치수 0이면 None(재계산 안 함)."""
    import math
    dens = _METAL_DENS.get(str(metal_gubun or '').strip())
    try:
        d, t, l = float(diam or 0), float(thick or 0), float(length or 0)
    except Exception:
        return None
    if not dens or d <= 0 or t <= 0 or l <= 0:
        return None
    return round(math.pi * (d - t) * t * l * dens / 1e6, 6)


# ── SUB(자도번) 품명 접미사 병기 (배치 r_sub_desc_suffix 정합·CRUD 저장 시 적용) ──────────
#   병행운영=배치가 매 sync 후 재병기 / 컷오버 후=레거시 신규 없음→CRUD 저장경로가 이걸로 자동부착.
#   (net_weight _geom_weight 자동재계산과 동일 패턴. 정본 = _schema/CUTOVER_MUST_AND_DAILY_MIGRATION §A 2-b·§B-1 3-a)
def _sub_desc_suffix(code, name):
    """SUB(자도번) 품명 앞에 '[-{접미사}] ' 병기(멱등·self-heal). 접미사=코드 첫 '-' 뒤 전부.
       스킵(원품명 유지): 접미사없음 / 원품명에 코드포함 / 원품명이 접미사로 시작.
       ★순수 문자열 변환 — 호출 전 code가 SUB(_is_sub_code)인지 확인. 배치 r_sub_desc_suffix와 동일 규칙."""
    code = (code or '').strip(); name = (name or '').strip()
    if '-' not in code:
        return name
    suf = code.split('-', 1)[1]
    pref = f"[-{suf}] "
    if name.startswith(pref):                       # self-heal: 이미 이 접미사 프리픽스 → 원품명
        base = name[len(pref):]
    elif name.startswith("[-") and "] " in name:    # 다른 프리픽스 잔재 → 제거
        base = name.split("] ", 1)[1]
    else:
        base = name
    if code in base:                                # 원품명에 코드포함 → 유지
        return base
    if base == suf or base.startswith(suf + "/") or base.startswith(suf + "-") or base.startswith(suf + " "):
        return base                                 # 원품명이 접미사로 시작 → 유지
    return f"[-{suf}] {base}"


def _is_sub_code(cur, code):
    """code가 등록된 SUB(자도번)인가 = nx.sub_code_map.raw_item 존재. CRUD 접미사 병기 스코프(비SUB 무변경)."""
    try:
        r = cur.execute("SELECT 1 FROM PARTNER_ERP_TEST3.nx.sub_code_map WHERE LTRIM(RTRIM(raw_item))=?",
                        (code or '').strip()).fetchone()
        return r is not None
    except Exception:
        return False

def _assert_open(cur, ymd, domain="MAT", what="이 작업"):
    """★마감 잠금 강제(전 재고이동 쓰기 공통). 마감된 기간이면 400으로 거부.
       규칙(사용자 확정 2026-08-27): 재고가 조금이라도 움직이면 잠근다.
         한 엔드포인트가 재고이동과 문서발행을 겸해 분리가 어려우면 → 막는 쪽으로 지정.
       사용: _assert_open(cur, ymd)            # 자재(기본)
             _assert_open(cur, ymd, "PRD")     # 생산
       정본 = _schema/STOCK_GATING_CLOSE_LOCK_RULES.md 규칙B."""
    from fastapi import HTTPException as _HE
    m = _lock_msg(cur, ymd, domain)
    if m:
        raise _HE(400, f"{m} ({what})")


# ===== 재고 변경 훅 — 캐시 stale 금지 (2026-08-28) =====
# ★수불장(close.py `_LEDGER_CACHE`)은 조회 전용 캐시다. 재고가 움직이면 반드시 버려야
#   화면이 옛 값을 보여주지 않는다. 재고를 쓰는 **모든** 경로가 이 함수를 부른다.
#   여기 두는 이유 = routers 끼리 서로 임포트하면 순환이 난다. common 은 모두가 이미 쓴다.
def stock_changed(reason=""):
    """재고가 바뀌었다 — 파생 캐시를 버린다. 실패해도 쓰기를 막지 않는다(조회 캐시일 뿐).
       ★게이트 가용재고 맵(_AVAIL_MAP)도 함께 버린다 — 안 버리면 방금 쓴 재고를 게이트가 못 본다."""
    try:
        _AVAIL_MAP["key"] = None; _AVAIL_MAP["map"] = {}; _AVAIL_MAP["at"] = 0.0
    except Exception:
        pass
    try:
        from routers.close import _ledger_cache_clear
        _ledger_cache_clear()
    except Exception:
        pass
