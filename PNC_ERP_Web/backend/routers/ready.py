# -*- coding: utf-8 -*-
"""ready 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE)

router = APIRouter()

# ===================== 준비실적처리(키팅) (w_pr_input_250/460_new) — 준비등록/취소(nx.ready_ledger) =====================
# 근거: 준비필요=계획−준비완료. 본체키팅=자재무차감(준비마킹). 잔량=SUM 파생. write=nx 신규원장(확정).
@router.get("/api/ready/plan")
def ready_plan(from_ymd: str = Query(""), to_ymd: str = Query(""), line: str = Query(""),
               item: str = Query(""), limit: int = Query(1000)):
    """자재별 정본 자재소요(nx.plan_part_mat) + 준비완료(nx.ready_ledger SUM) + 준비필요=소요−준비.
       ★정본 파이프라인 전환: nx.plan_part(구98%) → nx.plan_part_mat(레거시 STEP5→6→7 100%검증)."""
    def d6(s):
        d = ''.join(c for c in str(s or '') if c.isdigit())
        return d[2:8] if len(d) >= 8 else d
    cn = _conn(); cur = cn.cursor(); nx = _nx(); ncur = nx.cursor()
    try:
        w = ["1=1"]; p = []
        if from_ymd.strip(): w.append("pp.PLAN_YMD>=?"); p.append(d6(from_ymd))
        if to_ymd.strip(): w.append("pp.PLAN_YMD<=?"); p.append(d6(to_ymd))
        if line.strip(): w.append("pp.MAT_WORK_CENTER_CODE=?"); p.append(line.strip())
        if item.strip(): w.append("pp.MAT_CODE LIKE ?"); p.append(f"%{item.strip()}%")
        ncur.execute(f"""SELECT TOP {max(1,min(int(limit),3000))} pp.PLAN_YMD, pp.WORK_ORDER, pp.MAT_CODE, pp.MAT_WORK_CENTER_CODE,
              SUM(CAST(pp.PART_PLAN_QTY AS float)) plan_qty,
              ISNULL((SELECT SUM(rl.MAINT_QTY) FROM nx.stock_ledger rl WHERE rl.STOCK_POINT='RDY' AND rl.ITEM_CODE=pp.MAT_CODE AND ISNULL(rl.WORK_ORDER,'')=ISNULL(pp.WORK_ORDER,'') AND ISNULL(rl.INPUT_YMD,'')=ISNULL(pp.PLAN_YMD,'')),0) ready_qty
            FROM nx.plan_part_mat pp WHERE {' AND '.join(w)}
            GROUP BY pp.PLAN_YMD, pp.WORK_ORDER, pp.MAT_CODE, pp.MAT_WORK_CENTER_CODE
            ORDER BY pp.PLAN_YMD DESC, pp.MAT_CODE""", *p)
        rows = []; parts = set()
        for r in ncur.fetchall():
            g = lambda i: str(r[i] if r[i] is not None else "").strip()
            pq = float(r[4] or 0); rq = float(r[5] or 0)
            rows.append({"plan_ymd": g(0), "work_order": g(1), "item_code": g(2), "work_center": g(3),
                         "plan_qty": pq, "ready_qty": rq, "need_qty": round(max(pq - rq, 0), 2)})
            parts.add(g(2))
        nm = {}; pl = [x for x in parts if x]
        for i in range(0, len(pl), 900):
            ch = pl[i:i+900]; ph = ",".join("?" * len(ch))
            cur.execute(f"SELECT ITEM_CODE, ISNULL(ITEM_DESC,'') FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM WHERE ITEM_CODE IN ({ph})", *ch)
            for a, b in cur.fetchall(): nm[str(a).strip()] = b
        for x in rows: x["nm"] = nm.get(x["item_code"], "")
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close(); nx.close()

@router.post("/api/ready/register")
def ready_register(payload: dict = Body(...)):
    """준비등록(+)/취소(−) 다건. ★Phase1: 단일원장 nx.stock_ledger(STOCK_POINT='RDY', K1/K2). 셀키=item·wo·gpc(파트)·plan_ymd(INPUT_YMD).
       취소는 준비잔량 이내. flag-only(자재무차감). 쓰기 nx만."""
    mode = str(payload.get("mode", "register")).strip()
    rows = payload.get("rows", []) or []
    user = (str(payload.get("user", "") or "").strip() or "웹사용자")[:20]
    tag = "K2" if mode == "cancel" else "K1"; remk = "키팅취소" if mode == "cancel" else "키팅확인"
    nx = _nx(); cur = nx.cursor()
    try:
        n = 0; skipped = 0
        for r in rows:
            ic = str(r.get("item_code", "") or "").strip()
            qty = float(r.get("qty") or 0)
            if not ic or qty <= 0:
                skipped += 1; continue
            wo = str(r.get("work_order", "") or "").strip(); py = str(r.get("plan_ymd", "") or "").strip()
            gpc = (str(r.get("gpc") or r.get("work_center") or "").strip() or None)   # 파트(gpc) 우선, 없으면 작업처
            if mode == "cancel":
                cur.execute("""SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger WHERE STOCK_POINT='RDY'
                      AND ITEM_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=? AND ISNULL(WORK_ORDER,'')=? AND ISNULL(INPUT_YMD,'')=?""",
                      ic, (gpc or ''), wo, py)
                if qty > float(cur.fetchone()[0] or 0):
                    skipped += 1; continue
            cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.stock_ledger WHERE MAINT_YMD=RIGHT(CONVERT(varchar(8),GETDATE(),112),6)")
            seq = int(cur.fetchone()[0] or 1)
            cur.execute("""INSERT INTO nx.stock_ledger(STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,ITEM_CODE,GAGONG_PROC_CODE,
                  WORK_ORDER,INPUT_YMD,MAINT_QTY,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
                VALUES('RDY',RIGHT(CONVERT(varchar(8),GETDATE(),112),6),?,?,'Z99990',?,?,?,?,?,?,?,GETDATE())""",
                seq, tag, ic, gpc, (wo or None), (py or None), (-qty if mode == "cancel" else qty), remk, user)
            n += 1
        return {"ok": True, "count": n, "skipped": skipped, "mode": mode}
    finally:
        nx.close()
