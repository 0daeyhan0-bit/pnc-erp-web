# -*- coding: utf-8 -*-
"""
라이브 조회 API (읽기전용 PARTNER_ERP 레거시) — 스냅샷(data.js) 화면을 라이브로 승격.
- 모든 쿼리는 SELECT 전용. 사용자가 현행 ERP 화면과 대조 가능하도록 라이브 레거시를 그대로 조회.
- 검증된 쿼리(export_web_data.py / patch_*.py)를 그대로 이식, 일자/월만 파라미터화.
app.py 에서 include_router(live_router) 로 마운트.
"""
import os, sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'New_ERP'))  # Projects\New_ERP
import db_client, pyodbc
from fastapi import APIRouter, Query

live_router = APIRouter(prefix="/api/live", tags=["live"])

def _ro():
    """읽기전용 PARTNER_ERP 커넥션(쓰기 불가)."""
    cs = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
          f'DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
    return pyodbc.connect(cs, readonly=True)

def _rows(sql, *params):
    """SELECT 실행 → [{col:val}]. datetime은 isoformat."""
    cn = _ro(); cur = cn.cursor()
    try:
        cur.execute(sql, *params) if params else cur.execute(sql)
        cols = [d[0] for d in cur.description]
        out = []
        for r in cur.fetchall():
            d = {}
            for c, v in zip(cols, r):
                d[c] = (v.isoformat() if hasattr(v, "isoformat") else
                        (float(v) if hasattr(v, "as_tuple") else v))  # Decimal→float
            out.append(d)
        return cols, out
    finally:
        cn.close()

def _scalar(sql, *params):
    cn = _ro(); cur = cn.cursor()
    try:
        cur.execute(sql, *params) if params else cur.execute(sql)
        r = cur.fetchone()
        return r[0] if r else None
    finally:
        cn.close()

# ================= ★Phase5: nx.stock_ledger 파생(조회 8종 source=live|nx 토글) =================
# 방침: 기본 source=live(현행 유지·대조용) 절대불변. source=nx면 단일원장 파생(잔량=기초+ΣMAINT).
#   자재=MAT / 생산=PRD / 제품=ASY / 준비=RDY / 사급=SAG. PRD/ASY는 레거시 생산이력 미적재 → 컷오버 backfill 전까지 빈데이터(사유표시).
def _nxc():
    """nx(PARTNER_ERP_TEST3) 읽기전용 커넥션(파생 SELECT 전용)."""
    cs = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
          f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
    return pyodbc.connect(cs, readonly=True)

def _nx_rows(sql, *params):
    cn = _nxc(); cur = cn.cursor()
    try:
        cur.execute(sql, *params) if params else cur.execute(sql)
        cols = [d[0] for d in cur.description]
        out = []
        for r in cur.fetchall():
            d = {}
            for c, v in zip(cols, r):
                d[c] = (v.isoformat() if hasattr(v, "isoformat") else (float(v) if hasattr(v, "as_tuple") else v))
            out.append(d)
        return out
    finally:
        cn.close()

_NX_POINT_NOTE = {
    "MAT": "",  # 레거시 PU_T_STOCK_MAINT 스냅샷 재적재분 존재 → 라이브와 근사대조 가능",
    "PRD": "nx 원장에 레거시 생산이력 미적재(컷오버 backfill 전) — 라이브 기본 사용. nx모드는 웹 백플러시/조정분만.",
    "ASY": "nx 원장에 레거시 제품이력 미적재(컷오버 backfill 전) — 라이브 기본 사용. nx모드는 웹 사급/조정분만.",
    "RDY": "nx 원장 키팅(K1/K2)·조정분 파생.",
    "SAG": "nx 원장 사급(G1/G2/2/9/5) 파생.",
}

def _nx_derive(point, from6, to6, limit=8000):
    """단일원장 파생 재고 그리드. 잔량=기초(<from)+ΣMAINT(<=to). 입고=+, 출고=−(양수표시). 근거키 삭제/쓰기 없음(순수 SELECT)."""
    sql = f"""SELECT TOP {int(limit)}
        COALESCE(NULLIF(L.MAT_CODE,''),L.ITEM_CODE) cd, MAX(i.ITEM_DESC) nm, MAX(i.ITEM_SPEC) spec,
        ISNULL(L.GAGONG_PROC_CODE,'') gpc, ISNULL(L.CUST_CODE,'') cust,
        SUM(CASE WHEN L.MAINT_YMD<? THEN L.MAINT_QTY ELSE 0 END) base,
        SUM(CASE WHEN L.MAINT_YMD BETWEEN ? AND ? AND L.MAINT_QTY>0 THEN L.MAINT_QTY ELSE 0 END) inq,
        SUM(CASE WHEN L.MAINT_YMD BETWEEN ? AND ? AND L.MAINT_QTY<0 THEN -L.MAINT_QTY ELSE 0 END) outq,
        SUM(CASE WHEN L.MAINT_YMD<=? THEN L.MAINT_QTY ELSE 0 END) endq
      FROM nx.stock_ledger L
      LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM i ON i.ITEM_CODE=COALESCE(NULLIF(L.MAT_CODE,''),L.ITEM_CODE)
      WHERE L.STOCK_POINT=?
      GROUP BY COALESCE(NULLIF(L.MAT_CODE,''),L.ITEM_CODE), ISNULL(L.GAGONG_PROC_CODE,''), ISNULL(L.CUST_CODE,'')
      HAVING SUM(CASE WHEN L.MAINT_YMD<=? THEN L.MAINT_QTY ELSE 0 END)<>0
          OR SUM(CASE WHEN L.MAINT_YMD BETWEEN ? AND ? THEN 1 ELSE 0 END)>0
      ORDER BY cd"""
    rows = _nx_rows(sql, from6, from6, to6, from6, to6, to6, point, to6, from6, to6)
    for r in rows:
        for k in ("base", "inq", "outq", "endq"):
            r[k] = round(float(r[k] or 0), 3)
    # ★#4 코드→이름: 파트(gpc)=PR_M_PROC_GAGONG, 거래처(cust)=CM_M_CUST (품목처럼 이름 표시)
    def _q(s): return "'" + str(s).replace("'", "''") + "'"
    gpcs = sorted({(r.get("gpc") or "").strip() for r in rows if (r.get("gpc") or "").strip()})
    custs = sorted({(r.get("cust") or "").strip() for r in rows if (r.get("cust") or "").strip()})
    gmap, cmap = {}, {}
    if gpcs:
        _c, gr = _rows(f"SELECT gagong_proc_code cd, gagong_proc_desc nm FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG WHERE gagong_proc_code IN ({','.join(_q(x) for x in gpcs)})")
        gmap = {str(x["cd"]).strip(): (x["nm"] or "") for x in gr}
    if custs:
        _c, cr = _rows(f"SELECT cust_code cd, cust_desc nm FROM PARTNER_ERP_TEST3.nx.CM_M_CUST WHERE cust_code IN ({','.join(_q(x) for x in custs)})")
        cmap = {str(x["cd"]).strip(): (x["nm"] or "") for x in cr}
    for r in rows:
        r["gpc_nm"] = gmap.get((r.get("gpc") or "").strip(), "")
        r["cust_nm"] = cmap.get((r.get("cust") or "").strip(), "")
    return rows

def _nx_screen(point, from6, to6):
    """source=nx 응답(균일 파생 그리드 + 사유). 라이브 응답과 별개 최상위 shape(프론트 nx뷰가 렌더)."""
    rows = _nx_derive(point, from6, to6)
    tot = {"base": round(sum(r["base"] for r in rows), 3), "inq": round(sum(r["inq"] for r in rows), 3),
           "outq": round(sum(r["outq"] for r in rows), 3), "endq": round(sum(r["endq"] for r in rows), 3)}
    note = _NX_POINT_NOTE.get(point, "")
    if not rows and point in ("PRD", "ASY", "RDY", "SAG"):   # ★#4 RDY/SAG도 빈데이터 사유표시
        note = f"nx 원장에 {point} 이력 미적재(컷오버 backfill 전) — 라이브 기본 사용. nx모드는 웹 기입분만 표시."
    return {"source": "nx", "point": point, "from_ymd": from6, "to_ymd": to6,
            "count": len(rows), "rows": rows, "totals": tot, "nx_note": note}

# ================= 자재 수불장 (구매/자재, dw_pu_stock_260/160) =================
# 일수불=PU_T_MONTH_STOCK_WH_DAILY(일자별 스냅샷), 월수불=PU_T_MONTH_STOCK_WH(마감월).
# 원천/집계는 export_web_data.py 의 q_live 쿼리와 동일. 일자/월만 파라미터화.
_LEDGER_SELECT = """
select t.mat_code cd, max(m.item_desc) nm, max(m.item_spec) spec,
  isnull(max(m.item_sgroup),'') sg, max(m.unit) unit,
  isnull(max(m.in_cust_code),'') custcd, isnull(max(c.cust_desc),'') cust, isnull(max(c.cust_type),'') ctype,
  {lastin} lastin,
  sum(t.basic_qty) bq,  sum(t.basic_amt) ba,
  sum(t.input_qty) iq,  sum(t.input_amt) ia,
  sum(t.output_qty) oq, sum(t.output_amt) oa,
  sum(t.trans_qty) tq,  sum(t.trans_amt) ta,
  sum(t.stock_qty) sq,  sum(t.stock_amt) sa
from {tbl} t
join PARTNER_ERP_TEST3.nx.pr_m_item m on t.mat_code=m.item_code
join PARTNER_ERP_TEST3.nx.pr_m_proc_gagong g on t.gagong_proc_code=g.gagong_proc_code
left join PARTNER_ERP_TEST3.nx.cm_m_cust c on m.in_cust_code=c.cust_code
where t.cust_code='Z99990' and t.{col}=?
group by t.mat_code
order by t.mat_code
"""

@live_router.get("/matledger")
def matledger(period: str = Query("day"), ymd: str = Query(""), source: str = Query("live")):
    """자재수불장. 기본 source=live(현행 무변경). source=nx면 stock_ledger(MAT) 파생. period=day/month."""
    if period == "month":
        key = (ymd or "").replace("-", "").strip()
        if len(key) >= 6:  # YYYYMM → YYMM
            key = key[2:6]
        if not key:
            key = _scalar("SELECT MAX(STOCK_YYMM) FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH WHERE cust_code='Z99990'")
        if source == "nx":
            r = _nx_screen("MAT", str(key) + "01", str(key) + "31"); r["period"] = "month"; r["key"] = key; return r
        sql = _LEDGER_SELECT.format(tbl="PU_T_MONTH_STOCK_WH", col="STOCK_YYMM", lastin="''")
        _cols, rows = _rows(sql, key)
        return {"period": "month", "key": key, "count": len(rows), "rows": rows}
    else:
        key = (ymd or "").replace("-", "").strip()
        if len(key) == 8:  # YYYYMMDD → YYMMDD
            key = key[2:]
        if not key:
            key = _scalar("SELECT MAX(STOCK_YMD) FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH_DAILY WHERE cust_code='Z99990'")
        if source == "nx":
            r = _nx_screen("MAT", str(key), str(key)); r["period"] = "day"; r["key"] = key; return r
        sql = _LEDGER_SELECT.format(tbl="PU_T_MONTH_STOCK_WH_DAILY", col="STOCK_YMD", lastin="max(t.last_in_ymd)")
        _cols, rows = _rows(sql, key)
        return {"period": "day", "key": key, "count": len(rows), "rows": rows}

@live_router.get("/matledger/dates")
def matledger_dates():
    """선택 가능한 일자/마감월 범위(피커 힌트)."""
    dmax = _scalar("SELECT MAX(STOCK_YMD) FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH_DAILY WHERE cust_code='Z99990'")
    dmin = _scalar("SELECT MIN(STOCK_YMD) FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH_DAILY WHERE cust_code='Z99990'")
    mmax = _scalar("SELECT MAX(STOCK_YYMM) FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH WHERE cust_code='Z99990'")
    mmin = _scalar("SELECT MIN(STOCK_YYMM) FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH WHERE cust_code='Z99990'")
    return {"day": {"min": dmin, "max": dmax}, "month": {"min": mmin, "max": mmax}}

# ================= 자재불출집계표 (구매/자재, dw_pu_input_140) =================
# LG外 전 매출(유상사급 포함). 원장(PU/SA_T_STOCK_MAINT + PU_T_STOCK_MAINT_C) 기반 → 기간 파라미터화 라이브.
# 검증된 export_web_data.py _dispatch 쿼리 이식. 마감기준=업체별 마감일 구간, 불출기준=실제 이동일 구간.
def _digits(s, n=None):
    d = "".join(ch for ch in str(s or "") if ch.isdigit())
    return d[:n] if n else d

def _ym4(ym):
    """사용자 ym → YYMM(4자리). ★#3 견고성: 6자리(YYYYMM) 들어와도 안전(202606→2606). UI는 4자리이나 방어."""
    d = _digits(ym)
    return d[2:6] if len(d) >= 6 else d[:4]

def _def_range(dfrom, dto):
    """기간 기본값: 미지정 시 dto=오늘(실행일자), dfrom=당월1일."""
    t = _digits(dto, 6) or _scalar("SELECT FORMAT(GETDATE(),'yyMMdd')")
    f = _digits(dfrom, 6) or (_scalar("SELECT FORMAT(GETDATE(),'yyMM')") + "01")
    return f, t

def _dispatch_inner(dc):
    return f"""
   SELECT A.CUST_CODE, MAX(C2.CUST_DESC) CUST_DESC, C2.CUST_TYPE, A.MAT_CODE, A.MAINT_COST, A.MAINT_COST KRW_MAINT_COST, A.ITEM_CODE,
     MAX(M.ITEM_DESC) ITEM_DESC, MAX(M.ITEM_SPEC) ITEM_SPEC, MAX(M.UNIT) UNIT, M.ITEM_LGROUP, M.ITEM_SGROUP,
     SUM(-A.MAINT_QTY) MAINT_QTY, SUM(-A.MAINT_AMT) MAINT_AMT, SUM(-A.MAINT_AMT) KRW_MAINT_AMT, SUM(-A.MAINT_VAT) MAINT_VAT, SUM(-A.MAINT_VAT) KRW_MAINT_VAT,
     1 EXCHANGE_RATE, MAX(M.IN_CUST_CODE) IN_CUST_CODE, 'KRW' CURRENCY, MAX(M.ITEM_WEIGHT) ITEM_WEIGHT
    FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT A JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST C2 ON A.CUST_CODE=C2.CUST_CODE join MAGAM mg on a.cust_code=mg.cust_code
    WHERE {dc} AND A.MAINT_TAG IN ('5')
    GROUP BY A.CUST_CODE,A.MAINT_TAG,A.GAGONG_PROC_CODE,A.MAT_CODE,A.ITEM_CODE,C2.CUST_TYPE,A.MAINT_COST,M.ITEM_LGROUP,M.ITEM_SGROUP
   UNION ALL
   SELECT A.CUST_CODE, MAX(C2.CUST_DESC), C2.CUST_TYPE, A.ITEM_CODE, A.MAINT_COST, A.MAINT_COST, '',
     MAX(M.ITEM_DESC), MAX(M.ITEM_SPEC), MAX(M.UNIT), M.ITEM_LGROUP, M.ITEM_SGROUP,
     SUM(-A.MAINT_QTY), SUM(-A.MAINT_AMT), SUM(-A.MAINT_AMT), SUM(-A.MAINT_VAT), SUM(-A.MAINT_VAT), 1, MAX(M.IN_CUST_CODE), 'KRW', MAX(M.ITEM_WEIGHT)
    FROM PARTNER_ERP_TEST3.nx.SA_T_STOCK_MAINT A JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM M ON A.ITEM_CODE=M.ITEM_CODE JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST C2 ON A.CUST_CODE=C2.CUST_CODE join MAGAM mg on a.cust_code=mg.cust_code
    WHERE {dc} AND A.MAINT_TAG IN ('R')
    GROUP BY A.CUST_CODE,A.MAINT_TAG,A.ITEM_CODE,A.MAINT_COST,C2.CUST_TYPE,M.ITEM_LGROUP,M.ITEM_SGROUP
   UNION ALL
   SELECT A.CUST_CODE, MAX(C2.CUST_DESC), C2.CUST_TYPE, A.MAT_CODE, A.MAINT_COST, (A.MAINT_COST*A.EXCHANGE_RATE), A.ITEM_CODE,
     MAX(M.ITEM_DESC), MAX(M.ITEM_SPEC), MAX(M.UNIT), M.ITEM_LGROUP, M.ITEM_SGROUP,
     SUM(A.MAINT_QTY), SUM(A.MAINT_AMT), SUM(A.TAXPAYERS), 0, 0, A.EXCHANGE_RATE, MAX(M.IN_CUST_CODE), A.CURRENCY, MAX(M.ITEM_WEIGHT)
    FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT_C A JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST C2 ON A.CUST_CODE=C2.CUST_CODE join MAGAM mg on a.cust_code=mg.cust_code
    WHERE {dc} AND A.DIVISION='Q'
    GROUP BY A.CUST_CODE,A.MAINT_TAG,A.MAT_CODE,A.ITEM_CODE,A.MAINT_COST,C2.CUST_TYPE,A.EXCHANGE_RATE,M.ITEM_LGROUP,M.ITEM_SGROUP,A.CURRENCY"""

def _dispatch(dc, ref_ym):
    magam = f"""WITH MAGAM (CUST_CODE, JUN_YYMM, JUN_MAGAM_DAY, MAGAM_DAY) AS (
      SELECT CUST_CODE
        ,format(dateadd(MONTH,-1,convert(date,'{ref_ym}'+'01',12)),'yyMM') jun_yymm
        ,ISNULL((SELECT TOP 1 MAGAM_DAY FROM PARTNER_ERP_TEST3.nx.CM_M_CUST_MAGAM WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<=format(dateadd(MONTH,-1,convert(date,'{ref_ym}'+'01',12)),'yyMM') ORDER BY APPLY_YYMM DESC),'31') JUN_MAGAM_DAY
        ,ISNULL((SELECT TOP 1 MAGAM_DAY FROM PARTNER_ERP_TEST3.nx.CM_M_CUST_MAGAM WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<='{ref_ym}' ORDER BY APPLY_YYMM DESC),'31') MAGAM_DAY
      FROM PARTNER_ERP_TEST3.nx.CM_M_CUST A )"""
    sql = f"""{magam}
    SELECT T.CUST_CODE cc, MAX(T.CUST_DESC) cnm, T.CUST_TYPE ct, T.MAT_CODE mat, T.ITEM_CODE ic,
      MAX(T.ITEM_DESC) nm, MAX(T.ITEM_SPEC) spec, MAX(T.UNIT) unit, T.ITEM_LGROUP lg, T.ITEM_SGROUP sg,
      T.MAINT_COST cost, T.KRW_MAINT_COST kcost, T.EXCHANGE_RATE rate, T.CURRENCY cur,
      (SELECT CUST_DESC FROM PARTNER_ERP_TEST3.nx.CM_M_CUST WHERE CUST_CODE=MAX(T.IN_CUST_CODE)) incust, isnull(MAX(T.ITEM_WEIGHT),0) wt,
      SUM(T.MAINT_QTY) qty, SUM(T.MAINT_AMT) amt, SUM(T.MAINT_VAT) vat, SUM(T.KRW_MAINT_AMT) kamt, SUM(T.KRW_MAINT_VAT) kvat
    FROM ({_dispatch_inner(dc)}) T
    GROUP BY T.CUST_CODE,T.CUST_TYPE,T.ITEM_CODE,T.MAT_CODE,T.ITEM_LGROUP,T.ITEM_SGROUP,T.MAINT_COST,T.KRW_MAINT_COST,T.EXCHANGE_RATE,T.CURRENCY"""
    _cols, rows = _rows(sql)
    return rows

@live_router.get("/dispatch")
def dispatch(gijun: str = Query("close"), ym: str = Query(""), dfrom: str = Query(""), dto: str = Query("")):
    """자재불출집계표 라이브. gijun=close(마감기준, ym=YYMM) / issue(불출기준, dfrom~dto=YYMMDD)."""
    if gijun == "issue":
        f, t = _def_range(dfrom, dto)
        ref = t[:4]
        dc = f"A.MAINT_YMD between '{f}' and '{t}'"
        rows = _dispatch(dc, ref)
        return {"gijun": "issue", "dfrom": f, "dto": t, "count": len(rows), "rows": rows}
    else:
        y = _ym4(ym) or _scalar("SELECT FORMAT(GETDATE(),'yyMM')")  # 마감기준 기본=현재월(진행 중 마감)
        dc = f"A.MAINT_YMD > mg.jun_yymm+mg.jun_magam_day AND A.MAINT_YMD <= '{y}'+mg.magam_day"
        rows = _dispatch(dc, y)
        return {"gijun": "close", "ym": y, "count": len(rows), "rows": rows}

# ================= 확정입고집계표 (구매/자재, dw_pu_input_120) =================
# 확정입고(검사통과 9/S/C/G/H) + 수입(PU_T_STOCK_MAINT_C DIVISION='P'). grain=(cc,ic,mat). patch_receipt.py 이식.
def _receipt_inner(dc):
    return f"""
  SELECT A.CUST_CODE cc, C.CUST_DESC cnm, C.CUST_TYPE ct, A.ITEM_CODE ic, A.MAT_CODE mat,
    M.ITEM_DESC nm, M.ITEM_SPEC spec, M.ITEM_LGROUP lg, M.ITEM_SGROUP sg, M.ITEM_WEIGHT wt, M.UNIT unit,
    'KRW' cur, 1.0 rate, A.MAINT_COST cost, A.MAINT_COST kcost,
    A.MAINT_QTY qty, A.MAINT_AMT amt, A.MAINT_AMT kamt, A.MAINT_VAT vat, A.MAINT_VAT kvat
   FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT (nolock) A JOIN PARTNER_ERP_TEST3.nx.pr_m_item (nolock) M ON A.MAT_CODE=M.ITEM_CODE JOIN PARTNER_ERP_TEST3.nx.cm_m_cust (nolock) C ON A.CUST_CODE=C.CUST_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
   WHERE {dc} AND A.MAINT_TAG IN ('9','S','C','G','H')
     AND ((ISNULL(A.INSP_FLAG,'N') IN ('','N')) OR (ISNULL(A.INSP_FLAG,'N') IN ('S','F') AND A.INSP_PROC_YMD >= ''))
  UNION ALL
  SELECT A.CUST_CODE, C.CUST_DESC, C.CUST_TYPE, A.ITEM_CODE, A.MAT_CODE,
    M.ITEM_DESC, M.ITEM_SPEC, M.ITEM_LGROUP, M.ITEM_SGROUP, M.ITEM_WEIGHT, M.UNIT,
    A.CURRENCY, A.EXCHANGE_RATE, A.MAINT_COST, A.MAINT_COST*A.EXCHANGE_RATE,
    A.MAINT_QTY, A.MAINT_AMT, A.TAXPAYERS, 0, 0
   FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT_C (nolock) A JOIN PARTNER_ERP_TEST3.nx.pr_m_item (nolock) M ON A.MAT_CODE=M.ITEM_CODE JOIN PARTNER_ERP_TEST3.nx.cm_m_cust (nolock) C ON A.CUST_CODE=C.CUST_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
   WHERE {dc} AND A.DIVISION IN ('P')"""

def _receipt(dc, ref_ym):
    magam = f"""WITH MAGAM (CUST_CODE, JUN_YYMM, JUN_MAGAM_DAY, MAGAM_DAY) AS (
  SELECT CUST_CODE,format(dateadd(MONTH,-1,convert(date,'{ref_ym}'+'01',12)),'yyMM') jun_yymm
    ,ISNULL((SELECT TOP 1 MAGAM_DAY FROM PARTNER_ERP_TEST3.nx.CM_M_CUST_MAGAM (nolock) WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<=format(dateadd(MONTH,-1,convert(date,'{ref_ym}'+'01',12)),'yyMM') ORDER BY APPLY_YYMM DESC),'31') JUN_MAGAM_DAY
    ,ISNULL((SELECT TOP 1 MAGAM_DAY FROM PARTNER_ERP_TEST3.nx.CM_M_CUST_MAGAM (nolock) WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<='{ref_ym}' ORDER BY APPLY_YYMM DESC),'31') MAGAM_DAY
  FROM PARTNER_ERP_TEST3.nx.CM_M_CUST (nolock) A )"""
    sql = f"""{magam}
    SELECT T.cc, MAX(T.cnm) cnm, MAX(T.ct) ct, T.ic, T.mat, MAX(T.nm) nm, MAX(T.spec) spec,
      MAX(T.lg) lg, MAX(T.sg) sg, MAX(T.wt) wt, MAX(T.unit) unit, MAX(T.cur) cur, MAX(T.rate) rate,
      MAX(T.cost) cost, MAX(T.kcost) kcost,
      SUM(T.qty) qty, SUM(T.amt) amt, SUM(T.kamt) kamt, SUM(T.vat) vat, SUM(T.kvat) kvat
    FROM ({_receipt_inner(dc)}) T GROUP BY T.cc, T.ic, T.mat"""
    _cols, rows = _rows(sql)
    return rows

@live_router.get("/receipt")
def receipt(gijun: str = Query("close"), ym: str = Query(""), dfrom: str = Query(""), dto: str = Query("")):
    """확정입고집계표 라이브. gijun=close(마감기준, ym=YYMM) / issue(입고기준, dfrom~dto=YYMMDD)."""
    if gijun == "issue":
        f, t = _def_range(dfrom, dto)
        ref = t[:4]
        dc = f"A.MAINT_YMD between '{f}' and '{t}'"
        rows = _receipt(dc, ref)
        return {"gijun": "issue", "dfrom": f, "dto": t, "count": len(rows), "rows": rows}
    else:
        y = _ym4(ym) or _scalar("SELECT FORMAT(GETDATE(),'yyMM')")
        dc = f"A.MAINT_YMD > mg.jun_yymm+mg.jun_magam_day AND A.MAINT_YMD <= '{y}'+mg.magam_day"
        rows = _receipt(dc, y)
        return {"gijun": "close", "ym": y, "count": len(rows), "rows": rows}

# ================= 확정입고명세서 (구매/자재, dw_pu_input_110) — 라인단위 =================
def _MAGAM(ref_ym):
    return f"""WITH MAGAM (CUST_CODE, JUN_YYMM, JUN_MAGAM_DAY, MAGAM_DAY) AS (
  SELECT CUST_CODE,format(dateadd(MONTH,-1,convert(date,'{ref_ym}'+'01',12)),'yyMM') jun_yymm
    ,ISNULL((SELECT TOP 1 MAGAM_DAY FROM PARTNER_ERP_TEST3.nx.CM_M_CUST_MAGAM (nolock) WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<=format(dateadd(MONTH,-1,convert(date,'{ref_ym}'+'01',12)),'yyMM') ORDER BY APPLY_YYMM DESC),'31') JUN_MAGAM_DAY
    ,ISNULL((SELECT TOP 1 MAGAM_DAY FROM PARTNER_ERP_TEST3.nx.CM_M_CUST_MAGAM (nolock) WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<='{ref_ym}' ORDER BY APPLY_YYMM DESC),'31') MAGAM_DAY
  FROM PARTNER_ERP_TEST3.nx.CM_M_CUST (nolock) A )"""

def _receiptdetail(dc, ref_ym, q=""):
    # ★품번(자도번/품명) 스코프: 입력 시 서버 WHERE로 밀어 해당 품목만 스캔(기간 넓어도 인덱스 seek로 빠름).
    #   자도번/품명을 pr_m_item에서 코드셋으로 해석 → IN(). 미해석시 MAT_CODE LIKE 폴백. CI 콜레이션 전제.
    #   미입력이면 빈 문자열 = 기존 전체조회 무변경(회귀0). _matinout 동일 패턴.
    MF = ""
    q = (q or "").strip()
    if q:
        qe = q.replace("'", "''")
        _cf, _mr = _rows(f"SELECT UPPER(item_code) c FROM PARTNER_ERP_TEST3.nx.pr_m_item WHERE item_code LIKE '%{qe}%' OR item_desc LIKE '%{qe}%'")
        _codes = [r["c"] for r in _mr if r.get("c")]
        if _codes:
            _inl = ",".join("'" + c.replace("'", "''") + "'" for c in _codes)
            MF = f" AND A.MAT_CODE IN ({_inl})"
        else:
            MF = f" AND A.MAT_CODE LIKE '%{qe}%'"
    sql = f"""{_MAGAM(ref_ym)}
SELECT A.MAINT_YMD ymd, A.MAINT_SEQ seq, A.CUST_CODE cc, C.CUST_DESC cnm, C.CUST_TYPE ct,
  A.MAT_CODE mat, M.ITEM_DESC nm, M.ITEM_SPEC spec, M.ITEM_DIAM diam, M.ITEM_THICK thick, M.ITEM_LENGTH length,
  M.ITEM_LGROUP lg, M.ITEM_SGROUP sg, M.ITEM_WEIGHT wt, M.UNIT unit,
  A.MAINT_QTY qty, 'KRW' cur, 1.0 rate, A.MAINT_COST cost, A.MAINT_COST kcost, A.MAINT_AMT amt, A.MAINT_AMT kamt, A.MAINT_VAT vat
 FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT (nolock) A JOIN PARTNER_ERP_TEST3.nx.pr_m_item (nolock) M ON A.MAT_CODE=M.ITEM_CODE JOIN PARTNER_ERP_TEST3.nx.cm_m_cust (nolock) C ON A.CUST_CODE=C.CUST_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
 WHERE {dc} AND A.MAINT_TAG IN ('9','S','C','G','H')
   AND ((ISNULL(A.INSP_FLAG,'N') IN ('','N')) OR (ISNULL(A.INSP_FLAG,'N') IN ('S','F') AND A.INSP_PROC_YMD >= '')){MF}
UNION ALL
SELECT A.MAINT_YMD, A.MAINT_SEQ, A.CUST_CODE, C.CUST_DESC, C.CUST_TYPE,
  A.MAT_CODE, M.ITEM_DESC, M.ITEM_SPEC, M.ITEM_DIAM, M.ITEM_THICK, M.ITEM_LENGTH,
  M.ITEM_LGROUP, M.ITEM_SGROUP, M.ITEM_WEIGHT, M.UNIT,
  A.MAINT_QTY, A.CURRENCY, A.EXCHANGE_RATE, A.MAINT_COST, A.MAINT_COST*A.EXCHANGE_RATE, A.MAINT_AMT, A.TAXPAYERS, 0
 FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT_C (nolock) A JOIN PARTNER_ERP_TEST3.nx.pr_m_item (nolock) M ON A.MAT_CODE=M.ITEM_CODE JOIN PARTNER_ERP_TEST3.nx.cm_m_cust (nolock) C ON A.CUST_CODE=C.CUST_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
 WHERE {dc} AND A.DIVISION IN ('P'){MF}"""
    _cols, rows = _rows(sql)
    return rows

@live_router.get("/receiptdetail")
def receiptdetail(gijun: str = Query("close"), ym: str = Query(""), dfrom: str = Query(""), dto: str = Query(""), q: str = Query(""), source: str = Query("live")):
    """자재입고명세서. 기본 source=live(현행 무변경). source=nx면 stock_ledger(MAT) 파생(원장 재고, 명세shape 아님). gijun=close/issue.
    q(자도번/품명) 입력 시 서버 WHERE로 스코프 → 해당 품목만 조회(기간 넓어도 빠름). 미입력=전체(무변경)."""
    if gijun == "issue":
        f, t = _def_range(dfrom, dto)
        if source == "nx":
            r = _nx_screen("MAT", f, t); r["gijun"] = "issue"; return r
        ref = t[:4]
        dc = f"A.MAINT_YMD between '{f}' and '{t}'"
        rows = _receiptdetail(dc, ref, q)
        return {"gijun": "issue", "dfrom": f, "dto": t, "count": len(rows), "rows": rows, "q": q}
    else:
        y = _ym4(ym) or _scalar("SELECT FORMAT(GETDATE(),'yyMM')")
        if source == "nx":
            r = _nx_screen("MAT", y + "01", y + "31"); r["gijun"] = "close"; r["ym"] = y; return r
        dc = f"A.MAINT_YMD > mg.jun_yymm+mg.jun_magam_day AND A.MAINT_YMD <= '{y}'+mg.magam_day"
        rows = _receiptdetail(dc, y, q)
        return {"gijun": "close", "ym": y, "count": len(rows), "rows": rows, "q": q}

# ================= 자재불출명세서 (구매/자재, dw_pu_input_130) — 라인단위 =================
def _dispatchdetail(dc, ref_ym):
    sql = f"""{_MAGAM(ref_ym)}
SELECT A.MAINT_YMD ymd, A.MAINT_SEQ seq, A.CUST_CODE cc, C.CUST_DESC cnm, C.CUST_TYPE ct,
  A.MAT_CODE mat, A.ITEM_CODE ic, (SELECT CUST_DESC FROM PARTNER_ERP_TEST3.nx.CM_M_CUST WHERE CUST_CODE=M.IN_CUST_CODE) incust,
  M.ITEM_LGROUP lg, M.ITEM_SGROUP sg, M.ITEM_WEIGHT wt, M.UNIT unit, M.ITEM_DESC nm, M.ITEM_SPEC spec,
  -A.MAINT_QTY qty, 'KRW' cur, 1.0 rate, A.MAINT_COST cost, A.MAINT_COST kcost, -A.MAINT_AMT amt, -A.MAINT_AMT kamt, -A.MAINT_VAT vat
 FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT A JOIN PARTNER_ERP_TEST3.nx.pr_m_item M ON A.MAT_CODE=M.ITEM_CODE join MAGAM mg on a.cust_code=mg.cust_code join PARTNER_ERP_TEST3.nx.cm_m_cust C on A.CUST_CODE=C.CUST_CODE
 WHERE {dc} AND A.MAINT_TAG IN ('5')
UNION ALL
SELECT A.MAINT_YMD, A.MAINT_SEQ, A.CUST_CODE, C.CUST_DESC, C.CUST_TYPE,
  A.ITEM_CODE, '', (SELECT CUST_DESC FROM PARTNER_ERP_TEST3.nx.CM_M_CUST WHERE CUST_CODE=M.IN_CUST_CODE),
  M.ITEM_LGROUP, M.ITEM_SGROUP, M.ITEM_WEIGHT, M.UNIT, M.ITEM_DESC, M.ITEM_SPEC,
  -A.MAINT_QTY, 'KRW', 1.0, A.MAINT_COST, A.MAINT_COST, -A.MAINT_AMT, -A.MAINT_AMT, -A.MAINT_VAT
 FROM PARTNER_ERP_TEST3.nx.SA_T_STOCK_MAINT A JOIN PARTNER_ERP_TEST3.nx.pr_m_item M ON A.ITEM_CODE=M.ITEM_CODE join MAGAM mg on a.cust_code=mg.cust_code join PARTNER_ERP_TEST3.nx.cm_m_cust C on A.CUST_CODE=C.CUST_CODE
 WHERE {dc} AND A.MAINT_TAG IN ('5')
UNION ALL
SELECT A.MAINT_YMD, A.MAINT_SEQ, A.CUST_CODE, C.CUST_DESC, C.CUST_TYPE,
  A.MAT_CODE, A.ITEM_CODE, (SELECT CUST_DESC FROM PARTNER_ERP_TEST3.nx.CM_M_CUST WHERE CUST_CODE=M.IN_CUST_CODE),
  M.ITEM_LGROUP, M.ITEM_SGROUP, M.ITEM_WEIGHT, M.UNIT, M.ITEM_DESC, M.ITEM_SPEC,
  A.MAINT_QTY, A.CURRENCY, A.EXCHANGE_RATE, A.MAINT_COST, A.MAINT_COST*A.EXCHANGE_RATE, A.MAINT_AMT, A.TAXPAYERS, 0
 FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT_C A JOIN PARTNER_ERP_TEST3.nx.pr_m_item M ON A.MAT_CODE=M.ITEM_CODE join MAGAM mg on a.cust_code=mg.cust_code join PARTNER_ERP_TEST3.nx.cm_m_cust C on A.CUST_CODE=C.CUST_CODE
 WHERE {dc} AND A.DIVISION='Q'"""
    _cols, rows = _rows(sql)
    return rows

@live_router.get("/dispatchdetail")
def dispatchdetail(gijun: str = Query("close"), ym: str = Query(""), dfrom: str = Query(""), dto: str = Query(""), source: str = Query("live")):
    """자재불출명세서. 기본 source=live(현행 무변경). source=nx면 stock_ledger(MAT) 파생(원장 재고, 명세shape 아님). gijun=close/issue."""
    if gijun == "issue":
        f, t = _def_range(dfrom, dto)
        if source == "nx":
            r = _nx_screen("MAT", f, t); r["gijun"] = "issue"; return r
        ref = t[:4]
        dc = f"A.MAINT_YMD between '{f}' and '{t}'"
        rows = _dispatchdetail(dc, ref)
        return {"gijun": "issue", "dfrom": f, "dto": t, "count": len(rows), "rows": rows}
    else:
        y = _ym4(ym) or _scalar("SELECT FORMAT(GETDATE(),'yyMM')")
        if source == "nx":
            r = _nx_screen("MAT", y + "01", y + "31"); r["gijun"] = "close"; r["ym"] = y; return r
        dc = f"A.MAINT_YMD > mg.jun_yymm+mg.jun_magam_day AND A.MAINT_YMD <= '{y}'+mg.magam_day"
        rows = _dispatchdetail(dc, y)
        return {"gijun": "close", "ym": y, "count": len(rows), "rows": rows}

# ================= 자재입출고현황 (구매/자재, dw_pu_stock_060) — 마스터-디테일 =================
# 자재창고(Z99990/IS0001) 당월 입출고 상세라인 + 전월이월. patch_060full.py 이식, 월 파라미터화.
def _prev_ym(ym):
    yy, mm = int(ym[:2]), int(ym[2:4])
    return f"{(yy-1):02d}12" if mm == 1 else f"{yy:02d}{(mm-1):02d}"

def _matinout(from6, to6, stock_cust="Z99990", part_wh="IS0001", q=""):
    # ★레거시 dw_pu_stock_060_wh: 재고창고(stock_cust)·파트창고(part_wh) + 기간(from6~to6 YYMMDD).
    # 전기이월 = from6 직전월말 스냅샷 + from6 이전 무브. 기간 무브 = [from6, to6]. → 임의기간 재고 정확.
    sc = "".join(ch for ch in str(stock_cust or "Z99990") if ch.isalnum()) or "Z99990"
    pw = "".join(ch for ch in str(part_wh or "IS0001") if ch.isalnum()) or "IS0001"
    y01, y99 = from6, to6
    pv = _prev_ym(from6[:4]); pv99 = pv + "99"
    INSP = "NOT(ISNULL(a.insp_flag,'N') IN ('S','F') AND ISNULL(a.insp_proc_flag,'0')<>'1')"
    W = f"ISNULL(a.wh_cust_code,'Z99990')='{sc}' AND ISNULL(a.gagong_proc_code,'')='{pw}'"
    CUST = "ISNULL((SELECT cust_desc FROM PARTNER_ERP_TEST3.nx.cm_m_cust m WHERE m.cust_code=a.cust_code),'')"
    # ★품번(자도번/품명) 스코프: 입력 시 서버 WHERE로 밀어 해당 품목만 스캔(기간 무관 빠름).
    #   자도번/품명을 pr_m_item에서 코드셋으로 해석 → 인덱스 seek(IN). 미해석시 mat_code LIKE 폴백.
    #   CI 콜레이션 전제(코드 대소문자 무시). 미입력이면 빈 문자열 = 기존 전체조회 무변경.
    MFmat = MFitem = ""
    q = (q or "").strip()
    if q:
        qe = q.replace("'", "''")
        _cf, _mr = _rows(f"SELECT UPPER(item_code) c FROM PARTNER_ERP_TEST3.nx.pr_m_item WHERE item_code LIKE '%{qe}%' OR item_desc LIKE '%{qe}%'")
        _codes = [r["c"] for r in _mr if r.get("c")]
        if _codes:
            _inl = ",".join("'" + c.replace("'", "''") + "'" for c in _codes)
            MFmat = f" AND a.mat_code IN ({_inl})"
            MFitem = f" AND a.item_code IN ({_inl})"
        else:
            MFmat = f" AND a.mat_code LIKE '%{qe}%'"
            MFitem = f" AND a.item_code LIKE '%{qe}%'"
    LINES = f"""
 SELECT UPPER(a.mat_code) mat, a.maint_ymd ymd, a.maint_qty inq,CAST(0 AS decimal(18,4)) outq,CAST(0 AS decimal(18,4)) etc,CAST(0 AS decimal(18,4)) mv,
   CASE a.maint_tag WHEN '3' THEN '기초재고' WHEN '9' THEN '자재창고입고' WHEN 'C' THEN IIF(a.maint_qty>0,'가공이동입고','가공이동취소') WHEN 'G' THEN '축관입고' WHEN 'H' THEN '가공입고' WHEN 'S' THEN '세트입고' WHEN 'P' THEN '생산'+IIF(a.maint_qty<0,'취소','') WHEN 'R' THEN '반품' ELSE '' END div, {CUST} cust, a.work_order wo
  FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_tag IN ('3','9','C','G','H','S','P','R') AND a.maint_qty<>0 AND {INSP} AND {W}{MFmat}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_ymd, a.maint_qty,0,0,0,'도입-구매',{CUST},a.work_order FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint_c a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_qty<>0 AND a.wh_cust_code='{sc}' AND a.part_code='{pw}' AND a.division='P'{MFmat}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_ymd, a.maint_qty*-1,0,0,0,'생산창고반품',{CUST},a.work_order FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_tag IN ('T') AND a.maint_qty<>0 AND {INSP} AND {W}{MFmat}
 UNION ALL SELECT UPPER(a.mat_code), a.cut_ymd, a.cut_qty,0,0,0,'자재창고입고','작업처 : 제조1팀',NULL FROM pu_t_cut_dtl a WHERE a.cut_ymd>='{y01}' AND a.cut_ymd<='{y99}' AND a.cut_qty<>0 AND {W}{MFmat}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_ymd, 0,0,a.maint_qty,0,'재고조정',{CUST},a.work_order FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_tag='2' AND a.maint_qty<>0 AND {W}{MFmat}
 UNION ALL SELECT UPPER(a.item_code), a.move_ymd, 0,0,0, CASE WHEN a.to_cust_code='{sc}' AND a.to_gagong_proc_code='{pw}' THEN a.move_qty ELSE 0 END,'창고재고입고',ISNULL((SELECT cust_desc FROM PARTNER_ERP_TEST3.nx.cm_m_cust m WHERE m.cust_code=CASE WHEN a.to_cust_code='{sc}' THEN a.fr_cust_code ELSE a.to_cust_code END),''),'' FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MOVE a WHERE a.move_ymd>='{y01}' AND a.move_ymd<='{y99}' AND a.move_qty<>0 AND a.to_cust_code='{sc}' AND a.to_gagong_proc_code='{pw}'{MFitem}
 UNION ALL SELECT UPPER(a.item_code), a.move_ymd, 0,0,0, CASE WHEN a.fr_cust_code='{sc}' AND a.fr_gagong_proc_code='{pw}' THEN a.move_qty*-1 ELSE 0 END,'창고재고출고',ISNULL((SELECT cust_desc FROM PARTNER_ERP_TEST3.nx.cm_m_cust m WHERE m.cust_code=CASE WHEN a.to_cust_code='{sc}' THEN a.fr_cust_code ELSE a.to_cust_code END),''),'' FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MOVE a WHERE a.move_ymd>='{y01}' AND a.move_ymd<='{y99}' AND a.move_qty<>0 AND a.fr_cust_code='{sc}' AND a.fr_gagong_proc_code='{pw}'{MFitem}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_ymd, 0, a.maint_qty*-1,0,0,
   CASE a.maint_tag WHEN '1' THEN '불량' WHEN '4' THEN '생산사용'+IIF(a.maint_qty>0,'취소','') WHEN '5' THEN '협력업체판매' WHEN '6' THEN '일반간판출하' WHEN '8' THEN '라인무상공급' WHEN 'A' THEN '개발불출' WHEN 'B' THEN IIF(a.out_wh_gubun='1','생산창고출고','영업창고출고') WHEN 'J' THEN '출하'+IIF(a.maint_qty>0,'취소','') ELSE '' END,
   ISNULL((SELECT cust_desc FROM PARTNER_ERP_TEST3.nx.cm_m_cust m WHERE m.cust_code=a.cust_code AND a.cust_code<>'{sc}'),''), a.work_order
  FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_tag IN ('1','4','5','6','8','A','B','J') AND a.maint_qty<>0 AND {W}{MFmat}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_ymd, 0, a.maint_qty,0,0,'도입-판매',{CUST},a.work_order FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint_c a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_qty<>0 AND a.wh_cust_code='{sc}' AND a.part_code='{pw}' AND a.division='Q'{MFmat}
"""
    BF = f"""
 SELECT UPPER(a.mat_code) mat, a.stock_qty sq FROM PARTNER_ERP_TEST3.nx.pu_t_month_stock_wh a WHERE a.stock_yymm='{pv}' AND a.cust_code='{sc}' AND ISNULL(a.gagong_proc_code,'')='{pw}'{MFmat}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_qty FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE a.maint_ymd>'{pv99}' AND a.maint_ymd<'{y01}' AND a.maint_tag IN ('3','9','C','G','H','S','P','R') AND {INSP} AND {W}{MFmat}
 UNION ALL SELECT UPPER(a.mat_code), IIF(a.division='Q',-a.maint_qty,a.maint_qty) FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint_c a WHERE a.maint_ymd>'{pv99}' AND a.maint_ymd<'{y01}' AND a.wh_cust_code='{sc}' AND a.part_code='{pw}'{MFmat}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_qty*-1 FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE a.maint_ymd>'{pv99}' AND a.maint_ymd<'{y01}' AND a.maint_tag IN ('T') AND {INSP} AND {W}{MFmat}
 UNION ALL SELECT UPPER(a.mat_code), a.cut_qty FROM pu_t_cut_dtl a WHERE a.cut_ymd>'{pv99}' AND a.cut_ymd<'{y01}' AND {W}{MFmat}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_qty FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE a.maint_ymd>'{pv99}' AND a.maint_ymd<'{y01}' AND a.maint_tag='2' AND {W}{MFmat}
 UNION ALL SELECT UPPER(a.item_code), (CASE WHEN a.fr_cust_code='{sc}' AND a.fr_gagong_proc_code='{pw}' THEN a.move_qty*-1 ELSE 0 END)+(CASE WHEN a.to_cust_code='{sc}' AND a.to_gagong_proc_code='{pw}' THEN a.move_qty ELSE 0 END) FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MOVE a WHERE a.move_ymd>'{pv99}' AND a.move_ymd<'{y01}' AND ('{sc}' IN (a.fr_cust_code,a.to_cust_code)) AND ('{pw}' IN (a.fr_gagong_proc_code,a.to_gagong_proc_code)){MFitem}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_qty FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE a.maint_ymd>'{pv99}' AND a.maint_ymd<'{y01}' AND a.maint_tag IN ('1','4','5','6','8','A','B','J') AND {W}{MFmat}
"""
    _c1, moves = _rows(f"SELECT mat, ymd, inq i, outq o, etc e, mv, div, cust, ISNULL(wo,'') wo FROM ({LINES}) x")
    _c2, bfrows = _rows(f"SELECT mat, SUM(sq) bf FROM ({BF}) b GROUP BY mat")
    _c3, nmrows = _rows("SELECT UPPER(item_code) c, item_desc d FROM PARTNER_ERP_TEST3.nx.pr_m_item")
    nm = {r["c"]: r["d"] for r in nmrows}
    bfm = {r["mat"]: float(r["bf"] or 0) for r in bfrows}
    net, lastin = {}, {}
    for r in moves:
        m = r["mat"]
        net[m] = net.get(m, 0) + (float(r["i"] or 0) - float(r["o"] or 0) + float(r["e"] or 0) + float(r["mv"] or 0))
        if float(r["i"] or 0) > 0:
            y = str(r["ymd"] or "")
            if y > lastin.get(m, ""):
                lastin[m] = y
    mats = set(bfm) | set(net)
    stock = []
    for m in sorted(mats):
        bf = bfm.get(m, 0); st = bf + net.get(m, 0)
        stock.append({"mat": m, "nm": nm.get(m, ""), "stock": round(st, 4), "bf": round(bf, 4), "lastin": lastin.get(m, ""), "part": pw})
    return stock, moves

@live_router.get("/matinout")
def matinout(from_ymd: str = Query(""), to_ymd: str = Query(""), stock_cust: str = Query("Z99990"), part_wh: str = Query("IS0001"), q: str = Query(""), source: str = Query("live")):
    """자재 입출고현황. 기본 source=live(현행 무변경). source=nx면 stock_ledger(MAT) 파생. 기간 from_ymd~to_ymd(YYMMDD).
    q(자도번/품명) 입력 시 서버 WHERE로 스코프 → 해당 품목만 조회(기간 길어도 빠름)."""
    to6 = _digits(to_ymd, 6) or _scalar("SELECT FORMAT(GETDATE(),'yyMMdd')")
    from6 = _digits(from_ymd, 6) or (to6[:4] + "01")
    if from6 > to6:
        from6, to6 = to6, from6
    if source == "nx":
        return _nx_screen("MAT", from6, to6)
    stock, moves = _matinout(from6, to6, stock_cust, part_wh, q)
    return {"from_ymd": from6, "to_ymd": to6, "stock": stock, "moves": moves, "stock_cust": stock_cust, "part_wh": part_wh, "q": q}

# ================= 자재출고관리 (구매/자재, w_pu_stock_150 / dw_pu_stock_150) — 자재개별출고 조회 =================
# ★레거시 정본: PU_T_STOCK_MAINT WHERE MAINT_TAG='B'(자재개별출고=파트출고/생산투입 이동전표) + 기간.
#   13컬럼(출고일자/SEQ/FROM파트창고/P·N/TO창고구분/TO파트창고/자도번/출고수량(=maint_qty*-1)/출고단가/출고금액/비고/작업자/작업일시).
#   현재고/집계는 서버 SUM·COUNT(전체 매칭 대상)로 계산 → 500 cap 부분합 문제 제거.
def _qesc(s):
    return str(s or "").replace("'", "''")

@live_router.get("/stockissue")
def stockissue_view(from_ymd: str = Query(""), to_ymd: str = Query(""), pn: str = Query(""),
                    mat: str = Query(""), out_wh: str = Query(""), to_wh: str = Query(""),
                    from_wh: str = Query(""), page: int = Query(1), size: int = Query(2000)):
    """자재출고관리 라이브 조회(레거시 w_pu_stock_150, PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT MAINT_TAG='B'). 서버 집계(건수·수량합)+페이징."""
    t6 = _digits(to_ymd, 6) or _scalar("SELECT FORMAT(GETDATE(),'yyMMdd')")
    f6 = _digits(from_ymd, 6) or t6
    if f6 > t6:
        f6, t6 = t6, f6
    W = ["a.maint_tag='B'", f"a.maint_ymd BETWEEN '{f6}' AND '{t6}'"]
    if pn.strip():      W.append(f"a.item_code LIKE '%{_qesc(pn.strip())}%'")
    if mat.strip():     W.append(f"a.mat_code LIKE '%{_qesc(mat.strip())}%'")
    if out_wh in ("1", "2"): W.append(f"ISNULL(a.out_wh_gubun,'')='{out_wh}'")
    if to_wh.strip():   W.append(f"a.to_gagong_proc_code='{_qesc(to_wh.strip())}'")
    if from_wh.strip(): W.append(f"a.gagong_proc_code='{_qesc(from_wh.strip())}'")
    WH = " AND ".join(W)
    PW = f"a.maint_tag='B' AND a.maint_ymd BETWEEN '{f6}' AND '{t6}'"   # 드롭다운 옵션용(기간만)
    _c, agg = _rows(f"SELECT COUNT(*) cnt, ISNULL(SUM(a.maint_qty*-1),0) qty FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE {WH}")
    tot = agg[0] if agg else {"cnt": 0, "qty": 0}
    sz = max(1, min(int(size or 2000), 10000)); off = max(0, (int(page or 1) - 1)) * sz
    sql = f"""
      SELECT a.maint_ymd ymd, a.maint_seq seq,
        ISNULL((SELECT gagong_proc_desc FROM PARTNER_ERP_TEST3.nx.pr_m_proc_gagong g WHERE g.gagong_proc_code=a.gagong_proc_code),a.gagong_proc_code) from_wh,
        a.item_code pn, ISNULL((SELECT item_desc FROM PARTNER_ERP_TEST3.nx.pr_m_item i WHERE i.item_code=a.item_code),'') pn_nm,
        CASE ISNULL(a.out_wh_gubun,'') WHEN '1' THEN '생산창고' WHEN '2' THEN '영업창고' ELSE '' END out_wh_nm,
        ISNULL((SELECT gagong_proc_desc FROM PARTNER_ERP_TEST3.nx.pr_m_proc_gagong g WHERE g.gagong_proc_code=a.to_gagong_proc_code),a.to_gagong_proc_code) to_wh,
        a.mat_code mat, (a.maint_qty*-1) qty, ISNULL(a.maint_cost,0) cost, ISNULL(a.maint_amt,0) amt, ISNULL(a.remarks,'') remarks,
        ISNULL((SELECT user_name FROM cm_m_users_info u WHERE u.user_id=a.update_user_id),a.update_user_id) usr, a.update_datetime dt
      FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE {WH}
      ORDER BY a.maint_ymd DESC, a.maint_seq ASC
      OFFSET {off} ROWS FETCH NEXT {sz} ROWS ONLY"""
    _c2, rows = _rows(sql)
    _c3, fw = _rows(f"SELECT DISTINCT a.gagong_proc_code code, ISNULL((SELECT gagong_proc_desc FROM PARTNER_ERP_TEST3.nx.pr_m_proc_gagong g WHERE g.gagong_proc_code=a.gagong_proc_code),a.gagong_proc_code) nm FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE {PW} AND a.gagong_proc_code>'' ORDER BY 2")
    _c4, tw = _rows(f"SELECT DISTINCT a.to_gagong_proc_code code, ISNULL((SELECT gagong_proc_desc FROM PARTNER_ERP_TEST3.nx.pr_m_proc_gagong g WHERE g.gagong_proc_code=a.to_gagong_proc_code),a.to_gagong_proc_code) nm FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE {PW} AND a.to_gagong_proc_code>'' ORDER BY 2")
    cnt = int(tot["cnt"] or 0)
    return {"from_ymd": f6, "to_ymd": t6, "rows": rows, "total_cnt": cnt, "total_qty": float(tot["qty"] or 0),
            "page": int(page or 1), "size": sz, "pages": (cnt + sz - 1) // sz if cnt else 1,
            "from_whs": fw, "to_whs": tw}

# ================= 생산입출고현황 (생산, dw_pr_stock_460) — 파트×자도번 마스터-디테일 =================
# 유니버스=pr_t_mat_stock_wh(part,mat), BF=2502마감+2502~당월 이동(생산월마감이 2502에 멈춤=고정base), 당월=[ym01,ym99].
# patch_460c.py 이식, FR/BFT만 월 파라미터화(2502 base 고정).
def _prodinout(ym):
    y01, y99 = ym + "01", ym + "99"
    INSP = "NOT(ISNULL(a.insp_flag,'N') IN ('S','F') AND ISNULL(a.insp_proc_flag,'0')<>'1')"
    CUST = "ISNULL((SELECT cust_desc FROM PARTNER_ERP_TEST3.nx.cm_m_cust m WHERE m.cust_code=a.cust_code),'')"
    CUR = f"""
 SELECT a.TO_GAGONG_PROC_CODE part, UPPER(a.mat_code) mat, a.maint_ymd ymd, a.maint_qty*-1 inq,CAST(0 AS decimal(18,4)) outq,CAST(0 AS decimal(18,4)) etc,'생산창고입고' div, {CUST} tag
   FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_tag='B' AND ISNULL(a.out_wh_gubun,'1')='1' AND a.maint_qty<>0 AND {INSP} AND a.TO_GAGONG_PROC_CODE>''
 UNION ALL SELECT a.gagong_proc_code, UPPER(a.mat_code), a.cut_ymd, a.cut_qty,0,0,'가공생산입고','제조1팀' FROM pu_t_cut_dtl a WHERE a.cut_ymd>='{y01}' AND a.cut_ymd<='{y99}' AND a.cut_qty<>0 AND a.gagong_proc_code>''
 UNION ALL SELECT a.TO_GAGONG_PROC_CODE, UPPER(a.mat_code), a.maint_ymd, 0, a.maint_qty*-1,0,'자재창고반품',{CUST} FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_tag='T' AND ISNULL(a.out_wh_gubun,'3')='3' AND a.maint_qty<>0 AND a.TO_GAGONG_PROC_CODE>''
 UNION ALL SELECT a.TO_GAGONG_PROC_CODE, UPPER(a.mat_code), a.maint_ymd, 0, a.maint_qty,0,'가공부품이동',{CUST} FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_tag='C' AND a.maint_qty<>0 AND a.TO_GAGONG_PROC_CODE>''
 UNION ALL SELECT a.STOCK_PART_CODE, UPPER(a.item_code), a.prod_ymd, a.prod_qty,0,0,'SUB생산실적','' FROM PARTNER_ERP_TEST3.nx.pr_t_prod_dtl a WHERE a.prod_ymd>='{y01}' AND a.prod_ymd<='{y99}' AND a.STOCK_PART_CODE>'' AND NOT EXISTS(SELECT 1 FROM PARTNER_ERP_TEST3.nx.sa_t_stock_maint s WHERE s.maint_ymd=a.prod_ymd AND s.item_code=a.item_code AND s.in_part_code=a.stock_part_code)
 UNION ALL SELECT a.IN_PART_CODE, UPPER(a.item_code), a.maint_ymd, a.maint_qty,0,0,'생산실적',{CUST} FROM PARTNER_ERP_TEST3.nx.sa_t_stock_maint a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.IN_PART_CODE>''
 UNION ALL SELECT a.part_code, UPPER(a.mat_code), a.maint_ymd, a.maint_qty,0,0,'기초재고',{CUST} FROM PARTNER_ERP_TEST3.nx.PR_T_STOCK_MAINT_MAT a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.part_code>'' AND a.maint_tag='3' AND a.maint_qty<>0
 UNION ALL SELECT a.part_code, UPPER(a.mat_code), a.maint_ymd, 0,0,a.maint_qty,'재고조정',{CUST} FROM PARTNER_ERP_TEST3.nx.PR_T_STOCK_MAINT_MAT a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.part_code>'' AND a.maint_tag IN ('2','1') AND a.maint_qty<>0
 UNION ALL SELECT a.part_code, UPPER(a.mat_code), a.maint_ymd, 0, a.maint_qty*-1,0,'생산사용',{CUST} FROM PARTNER_ERP_TEST3.nx.PR_T_STOCK_MAINT_MAT a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.part_code>'' AND a.maint_tag='4' AND a.maint_qty<>0
"""
    BFT = f"'{y01}'"
    BF = f"""
 SELECT a.gagong_proc_code part, UPPER(a.mat_code) mat, a.stock_qty sq FROM PARTNER_ERP_TEST3.nx.PR_T_MONTH_STOCK_WH a WHERE a.stock_yymm='2502'
 UNION ALL SELECT a.TO_GAGONG_PROC_CODE, UPPER(a.mat_code), a.maint_qty*-1 FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT a WHERE a.maint_ymd>'250299' AND a.maint_ymd<{BFT} AND a.maint_tag='B' AND ISNULL(a.out_wh_gubun,'1')='1' AND {INSP} AND a.TO_GAGONG_PROC_CODE>''
 UNION ALL SELECT a.STOCK_PART_CODE, UPPER(a.item_code), a.prod_qty FROM PARTNER_ERP_TEST3.nx.pr_t_prod_dtl a WHERE a.prod_ymd>'250299' AND a.prod_ymd<{BFT} AND a.STOCK_PART_CODE>'' AND NOT EXISTS(SELECT 1 FROM PARTNER_ERP_TEST3.nx.sa_t_stock_maint s WHERE s.maint_ymd=a.prod_ymd AND s.item_code=a.item_code AND s.in_part_code=a.stock_part_code)
 UNION ALL SELECT a.IN_PART_CODE, UPPER(a.item_code), a.MAINT_QTY FROM PARTNER_ERP_TEST3.nx.sa_t_stock_maint a WHERE a.maint_ymd>'250299' AND a.maint_ymd<{BFT} AND a.IN_PART_CODE>''
 UNION ALL SELECT a.gagong_proc_code, UPPER(a.mat_code), a.cut_qty FROM pu_t_cut_dtl a WHERE a.cut_ymd>'250299' AND a.cut_ymd<{BFT} AND a.gagong_proc_code>'' AND a.cut_qty<>0
 UNION ALL SELECT a.PART_CODE, UPPER(a.MAT_CODE), a.MAINT_QTY FROM PARTNER_ERP_TEST3.nx.PR_T_STOCK_MAINT_MAT a WHERE a.MAINT_YMD>'250299' AND a.MAINT_YMD<{BFT} AND a.PART_CODE>'' AND a.MAINT_TAG IN ('3','2','1')
 UNION ALL SELECT a.PART_CODE, UPPER(a.MAT_CODE), a.MAINT_QTY FROM PARTNER_ERP_TEST3.nx.PR_T_STOCK_MAINT_MAT a WHERE a.MAINT_YMD>'250299' AND a.MAINT_YMD<{BFT} AND a.PART_CODE>'' AND a.MAINT_TAG='4'
 UNION ALL SELECT a.TO_GAGONG_PROC_CODE, UPPER(a.mat_code), a.MAINT_QTY FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT a WHERE a.MAINT_YMD>'250299' AND a.MAINT_YMD<{BFT} AND a.maint_tag='T' AND a.TO_GAGONG_PROC_CODE>''
 UNION ALL SELECT a.TO_GAGONG_PROC_CODE, UPPER(a.mat_code), a.MAINT_QTY*-1 FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT a WHERE a.MAINT_YMD>'250299' AND a.MAINT_YMD<{BFT} AND a.maint_tag='C' AND a.TO_GAGONG_PROC_CODE>''
"""
    _c1, uni = _rows("SELECT part_code part, UPPER(mat_code) mat, SUM(stock_qty) snap FROM PARTNER_ERP_TEST3.nx.pr_t_mat_stock_wh GROUP BY part_code, UPPER(mat_code)")
    _c2, bfrows = _rows(f"SELECT part, mat, SUM(sq) bf FROM ({BF}) b GROUP BY part, mat")
    _c3, moves = _rows(f"SELECT part, mat, ymd, inq, outq, etc, div, tag FROM ({CUR}) x")
    _c4, itrows = _rows("SELECT UPPER(item_code) mat, item_desc, item_spec, item_sgroup FROM cm_m_item")
    _c5, sgrows = _rows("SELECT DETAIL_CODE cd, REPLACE(REPLACE(DETAIL_DESC,CHAR(13),''),CHAR(10),'') nm FROM PARTNER_ERP_TEST3.nx.CM_M_MASTER_DETAIL WHERE KIND_CODE='PR006'")
    _c6, pnrows = _rows("SELECT gagong_proc_code code, gagong_proc_desc nm FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG")
    im = {r["mat"]: r for r in itrows}
    sgm = {str(r["cd"]).strip(): str(r["nm"]).strip() for r in sgrows}
    bfm = {(r["part"], r["mat"]): float(r["bf"] or 0) for r in bfrows}
    net = {}
    for r in moves:
        k = (r["part"], r["mat"])
        net[k] = net.get(k, 0) + (float(r["inq"] or 0) - float(r["outq"] or 0) + float(r["etc"] or 0))
    stock = []
    for u in uni:
        k = (u["part"], u["mat"]); bf = bfm.get(k, 0); st = bf + net.get(k, 0)
        if abs(st) <= 0.0001:
            continue
        it = im.get(u["mat"], {}); sg = str(it.get("item_sgroup") or "").strip()
        stock.append([u["part"], u["mat"], (it.get("item_desc") or ""), (it.get("item_spec") or ""),
                      sgm.get(sg, sg), round(st, 3), round(bf, 3)])
    keys = {r[0] + "||" + r[1] for r in stock}
    mv = {}
    for r in moves:
        k = str(r["part"]) + "||" + str(r["mat"])
        if k in keys:
            mv.setdefault(k, []).append([r["ymd"], round(float(r["inq"] or 0), 3), round(float(r["outq"] or 0), 3),
                                         round(float(r["etc"] or 0), 3), r["div"], (r["tag"] or "").strip()])
    partNames = {str(r["code"]).strip(): str(r["nm"]).strip() for r in pnrows}
    stock.sort(key=lambda r: (r[0], r[2], r[1]))
    return stock, mv, partNames

@live_router.get("/prodinout")
def prodinout(ym: str = Query(""), source: str = Query("live")):
    """생산입출고현황. 기본 source=live(현행 무변경). source=nx면 stock_ledger(PRD) 파생(컷오버 전 빈데이터 사유표시). ym=YYMM."""
    y = _ym4(ym) or _scalar("SELECT FORMAT(GETDATE(),'yyMM')")
    if source == "nx":
        r = _nx_screen("PRD", y + "01", y + "31"); r["ym"] = y; return r
    stock, moves, partNames = _prodinout(y)
    return {"ym": y, "stock": stock, "moves": moves, "partNames": partNames}

# ================= 제품입출고현황 (영업, dw_pr_stock_110) — 제품(P/N) 마스터-디테일 =================
# 유니버스=SA_T_ITEM_STOCK, BF=2502마감+2502~당월(고정base), 당월=[ym01,ym99]. patch_110.py 이식.
def _prodinvout(ym):
    y01, y99 = ym + "01", ym + "99"
    CUST = "ISNULL((SELECT cust_desc FROM PARTNER_ERP_TEST3.nx.cm_m_cust m WHERE m.cust_code=a.cust_code),'')"
    BF = f"""
 SELECT UPPER(item_code) item, stock_qty q FROM PARTNER_ERP_TEST3.nx.sa_t_month_stock WHERE stock_yymm='2502'
 UNION ALL SELECT UPPER(item_code), MAINT_QTY FROM PARTNER_ERP_TEST3.nx.sa_t_stock_maint WHERE MAINT_YMD>'250299' AND maint_ymd<'{y01}' AND maint_tag IN ('B','V','J','2','8','R')
 UNION ALL SELECT UPPER(item_code), MAINT_QTY FROM PARTNER_ERP_TEST3.nx.sa_t_stock_maint WHERE MAINT_YMD>'250299' AND maint_ymd<'{y01}' AND maint_tag='P' AND ISNULL(IN_PART_CODE,'')=''
 UNION ALL SELECT UPPER(mat_code), maint_qty*-1 FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint WHERE maint_ymd>'250299' AND maint_ymd<'{y01}' AND ISNULL(out_wh_gubun,'1')='2'
"""
    L1 = f"""
 SELECT UPPER(a.item_code) item, a.maint_ymd ymd, a.maint_qty inq, CAST(0 AS decimal(18,4)) outq, CAST(0 AS decimal(18,4)) etc, CASE a.maint_tag WHEN 'V' THEN '세트출하' WHEN 'P' THEN '생산완료' ELSE '입고' END div, {CUST} cust FROM PARTNER_ERP_TEST3.nx.sa_t_stock_maint a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_tag IN ('B','V') AND a.maint_qty<>0
 UNION ALL SELECT UPPER(a.item_code), a.maint_ymd, a.maint_qty,0,0,'생산완료', {CUST} FROM PARTNER_ERP_TEST3.nx.sa_t_stock_maint a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_tag='P' AND ISNULL(a.in_part_code,'')='' AND a.maint_qty<>0
 UNION ALL SELECT UPPER(a.mat_code), a.maint_ymd, a.maint_qty*-1,0,0,'자재창고에서입고', {CUST} FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND ISNULL(a.out_wh_gubun,'1')='2'
 UNION ALL SELECT UPPER(a.item_code), a.maint_ymd, 0, a.maint_qty*-1,0, CASE a.maint_tag WHEN '8' THEN '무상공급' WHEN 'R' THEN '출하반품' ELSE '출하' END, {CUST} FROM PARTNER_ERP_TEST3.nx.sa_t_stock_maint a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_tag IN ('J','8','R') AND a.maint_qty<>0
 UNION ALL SELECT UPPER(a.item_code), a.maint_ymd, 0,0, a.maint_qty*-1,'재고조정', {CUST} FROM PARTNER_ERP_TEST3.nx.sa_t_stock_maint a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_tag='2' AND a.maint_qty<>0
"""
    _c1, uni = _rows("SELECT UPPER(item_code) item, SUM(stock_qty) snap FROM PARTNER_ERP_TEST3.nx.SA_T_ITEM_STOCK GROUP BY UPPER(item_code)")
    _c2, bfrows = _rows(f"SELECT item, SUM(q) bf FROM ({BF}) t GROUP BY item")
    _c3, moves = _rows(f"SELECT item, ymd, inq, outq, etc, div, cust FROM ({L1}) x")
    _c4, inforows = _rows("""SELECT UPPER(item_code) item, item_desc, (SELECT cust_desc FROM PARTNER_ERP_TEST3.nx.cm_m_cust c WHERE c.cust_code=i.in_cust_code) work_nm FROM PARTNER_ERP_TEST3.nx.pr_m_item i""")
    info = {r["item"]: r for r in inforows}
    bfm = {r["item"]: float(r["bf"] or 0) for r in bfrows}
    net = {}
    for r in moves:  # 재고 = 기초+입고-출고-기타출고(etc=maint_qty*-1 → 빼기)
        it = r["item"]
        net[it] = net.get(it, 0) + (float(r["inq"] or 0) - float(r["outq"] or 0) - float(r["etc"] or 0))
    stock = []
    for u in uni:
        it = u["item"]; bf = bfm.get(it, 0); stv = bf + net.get(it, 0)
        if abs(stv) <= 0.0001:
            continue
        d = info.get(it, {})
        stock.append([it, (d.get("item_desc") or ""), (d.get("work_nm") or ""), round(stv, 3), round(bf, 3)])
    keys = {r[0] for r in stock}
    mv = {}
    for r in moves:
        it = r["item"]
        if it in keys:
            mv.setdefault(it, []).append([r["ymd"], round(float(r["inq"] or 0), 3), round(float(r["outq"] or 0), 3),
                                          round(float(r["etc"] or 0), 3), r["div"], (r["cust"] or "").strip()])
    stock.sort(key=lambda r: (r[2], r[0]))
    return stock, mv

@live_router.get("/prodinvout")
def prodinvout(ym: str = Query(""), source: str = Query("live")):
    """제품입출고현황. 기본 source=live(현행 무변경). source=nx면 stock_ledger(ASY) 파생(컷오버 전 빈데이터 사유표시). ym=YYMM."""
    y = _ym4(ym) or _scalar("SELECT FORMAT(GETDATE(),'yyMM')")
    if source == "nx":
        r = _nx_screen("ASY", y + "01", y + "31"); r["ym"] = y; return r
    stock, moves = _prodinvout(y)
    return {"ym": y, "stock": stock, "moves": moves}

# ================= 출하실적현황 (영업, dw_sa_list_010) — 라인단위 =================
@live_router.get("/shipment")
def shipment(dfrom: str = Query(""), dto: str = Query("")):
    """출하실적현황 라이브(라인). dfrom~dto=YYMMDD(미지정시 당월1일~오늘). patch_shipment.py 이식."""
    f, t = _def_range(dfrom, dto)
    sql = f"""
SELECT a.SALE_YMD ymd, a.WORK_ORDER wo, a.SPLIT_WORK_ORDER swo, a.ITEM_CODE item,
  a.SALE_QTY qty, a.SALE_COST cost, a.SALE_AMT amt,
  ISNULL((SELECT TOP 1 item_cost FROM PARTNER_ERP_TEST3.nx.pr_m_item_cost WHERE item_code=a.item_code AND cost_apply_ymd<=a.sale_ymd AND cost_tag='S' AND cust_code IN ('1010','1020') ORDER BY cost_apply_ymd DESC),0) mcost,
  a.SALE_USER_ID usr, a.SALE_HMS hms,
  CASE WHEN m.work_code>'' THEN (SELECT work_desc FROM PARTNER_ERP_TEST3.nx.pr_m_work WHERE work_code=m.work_code)
       ELSE (SELECT cust_desc FROM PARTNER_ERP_TEST3.nx.cm_m_cust WHERE cust_code=m.in_cust_code) END wc,
  m.item_desc nm, pi.REMARKS remarks
FROM PARTNER_ERP_TEST3.nx.sa_t_sale_dtl a JOIN PARTNER_ERP_TEST3.nx.pr_m_item m ON a.item_code=m.item_code
 OUTER APPLY (SELECT TOP 1 REMARKS FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_INPUT WHERE WORK_ORDER=a.WORK_ORDER) pi
WHERE a.sale_ymd BETWEEN '{f}' AND '{t}'
"""
    _c, rows = _rows(sql)
    return {"dfrom": f, "dto": t, "count": len(rows), "rows": rows}

# ================= 제품재고조회 (영업, dw_pr_stock_040) — 제품수불 플랫 =================
# 기초(2502+~기간전)+입고-출고-기타출고=재고. export_web_data.py _S040 이식, 기간 파라미터화(base 2502 고정).
@live_router.get("/salesstock")
def salesstock(dfrom: str = Query(""), dto: str = Query(""), source: str = Query("live")):
    """제품재고조회. 기본 source=live(현행 무변경). source=nx면 stock_ledger(ASY) 파생(컷오버 전 빈데이터 사유표시). dfrom~dto=YYMMDD."""
    f, t = _def_range(dfrom, dto)
    if source == "nx":
        return _nx_screen("ASY", f, t)
    S040 = f"""
select /*생산입고*/ UPPER(a.item_code) mat,0 basic,a.maint_qty inq,0 outq,0 etc
  from PARTNER_ERP_TEST3.nx.sa_t_stock_maint a
 where a.maint_ymd between '{f}' and '{t}' and a.maint_tag='P' and a.maint_qty<>0 and ISNULL(a.in_part_code,'')=''
union all
select UPPER(a.item_code),0,a.maint_qty,0,0 from PARTNER_ERP_TEST3.nx.sa_t_stock_maint a
 where a.maint_ymd between '{f}' and '{t}' and a.maint_tag in ('B','V') and a.maint_qty<>0
union all
select /*직납 자재입고*/ UPPER(a.mat_code),0,a.maint_qty*-1,0,0 from PARTNER_ERP_TEST3.nx.pu_t_stock_maint a
 where a.maint_ymd between '{f}' and '{t}' and isnull(a.out_wh_gubun,'1')='2'
union all
select /*창고출하*/ UPPER(a.item_code),0,0,a.maint_qty*-1,0 from PARTNER_ERP_TEST3.nx.sa_t_stock_maint a
 where a.maint_ymd between '{f}' and '{t}' and a.maint_tag in ('J','8','R') and a.maint_qty<>0
union all
select /*재고조정*/ UPPER(a.item_code),0,0,0,a.maint_qty*-1 from PARTNER_ERP_TEST3.nx.sa_t_stock_maint a
 where a.maint_ymd between '{f}' and '{t}' and a.maint_tag='2' and a.maint_qty<>0
union all
select /*월기초*/ item_code,stock_qty,0,0,0 from PARTNER_ERP_TEST3.nx.sa_t_month_stock where stock_yymm='2502'
union all
select /*이전 생산*/ item_code,maint_qty,0,0,0 from PARTNER_ERP_TEST3.nx.sa_t_stock_maint
 where maint_ymd>'250299' and maint_ymd<'{f}' and maint_tag='P' and ISNULL(in_part_code,'')=''
union all
select item_code,maint_qty,0,0,0 from PARTNER_ERP_TEST3.nx.sa_t_stock_maint
 where maint_ymd>'250299' and maint_ymd<'{f}' and maint_tag in ('B','V','J','2','R')
union all
select UPPER(a.mat_code),a.maint_qty*-1,0,0,0 from PARTNER_ERP_TEST3.nx.pu_t_stock_maint a
 where a.maint_ymd>'250299' and a.maint_ymd<'{f}' and isnull(a.out_wh_gubun,'1')='2'
"""
    sql = f"""
;WITH t AS ({S040})
SELECT t.mat cd, max(m.item_desc) nm, max(m.item_spec) spec, max(m.item_class) cls,
   sum(t.basic) basic, sum(t.inq) inq, sum(t.outq) outq, sum(t.etc) adj,
   sum(t.basic+t.inq-t.etc-t.outq) qty,
   (select top 1 item_cost from PARTNER_ERP_TEST3.nx.pr_m_item_cost where item_code=t.mat and cost_apply_ymd<='{t}' and cost_tag in ('S','E') order by cost_apply_ymd desc) cost,
   case when max(m.work_code)>'' then (select work_desc from PARTNER_ERP_TEST3.nx.pr_m_work where work_code=max(m.work_code))
        else (select cust_desc from PARTNER_ERP_TEST3.nx.cm_m_cust where cust_code=max(m.in_cust_code)) end wc
FROM t JOIN PARTNER_ERP_TEST3.nx.pr_m_item m ON t.mat=m.item_code
GROUP BY t.mat
"""
    _c, rows = _rows(sql)
    out = []
    for r in rows:
        q = float(r["qty"] or 0)
        if abs(q) <= 0.0001:
            continue
        cost = float(r["cost"] or 0)
        r["amt"] = round(q * cost)
        r["qty"] = q
        out.append(r)
    out.sort(key=lambda r: -abs(r.get("amt") or 0))
    return {"dfrom": f, "dto": t, "count": len(out), "rows": out}

# ================= LG리시빙관리 (영업, dw_sa_sale_110) — 도번×일자 피벗 =================
@live_router.get("/lgrecv")
def lgrecv(ym: str = Query(""), fr: str = Query(""), to: str = Query("")):
    """LG리시빙관리 라이브. ★기간조회: fr~to(YYMMDD). 미지정시 ym(YYMM) 월전체 또는 당월01~오늘.
    셀=item×mkt×일자(d=YYMMDD 전체날짜, 월경계 대응), items=작업처·동소요량. patch_lgrecv.py 이식."""
    fr6 = _digits(fr, 6); to6 = _digits(to, 6)
    if not fr6 or not to6:
        y = _ym4(ym) or _scalar("SELECT FORMAT(GETDATE(),'yyMM')")
        fr6 = fr6 or (y + "01")
        to6 = to6 or _scalar("SELECT FORMAT(GETDATE(),'yyMMdd')")
        if to6 < fr6:
            to6 = y + "31"
    _c1, cells = _rows(f"""
SELECT a.item_code item, ISNULL(a.mkt,'') mkt, a.receiving_ymd d,
  SUM(a.recv_qty) q, SUM(a.recv_amt) amt
FROM sa_t_lg_receiving_dtl a
WHERE a.receiving_ymd BETWEEN '{fr6}' AND '{to6}'
GROUP BY a.item_code, ISNULL(a.mkt,''), a.receiving_ymd""")
    _c2, items = _rows(f"""
SELECT m.item_code item,
  CASE WHEN m.work_code>'' THEN m.work_code ELSE m.in_cust_code END wcc,
  CASE WHEN m.work_code>'' THEN (SELECT work_desc FROM PARTNER_ERP_TEST3.nx.pr_m_work WHERE work_code=m.work_code)
       ELSE (SELECT cust_desc FROM PARTNER_ERP_TEST3.nx.cm_m_cust WHERE cust_code=m.in_cust_code) END wc
FROM PARTNER_ERP_TEST3.nx.pr_m_item m
WHERE m.item_code IN (SELECT DISTINCT item_code FROM sa_t_lg_receiving_dtl WHERE receiving_ymd BETWEEN '{fr6}' AND '{to6}')""")
    return {"fr": fr6, "to": to6, "ym": fr6[:4], "cells": cells, "items": items}

# ================= 생산재고조회 (생산, dw_pr_stock_040/480) — 가공(P0001)/용접(그외) 라인재고 =================
# 원장 9-union(2502기초+당월이동), 라인별 집계. export_web_data.py prodStock 이식, 레거시 pr_m_item 조인.
def _prodstock(ym):
    y01, y99 = ym + "01", ym + "99"
    U = f"""
SELECT a.gagong_proc_code gpc, A.MAT_CODE mat, A.STOCK_QTY basic,0 inq,0 outq,0 etc FROM PARTNER_ERP_TEST3.nx.PR_T_MONTH_STOCK_WH A WHERE A.STOCK_YYMM='2502'
UNION ALL SELECT a.to_gagong_proc_code,A.MAT_CODE,iif(a.maint_ymd<'{y01}',-A.MAINT_QTY,0),iif(a.maint_ymd<'{y01}',0,-A.MAINT_QTY),0,0 FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{y99}' AND a.maint_tag='B' AND isnull(a.out_wh_gubun,'1')='1'
UNION ALL SELECT A.gagong_proc_code,a.mat_code,iif(a.cut_ymd<'{y01}',a.cut_QTY,0),iif(a.cut_ymd<'{y01}',0,a.cut_QTY),0,0 FROM pu_t_cut_dtl a WHERE A.cut_ymd>'250299' and A.cut_ymd<='{y99}'
UNION ALL SELECT a.to_gagong_proc_code,A.MAT_CODE,iif(a.MAINT_YMD<'{y01}',a.MAINT_QTY,0),0,iif(a.MAINT_YMD<'{y01}',0,-a.MAINT_QTY),0 FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{y99}' AND a.maint_tag='T' and isnull(a.out_wh_gubun,'3')='3'
UNION ALL SELECT a.to_gagong_proc_code,A.MAT_CODE,iif(a.MAINT_YMD<'{y01}',-a.MAINT_QTY,0),0,iif(a.MAINT_YMD<'{y01}',0,a.MAINT_QTY),0 FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{y99}' AND a.maint_tag='C'
UNION ALL SELECT A.stock_part_code,a.item_code,iif(a.prod_ymd<'{y01}',a.prod_qty,0),iif(a.prod_ymd<'{y01}',0,a.prod_qty),0,0 FROM PARTNER_ERP_TEST3.nx.pr_t_prod_dtl a WHERE A.prod_ymd>'250299' and A.prod_ymd<='{y99}' and a.stock_part_code>'' and not exists (select 1 from PARTNER_ERP_TEST3.nx.sa_t_stock_maint where maint_ymd=a.prod_ymd and item_code=a.item_code and in_part_code=a.stock_part_code)
UNION ALL SELECT A.IN_PART_CODE,a.item_code,iif(a.MAINT_YMD<'{y01}',a.MAINT_QTY,0),iif(a.MAINT_YMD<'{y01}',0,a.MAINT_QTY),0,0 FROM PARTNER_ERP_TEST3.nx.sa_t_stock_maint a WHERE A.maint_ymd>'250299' and A.MAINT_YMD<='{y99}' and a.in_part_code>''
UNION ALL SELECT A.PART_CODE,A.MAT_CODE,iif(a.MAINT_YMD<'{y01}',a.MAINT_QTY,0),iif(a.MAINT_YMD<'{y01}',0,a.MAINT_QTY),0,0 FROM PARTNER_ERP_TEST3.nx.PR_T_STOCK_MAINT_MAT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{y99}' AND A.MAINT_TAG='3'
UNION ALL SELECT A.PART_CODE,A.MAT_CODE,iif(a.MAINT_YMD<'{y01}',a.MAINT_QTY,0),0,0,iif(a.MAINT_YMD<'{y01}',0,a.MAINT_QTY) FROM PARTNER_ERP_TEST3.nx.PR_T_STOCK_MAINT_MAT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{y99}' AND A.MAINT_TAG in ('2','1')
UNION ALL SELECT A.PART_CODE,A.MAT_CODE,iif(a.MAINT_YMD<'{y01}',a.MAINT_QTY,0),0,iif(a.MAINT_YMD<'{y01}',0,-a.MAINT_QTY),0 FROM PARTNER_ERP_TEST3.nx.PR_T_STOCK_MAINT_MAT A JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{y99}' AND A.MAINT_TAG='4'
"""
    C2 = f"(select top 1 q.item_cost from PARTNER_ERP_TEST3.nx.pr_m_item_cost q where q.item_code=agg.mat and q.cost_tag='1' and q.cost_apply_ymd<='{y01}' and q.cust_code=case when pi.work_code='P2' then '2228' else pi.in_cust_code end order by q.cost_apply_ymd desc)"
    sql = f"""
;WITH agg AS (
  SELECT LTRIM(RTRIM(t.mat)) mat, ISNULL(LTRIM(RTRIM(t.gpc)),'') line,
     SUM(basic) basic, SUM(inq) inq, SUM(outq) outq, SUM(etc) adj,
     SUM(basic)+SUM(inq)-SUM(outq)+SUM(etc) qty
  FROM ({U}) t GROUP BY LTRIM(RTRIM(t.mat)), ISNULL(LTRIM(RTRIM(t.gpc)),'')
  HAVING (SUM(basic)<>0 OR SUM(inq)<>0 OR SUM(outq)<>0 OR SUM(etc)<>0)
)
SELECT CASE WHEN agg.line='P0001' THEN 'GAGONG' ELSE 'WELD' END stage,
  CASE WHEN agg.line='P0001' THEN '' ELSE agg.line END loc,
  agg.mat cd, pi.item_desc nm, ISNULL(pi.item_class,'') type,
  agg.basic, agg.inq, agg.outq, agg.adj, agg.qty,
  {C2} cost, CAST(ROUND(agg.qty*ISNULL({C2},0),0) AS DECIMAL(18,0)) amt
FROM agg JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM pi ON pi.item_code=agg.mat
"""
    _c, rows = _rows(sql)
    return rows

@live_router.get("/prodstock")
def prodstock(ym: str = Query(""), source: str = Query("live")):
    """생산재고조회. 기본 source=live(현행 무변경). source=nx면 stock_ledger(PRD) 파생(컷오버 전 빈데이터 사유표시). ym=YYMM."""
    y = _ym4(ym) or _scalar("SELECT FORMAT(GETDATE(),'yyMM')")
    if source == "nx":
        r = _nx_screen("PRD", y + "01", y + "31"); r["ym"] = y; return r
    rows = _prodstock(y)
    return {"ym": y, "rows": rows}

# ================= ★Phase5: nx 파생 vs 라이브 대조 (diff 리포트) =================
@live_router.get("/nxcompare")
def nxcompare(point: str = Query("MAT"), ym: str = Query(""), ymd: str = Query("")):
    """nx 원장 파생 vs 라이브 재고 대조(근사). ymd=YYMMDD 우선, 없으면 ym=YYMM 월말.
    ★정직: nx MAT = PU_T_STOCK_MAINT 스냅샷(ymd>=260401) 재적재분만 → 라이브(cut_dtl·이동·월기초 포함)와 부분대조. PRD/ASY는 nx 미적재(0)."""
    to6 = _digits(ymd, 6) or ((_ym4(ym) or _scalar("SELECT FORMAT(GETDATE(),'yyMM')")) + "31")
    nx = _nx_rows("""SELECT ISNULL(SUM(MAINT_QTY),0) t, COUNT(DISTINCT COALESCE(NULLIF(MAT_CODE,''),ITEM_CODE)) c
        FROM nx.stock_ledger WHERE STOCK_POINT=? AND MAINT_YMD<=?""", point, to6)
    nx_t = round(float(nx[0]["t"] or 0), 3); nx_c = int(nx[0]["c"] or 0)
    live_t, live_c, note = None, None, ""
    if point == "MAT":
        key = _digits(ymd, 6) or (to6[:4] + "31")
        # 라이브 일수불 최신 스냅샷(<=기준일) 재고합
        d = _rows("SELECT MAX(STOCK_YMD) mx FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH_DAILY WHERE cust_code='Z99990' AND STOCK_YMD<=?", key)
        mx = d[1][0]["mx"] if d[1] else None
        if mx:
            lv = _rows("SELECT ISNULL(SUM(stock_qty),0) t, COUNT(DISTINCT mat_code) c FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH_DAILY WHERE cust_code='Z99990' AND STOCK_YMD=?", mx)[1]
            live_t = round(float(lv[0]["t"] or 0), 3); live_c = int(lv[0]["c"] or 0)
        note = "nx MAT=PU_T_STOCK_MAINT 스냅샷(ymd>=260401) 부분 — 라이브(자재창고 전체수불)와 범위차 존재(정상). 부호/추이 대조용."
    else:
        note = _NX_POINT_NOTE.get(point, "") or "nx 미적재 도메인(컷오버 backfill 전) — 라이브 기본."
    return {"point": point, "asof": to6, "nx_total": nx_t, "nx_items": nx_c,
            "live_total": live_t, "live_items": live_c,
            "diff_total": (round(nx_t - live_t, 3) if live_t is not None else None), "note": note}

# ================= 마감관리 현황 (시스템, 도메인별 최종 마감 라이브) =================
@live_router.get("/closestatus")
def closestatus():
    """도메인별 실제 최종 마감월/일을 라이브 조회. 마감 실행/취소(쓰기)는 마감엔진 별도."""
    def mx(sql):
        try: return _scalar(sql)
        except Exception: return None
    rows = [
        {"domain": "자재(일마감)", "name": "자재재고(일)", "ctype": "일", "tbl": "PU_T_MONTH_STOCK_WH_DAILY",
         "last": mx("SELECT MAX(STOCK_YMD) FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH_DAILY WHERE cust_code='Z99990'")},
        {"domain": "자재(월마감)", "name": "자재재고", "ctype": "월", "tbl": "PU_T_MONTH_STOCK_WH",
         "last": mx("SELECT MAX(STOCK_YYMM) FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH WHERE cust_code='Z99990'")},
        {"domain": "생산(월마감)", "name": "생산 파트재고", "ctype": "월", "tbl": "PR_T_MONTH_STOCK_WH",
         "last": mx("SELECT MAX(STOCK_YYMM) FROM PARTNER_ERP_TEST3.nx.PR_T_MONTH_STOCK_WH")},
        {"domain": "영업제품(월마감)", "name": "영업 제품재고", "ctype": "월", "tbl": "SA_T_MONTH_STOCK",
         "last": mx("SELECT MAX(STOCK_YYMM) FROM PARTNER_ERP_TEST3.nx.SA_T_MONTH_STOCK")},
    ]
    return {"rows": rows, "asof": _scalar("SELECT FORMAT(GETDATE(),'yyMMdd')"), "curym": _scalar("SELECT FORMAT(GETDATE(),'yyMM')")}
