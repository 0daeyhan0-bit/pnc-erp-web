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
        COALESCE(NULLIF(L.MAT_CODE,''),L.ITEM_CODE) cd, MAX(i.item_name) nm, MAX(i.ITEM_SPEC) spec,
        ISNULL(L.GAGONG_PROC_CODE,'') gpc, ISNULL(L.CUST_CODE,'') cust,
        SUM(CASE WHEN L.MAINT_YMD<? THEN L.MAINT_QTY ELSE 0 END) base,
        SUM(CASE WHEN L.MAINT_YMD BETWEEN ? AND ? AND L.MAINT_QTY>0 THEN L.MAINT_QTY ELSE 0 END) inq,
        SUM(CASE WHEN L.MAINT_YMD BETWEEN ? AND ? AND L.MAINT_QTY<0 THEN -L.MAINT_QTY ELSE 0 END) outq,
        SUM(CASE WHEN L.MAINT_YMD<=? THEN L.MAINT_QTY ELSE 0 END) endq
      FROM nx.stock_ledger L
      LEFT JOIN PARTNER_ERP_TEST3.nx.item i ON i.ITEM_CODE=COALESCE(NULLIF(L.MAT_CODE,''),L.ITEM_CODE)
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
select t.mat_code cd, max(M.item_name) nm, max(m.item_spec) spec,
  isnull(max(M.sgroup),'') sg, max(m.unit) unit,
  isnull(max(M.in_cust),'') custcd, isnull(max(c.cust_desc),'') cust, isnull(max(c.cust_type),'') ctype,
  {lastin} lastin,
  sum(t.basic_qty) bq,  sum(t.basic_amt) ba,
  sum(t.input_qty) iq,  sum(t.input_amt) ia,
  sum(t.output_qty) oq, sum(t.output_amt) oa,
  sum(t.trans_qty) tq,  sum(t.trans_amt) ta,
  sum(t.stock_qty) sq,  sum(t.stock_amt) sa
from {tbl} t
join PARTNER_ERP_TEST3.nx.item m on t.mat_code=m.item_code
join PARTNER_ERP_TEST3.nx.pr_m_proc_gagong g on t.gagong_proc_code=g.gagong_proc_code
left join PARTNER_ERP_TEST3.nx.cm_m_cust c on M.in_cust=c.cust_code
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

# ================= 자재 일마감(이동평균) — 우리 교정 nx.mat_stock_daily 조회 =================
# 기초=레거시 2606 월말 픽스 → 우리 이동평균 로직 일별 전개(수입환율·마이너스재고가드·tagP 반영).
# 매입(9,S,도입P)=평균갱신 / 이동·반품·가공·출고·조정=현재평균 불변. 소모품(sgroup 99%) 제외.
def _ymd6(s, default=None):
    k = (s or "").replace("-", "").strip()
    if len(k) == 8: k = k[2:]      # YYYYMMDD → YYMMDD
    return k or default

@live_router.get("/matclose/dates")
def matclose_dates():
    """우리 일마감(nx.mat_stock_daily) 가용 일자 범위."""
    lo = _scalar("SELECT MIN(ymd) FROM PARTNER_ERP_TEST3.nx.mat_stock_daily")
    hi = _scalar("SELECT MAX(ymd) FROM PARTNER_ERP_TEST3.nx.mat_stock_daily")
    return {"min": lo, "max": hi}

@live_router.get("/matclose")
def matclose(dfrom: str = Query(""), dto: str = Query("")):
    """자재 수불장(우리 이동평균). 기간 [dfrom,dto]: 기초(직전잔량)+Σ입고−Σ출고=기말. 품목별."""
    # ★기본 To는 '오늘'까지로 캡 — 다음달 이월 등 미래일자 전표로 MAX(ymd)가 미래여도 기본 조회기간이 미래로 튀지 않게.
    #   dto를 직접 지정하면 그 값을 존중(미래 이월도 원하면 조회 가능). fr은 to에서 파생되어 자동 교정됨.
    hi = _scalar("SELECT MAX(ymd) FROM PARTNER_ERP_TEST3.nx.mat_stock_daily WHERE ymd <= CONVERT(varchar(6), GETDATE(), 12)")
    to = _ymd6(dto, hi)
    fr = _ymd6(dfrom, to[:4] + "01")   # 미지정시 해당월 1일
    sql = """
    ;WITH per AS (
      SELECT UPPER(mat_code) cd, SUM(in_qty) iq, SUM(in_amt) ia, SUM(out_qty) oq, SUM(out_amt) oa
      FROM PARTNER_ERP_TEST3.nx.mat_stock_daily WHERE ymd BETWEEN ? AND ? GROUP BY UPPER(mat_code)),
    endd AS (
      SELECT cd, sq, sa, avg FROM (
        SELECT UPPER(mat_code) cd, stock_qty sq, stock_amt sa, avg_cost avg,
          ROW_NUMBER() OVER(PARTITION BY UPPER(mat_code) ORDER BY ymd DESC) rn
        FROM PARTNER_ERP_TEST3.nx.mat_stock_daily WHERE ymd <= ?) x WHERE rn=1),
    beg AS (
      SELECT cd, sq, sa FROM (
        SELECT UPPER(mat_code) cd, stock_qty sq, stock_amt sa,
          ROW_NUMBER() OVER(PARTITION BY UPPER(mat_code) ORDER BY ymd DESC) rn
        FROM PARTNER_ERP_TEST3.nx.mat_stock_daily WHERE ymd < ?) x WHERE rn=1),
    keys AS (SELECT cd FROM per UNION SELECT cd FROM endd UNION SELECT cd FROM beg)
    SELECT k.cd,
      MAX(M.item_name) nm, MAX(m.item_spec) spec, MAX(m.unit) unit,
      MAX(ISNULL(i.sgroup,'')) sg, MAX(ISNULL(sd.DETAIL_DESC,'')) sgnm, MAX(ISNULL(i.cut_gubun,'')) cut,
      MAX(ISNULL(b.sq,0)) bq, MAX(ISNULL(b.sa,0)) ba,
      MAX(ISNULL(p.iq,0)) iq, MAX(ISNULL(p.ia,0)) ia,
      MAX(ISNULL(p.oq,0)) oq, MAX(ISNULL(p.oa,0)) oa,
      MAX(ISNULL(e.sq,0)) sq, MAX(ISNULL(e.sa,0)) sa, MAX(ISNULL(e.avg,0)) avg
    FROM keys k
    LEFT JOIN per p ON p.cd=k.cd
    LEFT JOIN endd e ON e.cd=k.cd
    LEFT JOIN beg b ON b.cd=k.cd
    LEFT JOIN PARTNER_ERP_TEST3.nx.item m ON UPPER(m.item_code)=k.cd
    LEFT JOIN PARTNER_ERP_TEST3.nx.item i ON UPPER(i.item_code)=k.cd
    LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_MASTER_DETAIL sd ON sd.KIND_CODE='PR006' AND sd.DETAIL_CODE=i.sgroup
    GROUP BY k.cd ORDER BY k.cd
    """
    rows = _nx_rows(sql, fr, to, to, fr)
    return {"dfrom": fr, "dto": to, "count": len(rows), "rows": rows}

@live_router.get("/matclose/ledger")
def matclose_ledger(mat: str = Query(...), dfrom: str = Query(""), dto: str = Query("")):
    """단일 품목 일별 수불추이(우리 이동평균)."""
    hi = _scalar("SELECT MAX(ymd) FROM PARTNER_ERP_TEST3.nx.mat_stock_daily")
    to = _ymd6(dto, hi); fr = _ymd6(dfrom, to[:4] + "01")
    sql = """SELECT ymd, in_qty iq, in_amt ia, out_qty oq, out_amt oa,
        stock_qty sq, avg_cost avg, stock_amt sa
      FROM PARTNER_ERP_TEST3.nx.mat_stock_daily WHERE UPPER(mat_code)=? AND ymd BETWEEN ? AND ? ORDER BY ymd"""
    rows = _nx_rows(sql, mat.upper(), fr, to)
    return {"mat": mat.upper(), "dfrom": fr, "dto": to, "count": len(rows), "rows": rows}

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

def _dispatch_inner(dc, dc5=None):
    dc5 = dc5 or dc   # ★tag5(판매출고)만 매출마감 override(SALE) 적용. 반품(SA·MAT_CODE없음)·수입(Q)은 원 dc 유지.
    return f"""
   SELECT A.CUST_CODE, MAX(C2.CUST_DESC) CUST_DESC, C2.CUST_TYPE, A.MAT_CODE, A.MAINT_COST, A.MAINT_COST KRW_MAINT_COST, A.ITEM_CODE,
     MAX(M.item_name) ITEM_DESC, MAX(M.ITEM_SPEC) ITEM_SPEC, MAX(M.UNIT) UNIT, M.lgroup ITEM_LGROUP, M.sgroup ITEM_SGROUP,
     SUM(-A.MAINT_QTY) MAINT_QTY, SUM(-A.MAINT_AMT) MAINT_AMT, SUM(-A.MAINT_AMT) KRW_MAINT_AMT, SUM(-A.MAINT_VAT) MAINT_VAT, SUM(-A.MAINT_VAT) KRW_MAINT_VAT,
     1 EXCHANGE_RATE, MAX(M.in_cust) IN_CUST_CODE, 'KRW' CURRENCY, MAX(M.ITEM_WEIGHT) ITEM_WEIGHT
    FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT A JOIN PARTNER_ERP_TEST3.nx.item M ON A.MAT_CODE=M.ITEM_CODE JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST C2 ON A.CUST_CODE=C2.CUST_CODE join MAGAM mg on a.cust_code=mg.cust_code
    WHERE {dc5} AND A.MAINT_TAG IN ('5')
    GROUP BY A.CUST_CODE,A.MAINT_TAG,A.GAGONG_PROC_CODE,A.MAT_CODE,A.ITEM_CODE,C2.CUST_TYPE,A.MAINT_COST,M.lgroup,M.sgroup
   UNION ALL
   SELECT A.CUST_CODE, MAX(C2.CUST_DESC), C2.CUST_TYPE, A.ITEM_CODE, A.MAINT_COST, A.MAINT_COST, '',
     MAX(M.item_name), MAX(M.ITEM_SPEC), MAX(M.UNIT), M.lgroup, M.sgroup,
     SUM(-A.MAINT_QTY), SUM(-A.MAINT_AMT), SUM(-A.MAINT_AMT), SUM(-A.MAINT_VAT), SUM(-A.MAINT_VAT), 1, MAX(M.in_cust), 'KRW', MAX(M.ITEM_WEIGHT)
    FROM PARTNER_ERP_TEST3.nx.SA_T_STOCK_MAINT A JOIN PARTNER_ERP_TEST3.nx.item M ON A.ITEM_CODE=M.ITEM_CODE JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST C2 ON A.CUST_CODE=C2.CUST_CODE join MAGAM mg on a.cust_code=mg.cust_code
    WHERE {dc} AND A.MAINT_TAG IN ('R')
    GROUP BY A.CUST_CODE,A.MAINT_TAG,A.ITEM_CODE,A.MAINT_COST,C2.CUST_TYPE,M.lgroup,M.sgroup
   UNION ALL
   SELECT A.CUST_CODE, MAX(C2.CUST_DESC), C2.CUST_TYPE, A.MAT_CODE, A.MAINT_COST, (A.MAINT_COST*A.EXCHANGE_RATE), A.ITEM_CODE,
     MAX(M.item_name), MAX(M.ITEM_SPEC), MAX(M.UNIT), M.lgroup, M.sgroup,
     SUM(A.MAINT_QTY), SUM(A.MAINT_AMT), SUM(ROUND(A.MAINT_AMT*A.EXCHANGE_RATE,0,1)), 0, 0, A.EXCHANGE_RATE, MAX(M.in_cust), A.CURRENCY, MAX(M.ITEM_WEIGHT)
    FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT_C A JOIN PARTNER_ERP_TEST3.nx.item M ON A.MAT_CODE=M.ITEM_CODE JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST C2 ON A.CUST_CODE=C2.CUST_CODE join MAGAM mg on a.cust_code=mg.cust_code
    WHERE {dc} AND A.DIVISION='Q'
    GROUP BY A.CUST_CODE,A.MAINT_TAG,A.MAT_CODE,A.ITEM_CODE,A.MAINT_COST,C2.CUST_TYPE,A.EXCHANGE_RATE,M.lgroup,M.sgroup,A.CURRENCY"""

def _dispatch(dc, ref_ym, dc5=None):
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
    FROM ({_dispatch_inner(dc, dc5)}) T
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
        dc = f"A.MAINT_YMD > mg.jun_yymm+mg.jun_magam_day AND A.MAINT_YMD <= '{y}'+mg.magam_day"   # 반품(SA)·수입(Q)=원 마감창
        rows = _dispatch(dc, y, _win_ovr('SALE', y))   # ★tag5(판매출고)만 매출마감 수동이월(SALE) 반영
        return {"gijun": "close", "ym": y, "count": len(rows), "rows": rows}

# ★마감창 + 수동 이월(nx.magam_carry_ovr) 반영 — 마감 프로그램(매입=PUR/매출=SALE)의 이월/해제를 집계표·일일현황에도 동일 적용.
#   효과: 거래의 유효 귀속월==y(=마감창 자연판정 ± override). override 0건이면 원 마감창과 완전 동일(diff0).
#   ★A(대상 테이블)에 MAT_CODE·CUST_CODE·MAINT_YMD 가 있어야 함(SA_T_STOCK_MAINT는 MAT_CODE 없음 → tag5 파트에만 사용).
# _win_ovr = 마감 공용 단일창(common). 집계표·마감목록·일일현황이 같은 창을 쓴다(2026-09-03 통일).
from common import _win_ovr

# ================= 확정입고집계표 (구매/자재, dw_pu_input_120) =================
# 확정입고(검사통과 9/S/C/G/H) + 수입(PU_T_STOCK_MAINT_C DIVISION='P'). grain=(cc,ic,mat). patch_receipt.py 이식.
def _receipt_inner(dc):
    return f"""
  SELECT A.CUST_CODE cc, C.CUST_DESC cnm, C.CUST_TYPE ct, A.ITEM_CODE ic, A.MAT_CODE mat,
    M.item_name nm, M.ITEM_SPEC spec, M.lgroup lg, M.sgroup sg, M.ITEM_WEIGHT wt, M.UNIT unit,
    'KRW' cur, 1.0 rate, A.MAINT_COST cost, A.MAINT_COST kcost,
    A.MAINT_QTY qty, A.MAINT_AMT amt, A.MAINT_AMT kamt, A.MAINT_VAT vat, A.MAINT_VAT kvat
   FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT (nolock) A JOIN PARTNER_ERP_TEST3.nx.item (nolock) M ON A.MAT_CODE=M.ITEM_CODE JOIN PARTNER_ERP_TEST3.nx.cm_m_cust (nolock) C ON A.CUST_CODE=C.CUST_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
   WHERE {dc} AND A.MAINT_TAG IN ('9','S','C','G','H')
     AND ((ISNULL(A.INSP_FLAG,'N') IN ('','N')) OR (ISNULL(A.INSP_FLAG,'N') IN ('S','F') AND A.INSP_PROC_YMD >= ''))
  UNION ALL
  SELECT A.CUST_CODE, C.CUST_DESC, C.CUST_TYPE, A.ITEM_CODE, A.MAT_CODE,
    M.item_name, M.ITEM_SPEC, M.lgroup, M.sgroup, M.ITEM_WEIGHT, M.UNIT,
    A.CURRENCY, A.EXCHANGE_RATE, A.MAINT_COST, A.MAINT_COST*A.EXCHANGE_RATE,
    A.MAINT_QTY, A.MAINT_AMT, ROUND(A.MAINT_AMT*A.EXCHANGE_RATE,0,1), 0, 0
   FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT_C (nolock) A JOIN PARTNER_ERP_TEST3.nx.item (nolock) M ON A.MAT_CODE=M.ITEM_CODE JOIN PARTNER_ERP_TEST3.nx.cm_m_cust (nolock) C ON A.CUST_CODE=C.CUST_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
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
        dc = _win_ovr('PUR', y)   # ★마감창 + 매입마감 수동이월(PUR) 반영
        rows = _receipt(dc, y)
        return {"gijun": "close", "ym": y, "count": len(rows), "rows": rows}

# ================= 일일 영업/매입 현황 (경영) ① 매입/불출/실매입 by 구분 =================
_CT_NAME = {'1': '유상사급-부품', '4': '절삭-원자재', '5': '설치-원자재', '6': '절삭-협력사',
            '7': '절삭-부자재', '8': '설치-부자재', '9': '소모품', 'A': '이지링크'}
_GUBUN_ORDER = ['유상사급-원재료', '유상사급-부품', '절삭-원자재', '설치-원자재', '절삭-협력사',
                '절삭-부자재', '설치-부자재', '소모품', '이지링크']
_VGUBUN = None
def _vgubun():
    """거래처→매입구분 오버라이드(사급 원소재 등). nx.mgmt_vendor_gubun. 모듈캐시."""
    global _VGUBUN
    if _VGUBUN is None:
        try:
            _c, rs = _rows("SELECT cust_code, override_gubun FROM PARTNER_ERP_TEST3.nx.mgmt_vendor_gubun")
            _VGUBUN = {str(r['cust_code']).strip(): str(r['override_gubun']).strip() for r in rs}
        except Exception:
            _VGUBUN = {}
    return _VGUBUN

import time as _time
_DPI_CACHE = {}   # dailypurissue: d6 -> (expiry_ts, result). 무거운 재고조정 3쿼리(_prodstock 등) → 날짜별 캐시(재조회 즉시)

@live_router.get("/dailypurissue")
def dailypurissue(date: str = Query(""), frm: str = Query(""), nocache: str = Query("")):
    """일일 영업/매입 현황 ① 매입/불출/실매입 by 구분(CUST_TYPE + 사급원소재 오버라이드).
       date=종료일(YYMMDD·조회일), frm=시작일(YYMMDD, 기본=종료일 달의 1일). 기간=[frm, date].
       누적=시작~전일, 당일=종료일, 총=누적+당일. 기초재고=종료일 달 기준. 금액=공급가(MAINT_AMT, VAT제외).
       ★기간별 결과 캐시(TTL 180초). nocache=1로 강제 재계산."""
    d6 = _digits(date, 6) or _scalar("SELECT FORMAT(GETDATE(),'yyMMdd')")
    ym = d6[:4]
    frm6 = _digits(frm, 6) or (ym + '01')   # 시작일(기본=종료일 달의 1일)
    _now = _time.time()
    _ckey = d6 + '_' + frm6
    if not str(nocache).strip():
        _hit = _DPI_CACHE.get(_ckey)
        if _hit and _hit[0] > _now:
            return _hit[1]
    ov = _vgubun()
    def gb(cc, ct):
        return ov.get(str(cc or '').strip()) or _CT_NAME.get(str(ct or '').strip(), '기타(' + str(ct or '').strip() + ')')
    def agg(rows):
        m = {}
        for r in rows:
            g = gb(r.get('cc'), r.get('ct'))
            m[g] = m.get(g, 0.0) + float(r.get('kamt') or 0)   # ★KRW환산(외화 거래처=원통화 아님). 리포트=금액(KRW)
        return m
    # ★마감창 + 수동이월 반영(집계표와 동일). 매입=PUR override(전 파트 MAT_CODE) · 불출=SALE override는 tag5만(반품SA·수입Q는 원 마감창).
    win = f"A.MAINT_YMD > mg.jun_yymm+mg.jun_magam_day AND A.MAINT_YMD <= '{ym}'+mg.magam_day"   # 원 마감창(반품/수입용)
    winP = _win_ovr('PUR', ym); winS = _win_ovr('SALE', ym)
    _cd = lambda w, op: w + f" AND A.MAINT_YMD {op} '{d6}'"
    pur_cum, pur_day = agg(_receipt(_cd(winP, '<'), ym)), agg(_receipt(_cd(winP, '='), ym))   # 누적=마감창~전일, 당일=종료일
    out_cum, out_day = agg(_dispatch(_cd(win, '<'), ym, _cd(winS, '<'))), agg(_dispatch(_cd(win, '='), ym, _cd(winS, '=')))
    gubuns = list(_GUBUN_ORDER)
    for ex in sorted(set(list(pur_cum) + list(out_cum) + list(pur_day) + list(out_day)) - set(gubuns)):
        gubuns.append(ex)
    def blk(cum, day):
        rows = []
        for g in gubuns:
            c, dd = round(cum.get(g, 0)), round(day.get(g, 0))
            if c or dd: rows.append({"gubun": g, "cum": c, "day": dd, "tot": c + dd})
        return rows
    net_cum = {g: pur_cum.get(g, 0) - out_cum.get(g, 0) for g in gubuns}
    net_day = {g: pur_day.get(g, 0) - out_day.get(g, 0) for g in gubuns}
    pur, out, net = blk(pur_cum, pur_day), blk(out_cum, out_day), blk(net_cum, net_day)
    def tot(rs): return {"cum": sum(r['cum'] for r in rs), "day": sum(r['day'] for r in rs), "tot": sum(r['tot'] for r in rs)}
    pur_t, out_t, net_t = tot(pur), tot(out), tot(net)

    m0 = frm6   # 기간 시작일(기본=종료일 달의 1일). 리시빙/사급/매출요약 집계 시작.
    # ⑤ 현매출 = 리시빙(월초~조회일) × 품목구분(nx.item.cut_gubun). ★LG리시빙관리 소스와 동일: SUM(recv_amt) 그대로(GUBUN C−R 빼지 않음).
    _c, rr = _rows(f"""SELECT ISNULL(i.cut_gubun,'') cg, SUM(ISNULL(r.RECV_AMT,0)) amt
      FROM PARTNER_ERP.dbo.SA_T_LG_RECEIVING_DTL r  -- ★리시빙 기준=라이브(nx미러 stale로 최근입고 누락 → LG리시빙관리와 불일치 수정)
      LEFT JOIN PARTNER_ERP_TEST3.nx.item i ON i.item_code=UPPER(LTRIM(RTRIM(r.ITEM_CODE)))
      WHERE r.RECEIVING_YMD BETWEEN '{m0}' AND '{d6}' GROUP BY ISNULL(i.cut_gubun,'')""")
    cutm = {(r['cg'] or ''): float(r['amt'] or 0) for r in rr}
    hyeon_cut, hyeon_seol = round(cutm.get('절삭', 0)), round(cutm.get('설치', 0))
    hyeon_etc = round(sum(v for k, v in cutm.items() if k not in ('절삭', '설치')))   # 이지링크/분지관/미분류
    lg_sales = hyeon_cut + hyeon_seol + hyeon_etc   # LG매출액=현매출합계=전체 리시빙(원리포트 매출합계와 동일). ②분모.

    # ④ 사급율 원천 = OSP(nx.lg_sagub_actual) 월초~조회일. 원소재(TUBE)/부품.
    _c, ro = _rows(f"""SELECT CASE WHEN UPPER(item_name) LIKE '%TUBE%' THEN 'raw' ELSE 'part' END t,
        SUM(ISNULL(amt,0)) a FROM PARTNER_ERP_TEST3.nx.lg_sagub_actual
      WHERE ym='{ym}' AND ISNULL(ymd,'') BETWEEN '{m0}' AND '{d6}'
      GROUP BY CASE WHEN UPPER(item_name) LIKE '%TUBE%' THEN 'raw' ELSE 'part' END""")
    ospm = {r['t']: float(r['a'] or 0) for r in ro}
    osp_raw, osp_part = round(ospm.get('raw', 0)), round(ospm.get('part', 0))
    pct = lambda a, b: round(a / b * 100, 1) if b else 0.0

    # ③ 재고조정(버킷별) = 조회일 현재고 − 7월말(=조회월초) 기초 = 재고증가분(양수=증가, 음수=감소).
    #    용접/가공(생산 _prodstock stage=WELD/GAGONG)·영업(salesstock)·자재(nx.mat_stock_daily 이동평균 일마감).
    #    생산·영업 기초=2502스냅샷+월초직전무브(=7월말) × 월초원가, 현재고=조회일 수량 × 월초원가. 자재=일별 이동평균.
    #    실재고(조정후) = 실매입 + 재고증가합계.
    # ★재고(기초/기말) = 마감 확정 스냅샷 직독(nx.stock_snapshot). 기초=직전 월마감(월초 기초재고)·기말=조회일 일마감(없으면 직전 일마감).
    #   ★replay 없음=즉시(수불장 ledger는 월전체 재생으로 30초). 일단위 조회=확정 마감값 사용(수불장 runtime과 ~0.4%p 미세차·확정값이 권위적).
    _lc = _nxc(); _lcur = _lc.cursor()
    base_m = cur_m = base_prd = cur_prd = base_s = cur_s = 0
    def _snapsum(dom):
        # 기초 = 직전 월마감(M, period<ym)
        _lcur.execute("""SELECT ISNULL(SUM(stock_amt),0) FROM nx.stock_snapshot
            WHERE domain=? AND ptype='M' AND period=(SELECT MAX(period) FROM nx.stock_snapshot WHERE domain=? AND ptype='M' AND period<?)""", dom, dom, ym)
        b = float(_lcur.fetchone()[0] or 0)
        # 기말 = 조회일 이하 최신 일마감(D, period<=d6). 없으면 기초(변동0).
        _lcur.execute("""SELECT ISNULL(SUM(stock_amt),0) FROM nx.stock_snapshot
            WHERE domain=? AND ptype='D' AND period=(SELECT MAX(period) FROM nx.stock_snapshot WHERE domain=? AND ptype='D' AND period<=?)""", dom, dom, d6)
        e = float(_lcur.fetchone()[0] or 0)
        return round(b), round(e if e else b)
    try: base_m, cur_m = _snapsum('MAT')
    except Exception: pass
    try: base_prd, cur_prd = _snapsum('PRD')
    except Exception: pass
    try: base_s, cur_s = _snapsum('SAL')
    except Exception: pass
    _lc.close()
    jaego = (cur_m + cur_prd + cur_s) - (base_m + base_prd + base_s)   # 재고 증감(참고)
    silrae = net_t['tot'] + jaego   # 실재고(조정후)
    # ★재료비(사용기준) = 원재료매입(매입−불출=실매입) + Σ재고사용(기초−기말). 기말 감소=사용↑. 재고=자재/생산/영업 수불장.
    gicho = base_m + base_prd + base_s   # 기초재고 합계
    gimal = cur_m + cur_prd + cur_s      # 기말재고 합계
    jae_use = gicho - gimal              # 재고 사용(기초−기말)
    jaemat = round(net_t['tot'] + jae_use)      # 재료비 = 실매입(매입−불출) + 재고사용

    # 당사ERP 유상사급 = ①의 유상사급-원재료/부품(확정입고, 총). 원소재·부품 분리(LG사급 대사용).
    dangsa_raw = dangsa_part = 0
    for r in pur:
        if r['gubun'] == '유상사급-원재료': dangsa_raw += r['tot']
        elif r['gubun'] == '유상사급-부품': dangsa_part += r['tot']
    dangsa_sagub = dangsa_raw + dangsa_part
    lg_osp = osp_raw + osp_part   # LG전산(OSP) 총

    # ===== ⑤ 매출요약 (상반기 1~15 / 하반기 16~말 / 합계). 매출=조회일까지 실적(리시빙)+이후~월말 예상(forecast). 원화 =====
    import calendar as _cal
    _yr = 2000 + int(ym[:2]); _mo = int(ym[2:4]); _ld = _cal.monthrange(_yr, _mo)[1]
    eom = ym + ("%02d" % _ld)
    _half = lambda y6: 'H1' if (str(y6)[4:6] <= '15') else 'H2'
    MS = {k: {'H1': 0.0, 'H2': 0.0} for k in ('hyeon_cut', 'hyeon_seol', 'hyeon_etc', 'chuga_cut', 'chuga_seol', 'sagub_raw', 'sagub_raw_fc', 'sagub_part', 'sagub_part_fc', 'naesu')}
    def _madd(k, h, v): MS[k][h] += float(v or 0)
    # 현매출 실적 = 리시빙(월초~조회일) cut별·half별 + 내수(mkt=2)
    _c, _rr5 = _rows(f"""SELECT ISNULL(i.cut_gubun,'') cg, r.RECEIVING_YMD ymd, ISNULL(r.mkt,'') mkt, SUM(ISNULL(r.RECV_AMT,0)) amt
      FROM PARTNER_ERP.dbo.SA_T_LG_RECEIVING_DTL r  -- ★리시빙 기준=라이브(nx미러 stale로 최근입고 누락 → LG리시빙관리와 불일치 수정)
      LEFT JOIN PARTNER_ERP_TEST3.nx.item i ON i.item_code=UPPER(LTRIM(RTRIM(r.ITEM_CODE)))
      WHERE r.RECEIVING_YMD BETWEEN '{m0}' AND '{d6}' GROUP BY ISNULL(i.cut_gubun,''), r.RECEIVING_YMD, ISNULL(r.mkt,'')""")
    for _r in _rr5:
        _cg = (_r['cg'] or '').strip(); _h = _half(_r['ymd']); _a = float(_r['amt'] or 0)
        if _cg == '절삭': _madd('hyeon_cut', _h, _a)
        elif _cg == '설치': _madd('hyeon_seol', _h, _a)
        else: _madd('hyeon_etc', _h, _a)   # 기타(이지링크/분지관/미분류) — LG매출 합계 tie-out
        if str(_r['mkt']).strip() == '2': _madd('naesu', _h, _a)   # 내수(숨김·LG수금 산식용)
    # 다음날~월말 예상 기간
    try:
        from datetime import datetime as _dt5, timedelta as _td5
        _nb = (_dt5.strptime('20' + d6, '%Y%m%d') + _td5(days=1)).strftime('%y%m%d')
    except Exception:
        _nb = d6
    from routers import soyo as _soyo
    # 추가매출 예상 = forecast(다음날~월말) cut별·half별(일자)
    if _nb <= eom:
        try:
            for _g in _soyo.sales_forecast(base=_nb, to=eom).get('rows', []):
                _cg = (_g.get('cut') or '').strip(); _cst = float(_g.get('cost') or 0)
                for _y, _q in (_g.get('ndays') or {}).items():
                    _v = float(_q or 0) * _cst
                    if _cg == '절삭': _madd('chuga_cut', _half(_y), _v)
                    elif _cg == '설치': _madd('chuga_seol', _half(_y), _v)
        except Exception: pass
    # 사급 실적 = OSP(lg_sagub_actual, 월초~조회일) TUBE=원재료/그외=부품·half
    _c, _ro5 = _rows(f"""SELECT CASE WHEN UPPER(item_name) LIKE '%TUBE%' THEN 'raw' ELSE 'part' END t, ISNULL(ymd,'') ymd, SUM(ISNULL(amt,0)) a
      FROM PARTNER_ERP_TEST3.nx.lg_sagub_actual WHERE ym='{ym}' AND ISNULL(ymd,'') BETWEEN '{m0}' AND '{d6}'
      GROUP BY CASE WHEN UPPER(item_name) LIKE '%TUBE%' THEN 'raw' ELSE 'part' END, ISNULL(ymd,'')""")
    for _r in _ro5:
        _h = _half(_r['ymd']) if str(_r['ymd']) else 'H1'
        _madd('sagub_raw' if _r['t'] == 'raw' else 'sagub_part', _h, _r['a'])
    # 사급부품 예상 = forecast_sagub(다음날~월말)·half → sagub_part_fc(실적과 분리).
    if _nb <= eom:
        try:
            for _g in _soyo.sales_forecast_sagub(base=_nb, to=eom).get('rows', []):
                _cst = float(_g.get('cost') or 0)
                for _y, _q in (_g.get('ndays') or {}).items():
                    _madd('sagub_part_fc', _half(_y), float(_q or 0) * _cst)
        except Exception: pass
    # ★사급 원재료 예상(2026-09-01) = forecast(다음날~월말) 완제품×LG BOM 동 사급소요(Assembly Pull)×사급단가(price_metal), half별.
    #   부품예상(sagub_part_fc)과 대칭. 계산엔진=matexpect._rawmat_rows(driver={완제품:수량}) 재사용 → 사급분 amt 합. 실적(sagub_raw=OSP TUBE)과 분리.
    if _nb <= eom:
        _rc = _nxc(); _rcur = _rc.cursor()
        try:
            from routers.matexpect import _rawmat_rows as _rmr
            _drv = {'H1': {}, 'H2': {}}
            for _g in _soyo.sales_forecast(base=_nb, to=eom).get('rows', []):
                _it = _g.get('item')
                if not _it: continue
                for _y, _q in (_g.get('ndays') or {}).items():
                    if _q: _drv[_half(_y)][_it] = _drv[_half(_y)].get(_it, 0.0) + float(_q or 0)
            for _h in ('H1', 'H2'):
                if _drv[_h]:
                    for _rr in _rmr(_rcur, _drv[_h], eom):
                        if (_rr.get('sagub_gubun') or '') == '사급':
                            _madd('sagub_raw_fc', _h, _rr.get('amt') or 0)
        except Exception: pass
        finally:
            _rc.close()
    # 파생행 + LG수금 = (내수−사급예상)×10% + 유상제외(=총매출−사급예상)
    def _r3(d): h1 = round(d['H1']); h2 = round(d['H2']); return {"h1": h1, "h2": h2, "tot": h1 + h2}
    _hyeon_hab = {h: MS['hyeon_cut'][h] + MS['hyeon_seol'][h] + MS['hyeon_etc'][h] for h in ('H1', 'H2')}
    _sagub_part_sum = {h: MS['sagub_part'][h] + MS['sagub_part_fc'][h] for h in ('H1', 'H2')}   # 사급부품 실적+예상
    _sagub_raw_sum = {h: MS['sagub_raw'][h] + MS['sagub_raw_fc'][h] for h in ('H1', 'H2')}       # 사급원재료 실적+예상
    _sagub_hab = {h: _sagub_raw_sum[h] + _sagub_part_sum[h] for h in ('H1', 'H2')}
    _chong = {h: _hyeon_hab[h] + MS['chuga_cut'][h] + MS['chuga_seol'][h] for h in ('H1', 'H2')}   # 총예상매출 = 현매출+추가매출
    _yusang = {h: _chong[h] - _sagub_hab[h] for h in ('H1', 'H2')}   # 유상제외(숨김) = LG매출(총매출)−사급금액
    _lgsu = {h: _chong[h] - _sagub_hab[h] - _sagub_hab[h] * 0.1 + MS['naesu'][h] * 0.1 for h in ('H1', 'H2')}   # ★LG수금 = 총매출 − 사급합계 − 사급합계×10%(사급 부가세) + 내수×10% (2026-09-01 대표 확정·사급VAT 차감 누락 수정)
    maechul = {"hyeon_cut": _r3(MS['hyeon_cut']), "hyeon_seol": _r3(MS['hyeon_seol']), "hyeon_etc": _r3(MS['hyeon_etc']), "hyeon_hab": _r3(_hyeon_hab),
               "chuga_cut": _r3(MS['chuga_cut']), "chuga_seol": _r3(MS['chuga_seol']), "chong": _r3(_chong),
               "sagub_raw": _r3(MS['sagub_raw']), "sagub_raw_fc": _r3(MS['sagub_raw_fc']), "sagub_raw_sum": _r3(_sagub_raw_sum),
               "sagub_part": _r3(MS['sagub_part']), "sagub_part_fc": _r3(MS['sagub_part_fc']),
               "sagub_part_sum": _r3(_sagub_part_sum), "sagub_hab": _r3(_sagub_hab),
               "lg_sugum": _r3(_lgsu)}

    # ⑥ 당일 실적(조회일=d6만): 매출(리시빙 cut별 절삭/설치/기타) + 사급(OSP 원소재=TUBE/부품)
    _c, _rrt = _rows(f"""SELECT ISNULL(i.cut_gubun,'') cg, SUM(ISNULL(r.RECV_AMT,0)) amt
      FROM PARTNER_ERP.dbo.SA_T_LG_RECEIVING_DTL r
      LEFT JOIN PARTNER_ERP_TEST3.nx.item i ON i.item_code=UPPER(LTRIM(RTRIM(r.ITEM_CODE)))
      WHERE r.RECEIVING_YMD='{d6}' GROUP BY ISNULL(i.cut_gubun,'')""")
    _tc = {(r['cg'] or ''): float(r['amt'] or 0) for r in _rrt}
    t_cut, t_seol = round(_tc.get('절삭', 0)), round(_tc.get('설치', 0))
    t_etc = round(sum(v for k, v in _tc.items() if k not in ('절삭', '설치')))
    _c, _rot = _rows(f"""SELECT CASE WHEN UPPER(item_name) LIKE '%TUBE%' THEN 'raw' ELSE 'part' END t, SUM(ISNULL(amt,0)) a
      FROM PARTNER_ERP_TEST3.nx.lg_sagub_actual WHERE ym='{ym}' AND ISNULL(ymd,'')='{d6}'
      GROUP BY CASE WHEN UPPER(item_name) LIKE '%TUBE%' THEN 'raw' ELSE 'part' END""")
    _tsg = {r['t']: float(r['a'] or 0) for r in _rot}
    t_raw, t_part = round(_tsg.get('raw', 0)), round(_tsg.get('part', 0))

    _res = {"date": d6, "frm": frm6, "ym": ym,
            "pur": pur, "pur_tot": pur_t, "out": out, "out_tot": out_t, "net": net, "net_tot": net_t,
            # ⑥ 당일 실적(조회일) — 매출(절삭/설치/기타/합계) + 사급(원소재/부품/합계)
            "today": {"hyeon_cut": t_cut, "hyeon_seol": t_seol, "hyeon_etc": t_etc, "sales_hab": t_cut + t_seol + t_etc,
                      "sagub_raw": t_raw, "sagub_part": t_part, "sagub_hab": t_raw + t_part},
            # ② 재료비(사용기준) = 원재료매입(매입−불출) + 재고사용(기초−기말). %=재료비/LG매출.
            "jaemat": {"net": net_t['tot'], "use": jae_use, "jaemat": jaemat, "jaemat_pct": pct(jaemat, lg_sales)},
            # ⑤ 현매출 / ② 매입비율
            "sales": {"hyeon_cut": hyeon_cut, "hyeon_seol": hyeon_seol, "hyeon_etc": hyeon_etc, "lg_sales": lg_sales},
            "ratio": {"pur_pct": pct(pur_t['tot'], lg_sales), "net_pct": pct(net_t['tot'], lg_sales),
                      "pur": pur_t['tot'], "net": net_t['tot'], "lg_sales": lg_sales,
                      "silrae": silrae, "silrae_pct": pct(silrae, lg_sales)},
            # ③ 재고 (버킷별 기초/기말 = 자재/생산/영업 수불장). 차액(사용)=기초−기말은 프론트 계산.
            "jaego": {"total": jaego,
                      "base_mat": base_m, "cur_mat": cur_m, "base_prd": base_prd, "cur_prd": cur_prd,
                      "base_sales": base_s, "cur_sales": cur_s, "base_total": gicho, "cur_total": gimal},
            # ④ 사급율
            "sagubyul": {"osp_raw": osp_raw, "osp_part": osp_part, "jeolsak_sales": hyeon_cut,
                         "raw_pct": pct(osp_raw, hyeon_cut), "part_pct": pct(osp_part, hyeon_cut)},
            # D 유상사급 대사 (당사ERP 확정입고 vs LG전산 OSP) — ④사급율에 당사ERP·비교(차액) 흡수
            "dae": {"dangsa": dangsa_sagub, "lg": lg_osp, "diff": dangsa_sagub - lg_osp,
                    "lg_raw": osp_raw, "lg_part": osp_part, "dangsa_raw": dangsa_raw, "dangsa_part": dangsa_part},
            # ⑤ 매출요약 (상반기 h1 / 하반기 h2 / 합계 tot · 원화). 현매출=실적, 추가매출=예상, 사급=원재료(예상0)/부품, LG수금=(내수−사급)×10%+유상제외
            "maechul": maechul}
    _DPI_CACHE[_ckey] = (_time.time() + 180, _res)   # ★180초 캐시(기간별). 재조회 즉시.
    return _res

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
        _cf, _mr = _rows(f"SELECT UPPER(item_code) c FROM PARTNER_ERP_TEST3.nx.item WHERE item_code LIKE '%{qe}%' OR item_name LIKE '%{qe}%'")
        _codes = [r["c"] for r in _mr if r.get("c")]
        if _codes:
            _inl = ",".join("'" + c.replace("'", "''") + "'" for c in _codes)
            MF = f" AND A.MAT_CODE IN ({_inl})"
        else:
            MF = f" AND A.MAT_CODE LIKE '%{qe}%'"
    sql = f"""{_MAGAM(ref_ym)}
SELECT A.MAINT_YMD ymd, A.MAINT_SEQ seq, A.CUST_CODE cc, C.CUST_DESC cnm, C.CUST_TYPE ct,
  A.MAT_CODE mat, M.item_name nm, M.ITEM_SPEC spec, M.diam diam, M.thick thick, M.length length,
  M.lgroup lg, M.sgroup sg, M.ITEM_WEIGHT wt, M.UNIT unit,
  A.MAINT_QTY qty, 'KRW' cur, 1.0 rate, A.MAINT_COST cost, A.MAINT_COST kcost, A.MAINT_AMT amt, A.MAINT_AMT kamt, A.MAINT_VAT vat
 FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT (nolock) A JOIN PARTNER_ERP_TEST3.nx.item (nolock) M ON A.MAT_CODE=M.ITEM_CODE JOIN PARTNER_ERP_TEST3.nx.cm_m_cust (nolock) C ON A.CUST_CODE=C.CUST_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
 WHERE {dc} AND A.MAINT_TAG IN ('9','S','C','G','H')
   AND ((ISNULL(A.INSP_FLAG,'N') IN ('','N')) OR (ISNULL(A.INSP_FLAG,'N') IN ('S','F') AND A.INSP_PROC_YMD >= '')){MF}
UNION ALL
SELECT A.MAINT_YMD, A.MAINT_SEQ, A.CUST_CODE, C.CUST_DESC, C.CUST_TYPE,
  A.MAT_CODE, M.item_name, M.ITEM_SPEC, M.diam, M.thick, M.length,
  M.lgroup, M.sgroup, M.ITEM_WEIGHT, M.UNIT,
  A.MAINT_QTY, A.CURRENCY, A.EXCHANGE_RATE, A.MAINT_COST, A.MAINT_COST*A.EXCHANGE_RATE, A.MAINT_AMT, ROUND(A.MAINT_AMT*A.EXCHANGE_RATE,0,1), 0
 FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT_C (nolock) A JOIN PARTNER_ERP_TEST3.nx.item (nolock) M ON A.MAT_CODE=M.ITEM_CODE JOIN PARTNER_ERP_TEST3.nx.cm_m_cust (nolock) C ON A.CUST_CODE=C.CUST_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
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
        dc = _win_ovr('PUR', y)   # ★마감창 + 매입마감 수동이월(PUR) 반영
        rows = _receiptdetail(dc, y, q)
        return {"gijun": "close", "ym": y, "count": len(rows), "rows": rows, "q": q}

# ================= 자재불출명세서 (구매/자재, dw_pu_input_130) — 라인단위 =================
def _dispatchdetail(dc, ref_ym, dc5=None):
    dc5 = dc5 or dc   # ★PU tag5 파트만 매출마감 override(SALE). SA(MAT_CODE없음)·수입(Q)=원 dc.
    sql = f"""{_MAGAM(ref_ym)}
SELECT A.MAINT_YMD ymd, A.MAINT_SEQ seq, A.CUST_CODE cc, C.CUST_DESC cnm, C.CUST_TYPE ct,
  A.MAT_CODE mat, A.ITEM_CODE ic, (SELECT CUST_DESC FROM PARTNER_ERP_TEST3.nx.CM_M_CUST WHERE CUST_CODE=M.in_cust) incust,
  M.lgroup lg, M.sgroup sg, M.ITEM_WEIGHT wt, M.UNIT unit, M.item_name nm, M.ITEM_SPEC spec,
  -A.MAINT_QTY qty, 'KRW' cur, 1.0 rate, A.MAINT_COST cost, A.MAINT_COST kcost, -A.MAINT_AMT amt, -A.MAINT_AMT kamt, -A.MAINT_VAT vat
 FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT A JOIN PARTNER_ERP_TEST3.nx.item M ON A.MAT_CODE=M.ITEM_CODE join MAGAM mg on a.cust_code=mg.cust_code join PARTNER_ERP_TEST3.nx.cm_m_cust C on A.CUST_CODE=C.CUST_CODE
 WHERE {dc5} AND A.MAINT_TAG IN ('5')
UNION ALL
SELECT A.MAINT_YMD, A.MAINT_SEQ, A.CUST_CODE, C.CUST_DESC, C.CUST_TYPE,
  A.ITEM_CODE, '', (SELECT CUST_DESC FROM PARTNER_ERP_TEST3.nx.CM_M_CUST WHERE CUST_CODE=M.in_cust),
  M.lgroup, M.sgroup, M.ITEM_WEIGHT, M.UNIT, M.item_name, M.ITEM_SPEC,
  -A.MAINT_QTY, 'KRW', 1.0, A.MAINT_COST, A.MAINT_COST, -A.MAINT_AMT, -A.MAINT_AMT, -A.MAINT_VAT
 FROM PARTNER_ERP_TEST3.nx.SA_T_STOCK_MAINT A JOIN PARTNER_ERP_TEST3.nx.item M ON A.ITEM_CODE=M.ITEM_CODE join MAGAM mg on a.cust_code=mg.cust_code join PARTNER_ERP_TEST3.nx.cm_m_cust C on A.CUST_CODE=C.CUST_CODE
 WHERE {dc} AND A.MAINT_TAG IN ('5')
UNION ALL
SELECT A.MAINT_YMD, A.MAINT_SEQ, A.CUST_CODE, C.CUST_DESC, C.CUST_TYPE,
  A.MAT_CODE, A.ITEM_CODE, (SELECT CUST_DESC FROM PARTNER_ERP_TEST3.nx.CM_M_CUST WHERE CUST_CODE=M.in_cust),
  M.lgroup, M.sgroup, M.ITEM_WEIGHT, M.UNIT, M.item_name, M.ITEM_SPEC,
  A.MAINT_QTY, A.CURRENCY, A.EXCHANGE_RATE, A.MAINT_COST, A.MAINT_COST*A.EXCHANGE_RATE, A.MAINT_AMT, ROUND(A.MAINT_AMT*A.EXCHANGE_RATE,0,1), 0
 FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT_C A JOIN PARTNER_ERP_TEST3.nx.item M ON A.MAT_CODE=M.ITEM_CODE join MAGAM mg on a.cust_code=mg.cust_code join PARTNER_ERP_TEST3.nx.cm_m_cust C on A.CUST_CODE=C.CUST_CODE
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
        rows = _dispatchdetail(dc, y, _win_ovr('SALE', y))   # ★tag5(판매) 매출마감 이월 반영
        return {"gijun": "close", "ym": y, "count": len(rows), "rows": rows}

# ================= 자재입출고현황 (구매/자재, dw_pu_stock_060) — 마스터-디테일 =================
# 자재창고(Z99990/IS0001) 당월 입출고 상세라인 + 전월이월. patch_060full.py 이식, 월 파라미터화.
def _prev_ym(ym):
    yy, mm = int(ym[:2]), int(ym[2:4])
    return f"{(yy-1):02d}12" if mm == 1 else f"{yy:02d}{(mm-1):02d}"

# ※2026-09-01 시도했다가 되돌림 — 웹원장(nx.stock_ledger)을 이 화면에 UNION 하려 했으나
#   **중복계상**이 확인되어 중단했다. 같은 물량이 양쪽 원장에 모두 있다:
#     실측 8월 이후 웹원장 957행 중 693행이 미러에도 동일 (자재·일자·TAG·수량 일치)
#     예) 260831 AJR77225602-20-1 4개 — 웹 seq272(web) / 미러 seq372(김병기 13:32)
#   즉 8/31 은 웹·레거시 양쪽에서 같은 송장을 입고했다(병행운영 기간).
#   ⟹ 단순 UNION 은 재고를 2배로 만든다. 합치려면 **중복 판정 키**를 먼저 정해야 한다
#     (레거시 은퇴 시점 또는 웹 입고분 식별자). 별도 과제.
def _matinout(from6, to6, stock_cust="Z99990", part_wh="IS0001", q="", src="nx"):
    # ★2026-08-25 src 인자 수용(현재는 원천이 nx 중심 = 라이브 미러 + 웹실적이라
    #   nx/live 모두 동일 결과). 시그니처만 맞춰 호출부와 어긋나지 않게 한다.
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
        _cf, _mr = _rows(f"SELECT UPPER(item_code) c FROM PARTNER_ERP_TEST3.nx.item WHERE item_code LIKE '%{qe}%' OR item_name LIKE '%{qe}%'")
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
   CASE a.maint_tag WHEN '3' THEN '기초재고' WHEN '9' THEN '자재창고입고' WHEN 'C' THEN IIF(a.maint_qty>0,'가공이동입고','가공이동취소') WHEN 'G' THEN '축관입고' WHEN 'H' THEN '가공입고' WHEN 'S' THEN '세트입고' WHEN 'P' THEN '생산'+IIF(a.maint_qty<0,'취소','') WHEN 'R' THEN '반품' ELSE '' END div, {CUST} cust, a.work_order wo,
   ISNULL(a.item_code,'') itm, CONVERT(varchar(19),a.insert_datetime,120) wt
  FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_tag IN ('3','9','C','G','H','S','P','R') AND a.maint_qty<>0 AND {INSP} AND {W}{MFmat}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_ymd, a.maint_qty,0,0,0,'도입-구매',{CUST},a.work_order,ISNULL(a.item_code,''),CONVERT(varchar(19),a.insert_datetime,120) FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint_c a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_qty<>0 AND a.wh_cust_code='{sc}' AND a.part_code='{pw}' AND a.division='P'{MFmat}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_ymd, a.maint_qty*-1,0,0,0,'생산창고반품',{CUST},a.work_order,ISNULL(a.item_code,''),CONVERT(varchar(19),a.insert_datetime,120) FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_tag IN ('T') AND a.maint_qty<>0 AND {INSP} AND {W}{MFmat}
 UNION ALL SELECT UPPER(a.mat_code), a.cut_ymd, a.cut_qty,0,0,0,'자재창고입고','작업처 : 제조1팀',NULL,ISNULL(a.item_code,''),CONVERT(varchar(19),a.insert_datetime,120) FROM (SELECT * FROM PARTNER_ERP_TEST3.nx.pu_t_cut_dtl UNION ALL SELECT n.* FROM PARTNER_ERP_TEST3.nx.pu_t_cut_dtl n WHERE NOT EXISTS(SELECT 1 FROM PARTNER_ERP_TEST3.nx.pu_t_cut_dtl l WHERE l.BOX_NO=n.BOX_NO AND l.CUT_YMD=n.CUT_YMD AND l.CUT_HMS=n.CUT_HMS)) a WHERE a.cut_ymd>='{y01}' AND a.cut_ymd<='{y99}' AND a.cut_qty<>0 AND {W}{MFmat}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_ymd, 0,0,a.maint_qty,0,'재고조정',{CUST},a.work_order,ISNULL(a.item_code,''),CONVERT(varchar(19),a.insert_datetime,120) FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_tag='2' AND a.maint_qty<>0 AND {W}{MFmat}
 UNION ALL SELECT UPPER(a.item_code), a.move_ymd, 0,0,0, CASE WHEN a.to_cust_code='{sc}' AND a.to_gagong_proc_code='{pw}' THEN a.move_qty ELSE 0 END,'창고재고입고',ISNULL((SELECT cust_desc FROM PARTNER_ERP_TEST3.nx.cm_m_cust m WHERE m.cust_code=CASE WHEN a.to_cust_code='{sc}' THEN a.fr_cust_code ELSE a.to_cust_code END),''),'','',CONVERT(varchar(19),a.insert_datetime,120) FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MOVE a WHERE a.move_ymd>='{y01}' AND a.move_ymd<='{y99}' AND a.move_qty<>0 AND a.to_cust_code='{sc}' AND a.to_gagong_proc_code='{pw}'{MFitem}
 UNION ALL SELECT UPPER(a.item_code), a.move_ymd, 0,0,0, CASE WHEN a.fr_cust_code='{sc}' AND a.fr_gagong_proc_code='{pw}' THEN a.move_qty*-1 ELSE 0 END,'창고재고출고',ISNULL((SELECT cust_desc FROM PARTNER_ERP_TEST3.nx.cm_m_cust m WHERE m.cust_code=CASE WHEN a.to_cust_code='{sc}' THEN a.fr_cust_code ELSE a.to_cust_code END),''),'','',CONVERT(varchar(19),a.insert_datetime,120) FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MOVE a WHERE a.move_ymd>='{y01}' AND a.move_ymd<='{y99}' AND a.move_qty<>0 AND a.fr_cust_code='{sc}' AND a.fr_gagong_proc_code='{pw}'{MFitem}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_ymd, 0, a.maint_qty*-1,0,0,
   CASE a.maint_tag WHEN '1' THEN '불량' WHEN '4' THEN '생산사용'+IIF(a.maint_qty>0,'취소','') WHEN '5' THEN '협력업체판매' WHEN '6' THEN '일반간판출하' WHEN '8' THEN '라인무상공급' WHEN 'A' THEN '개발불출' WHEN 'B' THEN IIF(a.out_wh_gubun='1','생산창고출고','영업창고출고') WHEN 'J' THEN '출하'+IIF(a.maint_qty>0,'취소','') ELSE '' END,
   ISNULL((SELECT cust_desc FROM PARTNER_ERP_TEST3.nx.cm_m_cust m WHERE m.cust_code=a.cust_code AND a.cust_code<>'{sc}'),''), a.work_order,
   ISNULL(a.item_code,''), CONVERT(varchar(19),a.insert_datetime,120)
  FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_tag IN ('1','4','5','6','8','A','B','J') AND a.maint_qty<>0 AND {W}{MFmat}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_ymd, 0, a.maint_qty,0,0,'도입-판매',{CUST},a.work_order,ISNULL(a.item_code,''),CONVERT(varchar(19),a.insert_datetime,120) FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint_c a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_qty<>0 AND a.wh_cust_code='{sc}' AND a.part_code='{pw}' AND a.division='Q'{MFmat}
"""
    BF = f"""
 SELECT UPPER(a.mat_code) mat, a.stock_qty sq FROM PARTNER_ERP_TEST3.nx.pu_t_month_stock_wh a WHERE a.stock_yymm='{pv}' AND a.cust_code='{sc}' AND ISNULL(a.gagong_proc_code,'')='{pw}'{MFmat}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_qty FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE a.maint_ymd>'{pv99}' AND a.maint_ymd<'{y01}' AND a.maint_tag IN ('3','9','C','G','H','S','P','R') AND {INSP} AND {W}{MFmat}
 UNION ALL SELECT UPPER(a.mat_code), IIF(a.division='Q',-a.maint_qty,a.maint_qty) FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint_c a WHERE a.maint_ymd>'{pv99}' AND a.maint_ymd<'{y01}' AND a.wh_cust_code='{sc}' AND a.part_code='{pw}'{MFmat}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_qty*-1 FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE a.maint_ymd>'{pv99}' AND a.maint_ymd<'{y01}' AND a.maint_tag IN ('T') AND {INSP} AND {W}{MFmat}
 UNION ALL SELECT UPPER(a.mat_code), a.cut_qty FROM (SELECT * FROM PARTNER_ERP_TEST3.nx.pu_t_cut_dtl UNION ALL SELECT n.* FROM PARTNER_ERP_TEST3.nx.pu_t_cut_dtl n WHERE NOT EXISTS(SELECT 1 FROM PARTNER_ERP_TEST3.nx.pu_t_cut_dtl l WHERE l.BOX_NO=n.BOX_NO AND l.CUT_YMD=n.CUT_YMD AND l.CUT_HMS=n.CUT_HMS)) a WHERE a.cut_ymd>'{pv99}' AND a.cut_ymd<'{y01}' AND {W}{MFmat}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_qty FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE a.maint_ymd>'{pv99}' AND a.maint_ymd<'{y01}' AND a.maint_tag='2' AND {W}{MFmat}
 UNION ALL SELECT UPPER(a.item_code), (CASE WHEN a.fr_cust_code='{sc}' AND a.fr_gagong_proc_code='{pw}' THEN a.move_qty*-1 ELSE 0 END)+(CASE WHEN a.to_cust_code='{sc}' AND a.to_gagong_proc_code='{pw}' THEN a.move_qty ELSE 0 END) FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MOVE a WHERE a.move_ymd>'{pv99}' AND a.move_ymd<'{y01}' AND ('{sc}' IN (a.fr_cust_code,a.to_cust_code)) AND ('{pw}' IN (a.fr_gagong_proc_code,a.to_gagong_proc_code)){MFitem}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_qty FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE a.maint_ymd>'{pv99}' AND a.maint_ymd<'{y01}' AND a.maint_tag IN ('1','4','5','6','8','A','B','J') AND {W}{MFmat}
"""
    _c1, moves = _rows(f"SELECT mat, ymd, inq i, outq o, etc e, mv, div, cust, ISNULL(wo,'') wo, ISNULL(itm,'') itm, ISNULL(wt,'') wt FROM ({LINES}) x")
    _c2, bfrows = _rows(f"SELECT mat, SUM(sq) bf FROM ({BF}) b GROUP BY mat")
    _c3, nmrows = _rows("SELECT UPPER(item_code) c, item_name d, ISNULL((SELECT cust_desc FROM PARTNER_ERP_TEST3.nx.cm_m_cust m WHERE m.cust_code=i.in_cust),'') v FROM PARTNER_ERP_TEST3.nx.item i")
    nm = {r["c"]: r["d"] for r in nmrows}
    vend = {r["c"]: (r["v"] or "") for r in nmrows}   # 매입처(IN_CUST_CODE→거래처명)
    bfm = {r["mat"]: float(r["bf"] or 0) for r in bfrows}
    net, lastin, lastout = {}, {}, {}
    for r in moves:
        m = r["mat"]
        net[m] = net.get(m, 0) + (float(r["i"] or 0) - float(r["o"] or 0) + float(r["e"] or 0) + float(r["mv"] or 0))
        y = str(r["ymd"] or "")
        if float(r["i"] or 0) > 0 and y > lastin.get(m, ""):
            lastin[m] = y
        if float(r["o"] or 0) > 0 and y > lastout.get(m, ""):   # 최종출고일(출고>0 최대일)
            lastout[m] = y
    mats = set(bfm) | set(net)
    stock = []
    for m in sorted(mats):
        bf = bfm.get(m, 0); st = bf + net.get(m, 0)
        stock.append({"mat": m, "nm": nm.get(m, ""), "cust": vend.get(m, ""), "stock": round(st, 4), "bf": round(bf, 4), "lastin": lastin.get(m, ""), "lastout": lastout.get(m, ""), "part": pw})
    return stock, moves

@live_router.get("/matinout")
def matinout(from_ymd: str = Query(""), to_ymd: str = Query(""), stock_cust: str = Query("Z99990"), part_wh: str = Query("IS0001"), q: str = Query(""), source: str = Query("live")):
    """자재 입출고현황. 기본 source=live(현행 무변경). source=nx면 stock_ledger(MAT) 파생. 기간 from_ymd~to_ymd(YYMMDD).
    q(자도번/품명) 입력 시 서버 WHERE로 스코프 → 해당 품목만 조회(기간 길어도 빠름)."""
    to6 = _digits(to_ymd, 6) or _scalar("SELECT FORMAT(GETDATE(),'yyMMdd')")
    from6 = _digits(from_ymd, 6) or (to6[:4] + "01")
    if from6 > to6:
        from6, to6 = to6, from6
    # ★2026-08-25 생산입출고와 동일하게 source 의미 통일.
    #   nx(기본) = 라이브 수불 + 웹실적 / live = 라이브만 / ledger = 웹 자체원장(진단용)
    if source == "ledger":
        return _nx_screen("MAT", from6, to6)
    stock, moves = _matinout(from6, to6, stock_cust, part_wh, q, src=source)
    return {"from_ymd": from6, "to_ymd": to6, "stock": stock, "moves": moves, "stock_cust": stock_cust, "part_wh": part_wh, "q": q}

# ================= 자재출고관리 (구매/자재, w_pu_stock_150 / dw_pu_stock_150) — 자재개별출고 조회 =================
# ★레거시 정본(dw_pu_stock_150): PU_T_STOCK_MAINT WHERE MAINT_TAG IN('4','B') + 기간. 4=생산사용(축관)·B=자재개별출고(파트출고).
#   13컬럼(출고일자/SEQ/FROM파트창고/P·N/TO창고구분/TO파트창고/자도번/출고수량(=maint_qty*-1)/출고단가/출고금액/비고/작업자/작업일시).
#   현재고/집계는 서버 SUM·COUNT(전체 매칭 대상)로 계산 → 500 cap 부분합 문제 제거.
def _qesc(s):
    return str(s or "").replace("'", "''")

@live_router.get("/stockissue")
def stockissue_view(from_ymd: str = Query(""), to_ymd: str = Query(""), pn: str = Query(""),
                    mat: str = Query(""), out_wh: str = Query(""), to_wh: str = Query(""),
                    from_wh: str = Query(""), page: int = Query(1), size: int = Query(2000)):
    """자재출고관리 라이브 조회(레거시 w_pu_stock_150, PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT MAINT_TAG IN('4','B')). 서버 집계(건수·수량합)+페이징."""
    t6 = _digits(to_ymd, 6) or _scalar("SELECT FORMAT(GETDATE(),'yyMMdd')")
    f6 = _digits(from_ymd, 6) or t6
    if f6 > t6:
        f6, t6 = t6, f6
    W = ["a.maint_tag IN ('4','B')", f"a.maint_ymd BETWEEN '{f6}' AND '{t6}'"]   # ★레거시 w_pu_stock_150 = 4(생산사용/축관)+B(자재개별출고)
    if pn.strip():      W.append(f"a.item_code LIKE '%{_qesc(pn.strip())}%'")
    if mat.strip():     W.append(f"a.mat_code LIKE '%{_qesc(mat.strip())}%'")
    if out_wh in ("1", "2"): W.append(f"ISNULL(a.out_wh_gubun,'')='{out_wh}'")
    if to_wh.strip():   W.append(f"a.to_gagong_proc_code='{_qesc(to_wh.strip())}'")
    if from_wh.strip(): W.append(f"a.gagong_proc_code='{_qesc(from_wh.strip())}'")
    WH = " AND ".join(W)
    PW = f"a.maint_tag IN ('4','B') AND a.maint_ymd BETWEEN '{f6}' AND '{t6}'"   # 드롭다운 옵션용(기간만)
    _c, agg = _rows(f"SELECT COUNT(*) cnt, ISNULL(SUM(a.maint_qty*-1),0) qty FROM PARTNER_ERP_TEST3.nx.pu_t_stock_maint a WHERE {WH}")
    tot = agg[0] if agg else {"cnt": 0, "qty": 0}
    sz = max(1, min(int(size or 2000), 10000)); off = max(0, (int(page or 1) - 1)) * sz
    sql = f"""
      SELECT a.maint_ymd ymd, a.maint_seq seq,
        ISNULL((SELECT gagong_proc_desc FROM PARTNER_ERP_TEST3.nx.pr_m_proc_gagong g WHERE g.gagong_proc_code=a.gagong_proc_code),a.gagong_proc_code) from_wh,
        a.item_code pn, ISNULL((SELECT item_name FROM PARTNER_ERP_TEST3.nx.item i WHERE i.item_code=a.item_code),'') pn_nm,
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
def _prodinout(ym, frm=None, to=None, src="nx", inc_zero=False):
    """★2026-08-25 src 분기 추가.
         nx(기본) = nx 스키마(= 라이브 미러 + 웹실적) — 웹에서 잡은 실적이 보인다.
         live     = 라이브 스키마만 — 레거시와 순수 대조용.
       기존엔 원천이 nx 로 고정이라 '라이브' 를 골라도 nx 를 봤다."""
    # 레거시와 동일: 수불기간(frm~to). frm/to(YYMMDD) 우선, 없으면 ym월 전체.
    y01 = frm if frm else (ym + "01")
    y99 = to if to else (ym + "99")
    # ★2026-08-25 이력(우측)도 좌측 재고와 같은 원천을 봐야 한다.
    #   좌측은 라이브∪nx 잔액인데 이력만 nx 면 둘이 어긋난다
    #   (실측 AJR30027704-SUB6: 좌측 25 / 우측 누계 0).
    #   → nx 모드에서 각 수불테이블을 '라이브 ∪ nx(중복배제)' 인라인뷰로 바꾼다.
    #     중복배제 키는 각 테이블의 자연키. live 모드는 라이브 테이블 그대로.
    _live = str(src).strip() == "live"

    def _U(tbl, keys):
        """라이브 ∪ nx — nx 행 중 라이브에 같은 키가 없는 것만 얹는다."""
        if _live:
            return "PARTNER_ERP.dbo." + tbl
        # ★키 비교는 문자 캐스팅으로(2026-09-02 실측 버그). `ISNULL(수량,'')` 은
        #   decimal 에 빈 문자열을 넣는 꼴이라 8114(varchar→numeric) 로 쿼리가 죽고
        #   화면이 조회 0건이 된다. common._u_tbl 과 같은 처리.
        on = " AND ".join(
            f"ISNULL(CAST(l.{k} AS varchar(50)),'')=ISNULL(CAST(n.{k} AS varchar(50)),'')"
            for k in keys)
        return (f"(SELECT * FROM PARTNER_ERP_TEST3.nx.{tbl} UNION ALL SELECT n.* FROM PARTNER_ERP_TEST3.nx.{tbl} n"
                f" WHERE NOT EXISTS(SELECT 1 FROM PARTNER_ERP_TEST3.nx.{tbl} l WHERE {on}))")

    # ★2026-08-25 웹은 SEQ 20000 대역(common.WEB_SEQ_BASE)에만 쓴다 → 라이브(1~19,999)와
    #   번호가 절대 안 겹치므로 (YMD,SEQ) 만으로 중복배제가 성립한다.
    #   ※대역 분리 전 데이터(과거 웹 기입분)는 seq 가 겹칠 수 있어 품목/수량도 키에 남겨둔다.
    #     대역 정착 후에는 (YMD,SEQ)만으로 줄여도 된다.
    _PUSM = _U("PU_T_STOCK_MAINT", ["MAINT_YMD", "MAINT_SEQ", "MAT_CODE", "MAINT_QTY", "MAINT_TAG"])
    _PRPD = _U("PR_T_PROD_DTL", ["PROD_YMD", "PROD_HMS", "ITEM_CODE", "WORK_ORDER", "SPLIT_WORK_ORDER"])
    _SASM = _U("SA_T_STOCK_MAINT", ["MAINT_YMD", "MAINT_SEQ", "ITEM_CODE", "MAINT_QTY", "MAINT_TAG"])
    _PRSM = _U("PR_T_STOCK_MAINT_MAT", ["MAINT_YMD", "MAINT_SEQ", "MAT_CODE", "PART_CODE", "MAINT_QTY"])
    _S = "PARTNER_ERP.dbo" if _live else "PARTNER_ERP_TEST3.nx"
    INSP = "NOT(ISNULL(a.insp_flag,'N') IN ('S','F') AND ISNULL(a.insp_proc_flag,'0')<>'1')"
    CUST = "ISNULL((SELECT cust_desc FROM PARTNER_ERP_TEST3.nx.cm_m_cust m WHERE m.cust_code=a.cust_code),'')"
    CUR = f"""
 SELECT a.TO_GAGONG_PROC_CODE part, UPPER(a.mat_code) mat, a.maint_ymd ymd, a.maint_qty*-1 inq,CAST(0 AS decimal(18,4)) outq,CAST(0 AS decimal(18,4)) etc,'생산창고입고' div, {CUST} tag
   FROM {_PUSM} a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_tag='B' AND ISNULL(a.out_wh_gubun,'1')='1' AND a.maint_qty<>0 AND {INSP} AND a.TO_GAGONG_PROC_CODE>''
 UNION ALL SELECT a.gagong_proc_code, UPPER(a.mat_code), a.cut_ymd, a.cut_qty,0,0,'가공생산입고','제조1팀' FROM (SELECT * FROM PARTNER_ERP_TEST3.nx.pu_t_cut_dtl UNION ALL SELECT n.* FROM PARTNER_ERP_TEST3.nx.pu_t_cut_dtl n WHERE NOT EXISTS(SELECT 1 FROM PARTNER_ERP_TEST3.nx.pu_t_cut_dtl l WHERE l.BOX_NO=n.BOX_NO AND l.CUT_YMD=n.CUT_YMD AND l.CUT_HMS=n.CUT_HMS) AND '{src}'<>'live') a WHERE a.cut_ymd>='{y01}' AND a.cut_ymd<='{y99}' AND a.cut_qty<>0 AND a.gagong_proc_code>''
 UNION ALL SELECT a.TO_GAGONG_PROC_CODE, UPPER(a.mat_code), a.maint_ymd, 0, a.maint_qty*-1,0,'자재창고반품',{CUST} FROM {_PUSM} a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_tag='T' AND ISNULL(a.out_wh_gubun,'3')='3' AND a.maint_qty<>0 AND a.TO_GAGONG_PROC_CODE>''
 UNION ALL SELECT a.TO_GAGONG_PROC_CODE, UPPER(a.mat_code), a.maint_ymd, 0, a.maint_qty,0,'가공부품이동',{CUST} FROM {_PUSM} a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.maint_tag='C' AND a.maint_qty<>0 AND a.TO_GAGONG_PROC_CODE>''
 UNION ALL SELECT a.STOCK_PART_CODE, UPPER(a.item_code), a.prod_ymd, a.prod_qty,0,0,'SUB생산실적','' FROM {_PRPD} a WHERE a.prod_ymd>='{y01}' AND a.prod_ymd<='{y99}' AND a.STOCK_PART_CODE>'' AND NOT EXISTS(SELECT 1 FROM {_SASM} s WHERE s.maint_ymd=a.prod_ymd AND s.item_code=a.item_code AND (s.in_part_code=a.stock_part_code OR (ISNULL(s.in_part_code,'')='' AND s.maint_tag='P')))
 UNION ALL SELECT a.IN_PART_CODE, UPPER(a.item_code), a.maint_ymd, a.maint_qty,0,0,'생산실적',{CUST} FROM {_SASM} a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.IN_PART_CODE>''
 UNION ALL SELECT a.part_code, UPPER(a.mat_code), a.maint_ymd, a.maint_qty,0,0,'기초재고',{CUST} FROM {_PRSM} a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.part_code>'' AND a.maint_tag='3' AND a.maint_qty<>0
 UNION ALL SELECT a.part_code, UPPER(a.mat_code), a.maint_ymd, 0,0,a.maint_qty,'재고조정',{CUST} FROM {_PRSM} a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.part_code>'' AND a.maint_tag IN ('2','1') AND a.maint_qty<>0
 UNION ALL SELECT a.part_code, UPPER(a.mat_code), a.maint_ymd, 0, a.maint_qty*-1,0,'생산사용',{CUST} FROM {_PRSM} a WHERE a.maint_ymd>='{y01}' AND a.maint_ymd<='{y99}' AND a.part_code>'' AND a.maint_tag='4' AND a.maint_qty<>0
"""
    BFT = f"'{y01}'"
    # ★2026-09-02 기초재고(BF)도 **source 를 따른다**(nx 모드면 nx).
    #   종전에는 "미러 정지분만큼 비어 재고가 어긋난다"는 이유로 라이브 고정이었으나,
    #   그건 미러가 덜 채워졌던 시절 이야기다. 실측(2026-09-02)으로 미러가 따라잡았다:
    #     PR_T_MONTH_STOCK_WH 1,700=1,700 · pr_t_prod_dtl 171,306=171,306
    #     sa_t_stock_maint 296,129=296,129 · PR_T_STOCK_MAINT_MAT 654,378=654,378
    #     BF 총량 라이브 -1,767,957 / nx -1,768,376  (차 -419 = 0.02%)
    #     └ 라이브에만 230행(8/31 레거시 입력, 미러 지연) · nx 에만 48행(web 실적)
    #   ⟹ nx 가 오히려 **웹 실적까지 포함**해 정확하다.
    #   ★그리고 라이브 고정은 **컷오버에 죽는 코드**다(CLAUDE.md §1-9-1) —
    #     레거시가 은퇴하면 PARTNER_ERP.dbo 자체가 없어진다. 지금 클린으로 짠다.
    _B = "PARTNER_ERP.dbo" if _live else "PARTNER_ERP_TEST3.nx"
    BF = f"""
 SELECT a.gagong_proc_code part, UPPER(a.mat_code) mat, a.stock_qty sq FROM {_B}.PR_T_MONTH_STOCK_WH a WHERE a.stock_yymm='2502'
 UNION ALL SELECT a.TO_GAGONG_PROC_CODE, UPPER(a.mat_code), a.maint_qty*-1 FROM {_B}.PU_T_STOCK_MAINT a WHERE a.maint_ymd>'250299' AND a.maint_ymd<{BFT} AND a.maint_tag='B' AND ISNULL(a.out_wh_gubun,'1')='1' AND {INSP} AND a.TO_GAGONG_PROC_CODE>''
 UNION ALL SELECT a.STOCK_PART_CODE, UPPER(a.item_code), a.prod_qty FROM {_B}.pr_t_prod_dtl a WHERE a.prod_ymd>'250299' AND a.prod_ymd<{BFT} AND a.STOCK_PART_CODE>'' AND NOT EXISTS(SELECT 1 FROM {_B}.sa_t_stock_maint s WHERE s.maint_ymd=a.prod_ymd AND s.item_code=a.item_code AND s.in_part_code=a.stock_part_code)
 UNION ALL SELECT a.IN_PART_CODE, UPPER(a.item_code), a.MAINT_QTY FROM {_B}.sa_t_stock_maint a WHERE a.maint_ymd>'250299' AND a.maint_ymd<{BFT} AND a.IN_PART_CODE>''
 UNION ALL SELECT a.gagong_proc_code, UPPER(a.mat_code), a.cut_qty FROM (SELECT * FROM PARTNER_ERP_TEST3.nx.pu_t_cut_dtl UNION ALL SELECT n.* FROM PARTNER_ERP_TEST3.nx.pu_t_cut_dtl n WHERE NOT EXISTS(SELECT 1 FROM PARTNER_ERP_TEST3.nx.pu_t_cut_dtl l WHERE l.BOX_NO=n.BOX_NO AND l.CUT_YMD=n.CUT_YMD AND l.CUT_HMS=n.CUT_HMS) AND '{src}'<>'live') a WHERE a.cut_ymd>'250299' AND a.cut_ymd<{BFT} AND a.gagong_proc_code>'' AND a.cut_qty<>0
 UNION ALL SELECT a.PART_CODE, UPPER(a.MAT_CODE), a.MAINT_QTY FROM {_B}.PR_T_STOCK_MAINT_MAT a WHERE a.MAINT_YMD>'250299' AND a.MAINT_YMD<{BFT} AND a.PART_CODE>'' AND a.MAINT_TAG IN ('3','2','1')
 UNION ALL SELECT a.PART_CODE, UPPER(a.MAT_CODE), a.MAINT_QTY FROM {_B}.PR_T_STOCK_MAINT_MAT a WHERE a.MAINT_YMD>'250299' AND a.MAINT_YMD<{BFT} AND a.PART_CODE>'' AND a.MAINT_TAG='4'
 UNION ALL SELECT a.TO_GAGONG_PROC_CODE, UPPER(a.mat_code), a.MAINT_QTY FROM {_B}.PU_T_STOCK_MAINT a WHERE a.MAINT_YMD>'250299' AND a.MAINT_YMD<{BFT} AND a.maint_tag='T' AND a.TO_GAGONG_PROC_CODE>''
 UNION ALL SELECT a.TO_GAGONG_PROC_CODE, UPPER(a.mat_code), a.MAINT_QTY*-1 FROM {_B}.PU_T_STOCK_MAINT a WHERE a.MAINT_YMD>'250299' AND a.MAINT_YMD<{BFT} AND a.maint_tag='C' AND a.TO_GAGONG_PROC_CODE>''
"""
    # ★2026-08-25 유니버스(좌측 목록) = 잔액 테이블 기준. nx 모드는 라이브 ∪ nx.
    #   nx 에만 있는 품목(웹이 새로 만든 것)도, 라이브에만 있는 품목(미러 미반영)도
    #   둘 다 목록에 떠야 한다.
    _UNI = (f"SELECT part_code part, UPPER(mat_code) mat, SUM(stock_qty) snap FROM {_S}.pr_t_mat_stock_wh GROUP BY part_code, UPPER(mat_code)"
            if str(src).strip() == "live" else
            """SELECT part, mat, MAX(snap) snap FROM (
                 SELECT part_code part, UPPER(mat_code) mat, SUM(stock_qty) snap FROM PARTNER_ERP_TEST3.nx.pr_t_mat_stock_wh GROUP BY part_code, UPPER(mat_code)
                 UNION ALL
                 SELECT part_code, UPPER(mat_code), SUM(stock_qty) FROM PARTNER_ERP_TEST3.nx.pr_t_mat_stock_wh GROUP BY part_code, UPPER(mat_code)
               ) u GROUP BY part, mat""")
    _c1, uni = _rows(_UNI)
    _c2, bfrows = _rows(f"SELECT part, mat, SUM(sq) bf FROM ({BF}) b GROUP BY part, mat")
    _c3, moves = _rows(f"SELECT part, mat, ymd, inq, outq, etc, div, tag FROM ({CUR}) x")
    _c4, itrows = _rows("SELECT UPPER(item_code) mat, item_desc AS item_name, item_spec, item_sgroup FROM cm_m_item")
    _c5, sgrows = _rows("SELECT DETAIL_CODE cd, REPLACE(REPLACE(DETAIL_DESC,CHAR(13),''),CHAR(10),'') nm FROM PARTNER_ERP_TEST3.nx.CM_M_MASTER_DETAIL WHERE KIND_CODE='PR006'")
    _c6, pnrows = _rows("SELECT gagong_proc_code code, gagong_proc_desc nm FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG")
    im = {r["mat"]: r for r in itrows}
    sgm = {str(r["cd"]).strip(): str(r["nm"]).strip() for r in sgrows}
    bfm = {(r["part"], r["mat"]): float(r["bf"] or 0) for r in bfrows}
    net = {}
    for r in moves:
        k = (r["part"], r["mat"])
        net[k] = net.get(k, 0) + (float(r["inq"] or 0) - float(r["outq"] or 0) + float(r["etc"] or 0))
    # ★2026-08-25 현재고 = 전월이월(BF) + 기간이동(net). 좌측·우측이 같은 근거여야 한다.
    #   (한때 잔액 스냅샷을 정본으로 썼는데, 그러면 우측 이력 누계와 값이 어긋난다 —
    #    실측 nx 300/1655행 불일치. 사용자는 이력이 근거라고 확인.)
    #   nx 모드는 CUR/BF 원천을 '라이브 ∪ nx(중복배제)' 로 읽으므로 미러 지연분도 잡힌다.
    #   유니버스는 라이브∪nx 잔액이라 어느 쪽에만 있는 품목도 목록에는 뜬다.
    stock = []
    for u in uni:
        k = (u["part"], u["mat"]); bf = bfm.get(k, 0)
        st = bf + net.get(k, 0)
        # ★0재고 숨김/표시 — inc_zero=1 이면 0 도 남긴다(2026-08-28 사용자요청).
        #   0 이어도 기간 중 입·출고가 있었으면 이력을 봐야 한다(가공이동으로 0 이 된 품목 등).
        if abs(st) <= 0.0001 and not inc_zero:
            continue
        it = im.get(u["mat"], {}); sg = str(it.get("item_sgroup") or "").strip()
        stock.append([u["part"], u["mat"], (it.get("item_name") or ""), (it.get("item_spec") or ""),
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
def prodinout(ym: str = Query(""), frm: str = Query(""), to: str = Query(""), source: str = Query("live"),
              inc_zero: int = Query(0)):
    """생산입출고현황. 수불기간 frm~to(YYMMDD) 우선. 없으면 ym 월전체(하위호환).

       ★2026-08-25 source 의미를 다른 화면(410·키팅)과 통일.
         nx   = 라이브 수불 + 웹실적   ← 기본. _prodinout 이 이미 nx 테이블을 읽는다.
         live = 라이브만(레거시 대조)
       구버전은 nx 를 stock_ledger(PRD) 파생으로 보냈는데 그 원장에 PRD 이력이
       0건이라(컷오버 backfill 전) 조회하면 늘 빈 화면이었다. 정작 웹 바코드실적은
       PR_T_PROD_DTL / PR_T_MAT_STOCK_WH 에 쌓여 live 경로에서만 보였다.
       (웹 원장만 격리해서 보려면 source=ledger)"""
    f6, t6 = _digits(frm, 6), _digits(to, 6)
    y = _ym4(ym) or (f6[:4] if f6 else None) or _scalar("SELECT FORMAT(GETDATE(),'yyMM')")
    if source == "ledger":   # 웹 자체원장(stock_ledger)만 — 진단용
        r = _nx_screen("PRD", (f6 or y + "01"), (t6 or y + "31")); r["ym"] = y; return r
    stock, moves, partNames = _prodinout(y, f6 or None, t6 or None, src=source, inc_zero=bool(inc_zero))
    return {"ym": y, "frm": f6 or (y + "01"), "to": t6 or (y + "99"), "stock": stock, "moves": moves,
            "partNames": partNames, "inc_zero": bool(inc_zero)}

# ================= 제품입출고현황 (영업, dw_pr_stock_110) — 제품(P/N) 마스터-디테일 =================
# 유니버스=SA_T_ITEM_STOCK, BF=2502마감+2502~당월(고정base), 당월=[ym01,ym99]. patch_110.py 이식.
def _prodinvout(ym, frm=None, to=None):
    # 레거시 dw_pr_stock_110과 동일: 수불기간(frm~to). frm/to(YYMMDD) 우선, 없으면 ym월 전체.
    y01 = frm if frm else (ym + "01")
    y99 = to if to else (ym + "99")
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
    # ★유니버스 = 라이브 ∪ nx (큰 쪽). nx 에만 있는 웹 신규분도, 라이브에만 있는
    #   미러 미반영분도 둘 다 보여야 한다.
    _c1, uni = _rows("""SELECT item, MAX(snap) snap FROM (
           SELECT UPPER(item_code) item, SUM(stock_qty) snap FROM PARTNER_ERP_TEST3.nx.SA_T_ITEM_STOCK GROUP BY UPPER(item_code)
           UNION ALL
           SELECT UPPER(item_code), SUM(stock_qty) FROM PARTNER_ERP_TEST3.nx.SA_T_ITEM_STOCK GROUP BY UPPER(item_code)
         ) u GROUP BY item""")
    _c2, bfrows = _rows(f"SELECT item, SUM(q) bf FROM ({BF}) t GROUP BY item")
    _c3, moves = _rows(f"SELECT item, ymd, inq, outq, etc, div, cust FROM ({L1}) x")
    _c4, inforows = _rows("""SELECT UPPER(item_code) item, item_name, (SELECT cust_desc FROM PARTNER_ERP_TEST3.nx.cm_m_cust c WHERE c.cust_code=i.in_cust) work_nm FROM PARTNER_ERP_TEST3.nx.item i""")
    info = {r["item"]: r for r in inforows}
    bfm = {r["item"]: float(r["bf"] or 0) for r in bfrows}
    net = {}
    for r in moves:  # 재고 = 기초+입고-출고-기타출고(etc=maint_qty*-1 → 빼기)
        it = r["item"]
        net[it] = net.get(it, 0) + (float(r["inq"] or 0) - float(r["outq"] or 0) - float(r["etc"] or 0))
    # ★2026-08-25 현재고 = 잔액 스냅샷(SA_T_ITEM_STOCK) 정본.
    #   생산입출고(_prodinout)와 같은 이유 — BF+net 은 원천 하나만 미러가 늦어도
    #   값이 통째로 어긋나고, 0 이 되면 목록에서 사라진다(실측 nx 0행).
    #   잔액 테이블은 웹 실적/조정이 즉시 반영되는 정본이다.
    stock = []
    for u in uni:
        it = u["item"]; bf = bfm.get(it, 0); stv = float(u.get("snap") or 0)
        if abs(stv) <= 0.0001:
            continue
        d = info.get(it, {})
        stock.append([it, (d.get("item_name") or ""), (d.get("work_nm") or ""), round(stv, 3), round(bf, 3)])
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
def prodinvout(ym: str = Query(""), frm: str = Query(""), to: str = Query(""), source: str = Query("live")):
    """제품입출고현황(레거시 dw_pr_stock_110). 수불기간 frm~to(YYMMDD) 우선. 없으면 ym 월전체(하위호환). source=nx면 stock_ledger(ASY) 파생."""
    f6, t6 = _digits(frm, 6), _digits(to, 6)
    y = _ym4(ym) or (f6[:4] if f6 else None) or _scalar("SELECT FORMAT(GETDATE(),'yyMM')")
    # ★2026-08-25 생산·자재입출고와 동일하게 통일.
    #   nx(기본) = 라이브 + 웹실적 / live = 라이브만 / ledger = 웹 자체원장(진단용)
    if source == "ledger":
        r = _nx_screen("ASY", (f6 or y + "01"), (t6 or y + "31")); r["ym"] = y; return r
    stock, moves = _prodinvout(y, f6 or None, t6 or None)
    return {"ym": y, "frm": f6 or (y + "01"), "to": t6 or (y + "99"), "stock": stock, "moves": moves}

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
       ELSE (SELECT cust_desc FROM PARTNER_ERP_TEST3.nx.cm_m_cust WHERE cust_code=M.in_cust) END wc,
  M.item_name nm, pi.REMARKS remarks
FROM PARTNER_ERP_TEST3.nx.sa_t_sale_dtl a JOIN PARTNER_ERP_TEST3.nx.item m ON a.item_code=m.item_code
 OUTER APPLY (SELECT TOP 1 REMARKS FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_INPUT WHERE WORK_ORDER=a.WORK_ORDER) pi
WHERE a.sale_ymd BETWEEN '{f}' AND '{t}'
"""
    _c, rows = _rows(sql)
    return {"dfrom": f, "dto": t, "count": len(rows), "rows": rows}

# ================= 제품재고조회 (영업, dw_pr_stock_040) — 제품수불 플랫 =================
# 기초(2502+~기간전)+입고-출고-기타출고=재고. export_web_data.py _S040 이식, 기간 파라미터화(base 2502 고정).
@live_router.get("/salesstock")
def salesstock(dfrom: str = Query(""), dto: str = Query(""), source: str = Query("live"), zero: str = Query("")):
    """제품재고조회. 기본 source=live(현행 무변경). source=nx면 stock_ledger(ASY) 파생(컷오버 전 빈데이터 사유표시). dfrom~dto=YYMMDD.
    zero=1이면 최종재고 0인 품목도 포함(레거시 w_pr_stock_040 2,172건과 동일 gross 대조용). 기본=0재고 숨김."""
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
SELECT t.mat cd, max(M.item_name) nm, max(m.item_spec) spec, max(m.item_class) cls,
   sum(t.basic) basic, sum(t.inq) inq, sum(t.outq) outq, sum(t.etc) adj,
   sum(t.basic+t.inq-t.etc-t.outq) qty,
   (select top 1 item_cost from PARTNER_ERP_TEST3.nx.pr_m_item_cost where item_code=t.mat and cost_apply_ymd<='{t}' and cost_tag in ('S','E') order by cost_apply_ymd desc) cost,
   case when max(m.work_code)>'' then (select work_desc from PARTNER_ERP_TEST3.nx.pr_m_work where work_code=max(m.work_code))
        else (select cust_desc from PARTNER_ERP_TEST3.nx.cm_m_cust where cust_code=max(M.in_cust)) end wc
FROM t JOIN PARTNER_ERP_TEST3.nx.item m ON t.mat=m.item_code
GROUP BY t.mat
"""
    _c, rows = _rows(sql)
    inc_zero = str(zero).strip() in ("1", "true", "y", "Y")
    out = []
    for r in rows:
        q = float(r["qty"] or 0)
        if abs(q) <= 0.0001 and not inc_zero:
            continue
        cost = float(r["cost"] or 0)
        r["amt"] = round(q * cost)
        r["qty"] = q
        out.append(r)
    # ★단가·금액을 영업 수불장과 동일하게(대표 확정 '가' — 생산과 같은 방침).
    #   영업 수불장 단가 = **판가 기반 이동평균**(_snap_sal · 신고 평가방법 §7-4).
    #   여기서 as-of 판가를 그대로 쓰면 두 화면이 갈린다(실측: 단가 89건·금액 45건 불일치).
    #   ※영업은 품번 1축이다(생산은 품번×재고위치 2축) → keyloc=False.
    #   ※수불장에 없는 품목은 손대지 않는다 — 없는 값을 만들어내지 않는다.
    _apply_ledger_price(out, f, t, domain="SAL", keyloc=False)
    out.sort(key=lambda r: -abs(r.get("amt") or 0))
    return {"dfrom": f, "dto": t, "count": len(out), "zero": 1 if inc_zero else 0, "rows": out}

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
FROM PARTNER_ERP.dbo.SA_T_LG_RECEIVING_DTL a  -- ★컷오버 flip 대상(→nx). 업로드=nx 쓰기(routers/lgrecv.py)
WHERE a.receiving_ymd BETWEEN '{fr6}' AND '{to6}'
GROUP BY a.item_code, ISNULL(a.mkt,''), a.receiving_ymd""")
    _c2, items = _rows(f"""
SELECT m.item_code item,
  CASE WHEN m.work_code>'' THEN m.work_code ELSE M.in_cust END wcc,
  CASE WHEN m.work_code>'' THEN (SELECT work_desc FROM PARTNER_ERP_TEST3.nx.pr_m_work WHERE work_code=m.work_code)
       ELSE (SELECT cust_desc FROM PARTNER_ERP_TEST3.nx.cm_m_cust WHERE cust_code=M.in_cust) END wc
FROM PARTNER_ERP_TEST3.nx.item m
WHERE m.item_code IN (SELECT DISTINCT item_code FROM PARTNER_ERP.dbo.SA_T_LG_RECEIVING_DTL WHERE receiving_ymd BETWEEN '{fr6}' AND '{to6}')""")
    return {"fr": fr6, "to": to6, "ym": fr6[:4], "cells": cells, "items": items}

# ================= 생산재고조회 (생산, dw_pr_stock_040/480) — 가공(P0001)/용접(그외) 라인재고 =================
# 원장 9-union(2502기초+당월이동), 라인별 집계. export_web_data.py prodStock 이식, 레거시 pr_m_item 조인.
def _apply_ledger_price(rows, fr6, to6, domain="PRD", keyloc=True):
    """★단가·금액을 **생산 수불장과 동일**하게 맞춘다. 맞춘 행 수를 돌려준다.

       왜 수불장 결과를 그대로 쓰나 — 수불장 단가는 조회값이 아니라
       **기초 + 입고 가중평균을 일자별로 굴린 결과(avg)** 다.
       같은 식을 여기서 다시 짜면 반드시 갈린다(§21: 화면이 따로 계산하면 값이 갈린다).
       ⟹ `close._prd_ledger` 를 **그대로 호출**한다. 같은 함수 = 같은 값.
       (성능은 close._LEDGER_CACHE 가 (도메인,기간) 단위로 흡수한다.)

       ★대표 확정 2026-08-29: 재고조회를 수불장에 맞춘다.
         이로써 레거시 w_pr_stock_480(마스터 단가)과는 달라진다 — 그 대가를 알고 택했다.
    """
    try:
        from routers.close import ledger_cached          # ★엔드포인트와 캐시 공유
    except Exception:
        return 0
    cn = _nxc(); cur = cn.cursor()
    try:
        _r = ledger_cached(cur, domain, fr6, to6)        # ★(rows, breaks, basis) 3-튜플
        lrows = _r[0] if isinstance(_r, tuple) else _r
    except Exception as _e:
        # ★삼키지 않는다 — 조용히 실패하면 값이 안 맞는 걸 못 본다.
        #   단 full traceback 은 찍지 않는다(마감 배치에서 재귀 출력으로 로그가 터졌다 2026-08-30).
        print(f"[_apply_ledger_price] {type(_e).__name__}: {str(_e)[:150]}")
        return 0
    finally:
        cn.close()
    # ★생산은 (품번,재고위치) 2축, 영업은 품번 1축이다(수불장 축을 그대로 따른다)
    def _k(r, loc_field="loc"):
        cd = str(r.get("cd") or r.get("mat") or "").strip()
        return (cd, str(r.get(loc_field) or "").strip()) if keyloc else cd
    px = {}
    for r in lrows:
        px[_k(r)] = float(r.get("avg") or 0)
    n = 0
    for r in rows:
        k = _k(r)
        if k in px:
            u = px[k]
            r["cost"] = u
            r["amt"] = float(round(float(r.get("qty") or 0) * u))
            r["cost_src"] = "수불장(이동평균)"
            n += 1
    # ★수불장에 없는 품목은 **손대지 않는다** — 수불장이 단가0·음수를 스냅샷에서 빼기 때문이다
    #   (_snap_bulk 제외규칙). 없는 값을 만들어내지 않는다.
    return n


def _fill_bom_price(rows, target):
    """★단가를 못 구한 품목을 **BOM 하위 부품 합산**으로 채운다. 채운 행 수를 돌려준다.

       왜 필요한가 — SUB·은납 반제품은 `pr_m_item_cost` 에 단가가 없어 **금액이 0 으로 빠진다.**
         실측(2026-08-29 · 용접): 1,009행 중 126행 단가없음 → 재고금액이 23% 과소계상.
       ★생산 수불장·마감(`close._prd_price_bom`)이 **이미 같은 일을 하고 있다.**
         그래서 여기서 새로 짜지 않고 **그 함수를 그대로 부른다** —
         따로 짜면 두 화면 금액이 갈려 비교가 안 된다(사용자 요구: 값이 동일해야 비교 가능).
       규칙도 수불장과 같다: **못 구한 것만** 채운다. 이미 단가가 있으면 손대지 않는다.
    """
    need = sorted({str(r.get("cd") or "").strip() for r in rows
                   if not float(r.get("cost") or 0) and float(r.get("qty") or 0)})
    if not need:
        return 0
    try:
        from routers.close import _prd_price_bom          # ★순환 임포트 회피 — 함수 안에서
    except Exception:
        return 0
    cn = _nxc(); cur = cn.cursor()          # ★조회 전용(readonly) — _prd_price_bom 은 SELECT 만 한다
    try:
        px = _prd_price_bom(cur, str(target), need)
    except Exception:
        return 0
    finally:
        cn.close()
    n = 0
    for r in rows:
        cd = str(r.get("cd") or "").strip()
        hit = px.get(cd)
        if hit and not float(r.get("cost") or 0):
            u = float(hit[0] or 0)
            if not u:
                continue
            r["cost"] = u
            # 금액 반올림은 SQL(CAST(ROUND(...,0)))과 맞춘다
            r["amt"] = float(round(float(r.get("qty") or 0) * u))
            r["cost_src"] = "BOM부품합산"          # 화면이 출처를 표시할 수 있게
            n += 1
    return n


def _prodstock(ym, frm=None, to=None):
    # 레거시 w_pr_stock_480과 동일: 수불기간(frm~to) 일범위. frm/to(YYMMDD) 우선, 없으면 ym월 전체.
    y01 = frm if frm else (ym + "01")
    y99 = to if to else (ym + "99")
    U = f"""
SELECT a.gagong_proc_code gpc, A.MAT_CODE mat, A.STOCK_QTY basic,0 inq,0 outq,0 etc FROM PARTNER_ERP_TEST3.nx.PR_T_MONTH_STOCK_WH A WHERE A.STOCK_YYMM='2502'
UNION ALL SELECT a.to_gagong_proc_code,A.MAT_CODE,iif(a.maint_ymd<'{y01}',-A.MAINT_QTY,0),iif(a.maint_ymd<'{y01}',0,-A.MAINT_QTY),0,0 FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{y99}' AND a.maint_tag='B' AND isnull(a.out_wh_gubun,'1')='1'
UNION ALL SELECT A.gagong_proc_code,a.mat_code,iif(a.cut_ymd<'{y01}',a.cut_QTY,0),iif(a.cut_ymd<'{y01}',0,a.cut_QTY),0,0 FROM (SELECT * FROM PARTNER_ERP_TEST3.nx.pu_t_cut_dtl UNION ALL SELECT n.* FROM PARTNER_ERP_TEST3.nx.pu_t_cut_dtl n WHERE NOT EXISTS(SELECT 1 FROM PARTNER_ERP_TEST3.nx.pu_t_cut_dtl l WHERE l.BOX_NO=n.BOX_NO AND l.CUT_YMD=n.CUT_YMD AND l.CUT_HMS=n.CUT_HMS)) a WHERE A.cut_ymd>'250299' and A.cut_ymd<='{y99}'
UNION ALL SELECT a.to_gagong_proc_code,A.MAT_CODE,iif(a.MAINT_YMD<'{y01}',a.MAINT_QTY,0),0,iif(a.MAINT_YMD<'{y01}',0,-a.MAINT_QTY),0 FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{y99}' AND a.maint_tag='T' and isnull(a.out_wh_gubun,'3')='3'
UNION ALL SELECT a.to_gagong_proc_code,A.MAT_CODE,iif(a.MAINT_YMD<'{y01}',-a.MAINT_QTY,0),0,iif(a.MAINT_YMD<'{y01}',0,a.MAINT_QTY),0 FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{y99}' AND a.maint_tag='C'
UNION ALL SELECT A.stock_part_code,a.item_code,iif(a.prod_ymd<'{y01}',a.prod_qty,0),iif(a.prod_ymd<'{y01}',0,a.prod_qty),0,0 FROM PARTNER_ERP_TEST3.nx.pr_t_prod_dtl a WHERE A.prod_ymd>'250299' and A.prod_ymd<='{y99}' and a.stock_part_code>'' and not exists (select 1 from PARTNER_ERP_TEST3.nx.sa_t_stock_maint where maint_ymd=a.prod_ymd and item_code=a.item_code and in_part_code=a.stock_part_code)
UNION ALL SELECT A.IN_PART_CODE,a.item_code,iif(a.MAINT_YMD<'{y01}',a.MAINT_QTY,0),iif(a.MAINT_YMD<'{y01}',0,a.MAINT_QTY),0,0 FROM PARTNER_ERP_TEST3.nx.sa_t_stock_maint a WHERE A.maint_ymd>'250299' and A.MAINT_YMD<='{y99}' and a.in_part_code>''
UNION ALL SELECT A.PART_CODE,A.MAT_CODE,iif(a.MAINT_YMD<'{y01}',a.MAINT_QTY,0),iif(a.MAINT_YMD<'{y01}',0,a.MAINT_QTY),0,0 FROM PARTNER_ERP_TEST3.nx.PR_T_STOCK_MAINT_MAT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{y99}' AND A.MAINT_TAG='3'
UNION ALL SELECT A.PART_CODE,A.MAT_CODE,iif(a.MAINT_YMD<'{y01}',a.MAINT_QTY,0),0,0,iif(a.MAINT_YMD<'{y01}',0,a.MAINT_QTY) FROM PARTNER_ERP_TEST3.nx.PR_T_STOCK_MAINT_MAT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{y99}' AND A.MAINT_TAG in ('2','1')
UNION ALL SELECT A.PART_CODE,A.MAT_CODE,iif(a.MAINT_YMD<'{y01}',a.MAINT_QTY,0),0,iif(a.MAINT_YMD<'{y01}',0,-a.MAINT_QTY),0 FROM PARTNER_ERP_TEST3.nx.PR_T_STOCK_MAINT_MAT A JOIN PARTNER_ERP_TEST3.nx.item M ON A.MAT_CODE=M.ITEM_CODE WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{y99}' AND A.MAINT_TAG='4'
"""
    # ★단가 상관서브쿼리를 OUTER APPLY로 1회만 계산(기존엔 cost·amt에 2회 → 품목당 2배). 값 동일·성능개선.
    C2A = f"select top 1 q.item_cost cost from PARTNER_ERP_TEST3.nx.pr_m_item_cost q where q.item_code=agg.mat and q.cost_tag='1' and q.cost_apply_ymd<='{y01}' and q.cust_code=case when pi.work_code='P2' then '2228' else pi.in_cust end order by q.cost_apply_ymd desc"
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
  agg.mat cd, pi.item_name nm, ISNULL(pi.item_class,'') type,
  agg.basic, agg.inq, agg.outq, agg.adj, agg.qty,
  cc.cost cost, CAST(ROUND(agg.qty*ISNULL(cc.cost,0),0) AS DECIMAL(18,0)) amt
FROM agg JOIN PARTNER_ERP_TEST3.nx.item pi ON pi.item_code=agg.mat
  OUTER APPLY ({C2A}) cc
"""
    _c, rows = _rows(sql)
    # ★단가·금액을 생산 수불장과 동일하게 맞춘다(대표 확정 '가').
    #   수불장 단가에는 BOM 하위 합산·자재단가 보정이 **이미 들어 있다** —
    #   그래서 _fill_bom_price 를 따로 부르지 않는다(이중 적용 방지).
    _n = _apply_ledger_price(rows, (frm or (ym + "01")), y99)
    if not _n:
        # 수불장을 못 얻은 경우에만 최소 보강(단가 0 인 SUB 를 BOM 합산으로) — 화면이 빈손이 되지 않게
        _fill_bom_price(rows, y99)
    return rows

@live_router.get("/prodstock")
def prodstock(ym: str = Query(""), frm: str = Query(""), to: str = Query(""), source: str = Query("live")):
    """생산재고조회(레거시 w_pr_stock_480). 수불기간 frm~to(YYMMDD) 우선 = 레거시 화면과 동일 일범위.
    frm/to 없으면 ym(YYMM) 월전체(하위호환). source=nx면 stock_ledger(PRD) 파생."""
    f6, t6 = _digits(frm, 6), _digits(to, 6)
    y = _ym4(ym) or (f6[:4] if f6 else None) or _scalar("SELECT FORMAT(GETDATE(),'yyMM')")
    if source == "nx":
        r = _nx_screen("PRD", (f6 or y + "01"), (t6 or y + "31")); r["ym"] = y; return r
    rows = _prodstock(y, f6 or None, t6 or None)
    return {"ym": y, "frm": f6 or (y + "01"), "to": t6 or (y + "99"), "rows": rows}

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
