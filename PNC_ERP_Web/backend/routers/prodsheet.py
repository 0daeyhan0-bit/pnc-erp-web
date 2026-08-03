# -*- coding: utf-8 -*-
"""prodsheet 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE)

from routers.backflush import _backflush_core, _final_proc_code, _is_inner_prod
router = APIRouter()

# ===================== 생산전표출력관리 (w_pr_input_468 등) — 전표/간판/라벨 조회·발행(nx)·인쇄 =====================
# 근거: jp_proc_method(J전표/G간판). 계획=nx.plan_part(도번). 발행=nx.sheet_issue(컷오버=nx 신규원장).
@router.get("/api/prodsheet/list")
def prodsheet_list(from_ymd: str = Query(""), to_ymd: str = Query(""), line: str = Query(""),
                   item: str = Query(""), limit: int = Query(1000)):
    """도번별 생산계획 + jp_proc_method(J전표/G간판) + 발행현황(nx.sheet_issue)."""
    def d6(s):
        d = ''.join(c for c in str(s or '') if c.isdigit())
        return d[2:8] if len(d) >= 8 else d
    cn = _conn(); cur = cn.cursor()
    nx = _nx(); ncur = nx.cursor()
    try:
        jp = {}
        cur.execute("SELECT ITEM_CODE, MAX(JP_PROC_METHOD) FROM PR_M_ITEM_PROC_GAGONG WHERE JP_PROC_METHOD IN ('J','G') GROUP BY ITEM_CODE")
        for r in cur.fetchall(): jp[str(r[0]).strip()] = str(r[1]).strip()
        w = ["1=1"]; p = []
        if from_ymd.strip(): w.append("pp.PLAN_YMD>=?"); p.append(d6(from_ymd))
        if to_ymd.strip(): w.append("pp.PLAN_YMD<=?"); p.append(d6(to_ymd))
        if line.strip(): w.append("pp.WORK_CENTER=?"); p.append(line.strip())
        if item.strip(): w.append("pp.PART_CODE LIKE ?"); p.append(f"%{item.strip()}%")
        ncur.execute(f"""SELECT TOP {max(1,min(int(limit),3000))} pp.PLAN_YMD, pp.WORK_ORDER, pp.ASSY_ITEM_CODE, pp.PART_CODE,
              pp.WORK_CENTER, pp.PLAN_QTY,
              (SELECT COUNT(*) FROM nx.sheet_issue si WHERE si.item_code=pp.PART_CODE AND si.plan_ymd=pp.PLAN_YMD AND si.kind='G'),
              (SELECT COUNT(*) FROM nx.sheet_issue si WHERE si.item_code=pp.PART_CODE AND si.plan_ymd=pp.PLAN_YMD AND si.kind='L'),
              (SELECT COUNT(*) FROM nx.sheet_issue si WHERE si.item_code=pp.PART_CODE AND si.plan_ymd=pp.PLAN_YMD AND si.kind='J')
            FROM nx.plan_part pp WHERE {' AND '.join(w)} ORDER BY pp.PLAN_YMD DESC, pp.PART_CODE""", *p)
        rows = []; parts = set()
        for r in ncur.fetchall():
            g = lambda i: str(r[i] if r[i] is not None else "").strip()
            pc = g(3)
            rows.append({"plan_ymd": g(0), "work_order": g(1), "assy": g(2), "item_code": pc, "work_center": g(4),
                         "plan_qty": float(r[5] or 0), "method": jp.get(pc, ""),
                         "gcnt": int(r[6] or 0), "lcnt": int(r[7] or 0), "jcnt": int(r[8] or 0)})
            parts.add(pc)
        nm = {}; pl = [x for x in parts if x]
        for i in range(0, len(pl), 900):
            ch = pl[i:i+900]; ph = ",".join("?" * len(ch))
            cur.execute(f"SELECT ITEM_CODE, ISNULL(ITEM_DESC,'') FROM PR_M_ITEM WHERE ITEM_CODE IN ({ph})", *ch)
            for a, b in cur.fetchall(): nm[str(a).strip()] = b
        for x in rows:
            x["nm"] = nm.get(x["item_code"], "")
            x["method_nm"] = {"J": "전표", "G": "간판"}.get(x["method"], "미지정")
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close(); nx.close()

@router.post("/api/prodsheet/issue")
def prodsheet_issue(payload: dict = Body(...)):
    """발행 채번 → nx.sheet_issue. kind J전표/G간판/L라벨. box_no/print_seq/sheet_no=nx max+1."""
    kind = str(payload.get("kind", "")).strip()
    rows = payload.get("rows", []) or []
    if kind not in ("J", "G", "L"):
        raise HTTPException(400, "kind 오류(J전표/G간판/L라벨)")
    user = (str(payload.get("user", "") or "").strip() or "웹사용자")[:20]
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("SELECT ISNULL(MAX(box_no),0), ISNULL(MAX(print_seq),0), ISNULL(MAX(sheet_no),0) FROM nx.sheet_issue")
        mx = cur.fetchone(); box = int(mx[0] or 0); seq = int(mx[1] or 0); sheet = int(mx[2] or 0)
        issued = 0
        for r in rows:
            ic = str(r.get("item_code", "") or "").strip()
            if not ic:
                continue
            qty = float(r.get("plan_qty") or 0)
            sheet += 1; bx = ps = qf = qt = None
            if kind == "G":
                box += 1; bx = box
            elif kind == "L":
                seq += 1; ps = seq
                qf = f"{ic}{sheet:08d}0001"; qt = f"{ic}{sheet:08d}{int(max(qty,1)):04d}"
            cur.execute("""INSERT INTO nx.sheet_issue(kind,item_code,assy_code,work_order,line_no,plan_ymd,plan_qty,
                box_no,print_seq,qr_from,qr_to,sheet_no,issue_user,issue_dt)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,GETDATE())""",
                kind, ic, (r.get("assy") or None), (r.get("work_order") or None), (r.get("work_center") or None),
                (r.get("plan_ymd") or None), qty, bx, ps, qf, qt, sheet, user)
            issued += 1
        return {"ok": True, "issued": issued, "kind": kind}
    finally:
        nx.close()

# ===================== 공정별 바코드생산실적 (w_pr_input_520) — 스캔→자동채움→등록/취소(nx.proc_barcode) =====================
# 근거: 220/527 근사(520 소스 부재). 간판(GP+box_no)/라벨(QR) 스캔→마스터조회→토글. ★커밋 상세는 원본 확보 후 대조.
@router.get("/api/procbc/lookup")
def procbc_lookup(barcode: str = Query(...), proc_code: str = Query("")):
    """바코드 파싱→간판/라벨 마스터(nx.sheet_issue+레거시) 조회→품번·수량·등록/취소 판정."""
    bc = barcode.strip()
    if not bc:
        raise HTTPException(400, "바코드가 필요합니다.")
    item = None; qty = 0.0; sheet = None; kind = None; src = None
    nx = _nx(); cur = nx.cursor()
    try:
        if bc.upper().startswith("GP") and bc[2:].isdigit():
            cur.execute("SELECT TOP 1 item_code, plan_qty, sheet_no FROM nx.sheet_issue WHERE kind='G' AND box_no=?", int(bc[2:]))
            r = cur.fetchone()
            if r: item, qty, sheet, kind, src = str(r[0]).strip(), float(r[1] or 0), int(r[2] or 0), "간판", "nx"
        if not item:
            cur.execute("SELECT TOP 1 item_code, plan_qty, sheet_no FROM nx.sheet_issue WHERE qr_from=? OR qr_to=?", bc, bc)
            r = cur.fetchone()
            if r: item, qty, sheet, kind, src = str(r[0]).strip(), float(r[1] or 0), int(r[2] or 0), "라벨", "nx"
        if not item:
            cn = _conn(); c2 = cn.cursor()
            try:
                if bc.upper().startswith("GP") and bc[2:].isdigit():
                    c2.execute("SELECT TOP 1 ITEM_CODE, PLAN_QTY, SHEET_NO FROM PR_T_INDI_SHEET2 WHERE BOX_NO=?", int(bc[2:]))
                    r = c2.fetchone()
                    if r: item, qty, sheet, kind, src = str(r[0]).strip(), float(r[1] or 0), int(r[2] or 0), "간판", "legacy"
                if not item:
                    c2.execute("SELECT TOP 1 ITEM_CODE, PRINT_QTY, SHEET_NO FROM PR_T_PRINT_STICKER WHERE QR_BARCODE_FROM=? OR QR_BARCODE_TO=?", bc, bc)
                    r = c2.fetchone()
                    if r: item, qty, sheet, kind, src = str(r[0]).strip(), float(r[1] or 0), int(r[2] or 0), "라벨", "legacy"
                nm = ""
                if item:
                    c2.execute("SELECT ISNULL(ITEM_DESC,'') FROM PR_M_ITEM WHERE ITEM_CODE=?", item)
                    rr = c2.fetchone(); nm = rr[0] if rr else ""
            finally: cn.close()
        else:
            cn = _conn(); c2 = cn.cursor()
            try:
                c2.execute("SELECT ISNULL(ITEM_DESC,'') FROM PR_M_ITEM WHERE ITEM_CODE=?", item)
                rr = c2.fetchone(); nm = rr[0] if rr else ""
            finally: cn.close()
        if not item:
            return {"found": False, "msg": "바코드를 찾을 수 없습니다 (간판 GP…/라벨 QR)"}
        cur.execute("SELECT ISNULL(SUM(prod_qty),0) FROM nx.proc_barcode WHERE barcode=? AND ISNULL(proc_code,'')=?", bc, proc_code.strip())
        prev = float(cur.fetchone()[0] or 0)
        return {"found": True, "barcode": bc, "kind": kind, "src": src, "item_code": item, "item_name": nm,
                "qty": qty, "sheet_no": sheet, "prev_qty": prev, "action": ("취소" if prev > 0 else "등록")}
    finally:
        nx.close()

@router.post("/api/procbc/save")
def procbc_save(payload: dict = Body(...)):
    """스캔 실적 저장 — 등록(+수량)/취소(−기실적) 토글. nx.proc_barcode.
    ★자동 백플러시: 완성공정(proc==품목 MAX PROC_SEQ 또는 finish_flag='1') AND INNER_PROD=1 이면
      등록→backflush post(전체BOM×수량, +ASY/+PRD), 취소→reverse. bc_id+ref_key(BC:{bc}:{proc}) 멱등.
      바코드 INSERT + 백플러시(소비/생산/log)를 _nx_tx 동일 트랜잭션(부분실패 전체 롤백)."""
    p = payload
    bc = str(p.get("barcode", "") or "").strip()
    proc = str(p.get("proc_code", "") or "").strip()
    item = str(p.get("item_code", "") or "").strip()
    qty = float(p.get("qty") or 0)
    user = (str(p.get("user") or "웹사용자")[:20])
    if not bc or not item:
        raise HTTPException(400, "바코드·품번이 필요합니다.")
    if not proc:
        raise HTTPException(400, "공정을 선택하세요.")
    cn = _conn(); nx = _nx_tx(); cur = nx.cursor()   # cn=RO(완성공정·INNER_PROD 판정), nx=쓰기 tx
    try:
        cur.execute("SELECT ISNULL(SUM(prod_qty),0) FROM nx.proc_barcode WHERE barcode=? AND ISNULL(proc_code,'')=?", bc, proc)
        prev = float(cur.fetchone()[0] or 0)
        store = -prev if prev > 0 else qty
        if store == 0:
            nx.rollback(); return {"ok": False, "errors": ["처리할 수량이 없습니다."]}
        cur.execute("""INSERT INTO nx.proc_barcode(barcode,proc_code,item_code,work_code,prod_tag,mach_code,worker_code,sheet_no,prod_qty,prod_datetime,insert_user)
            OUTPUT INSERTED.bc_id VALUES(?,?,?,?,?,?,?,?,?,GETDATE(),?)""",
            bc, proc, item, (str(p.get("work_code") or "").strip() or None), (str(p.get("prod_tag") or "").strip() or None),
            (str(p.get("mach_code") or "").strip() or None), (str(p.get("worker_code") or "").strip() or None),
            (int(p.get("sheet_no")) if str(p.get("sheet_no") or "").strip().isdigit() else None),
            store, user)
        new_bc = int(cur.fetchone()[0])
        # ★완성공정 자동 백플러시 훅
        bf = None
        final = _final_proc_code(cn, item)
        is_final = (bool(final) and proc == final) or str(p.get("finish_flag", "")).strip() == "1"
        if is_final and _is_inner_prod(cn, item):
            ref_key = f"BC:{bc}:{proc}"
            gpc = proc
            wo = (str(p.get("sheet_no") or "").strip() or f"BC{new_bc}")
            if store > 0:   # 등록 → 백플러시 post
                bf = _backflush_core(cn, nx, item, store, wo, gpc, "post", user, ref_key, ref_bc=new_bc)
            else:           # 취소 → 백플러시 reverse
                bf = _backflush_core(cn, nx, item, prev, wo, gpc, "reverse", user, ref_key, ref_bc=new_bc)
        nx.commit()
        return {"ok": True, "action": ("취소" if prev > 0 else "등록"), "qty": store, "bc_id": new_bc,
                "final_proc": (proc if is_final else ""), "backflush": bf}
    except Exception as e:
        try: nx.rollback()
        except Exception: pass
        return {"ok": False, "errors": [str(e)[:200]]}
    finally:
        cn.close(); nx.close()

@router.get("/api/procbc/list")
def procbc_list(from_ymd: str = Query(""), to_ymd: str = Query(""), proc: str = Query(""), limit: int = Query(300)):
    """바코드 실적 이력(nx.proc_barcode). 품명 디코드."""
    nx = _nx(); cur = nx.cursor()
    cn = _conn(); c2 = cn.cursor()
    try:
        w = ["1=1"]; pr = []
        if from_ymd.strip(): w.append("b.prod_datetime>=?"); pr.append(from_ymd.strip() + " 00:00:00")
        if to_ymd.strip(): w.append("b.prod_datetime<=?"); pr.append(to_ymd.strip() + " 23:59:59")
        if proc.strip(): w.append("b.proc_code=?"); pr.append(proc.strip())
        cur.execute(f"""SELECT TOP {max(1,min(int(limit),2000))} b.bc_id,b.barcode,b.proc_code,b.item_code,b.prod_qty,
              b.worker_code,b.mach_code,b.sheet_no,b.prod_datetime,b.insert_user
            FROM nx.proc_barcode b WHERE {' AND '.join(w)} ORDER BY b.prod_datetime DESC, b.bc_id DESC""", *pr)
        rows = []; items = set()
        for r in cur.fetchall():
            g = lambda i: str(r[i] if r[i] is not None else "").strip()
            rows.append({"bc_id": r[0], "barcode": g(1), "proc": g(2), "item_code": g(3), "qty": float(r[4] or 0),
                         "worker": g(5), "mach": g(6), "sheet_no": r[7],
                         "dt": (r[8].isoformat() if hasattr(r[8], "isoformat") else ""), "user": g(9)})
            items.add(g(3))
        nm = {}; il = [x for x in items if x]
        for i in range(0, len(il), 900):
            ch = il[i:i+900]; ph = ",".join("?" * len(ch))
            c2.execute(f"SELECT ITEM_CODE, ISNULL(ITEM_DESC,'') FROM PR_M_ITEM WHERE ITEM_CODE IN ({ph})", *ch)
            for a, b in c2.fetchall(): nm[str(a).strip()] = b
        for x in rows: x["nm"] = nm.get(x["item_code"], "")
        return {"rows": rows, "cnt": len(rows)}
    finally:
        nx.close(); cn.close()
