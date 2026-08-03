# -*- coding: utf-8 -*-
"""prodplan 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ============ 생산: 생산계획현황(라이브 SA_T_PLAN_DTL) — 제번×일자 피벗 ============
@router.get("/api/prodplan/status")
def prodplan_status(from_ymd: str = Query(""), to_ymd: str = Query(""), line: str = Query(""),
                    wo: str = Query(""), model: str = Query(""), cr: str = Query("")):
    """라이브 생산계획현황. SA_T_PLAN_DTL(현행 LG 생산계획)을 제번(WO)×일자로 피벗(읽기전용)."""
    cn = _conn(); cur = cn.cursor()
    try:
        w = ["1=1"]; p = []
        if from_ymd: w.append("PLAN_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("PLAN_YMD<=?"); p.append(_d6(to_ymd))
        if line.strip():  w.append("LINE_NO=?"); p.append(line.strip())
        if wo.strip():    w.append("WORK_ORDER LIKE ?"); p.append(f"%{wo.strip()}%")
        if model.strip(): w.append("MODEL_NO LIKE ?"); p.append(f"%{model.strip()}%")
        if cr in ("C", "R"): w.append("CR_FLAG=?"); p.append(cr)
        cur.execute(f"""SELECT PLAN_YMD, WORK_ORDER, MODEL_NO, LINE_NO, ISNULL(PLAN_QTY,0) PLAN_QTY,
              ISNULL(LOT_QTY,0) LOT_QTY, ISNULL(TOOLS_DESC,'') TOOLS_DESC, ISNULL(CR_FLAG,'') CR_FLAG,
              ISNULL(OUTPUT_HM,'') OUTPUT_HM
            FROM SA_T_PLAN_DTL WHERE {' AND '.join(w)}""", *p)
        cols = [d[0] for d in cur.description]
        raw = [dict(zip(cols, row)) for row in cur.fetchall()]
        dates = sorted({r["PLAN_YMD"] for r in raw})
        wos = {}
        for r in raw:
            k = r["WORK_ORDER"]
            g = wos.get(k)
            if not g:
                g = {"wo": k, "model": r["MODEL_NO"], "line": r["LINE_NO"], "tool": r["TOOLS_DESC"],
                     "cr": r["CR_FLAG"], "hm": r["OUTPUT_HM"], "total": 0, "days": {}}
                wos[k] = g
            q = float(r["PLAN_QTY"] or 0)
            g["days"][r["PLAN_YMD"]] = g["days"].get(r["PLAN_YMD"], 0) + q
            g["total"] += q
        rows = sorted(wos.values(), key=lambda x: (x["line"] or "", x["wo"]))
        return {"dates": dates, "rows": rows, "wo_count": len(rows),
                "sum_qty": sum(float(r["PLAN_QTY"] or 0) for r in raw), "src": "SA_T_PLAN_DTL(라이브)"}
    finally:
        cn.close()
