# -*- coding: utf-8 -*-
"""purmagam 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ================= 매입마감처리 (구매/자재, w_pu_sale_010) — 거래처별, 확정입고(매입) =================
def _pur_src(win):
    """확정입고(매입) 원천: 9/S/C/G/H(검사통과) + 수입(_C DIVISION=P). 금액 양수. win=마감기준 조건(mg 참조)."""
    return f"""
    SELECT A.CUST_CODE cc, A.MAT_CODE mat, A.MAINT_COST cost, A.MAINT_YMD ymd, A.MAINT_QTY qty, A.MAINT_AMT amt, A.MAINT_VAT vat
     FROM PU_T_STOCK_MAINT A JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
     WHERE {win} AND A.MAINT_TAG IN ('9','S','C','G','H')
       AND ((ISNULL(A.INSP_FLAG,'N') IN ('','N')) OR (ISNULL(A.INSP_FLAG,'N') IN ('S','F') AND A.INSP_PROC_YMD >= ''))
    UNION ALL
    SELECT A.CUST_CODE, A.MAT_CODE, A.MAINT_COST, A.MAINT_YMD, A.MAINT_QTY, A.MAINT_AMT, ISNULL(A.TAXPAYERS,0)
     FROM PU_T_STOCK_MAINT_C A JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
     WHERE {win} AND A.DIVISION='P'"""

@router.get("/api/purmagam/list")
def purmagam_list(ym: str = Query("")):
    """매입마감 거래처별 집계(확정입고, 마감기준) + nx 마감상태·조정합."""
    y = _dig4(ym) or _cur_ym()
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute(f"""{_SALE_MAGAM.format(ym=y)}
          SELECT S.cc cc, MAX(C.CUST_DESC) nm, MAX(C.CUST_TYPE) ct,
            MAX(LTRIM(RTRIM(ISNULL(NULLIF(C.CHARGE_USER_ID,''),ISNULL(C.CHARGE_NAME,''))))) chg,
            SUM(S.qty) qty, SUM(S.amt) amt, SUM(S.vat) vat, COUNT(DISTINCT S.mat) items
          FROM ({_pur_src(_sale_win().format(ym=y))}) S JOIN CM_M_CUST C ON S.cc=C.CUST_CODE
          GROUP BY S.cc HAVING SUM(S.amt)<>0 ORDER BY SUM(S.amt) DESC""")
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        cn.close()
    nx = _nx(); nc = nx.cursor()
    try:
        nc.execute("SELECT cust_code,close_flag,bill_flag FROM nx.pur_close WHERE ym=?", y)
        st = {r[0]: (int(r[1] or 0), int(r[2] or 0)) for r in nc.fetchall()}
        nc.execute("SELECT cust_code, SUM(delta_amt) FROM nx.pur_adjust WHERE ym=? GROUP BY cust_code", y)
        adj = {r[0]: float(r[1] or 0) for r in nc.fetchall()}
    finally:
        nx.close()
    for r in rows:
        cc = r["cc"]; s = st.get(cc, (0, 0))
        r["qty"] = float(r["qty"] or 0); r["amt"] = float(r["amt"] or 0); r["vat"] = float(r["vat"] or 0); r["items"] = int(r["items"] or 0)
        r["close_flag"] = s[0]; r["bill_flag"] = s[1]
        r["adj_amt"] = adj.get(cc, 0.0); r["final_amt"] = round(r["amt"] + adj.get(cc, 0.0), 2)
    return {"ym": y, "rows": rows}

@router.get("/api/purmagam/detail")
def purmagam_detail(ym: str = Query(""), cc: str = Query(...)):
    """매입 거래처 마감상세: 품목×일자 + 저장된 조정."""
    y = _dig4(ym) or _cur_ym()
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute(f"""{_SALE_MAGAM.format(ym=y)}
          SELECT S.mat mat, MAX(M.ITEM_DESC) nm, MAX(M.ITEM_SPEC) spec, MAX(M.UNIT) unit, S.cost cost,
            CAST(RIGHT(S.ymd,2) AS INT) d, SUM(S.qty) q, SUM(S.amt) amt
          FROM ({_pur_src(_sale_win().format(ym=y))}) S JOIN PR_M_ITEM M ON S.mat=M.ITEM_CODE
          WHERE S.cc=? GROUP BY S.mat, S.cost, CAST(RIGHT(S.ymd,2) AS INT)""", cc)
        raw = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    finally:
        cn.close()
    items = {}; days = set()
    for r in raw:
        mat = str(r["mat"]).strip(); d = int(r["d"] or 0); days.add(d)
        it = items.setdefault(mat, {"mat": mat, "nm": r["nm"], "spec": r["spec"], "unit": r["unit"],
                                    "cost": float(r["cost"] or 0), "qty": 0.0, "amt": 0.0, "_bd": {}})
        qv = float(r["q"] or 0); av = float(r["amt"] or 0); cv = float(r["cost"] or 0)
        it["qty"] += qv; it["amt"] += av
        bd = it["_bd"].setdefault(d, {"d": d, "qty": 0.0, "amt": 0.0, "cost": cv})
        bd["qty"] += qv; bd["amt"] += av; bd["cost"] = cv
    for it in items.values():
        it["byday"] = sorted(it.pop("_bd").values(), key=lambda x: x["d"])
    items_list = sorted(items.values(), key=lambda x: -abs(x["amt"]))
    nx = _nx(); nc = nx.cursor()
    try:
        nc.execute("""SELECT adj_seq,adj_type,scope,mat_code,target_ymd,old_cost,new_cost,old_qty,new_qty,delta_amt,reason_code,reason_detail
                      FROM nx.pur_adjust WHERE ym=? AND cust_code=? ORDER BY adj_seq""", y, cc)
        adjs = [{"adj_type": r[1], "scope": r[2], "mat_code": r[3], "target_ymd": r[4],
                 "old_cost": (float(r[5]) if r[5] is not None else None), "new_cost": (float(r[6]) if r[6] is not None else None),
                 "old_qty": (float(r[7]) if r[7] is not None else None), "new_qty": (float(r[8]) if r[8] is not None else None),
                 "delta_amt": float(r[9] or 0), "reason_code": r[10], "reason_detail": r[11]} for r in nc.fetchall()]
        nc.execute("SELECT close_flag FROM nx.pur_close WHERE ym=? AND cust_code=?", y, cc)
        cr = nc.fetchone(); closed = int(cr[0]) if cr else 0
    finally:
        nx.close()
    return {"ym": y, "cc": cc, "days": sorted(days), "items": items_list, "adjustments": adjs, "close_flag": closed}

@router.post("/api/purmagam/save")
def purmagam_save(payload: dict = Body(...)):
    """매입 조정 replace-all + 선택시 마감. 가드: 사유필수·이미마감 거부."""
    y = _dig4(payload.get("ym")); cc = str(payload.get("cust_code", "")).strip()
    adjs = payload.get("adjustments", []) or []; do_close = bool(payload.get("close"))
    base = float(payload.get("base_amt", 0) or 0)
    if not y or not cc:
        raise HTTPException(400, "ym·cust_code 필요")
    nx = _nx(); nc = nx.cursor()
    try:
        nc.execute("SELECT close_flag FROM nx.pur_close WHERE ym=? AND cust_code=?", y, cc)
        cr = nc.fetchone()
        if cr and int(cr[0]) == 1:
            raise HTTPException(409, "이미 마감된 거래처입니다. 마감취소 후 수정하세요.")
        for a in adjs:
            if float(a.get("delta_amt", 0) or 0) != 0 and not (a.get("reason_code") or (a.get("reason_detail") or "").strip()):
                raise HTTPException(400, "사유(코드 또는 세부내역)가 필요한 조정이 있습니다.")
        nc.execute("DELETE FROM nx.pur_adjust WHERE ym=? AND cust_code=?", y, cc)
        for a in adjs:
            nc.execute("""INSERT INTO nx.pur_adjust(ym,cust_code,adj_type,scope,mat_code,target_ymd,old_cost,new_cost,old_qty,new_qty,delta_amt,reason_code,reason_detail,ins_user)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", y, cc, a.get("adj_type"), a.get("scope"), a.get("mat_code"),
                       a.get("target_ymd"), a.get("old_cost"), a.get("new_cost"), a.get("old_qty"), a.get("new_qty"),
                       float(a.get("delta_amt", 0) or 0), a.get("reason_code"), a.get("reason_detail"), "web")
        adj_sum = sum(float(a.get("delta_amt", 0) or 0) for a in adjs)
        nc.execute("""MERGE nx.pur_close AS T USING (SELECT ? ym, ? cc) AS S ON T.ym=S.ym AND T.cust_code=S.cc
                      WHEN MATCHED THEN UPDATE SET base_amt=?, adj_amt=?, final_amt=?, close_flag=?, close_user=?, close_dt=?
                      WHEN NOT MATCHED THEN INSERT(ym,cust_code,base_amt,adj_amt,final_amt,close_flag,close_user,close_dt)
                        VALUES(?,?,?,?,?,?,?,?);""",
                   y, cc, base, adj_sum, base+adj_sum, (1 if do_close else 0), ("web" if do_close else None), (None),
                   y, cc, base, adj_sum, base+adj_sum, (1 if do_close else 0), ("web" if do_close else None), None)
        if do_close:
            nc.execute("UPDATE nx.pur_close SET close_flag=1, close_user='web', close_dt=GETDATE() WHERE ym=? AND cust_code=?", y, cc)
        return {"ok": True, "closed": do_close, "adj_sum": adj_sum}
    finally:
        nx.close()

@router.post("/api/purmagam/reopen")
def purmagam_reopen(payload: dict = Body(...)):
    y = _dig4(payload.get("ym")); cc = str(payload.get("cust_code", "")).strip()
    nx = _nx(); nc = nx.cursor()
    try:
        nc.execute("UPDATE nx.pur_close SET close_flag=0, close_dt=NULL WHERE ym=? AND cust_code=?", y, cc)
        return {"ok": True, "reopened": nc.rowcount}
    finally:
        nx.close()
