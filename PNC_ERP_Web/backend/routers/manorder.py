# -*- coding: utf-8 -*-
"""manorder 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ================= 수동발주 (구매/자재, w_pr_input_410 시나리오) =================
@router.get("/api/manorder/vendors")
def manorder_vendors(q: str = Query("")):
    """매입처 검색(그 업체가 납품하는 품목 보유=IN_CUST_CODE). 단일선택 코드 구분."""
    cn = _conn(); cur = cn.cursor()
    try:
        like = f"%{q.strip()}%"
        cur.execute("""SELECT TOP 30 C.CUST_CODE, MAX(C.CUST_DESC) nm, MAX(C.CUST_TYPE) ct, COUNT(M.ITEM_CODE) items
          FROM CM_M_CUST C JOIN PR_M_ITEM M ON M.IN_CUST_CODE=C.CUST_CODE AND ISNULL(M.ITEM_STATUS,'1') IN ('1','2')
          WHERE (C.CUST_CODE LIKE ? OR C.CUST_DESC LIKE ?)
          GROUP BY C.CUST_CODE HAVING COUNT(M.ITEM_CODE)>0
          ORDER BY COUNT(M.ITEM_CODE) DESC""", like, like)
        return {"rows": [{"cc": r[0], "nm": r[1], "ct": r[2], "items": r[3]} for r in cur.fetchall()]}
    finally:
        cn.close()

@router.get("/api/manorder/items")
def manorder_items(cc: str = Query(...), ym: str = Query("")):
    """선택 업체 품목별 계획수량·현재고. ★계획 윈도우 = 오늘~+1개월(from6~to6). 좌측 계획수량·우측 일자별 동일 윈도우 → 계=계획수량. ym(YYMM) 지정 시 해당 월 전체."""
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("SELECT FORMAT(GETDATE(),'yyMMdd'), FORMAT(DATEADD(MONTH,1,GETDATE()),'yyMMdd')")
        from6, to6 = cur.fetchone()
        y = _dig4(ym)
        if y:                       # 특정 월 지정 시 그 달 전체
            from6, to6 = y + "01", y + "99"
        cur.execute("SELECT MAX(STOCK_YYMM) FROM PU_T_MONTH_STOCK_WH")
        smax = cur.fetchone()[0]
        # 계획수량: 부품 접미사 제거한 부모 도번 기준(부모별 1회 집계 후 조인=고속). 기발주=PU_T_PURCHASE_DTL 미입고잔량.
        cur.execute("""
          WITH PLANP AS (
            SELECT LEFT(C_ITEM_CODE, CASE WHEN CHARINDEX('-',C_ITEM_CODE)>0 THEN CHARINDEX('-',C_ITEM_CODE)-1 ELSE LEN(C_ITEM_CODE) END) parent, SUM(PLAN_QTY) pq
            FROM PR_T_PLAN_ITEM_DTL WHERE PLAN_YMD BETWEEN ? AND ?
            GROUP BY LEFT(C_ITEM_CODE, CASE WHEN CHARINDEX('-',C_ITEM_CODE)>0 THEN CHARINDEX('-',C_ITEM_CODE)-1 ELSE LEN(C_ITEM_CODE) END))
          SELECT M.ITEM_CODE ic, M.ITEM_DESC nm, ISNULL(M.ITEM_SPEC,'') spec, ISNULL(M.UNIT,'EA') unit,
            ISNULL(PP.pq,0) plan_qty, ISNULL(S.sq,0) stock_qty, ISNULL(PO.remain,0) po_qty
          FROM PR_M_ITEM M
          LEFT JOIN PLANP PP ON PP.parent = LEFT(M.ITEM_CODE, CASE WHEN CHARINDEX('-',M.ITEM_CODE)>0 THEN CHARINDEX('-',M.ITEM_CODE)-1 ELSE LEN(M.ITEM_CODE) END)
          LEFT JOIN (SELECT MAT_CODE, SUM(STOCK_QTY) sq FROM PU_T_MONTH_STOCK_WH WHERE STOCK_YYMM=? GROUP BY MAT_CODE) S ON S.MAT_CODE=M.ITEM_CODE
          LEFT JOIN (SELECT ITEM_CODE, SUM(PUR_QTY-ISNULL(IN_QTY,0)-ISNULL(CANCEL_QTY,0)) remain
             FROM PU_T_PURCHASE_DTL WHERE CUST_CODE=? AND ISNULL(IN_FINISH_FLAG,'N')<>'Y'
             GROUP BY ITEM_CODE HAVING SUM(PUR_QTY-ISNULL(IN_QTY,0)-ISNULL(CANCEL_QTY,0))>0) PO ON PO.ITEM_CODE=M.ITEM_CODE
          WHERE M.IN_CUST_CODE=? AND ISNULL(M.ITEM_STATUS,'1') IN ('1','2')
          ORDER BY ISNULL(PP.pq,0) DESC, M.ITEM_CODE""", from6, to6, smax, cc, cc)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["plan_qty"] = float(r["plan_qty"] or 0); r["stock_qty"] = float(r["stock_qty"] or 0)
            r["po_qty"] = float(r["po_qty"] or 0)  # 기발주 = PU_T_PURCHASE_DTL 미입고 발주잔량
        # ★우측 협력사 일자별 계획 = 좌측과 동일 소스(PR_T_PLAN_ITEM_DTL). 부모 도번별 PLAN_YMD 분포 → 일자별 합 = 좌측 계획수량.
        cur.execute("""
          WITH ITM AS (SELECT DISTINCT LEFT(ITEM_CODE, CASE WHEN CHARINDEX('-',ITEM_CODE)>0 THEN CHARINDEX('-',ITEM_CODE)-1 ELSE LEN(ITEM_CODE) END) parent
                       FROM PR_M_ITEM WHERE IN_CUST_CODE=? AND ISNULL(ITEM_STATUS,'1') IN ('1','2'))
          SELECT LEFT(D.C_ITEM_CODE, CASE WHEN CHARINDEX('-',D.C_ITEM_CODE)>0 THEN CHARINDEX('-',D.C_ITEM_CODE)-1 ELSE LEN(D.C_ITEM_CODE) END) parent,
                 D.PLAN_YMD ymd, SUM(D.PLAN_QTY) pq
          FROM PR_T_PLAN_ITEM_DTL D
          JOIN ITM ON ITM.parent = LEFT(D.C_ITEM_CODE, CASE WHEN CHARINDEX('-',D.C_ITEM_CODE)>0 THEN CHARINDEX('-',D.C_ITEM_CODE)-1 ELSE LEN(D.C_ITEM_CODE) END)
          WHERE D.PLAN_YMD BETWEEN ? AND ?
          GROUP BY LEFT(D.C_ITEM_CODE, CASE WHEN CHARINDEX('-',D.C_ITEM_CODE)>0 THEN CHARINDEX('-',D.C_ITEM_CODE)-1 ELSE LEN(D.C_ITEM_CODE) END), D.PLAN_YMD""", cc, from6, to6)
        daily = {}; dset = set()
        for pr, ymd, pq in cur.fetchall():
            ymd = str(ymd).strip(); dset.add(ymd)
            daily.setdefault(str(pr).strip(), {})[ymd] = float(pq or 0)
        dates = sorted(dset)
        def _par(ic):
            ic = str(ic or ""); i = ic.find("-"); return ic[:i] if i > 0 else ic
        for r in rows:
            r["days"] = daily.get(_par(r["ic"]), {})
        cn2 = _conn(); c2 = cn2.cursor()
        try:
            c2.execute("SELECT CUST_DESC FROM CM_M_CUST WHERE CUST_CODE=?", cc)
            rr = c2.fetchone(); nm = rr[0] if rr else cc
        finally:
            cn2.close()
        ymlbl = f"{from6[0:2]}/{from6[2:4]}/{from6[4:6]}~{to6[0:2]}/{to6[2:4]}/{to6[4:6]}"
        return {"cc": cc, "cust_name": nm, "ym": ymlbl, "from_ymd": from6, "to_ymd": to6, "stock_ym": smax, "rows": rows, "dates": dates}
    finally:
        cn.close()
