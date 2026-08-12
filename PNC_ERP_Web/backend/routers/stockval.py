# -*- coding: utf-8 -*-
"""stockval 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ============ 기준정보: 업체별 재고금액(월재고 스냅샷 → 매입처 집계) ============
@router.get("/api/stockval/list")
def stockval_list(ym: str = Query(""), incust: str = Query("")):
    """업체별(매입처) 재고금액. 월재고 스냅샷 PU_T_MONTH_STOCK_WH를 MAT→PR_M_ITEM.IN_CUST_CODE로 집계.
    incust 지정 시 해당 매입처 자재 명세. 라이브·읽기전용."""
    cn = _conn(); cur = cn.cursor()
    try:
        y = _dig4(ym)
        if not y:
            cur.execute("SELECT MAX(STOCK_YYMM) FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH"); y = cur.fetchone()[0]
        cur.execute("SELECT DISTINCT TOP 24 STOCK_YYMM FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH ORDER BY STOCK_YYMM DESC")
        months = [r[0] for r in cur.fetchall()]
        if incust.strip():
            cur.execute("""SELECT TOP 5000 W.MAT_CODE mat, ISNULL(M.ITEM_DESC,'') nm, ISNULL(M.ITEM_SPEC,'') spec,
                  ISNULL(M.UNIT,'') unit, SUM(W.STOCK_QTY) qty, MAX(W.STOCK_COST) cost, SUM(W.STOCK_AMT) amt
                FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH W JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM M ON M.ITEM_CODE=W.MAT_CODE
                WHERE W.STOCK_YYMM=? AND ISNULL(M.IN_CUST_CODE,'')=?
                GROUP BY W.MAT_CODE, M.ITEM_DESC, M.ITEM_SPEC, M.UNIT HAVING SUM(W.STOCK_QTY)<>0
                ORDER BY SUM(W.STOCK_AMT) DESC""", y, incust.strip())
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            for r in rows:
                r["qty"] = float(r["qty"] or 0); r["cost"] = float(r["cost"] or 0); r["amt"] = float(r["amt"] or 0)
            return {"mode": "detail", "ym": y, "months": months, "incust": incust.strip(),
                    "rows": rows, "cnt": len(rows), "sum_amt": sum(r["amt"] for r in rows)}
        cur.execute("""SELECT ISNULL(M.IN_CUST_CODE,'') incust, MAX(ISNULL(C.CUST_DESC,'')) nm,
              COUNT(DISTINCT W.MAT_CODE) items, SUM(W.STOCK_QTY) qty, SUM(W.STOCK_AMT) amt
            FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH W JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM M ON M.ITEM_CODE=W.MAT_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST C ON C.CUST_CODE=M.IN_CUST_CODE
            WHERE W.STOCK_YYMM=? GROUP BY M.IN_CUST_CODE HAVING SUM(W.STOCK_AMT)<>0
            ORDER BY SUM(W.STOCK_AMT) DESC""", y)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["items"] = int(r["items"] or 0); r["qty"] = float(r["qty"] or 0); r["amt"] = float(r["amt"] or 0)
        return {"mode": "summary", "ym": y, "months": months, "rows": rows, "cnt": len(rows),
                "sum_amt": sum(r["amt"] for r in rows)}
    finally:
        cn.close()
