# -*- coding: utf-8 -*-
"""partplandtl 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ================= 생산 ②: 파트별 생산계획 (w_pr_input_410) — PR_T_PLAN_PART_MAT 라이브 =================
# 협력사계획 생성결과(SP_PR_CREATE_PLAN_협력사계획_생성) = 도번→자도번 전개 + 작업처 라우팅 + 일자별 계획.
@router.get("/api/partplan/list")
def partplan_list(from_ymd: str = Query(""), to_ymd: str = Query(""), wc: str = Query(""),
                  part: str = Query(""), assy: str = Query(""), line: str = Query(""),
                  diam: str = Query(""), thick: str = Query(""), pipe: str = Query("")):
    cn = _conn(); cur = cn.cursor()
    try:
        w = ["p.PART_PLAN_QTY>0"]; pr = []
        if from_ymd: w.append("p.PART_PLAN_YMD>=?"); pr.append(_d6(from_ymd))
        if to_ymd:   w.append("p.PART_PLAN_YMD<=?"); pr.append(_d6(to_ymd))
        if wc.strip():   w.append("p.MAT_WORK_CENTER_CODE=?"); pr.append(wc.strip())
        if part.strip(): w.append("p.MAT_CODE LIKE ?"); pr.append(f"%{part.strip()}%")
        if assy.strip(): w.append("p.ASSY_ITEM_CODE LIKE ?"); pr.append(f"%{assy.strip()}%")
        if line.strip(): w.append("p.LINE_NO=?"); pr.append(line.strip())
        if diam.strip():  w.append("i.diam=?"); pr.append(float(diam))
        if thick.strip(): w.append("i.thick=?"); pr.append(float(thick))
        if pipe == '1':   w.append("i.METAL_GUBUN IN ('CU','고강도') AND ISNULL(i.diam,0)>0")  # 동파이프만
        cur.execute(f"""SELECT p.PART_PLAN_YMD, p.ASSY_ITEM_CODE, p.MAT_CODE, MAX(p.LINE_NO) line,
              p.MAT_WORK_CENTER_CODE wc,
              MAX(COALESCE(w.WORK_DESC, cu.CUST_DESC, '')) wcnm, MAX(ISNULL(i.item_name,'')) nm,
              MAX(ISNULL(i.diam,0)) diam, MAX(ISNULL(i.thick,0)) thick, MAX(ISNULL(i.length,0)) length,
              MAX(p.CUM_USE_QTY) useq, SUM(p.PART_PLAN_QTY) pq
            FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_PART_MAT p
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_WORK w ON w.WORK_CODE=p.MAT_WORK_CENTER_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST cu ON cu.CUST_CODE=p.MAT_WORK_CENTER_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.item i ON i.ITEM_CODE=p.MAT_CODE
            WHERE {' AND '.join(w)}
            GROUP BY p.PART_PLAN_YMD, p.ASSY_ITEM_CODE, p.MAT_CODE, p.MAT_WORK_CENTER_CODE""", *pr)
        cols = [d[0] for d in cur.description]
        raw = [dict(zip(cols, r)) for r in cur.fetchall()]
        dates = sorted({r["PART_PLAN_YMD"] for r in raw})
        keyed = {}
        for r in raw:
            k = (r["ASSY_ITEM_CODE"], r["MAT_CODE"], r["wc"])
            g = keyed.get(k)
            if not g:
                g = {"assy": r["ASSY_ITEM_CODE"], "part": r["MAT_CODE"], "nm": r["nm"], "line": r["line"],
                     "wc": r["wc"], "wcnm": r["wcnm"], "use": float(r["useq"] or 0),
                     "diam": float(r["diam"] or 0), "thick": float(r["thick"] or 0), "length": float(r["length"] or 0),
                     "days": {}, "tot": 0}
                keyed[k] = g
            q = float(r["pq"] or 0); g["days"][r["PART_PLAN_YMD"]] = g["days"].get(r["PART_PLAN_YMD"], 0) + q; g["tot"] += q
        rows = sorted(keyed.values(), key=lambda x: (x["wcnm"] or "", x["part"]))
        return {"dates": dates, "rows": rows, "part_count": len(rows),
                "sum_qty": sum(float(r["pq"] or 0) for r in raw)}
    finally:
        cn.close()

@router.get("/api/partplan/workcenters")
def partplan_workcenters():
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("""SELECT p.MAT_WORK_CENTER_CODE cc, COALESCE(w.WORK_DESC, cu.CUST_DESC, '') nm, COUNT(*) n
            FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_PART_MAT p
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_WORK w ON w.WORK_CODE=p.MAT_WORK_CENTER_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST cu ON cu.CUST_CODE=p.MAT_WORK_CENTER_CODE
            WHERE p.PART_PLAN_QTY>0 AND p.MAT_WORK_CENTER_CODE>''
            GROUP BY p.MAT_WORK_CENTER_CODE, COALESCE(w.WORK_DESC, cu.CUST_DESC, '')
            ORDER BY COUNT(*) DESC""")
        return {"rows": [{"cc": r[0], "nm": r[1], "n": r[2]} for r in cur.fetchall()]}
    finally:
        cn.close()
