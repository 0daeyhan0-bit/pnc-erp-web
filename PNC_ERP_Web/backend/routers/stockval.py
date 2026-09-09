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
    """업체별(매입처) 재고금액. **우리 월마감 확정 스냅샷**(nx.stock_snapshot, domain='MAT')을
    매입처(nx.item.in_cust)로 집계한다. incust 지정 시 그 매입처 자재 명세.

    ★2026-09-08 원천 교체 — 종전엔 레거시 PU_T_MONTH_STOCK_WH 를 읽었다. 두 가지가 잘못이다:
      ① 그 테이블은 레거시가 채운다 → **2607 까지밖에 없어 2608 조회가 0행**이었고,
         컷오버 후에는 영구히 빈다(하드룰: 컷오버 후 단일 테이블·폴백 금지).
      ② 값도 우리 마감과 다르다(2607 실측 레거시 4,473,853,756 vs 우리 마감 4,396,686,967).
      ⟹ 수불장·생산재고480·제품재고040 과 **같은 원천**(마감 스냅샷)을 본다.
    ※제외분(stock_snapshot_drop = 단가0·음수·잔량0)도 함께 읽는다 — 표시·평가에서 뺀 것이지
      재고가 없던 것이 아니다(§7 기초연쇄 규칙과 동일). 그래야 수불장 기말 합계와 일치한다.
    라이브·읽기전용."""
    SNAP = """(SELECT item_code, stock_qty, stock_amt, avg_cost, period
                 FROM PARTNER_ERP_TEST3.nx.stock_snapshot WHERE domain='MAT' AND ptype='M'
               UNION ALL
               SELECT item_code, stock_qty, stock_amt, avg_cost, period
                 FROM PARTNER_ERP_TEST3.nx.stock_snapshot_drop WHERE domain='MAT' AND ptype='M')"""
    cn = _conn(); cur = cn.cursor()
    try:
        y = _dig4(ym)
        cur.execute("""SELECT period FROM PARTNER_ERP_TEST3.nx.period_close
                        WHERE domain='MAT' AND ptype='M' AND close_flag=1 ORDER BY period DESC""")
        months = [r[0] for r in cur.fetchall()][:24]
        if not y:
            y = months[0] if months else ""
        if not y:
            return {"mode": "summary", "ym": "", "months": [], "rows": [], "cnt": 0, "sum_amt": 0.0,
                    "msg": "확정된 자재 월마감이 없습니다 — 마감관리에서 월마감을 먼저 실행하세요."}
        if incust.strip():
            cur.execute(f"""SELECT TOP 5000 W.item_code mat, ISNULL(M.item_name,'') nm, ISNULL(M.item_spec,'') spec,
                  ISNULL(M.unit,'') unit, SUM(W.stock_qty) qty, MAX(W.avg_cost) cost, SUM(W.stock_amt) amt
                FROM {SNAP} W JOIN PARTNER_ERP_TEST3.nx.item M ON M.item_code=W.item_code
                WHERE W.period=? AND ISNULL(M.in_cust,'')=?
                GROUP BY W.item_code, M.item_name, M.item_spec, M.unit HAVING SUM(W.stock_qty)<>0
                ORDER BY SUM(W.stock_amt) DESC""", y, incust.strip())
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            for r in rows:
                r["qty"] = float(r["qty"] or 0); r["cost"] = float(r["cost"] or 0); r["amt"] = float(r["amt"] or 0)
            return {"mode": "detail", "ym": y, "months": months, "incust": incust.strip(),
                    "rows": rows, "cnt": len(rows), "sum_amt": sum(r["amt"] for r in rows)}
<<<<<<< HEAD
        cur.execute("""SELECT ISNULL(M.in_cust,'') incust, MAX(ISNULL(C.CUST_DESC,'')) nm,
              COUNT(DISTINCT W.MAT_CODE) items, SUM(W.STOCK_QTY) qty, SUM(W.STOCK_AMT) amt
            FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH W JOIN PARTNER_ERP_TEST3.nx.item M ON M.item_code=W.MAT_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.v_cm_m_cust C ON C.CUST_CODE=M.in_cust
            WHERE W.STOCK_YYMM=? GROUP BY M.in_cust HAVING SUM(W.STOCK_AMT)<>0
            ORDER BY SUM(W.STOCK_AMT) DESC""", y)
=======
        cur.execute(f"""SELECT ISNULL(M.in_cust,'') incust, MAX(ISNULL(C.CUST_DESC,'')) nm,
              COUNT(DISTINCT W.item_code) items, SUM(W.stock_qty) qty, SUM(W.stock_amt) amt
            FROM {SNAP} W JOIN PARTNER_ERP_TEST3.nx.item M ON M.item_code=W.item_code
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST C ON C.CUST_CODE=M.in_cust
            WHERE W.period=? GROUP BY M.in_cust HAVING SUM(W.stock_amt)<>0
            ORDER BY SUM(W.stock_amt) DESC""", y)
>>>>>>> zt/main
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["items"] = int(r["items"] or 0); r["qty"] = float(r["qty"] or 0); r["amt"] = float(r["amt"] or 0)
        return {"mode": "summary", "ym": y, "months": months, "rows": rows, "cnt": len(rows),
                "sum_amt": sum(r["amt"] for r in rows)}
    finally:
        cn.close()
