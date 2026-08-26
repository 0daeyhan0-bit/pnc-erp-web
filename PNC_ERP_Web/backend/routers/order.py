# -*- coding: utf-8 -*-
"""order 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ================= 생산: 주문UPLOAD(w_pr_plan_010) · 생산계획UPLOAD(w_pr_plan_020) =================
# 소스=LG PU-SCS 2.0 엑셀(Purchase Order / Production Plan Status). 레거시 SP_LGE_RECV_ORDER 매핑을
# 실측검증(품번·단가·워크오더·납기·CR_FLAG 0불일치, 생산계획 WO총량 100%)한 규칙 그대로 적재. 저장=nx(TEST3).
def _d6(s):
    d = ''.join(ch for ch in str(s or '') if ch.isdigit())
    if len(d) == 8: return d[2:8]      # yyyymmdd → yymmdd
    return d[-6:] if len(d) >= 6 else d

def _po_rows(ws, cr):
    """Purchase Order 시트 → recv 튜플. WORK_ORDER=P/S Order '-' 앞부분, ITEM_COST=Unit Price."""
    def y6(v):
        s = str(v); return (s[2:4]+s[5:7]+s[8:10]) if len(s) >= 10 and s[4] == '-' else ''
    out = []
    for r in ws.iter_rows(min_row=3, values_only=True):
        if not r or r[3] is None or str(r[0]) == 'Total Sum': continue
        on = f"{str(r[3]).strip()}-{str(r[4]).strip() if r[4] is not None else ''}"
        ps = str(r[17]).strip() if r[17] else ''
        out.append((on, str(r[1]).strip() if r[1] else '', y6(r[5]), '0000', int(r[9] or 0), int(r[8] or 0),
                    ps[:8], ps, y6(r[33]), cr, str(r[2] or '')[:40], round(float(r[24] or 0), 2)))  # WORK_ORDER=LEFT(P/S,8) 레거시 정본
    return out

def _plan_rows(rows, cr):
    """Production Plan Status 행들 → plan 튜플(WO,일자별). 일별 컬럼(MM/DD) 전개."""
    import re as _re
    def cymd(h):
        m = _re.match(r'(\d\d)/(\d\d)', str(h)); return ('26'+m.group(1)+m.group(2)) if m else None
    hdr = rows[0]; dcol = {i: cymd(hdr[i]) for i in range(len(hdr)) if cymd(hdr[i])}
    agg = {}
    for r in rows[1:]:
        if not r or r[3] is None: continue
        wo = str(r[3]).strip(); line = str(r[1]).strip() if r[1] else ''; sg = str(r[2]).strip() if r[2] else ''
        model = str(r[4]).strip() if r[4] else ''; buyer = str(r[5]).strip() if r[5] else ''
        tot = int(float(r[6] or 0)); rem = int(float(r[7] or 0))
        st = str(r[46]) if len(r) > 46 and r[46] else ''
        sh = (st[11:13]+st[14:16]) if len(st) >= 16 else ''
        if not ('0000' <= sh <= '2359'): sh = '0800'   # 레거시: 무효 Start Time → 0800
        fs = str(r[47]).strip() if len(r) > 47 and r[47] is not None else ''
        ts = str(r[48]).strip() if len(r) > 48 and r[48] is not None else ''
        tool = str(r[49]).strip() if len(r) > 49 and r[49] else ''
        for ci, ymd in dcol.items():
            if ci < len(r) and r[ci] and float(r[ci]) > 0:
                q = int(float(r[ci])); k = (wo, ymd)
                if k in agg:
                    p = list(agg[k]); p[6] += q; agg[k] = tuple(p)
                else:
                    agg[k] = (ymd, wo, model, buyer, line, sg, q, tot, rem, sh, tool[:40], fs[:20], ts[:20], cr)
    return list(agg.values())

def _load_xlsx(b64):
    import base64, io as _io, openpyxl
    raw = base64.b64decode(str(b64).split(',')[-1])
    return openpyxl.load_workbook(_io.BytesIO(raw), data_only=True, read_only=True)

@router.get("/api/order/list")
def order_list(from_ymd: str = Query(""), to_ymd: str = Query(""), need_from: str = Query(""),
               need_to: str = Query(""), done: str = Query("all"), item: str = Query(""),
               wo: str = Query(""), cr: str = Query("")):
    nx = _nx(); cur = nx.cursor()
    try:
        w = ["1=1"]; p = []
        if from_ymd: w.append("r.ORDER_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("r.ORDER_YMD<=?"); p.append(_d6(to_ymd))
        if need_from: w.append("r.NEED_BY_YMD>=?"); p.append(_d6(need_from))
        if need_to:   w.append("r.NEED_BY_YMD<=?"); p.append(_d6(need_to))
        if item.strip(): w.append("r.ITEM_CODE LIKE ?"); p.append(f"%{item.strip()}%")
        if wo.strip():   w.append("(r.WORK_ORDER LIKE ? OR r.PS_ORDER LIKE ?)"); p += [f"%{wo.strip()}%"]*2
        if cr in ('C', 'R'): w.append("r.CR_FLAG=?"); p.append(cr)
        if done == 'done':   w.append("r.REMAIN_QTY<=0")
        elif done == 'undone': w.append("r.REMAIN_QTY>0")
        cur.execute(f"""SELECT TOP 5000 r.ORDER_NO,r.ORDER_YMD,r.ITEM_CODE,ISNULL(i.item_name,'') nm,
            r.ORDER_QTY,r.REMAIN_QTY,r.NEED_BY_YMD,r.NEED_BY_HM,r.WORK_ORDER,r.PS_ORDER,r.ITEM_COST,r.CR_FLAG,r.PO_TYPE
          FROM nx.recv_dtl r LEFT JOIN PARTNER_ERP_TEST3.nx.item i ON i.item_code=r.ITEM_CODE
          WHERE {' AND '.join(w)} ORDER BY r.ORDER_YMD DESC, r.ORDER_NO""", *p)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        for r in rows:
            r["ITEM_COST"] = float(r["ITEM_COST"] or 0)
            r["AMT"] = round(r["ITEM_COST"] * (r["ORDER_QTY"] or 0))
        return {"rows": rows, "count": len(rows),
                "sum_qty": sum(r["ORDER_QTY"] or 0 for r in rows),
                "sum_amt": sum(r["AMT"] for r in rows)}
    finally:
        nx.close()

@router.post("/api/order/upload")
def order_upload(payload: dict = Body(...)):
    cr = (str(payload.get("cr", "C")).strip() or "C")[:1]
    try:
        wb = _load_xlsx(payload.get("b64", ""))
    except Exception as e:
        raise HTTPException(400, f"엑셀 파싱 실패: {e}")
    recs = _po_rows(wb[wb.sheetnames[0]], cr); wb.close()
    if not recs:
        return {"ok": True, "inserted": 0, "updated": 0, "total": 0, "cr": cr}
    nx = _nx(); cur = nx.cursor()
    try:
        # 레거시 방식(temp→일괄): 세트기반 upsert로 고속 처리
        cur.execute("IF OBJECT_ID('tempdb..#s') IS NOT NULL DROP TABLE #s")
        cur.execute("""CREATE TABLE #s(ORDER_NO varchar(24),ITEM_CODE varchar(20),NEED_BY_YMD varchar(6),NEED_BY_HM varchar(4),
            ORDER_QTY int,REMAIN_QTY int,WORK_ORDER varchar(20),PS_ORDER varchar(30),ORDER_YMD varchar(6),
            CR_FLAG varchar(1),PO_TYPE varchar(40),ITEM_COST decimal(18,2))""")
        cur.fast_executemany = True
        cur.executemany("INSERT INTO #s VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", recs)
        upd = cur.execute("SELECT COUNT(*) FROM nx.recv_dtl r JOIN #s s ON r.ORDER_NO=s.ORDER_NO").fetchone()[0]
        cur.execute("DELETE r FROM nx.recv_dtl r JOIN #s s ON r.ORDER_NO=s.ORDER_NO")
        cur.execute("""INSERT INTO nx.recv_dtl(ORDER_NO,ITEM_CODE,NEED_BY_YMD,NEED_BY_HM,ORDER_QTY,REMAIN_QTY,
            WORK_ORDER,PS_ORDER,ORDER_YMD,CR_FLAG,PO_TYPE,ITEM_COST,UPLOAD_DT)
            SELECT ORDER_NO,ITEM_CODE,NEED_BY_YMD,NEED_BY_HM,ORDER_QTY,REMAIN_QTY,WORK_ORDER,PS_ORDER,ORDER_YMD,
                   CR_FLAG,PO_TYPE,ITEM_COST,getdate() FROM #s""")
        return {"ok": True, "inserted": len(recs) - upd, "updated": upd, "total": len(recs), "cr": cr}
    finally:
        nx.close()

@router.get("/api/plan/list")
def plan_list(from_ymd: str = Query(""), to_ymd: str = Query(""), line: str = Query(""),
              sched: str = Query(""), wo: str = Query(""), model: str = Query(""), cr: str = Query("")):
    nx = _nx(); cur = nx.cursor()
    try:
        w = ["1=1"]; p = []
        if from_ymd: w.append("PLAN_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("PLAN_YMD<=?"); p.append(_d6(to_ymd))
        if line.strip():  w.append("LINE_NO=?"); p.append(line.strip())
        if sched.strip(): w.append("SCHED_GROUP=?"); p.append(sched.strip())
        if wo.strip():    w.append("WORK_ORDER LIKE ?"); p.append(f"%{wo.strip()}%")
        if model.strip(): w.append("MODEL_NO LIKE ?"); p.append(f"%{model.strip()}%")
        if cr in ('C', 'R'): w.append("CR_FLAG=?"); p.append(cr)
        cur.execute(f"""SELECT PLAN_YMD,WORK_ORDER,MODEL_NO,BUYER_MODEL,LINE_NO,SCHED_GROUP,PLAN_QTY,
            TOTAL_QTY,REMAIN_QTY,START_HM,TOOL,FROM_SEQ,TO_SEQ,CR_FLAG
          FROM nx.plan_dtl WHERE {' AND '.join(w)}""", *p)
        cols = [d[0] for d in cur.description]
        raw = [dict(zip(cols, row)) for row in cur.fetchall()]
        dates = sorted({r["PLAN_YMD"] for r in raw})
        wos = {}
        for r in raw:
            k = r["WORK_ORDER"]
            g = wos.get(k)
            if not g:
                g = {"wo": k, "model": r["MODEL_NO"], "buyer": r["BUYER_MODEL"], "line": r["LINE_NO"],
                     "sched": r["SCHED_GROUP"], "total": r["TOTAL_QTY"], "remain": r["REMAIN_QTY"],
                     "tool": r["TOOL"], "cr": r["CR_FLAG"], "days": {}}
                wos[k] = g
            g["days"][r["PLAN_YMD"]] = (g["days"].get(r["PLAN_YMD"], 0) + (r["PLAN_QTY"] or 0))
        rows = sorted(wos.values(), key=lambda x: (x["line"] or "", x["wo"]))
        return {"dates": dates, "rows": rows, "wo_count": len(rows),
                "sum_qty": sum(r["PLAN_QTY"] or 0 for r in raw)}
    finally:
        nx.close()

@router.post("/api/plan/upload")
def plan_upload(payload: dict = Body(...)):
    cr = (str(payload.get("cr", "C")).strip() or "C")[:1]
    try:
        wb = _load_xlsx(payload.get("b64", ""))
    except Exception as e:
        raise HTTPException(400, f"엑셀 파싱 실패: {e}")
    ws = wb[wb.sheetnames[0]]; rows = list(ws.iter_rows(values_only=True)); wb.close()
    recs = _plan_rows(rows, cr)
    if not recs:
        return {"ok": True, "inserted": 0, "updated": 0, "total": 0, "cr": cr}
    nx = _nx(); cur = nx.cursor()
    try:  # recs t=(PLAN_YMD,WORK_ORDER,MODEL_NO,BUYER_MODEL,LINE_NO,SCHED_GROUP,PLAN_QTY,TOTAL_QTY,REMAIN_QTY,START_HM,TOOL,FROM_SEQ,TO_SEQ,CR_FLAG)
        cur.execute("IF OBJECT_ID('tempdb..#p') IS NOT NULL DROP TABLE #p")
        cur.execute("""CREATE TABLE #p(PLAN_YMD varchar(6),WORK_ORDER varchar(20),MODEL_NO varchar(30),BUYER_MODEL varchar(30),
            LINE_NO varchar(10),SCHED_GROUP varchar(6),PLAN_QTY int,TOTAL_QTY int,REMAIN_QTY int,START_HM varchar(4),
            TOOL varchar(40),FROM_SEQ varchar(20),TO_SEQ varchar(20),CR_FLAG varchar(1))""")
        cur.fast_executemany = True
        cur.executemany("INSERT INTO #p VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", recs)
        # 레거시 STEP0: "cr별 삭제 후 재적재"(full replace). 업로드 파일 = 해당 CR의 완전한 현재 계획.
        # ★해당 CR 전체 삭제(과거일자 포함) → 재적재. 계획일자 이동/재업로드 시 stale행 누적(2배)·
        #   과거일자 잔재(compose_mat 부풀림) 방지. 과거 이력은 별도 _daily 백업 대상(현 미구현).
        fmin = min(r[0] for r in recs)
        upd = cur.execute("SELECT COUNT(*) FROM nx.plan_dtl WHERE CR_FLAG=?", cr).fetchone()[0]
        cur.execute("DELETE FROM nx.plan_dtl WHERE CR_FLAG=?", cr)
        cur.execute("""INSERT INTO nx.plan_dtl(PLAN_YMD,WORK_ORDER,MODEL_NO,BUYER_MODEL,LINE_NO,SCHED_GROUP,PLAN_QTY,
            TOTAL_QTY,REMAIN_QTY,START_HM,TOOL,FROM_SEQ,TO_SEQ,CR_FLAG,UPLOAD_DT)
            SELECT PLAN_YMD,WORK_ORDER,MODEL_NO,BUYER_MODEL,LINE_NO,SCHED_GROUP,PLAN_QTY,TOTAL_QTY,REMAIN_QTY,START_HM,
                   TOOL,FROM_SEQ,TO_SEQ,CR_FLAG,getdate() FROM #p""")
        # full-replace(cr별): 기존 upd행 삭제 후 recs행 재적재
        return {"ok": True, "inserted": len(recs), "replaced": upd, "total": len(recs), "cr": cr, "from_ymd": fmin}
    finally:
        nx.close()
