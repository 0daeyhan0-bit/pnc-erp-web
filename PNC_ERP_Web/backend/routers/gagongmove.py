# -*- coding: utf-8 -*-
"""gagongmove 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ================= 가공창고 이동계획 (w_pr_input_580) — 도번×라인, 자도번LIST + 이동필요/완료 =================
@router.get("/api/gagong/move580")
def gagong_move580(from_ymd: str = Query(""), to_ymd: str = Query(""), wc: str = Query(""),
                   item: str = Query(""), part: str = Query(""), mv: str = Query("전체"), limit: int = Query(2500)):
    """가공창고 이동계획. 계획=PR_T_PLAN_PART_MAT, 이동완료=PU_T_STOCK_MAINT_GAGONG_MOVE(IN_CONFIRM_FLAG='1').
       이동필요수=계획−이동완료. 도번(ASSY)×라인 그룹, 자도번LIST 묶기. (레거시 SP 암호화→라이브 역설계)"""
    cn = _conn(); cur = cn.cursor()
    try:
        w = ["pp.PART_PLAN_QTY>0"]; p = []
        if from_ymd: w.append("pp.PART_PLAN_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("pp.PART_PLAN_YMD<=?"); p.append(_d6(to_ymd))
        if wc.strip():   w.append("ia.WORK_CODE=?"); p.append(wc.strip())
        if item.strip(): w.append("pp.ASSY_ITEM_CODE LIKE ?"); p.append(f"%{item.strip()}%")
        if part.strip(): w.append("pp.MAT_CODE LIKE ?"); p.append(f"%{part.strip()}%")
        cur.execute(f"""SELECT TOP {int(limit) * 60} pp.ASSY_ITEM_CODE assy, ISNULL(ia.ITEM_DESC,'') nm,
              ISNULL(pp.LINE_NO,'') line, COALESCE(cw.WORK_DESC, cc.CUST_DESC, pp.MAT_WORK_CENTER_CODE, '') dest,
              pp.MAT_CODE mat, pp.PART_PLAN_YMD ymd, MIN(ISNULL(pp.PART_OUTPUT_HM,'')) hm,
              SUM(CAST(pp.PART_PLAN_QTY AS float)) q
            FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_PART_MAT pp
            JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM ia ON ia.ITEM_CODE=pp.ASSY_ITEM_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_WORK cw ON cw.WORK_CODE=pp.MAT_WORK_CENTER_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST cc ON cc.CUST_CODE=pp.MAT_WORK_CENTER_CODE
            WHERE {' AND '.join(w)}
            GROUP BY pp.ASSY_ITEM_CODE, ISNULL(ia.ITEM_DESC,''), pp.LINE_NO,
              COALESCE(cw.WORK_DESC, cc.CUST_DESC, pp.MAT_WORK_CENTER_CODE, ''), pp.MAT_CODE, pp.PART_PLAN_YMD
            ORDER BY assy, line""", *p)
        cols = [d[0] for d in cur.description]; raw = [dict(zip(cols, r)) for r in cur.fetchall()]
        keyed = {}
        for r in raw:
            k = (r["assy"], r["line"], r["dest"])
            g = keyed.get(k)
            if not g:
                g = {"assy": r["assy"], "nm": r["nm"], "line": r["line"], "dest": r["dest"],
                     "days": {}, "mats": {}, "plan_qty": 0.0, "part_ymd": r["ymd"], "hm": r["hm"] or ""}
                keyed[k] = g
            q = float(r["q"] or 0)
            g["days"][r["ymd"]] = g["days"].get(r["ymd"], 0) + q
            g["mats"][r["mat"]] = g["mats"].get(r["mat"], 0) + q
            g["plan_qty"] += q
            if r["ymd"] < g["part_ymd"]: g["part_ymd"] = r["ymd"]; g["hm"] = r["hm"] or ""
        rows = list(keyed.values()); capped = len(keyed) > int(limit); rows = rows[:int(limit)]
        for g in rows:
            g["jado"] = ",".join(f"{m}{{{int(v)}}}" for m, v in sorted(g["mats"].items()))
            g["matcnt"] = len(g["mats"]); g["matlist"] = list(g["mats"].keys()); del g["mats"]
        # 이동완료 = 이동원장(IN_CONFIRM_FLAG='1') by MAT_CODE, 조회범위 date-scope
        matset = list({m for g in rows for m in g["matlist"]}); moved = {}
        d6a = _d6(from_ymd) if from_ymd else None; d6b = _d6(to_ymd) if to_ymd else None
        CH = 1000
        for i in range(0, len(matset), CH):
            ck = matset[i:i + CH]; ph = ",".join("?" * len(ck)); pr = list(ck)
            q = f"SELECT MAT_CODE, SUM(CAST(MAINT_QTY AS float)) FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT_GAGONG_MOVE WHERE IN_CONFIRM_FLAG='1' AND MAT_CODE IN ({ph})"
            if d6a: q += " AND MAINT_YMD>=?"; pr.append(d6a)
            if d6b: q += " AND MAINT_YMD<=?"; pr.append(d6b)
            q += " GROUP BY MAT_CODE"
            try:
                cur.execute(q, *pr)
                for rr in cur.fetchall(): moved[rr[0]] = moved.get(rr[0], 0.0) + float(rr[1] or 0)
            except Exception:
                pass
        for g in rows:
            g["moved"] = sum(moved.get(m, 0.0) for m in g["matlist"])
            g["need"] = max(0.0, g["plan_qty"] - g["moved"])
            del g["matlist"]
        m = mv.strip()
        if m == "이동필요": rows = [r for r in rows if r["need"] > 0]
        elif m == "이동완료": rows = [r for r in rows if r["need"] <= 0]
        dates = sorted({ymd for g in rows for ymd in g["days"]})
        rows.sort(key=lambda x: (x["part_ymd"], x["assy"]))
        note = f"⚠ 상위 {limit}건만 표시 — 작업처·도번으로 필터하세요." if capped else ""
        return {"dates": dates, "rows": rows, "cnt": len(rows),
                "plan_sum": sum(r["plan_qty"] for r in rows), "need_sum": sum(r["need"] for r in rows),
                "moved_sum": sum(r["moved"] for r in rows), "note": note}
    finally:
        cn.close()
