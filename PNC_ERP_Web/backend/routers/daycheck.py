# -*- coding: utf-8 -*-
"""daycheck 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ============ 일반업무: 일일체크리스트(부서간 일일 이슈/체크, DAY_CHECK_LIST 라이브 조회) ============
@router.get("/api/daycheck/list")
def daycheck_list(from_ymd: str = Query(""), to_ymd: str = Query(""), dept: str = Query("")):
    """일일체크리스트 조회(읽기전용). ※원본 DAY_CHECK_LIST는 현재 과거이력(≈2016)만 보유."""
    cn = _conn(); cur = cn.cursor()
    try:
        w = ["1=1"]; p = []
        if from_ymd: w.append("check_ymd>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("check_ymd<=?"); p.append(_d6(to_ymd))
        if dept.strip(): w.append("check_dept LIKE ?"); p.append(f"%{dept.strip()}%")
        cur.execute(f"""SELECT TOP 2000 check_ymd ymd, check_seq seq, ISNULL(check_dept,'') dept,
              ISNULL(request_member,'') req, ISNULL(issue_item,'') item, ISNULL(issue_note,'') note,
              ISNULL(contents,'') contents, ISNULL(result_check,'') result, ISNULL(result_member,'') rmember,
              ISNULL(imp_check,'0') imp
            FROM DAY_CHECK_LIST WHERE {' AND '.join(w)} ORDER BY check_ymd DESC, check_seq DESC""", *p)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            for k in ("dept", "req", "item", "note", "contents", "rmember"): r[k] = str(r[k]).strip()
            r["imp"] = 1 if str(r["imp"]).strip() == "1" else 0
        cur.execute("SELECT MAX(check_ymd) FROM DAY_CHECK_LIST")
        return {"rows": rows, "cnt": len(rows), "max_ymd": cur.fetchone()[0],
                "note": "원본(DAY_CHECK_LIST)은 과거이력(≈2016)만 보유 — 현행 일일점검은 설비/안전 체크리스트 별도"}
    finally:
        cn.close()
