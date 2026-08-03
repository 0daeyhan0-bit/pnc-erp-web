# -*- coding: utf-8 -*-
"""coopplan 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ================= 협력사 ①: 협력사계획현황 (w_pr_outside_040) — nx.plan_part 편성결과 =================
@router.get("/api/partner/workcenters")
def partner_workcenters():
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("IF OBJECT_ID('nx.plan_part_mat') IS NULL SELECT 1 WHERE 1=0")
        C = " COLLATE DATABASE_DEFAULT"
        try:
            cur.execute(f"""SELECT pp.MAT_WORK_CENTER_CODE, COALESCE(w.WORK_DESC, cu.CUST_DESC, pp.MAT_WORK_CENTER_CODE) nm, COUNT(*) n
                FROM nx.plan_part_mat pp
                LEFT JOIN PARTNER_ERP.dbo.PR_M_WORK w ON w.WORK_CODE{C}=pp.MAT_WORK_CENTER_CODE{C}
                LEFT JOIN PARTNER_ERP.dbo.CM_M_CUST cu ON cu.CUST_CODE{C}=pp.MAT_WORK_CENTER_CODE{C}
                WHERE pp.MAT_WORK_CENTER_CODE>'' GROUP BY pp.MAT_WORK_CENTER_CODE, COALESCE(w.WORK_DESC, cu.CUST_DESC, pp.MAT_WORK_CENTER_CODE)
                ORDER BY COUNT(*) DESC""")
            return {"rows": [{"cc": r[0], "nm": r[1], "n": r[2]} for r in cur.fetchall()]}
        except Exception:
            return {"rows": []}
    finally:
        nx.close()

@router.get("/api/partner/planstatus")
def partner_planstatus(from_ymd: str = Query(""), to_ymd: str = Query(""), wc: str = Query(""),
                       part: str = Query(""), assy: str = Query(""), line: str = Query(""),
                       gubun: str = Query("외주")):
    """협력사(납품업체)별 자도번 일자계획. gubun: 외주(협력사=CUST, 기본)/자체(내부공정=WORK)/전체.
       ★정본 파이프라인 전환: nx.plan_part(구98%) → nx.plan_part_mat(레거시 STEP5→6→7 100%검증). 가공처=mat_work_center_code, 자도번=mat_code."""
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("IF OBJECT_ID('nx.plan_part_mat') IS NULL SELECT 1 WHERE 1=0")
        C = " COLLATE DATABASE_DEFAULT"
        w = ["1=1"]; p = []
        if from_ymd: w.append("pp.PLAN_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("pp.PLAN_YMD<=?"); p.append(_d6(to_ymd))
        if wc.strip():   w.append("pp.MAT_WORK_CENTER_CODE=?"); p.append(wc.strip())
        if part.strip(): w.append("pp.MAT_CODE LIKE ?"); p.append(f"%{part.strip()}%")
        if assy.strip(): w.append("pp.ASSY_ITEM_CODE LIKE ?"); p.append(f"%{assy.strip()}%")
        if line.strip(): w.append("pd.LINE_NO=?"); p.append(line.strip())
        if gubun == "외주":   w.append("w.WORK_CODE IS NULL AND cu.CUST_CODE IS NOT NULL")  # 거래처(협력사)만
        elif gubun == "자체": w.append("w.WORK_CODE IS NOT NULL")                            # 내부공정(P1/P2)
        # ★정본 nx.plan_part_mat은 자재단위라 행수가 큼(외주 5만+) → 브라우저 과부하 방지: 자도번(part)×가공처 단위로 먼저 집계(일자는 유지)
        #   후 상한(CAP). 필터(가공처/제번/자도번) 걸면 좁혀짐.
        CAP = 4000
        try:
            cur.execute(f"""SELECT TOP {CAP} pp.PLAN_YMD, pp.MAT_WORK_CENTER_CODE, COALESCE(w.WORK_DESC, cu.CUST_DESC, pp.MAT_WORK_CENTER_CODE) wcnm,
                  pp.WORK_ORDER, pp.ASSY_ITEM_CODE, pp.MAT_CODE, ISNULL(i.ITEM_DESC,'') nm,
                  ISNULL(pd.LINE_NO,'') line, ISNULL(pd.MODEL_NO,'') model, SUM(CAST(pp.PART_PLAN_QTY AS float)) q
                FROM nx.plan_part_mat pp
                LEFT JOIN (SELECT WORK_ORDER, MAX(LINE_NO) LINE_NO, MAX(MODEL_NO) MODEL_NO FROM nx.plan_dtl GROUP BY WORK_ORDER) pd ON pd.WORK_ORDER=pp.WORK_ORDER
                LEFT JOIN PARTNER_ERP.dbo.PR_M_WORK w ON w.WORK_CODE{C}=pp.MAT_WORK_CENTER_CODE{C}
                LEFT JOIN PARTNER_ERP.dbo.CM_M_CUST cu ON cu.CUST_CODE{C}=pp.MAT_WORK_CENTER_CODE{C}
                LEFT JOIN PARTNER_ERP.dbo.PR_M_ITEM i ON i.ITEM_CODE{C}=pp.MAT_CODE{C}
                WHERE {' AND '.join(w)}
                GROUP BY pp.PLAN_YMD, pp.MAT_WORK_CENTER_CODE, COALESCE(w.WORK_DESC, cu.CUST_DESC, pp.MAT_WORK_CENTER_CODE),
                  pp.WORK_ORDER, pp.ASSY_ITEM_CODE, pp.MAT_CODE, i.ITEM_DESC, pd.LINE_NO, pd.MODEL_NO
                ORDER BY wcnm, pp.WORK_ORDER, pp.MAT_CODE""", *p)
        except Exception as e:
            return {"dates": [], "rows": [], "cnt": 0, "sum_qty": 0, "note": "편성 먼저 실행(생산계획업로드 → 🧾자재소요·조달 편성). 오류: " + str(e)[:120]}
        cols = [d[0] for d in cur.description]; raw = [dict(zip(cols, r)) for r in cur.fetchall()]
        capped = len(raw) >= CAP
        dates = sorted({r["PLAN_YMD"] for r in raw})
        keyed = {}
        for r in raw:
            k = (r["MAT_WORK_CENTER_CODE"], r["WORK_ORDER"], r["ASSY_ITEM_CODE"], r["MAT_CODE"])
            g = keyed.get(k)
            if not g:
                g = {"wc": r["MAT_WORK_CENTER_CODE"], "wcnm": r["wcnm"], "wo": r["WORK_ORDER"], "assy": r["ASSY_ITEM_CODE"],
                     "part": r["MAT_CODE"], "nm": r["nm"], "line": r["line"], "model": r["model"], "days": {}, "tot": 0}
                keyed[k] = g
            q = float(r["q"] or 0); g["days"][r["PLAN_YMD"]] = g["days"].get(r["PLAN_YMD"], 0) + q; g["tot"] += q
        rows = sorted(keyed.values(), key=lambda x: (x["wcnm"] or "", x["line"], x["wo"], x["part"]))
        note = f"⚠ 결과가 많아 상위 {CAP}건만 표시했습니다. 협력사(가공처)·제번·자도번으로 필터하세요." if capped else ""
        return {"dates": dates, "rows": rows, "cnt": len(rows), "sum_qty": sum(float(r["q"] or 0) for r in raw), "note": note}
    finally:
        nx.close()
