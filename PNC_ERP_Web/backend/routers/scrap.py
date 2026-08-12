# -*- coding: utf-8 -*-
"""scrap 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ================= 가공스크랩관리 (w_qa_raw_input_100/120/125) — QA_T_RAW_ERROR 조회 ∪ nx.scrap_raw(쓰기) =================
# 조회=라이브 QA_T_RAW_ERROR(RO)+nx.scrap_raw 합집합 / 추가·수정·삭제·복사=nx만. 컬럼=SEQ·구분·불량일자·P/No·품명·작업처·작업자·소재항목·불량내용·발생공정·스크랩중량(kg).
_SCRAP_TAG = {"1": "재료", "2": "가공스크랩"}     # 구분(error_tag) — 코드마스터 부재, 데이터 추론(정확명 담당확인)
_SCRAP_SOJE = ["Scrap 일반", "동칩", "동가루", "작업 불량", "고강도", "세팅 불량"]   # 소재항목(실측 고정값)

@router.get("/api/scrap/list")
def scrap_list(from_ymd: str = Query(""), to_ymd: str = Query(""), tag: str = Query(""),
               item: str = Query(""), src: str = Query("")):
    """가공스크랩 목록. 불량기간(error_ymd)·구분(error_tag)·품번 필터. src: L(라이브)/N(nx)/공백=합집합. 하단합계=건수·총중량(kg)."""
    f6 = _d6(from_ymd) if from_ymd else ""; t6 = _d6(to_ymd) if to_ymd else ""
    rows = []
    if src != "N":   # 라이브 QA_T_RAW_ERROR (읽기전용)
        cn = _conn(); cur = cn.cursor()
        try:
            w = ["1=1"]; p = []
            if f6: w.append("e.ERROR_YMD>=?"); p.append(f6)
            if t6: w.append("e.ERROR_YMD<=?"); p.append(t6)
            if tag.strip(): w.append("e.ERROR_TAG=?"); p.append(tag.strip())
            if item.strip(): w.append("e.ITEM_CODE LIKE ?"); p.append(f"%{item.strip()}%")
            cur.execute(f"""SELECT TOP 3000 e.SEQ seq, ISNULL(e.ERROR_TAG,'') tag, e.ERROR_YMD ymd, ISNULL(e.ITEM_CODE,'') item,
                  ISNULL(e.ITEM_DESC,'') item_desc, ISNULL(e.WORK_CODE,'') work, ISNULL(w.WORK_DESC,'') work_desc,
                  ISNULL(e.ERROR_MEMBER_NAME,'') worker, ISNULL(e.ERROR_ITEM,'') soje, ISNULL(e.ERROR_DESC,'') err_desc,
                  ISNULL(e.PROC_CODE,'') pcode, ISNULL(g.GAGONG_PROC_DESC,'') proc_desc, ISNULL(e.LOT_QTY,0) wt, ISNULL(e.INSERT_USER_ID,'') usr
                FROM PARTNER_ERP_TEST3.nx.QA_T_RAW_ERROR e
                LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_WORK w ON w.WORK_CODE=e.WORK_CODE
                LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG g ON g.GAGONG_PROC_CODE=e.PROC_CODE
                WHERE {' AND '.join(w)} ORDER BY e.ERROR_YMD DESC, e.SEQ DESC""", *p)
            cols = [c[0] for c in cur.description]
            for r in cur.fetchall():
                d = dict(zip(cols, r)); d["wt"] = float(d["wt"] or 0)
                d["id"] = f"L{int(d['seq'])}"; d["src"] = "L"; rows.append(d)
        finally: cn.close()
    if src != "L":   # nx.scrap_raw (신규 쓰기분)
        nx = _nx(); cur = nx.cursor()
        try:
            w = ["1=1"]; p = []
            if f6: w.append("s.error_ymd>=?"); p.append(f6)
            if t6: w.append("s.error_ymd<=?"); p.append(t6)
            if tag.strip(): w.append("s.error_tag=?"); p.append(tag.strip())
            if item.strip(): w.append("s.item_code LIKE ?"); p.append(f"%{item.strip()}%")
            cur.execute(f"""SELECT s.id seq, ISNULL(s.error_tag,'') tag, s.error_ymd ymd, ISNULL(s.item_code,'') item,
                  ISNULL(s.item_desc,'') item_desc, ISNULL(s.work_code,'') work, ISNULL(w.WORK_DESC,'') work_desc,
                  ISNULL(s.error_member_name,'') worker, ISNULL(s.error_item,'') soje, ISNULL(s.error_desc,'') err_desc,
                  ISNULL(s.proc_code,'') pcode, ISNULL(g.GAGONG_PROC_DESC,'') proc_desc, ISNULL(s.lot_qty,0) wt, ISNULL(s.insert_user_id,'') usr
                FROM nx.scrap_raw s
                LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_WORK w ON w.WORK_CODE=s.work_code
                LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG g ON g.GAGONG_PROC_CODE=s.proc_code
                WHERE {' AND '.join(w)} ORDER BY s.error_ymd DESC, s.id DESC""", *p)
            cols = [c[0] for c in cur.description]
            for r in cur.fetchall():
                d = dict(zip(cols, r)); d["wt"] = float(d["wt"] or 0)
                d["id"] = f"N{int(d['seq'])}"; d["src"] = "N"; rows.append(d)
        finally: nx.close()
    rows.sort(key=lambda r: (str(r["ymd"]), str(r["src"]), r["seq"]), reverse=True)
    tags = [{"code": k, "name": f"{k} {v}"} for k, v in _SCRAP_TAG.items()]
    procs = sorted({(r["pcode"], r["proc_desc"]) for r in rows if r["pcode"]})
    works = sorted({(r["work"], r["work_desc"]) for r in rows if r["work"]})
    workers = sorted({r["worker"] for r in rows if r["worker"]})
    return {"rows": rows, "cnt": len(rows), "total_wt": round(sum(r["wt"] for r in rows), 2),
            "tags": tags, "sojes": _SCRAP_SOJE, "procs": [{"code": c, "name": (n or c)} for c, n in procs],
            "works": [{"code": c, "name": (n or c)} for c, n in works], "workers": workers}

@router.post("/api/scrap/save")
def scrap_save(payload: dict = Body(...)):
    """가공스크랩 추가/수정 → nx.scrap_raw. ★라이브(L*) 수정불가(읽기전용, 신규만 nx). 필수=불량일자·스크랩중량(>0)."""
    p = payload
    ymd = _d6(str(p.get("error_ymd", "")))
    lot = float(p.get("lot_qty") or 0)
    if not ymd:
        raise HTTPException(400, "불량일자는 필수입니다.")
    if lot <= 0:
        raise HTTPException(400, "스크랩중량(kg)은 0보다 커야 합니다.")
    tag = str(p.get("error_tag", "")).strip()[:2]
    item = str(p.get("item_code", "")).strip()[:20]
    idesc = str(p.get("item_desc", "")).strip()[:60]
    work = str(p.get("work_code", "") or "P2").strip()[:4]
    wcust = str(p.get("work_cust_code", "") or "Z99990").strip()[:10]
    proc = str(p.get("proc_code", "") or "P0001").strip()[:10]
    mach = str(p.get("mach_code", "")).strip()[:10]
    worker = str(p.get("error_member_name", "")).strip()[:30]
    soje = str(p.get("error_item", "")).strip()[:100]
    edesc = str(p.get("error_desc", "")).strip()[:300]
    eqty = float(p.get("error_qty") or 0)
    usr = (str(p.get("user", "")).strip() or "웹사용자")[:30]
    rid = str(p.get("id", "") or "").strip()
    nx = _nx(); cur = nx.cursor()
    try:
        if rid:
            if not rid.startswith("N"):
                raise HTTPException(409, "라이브(레거시) 자료는 수정할 수 없습니다 — 신규 등록분만 수정 가능(nx).")
            sid = int(rid[1:])
            cur.execute("""UPDATE nx.scrap_raw SET error_ymd=?, error_tag=?, item_code=?, item_desc=?, work_code=?, work_cust_code=?,
                  proc_code=?, mach_code=?, error_member_name=?, error_item=?, error_desc=?, lot_qty=?, error_qty=?,
                  update_user_id=?, update_datetime=getdate() WHERE id=?""",
                  ymd, tag, item, idesc, work, wcust, proc, mach, worker, soje, edesc, lot, eqty, usr, sid)
            if cur.rowcount == 0:
                raise HTTPException(404, f"대상 없음(N{sid})")
            return {"ok": True, "id": f"N{sid}", "mode": "update"}
        cur.execute("""INSERT INTO nx.scrap_raw(error_ymd,error_tag,item_code,item_desc,work_code,work_cust_code,proc_code,mach_code,
              error_member_name,error_item,error_desc,lot_qty,error_qty,insert_user_id)
            OUTPUT INSERTED.id VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ymd, tag, item, idesc, work, wcust, proc, mach, worker, soje, edesc, lot, eqty, usr)
        nid = int(cur.fetchone()[0])
        return {"ok": True, "id": f"N{nid}", "mode": "insert"}
    finally:
        nx.close()

@router.post("/api/scrap/delete")
def scrap_delete(payload: dict = Body(...)):
    """가공스크랩 삭제(nx만). 라이브(L*) 삭제 불가."""
    ids = [str(x) for x in (payload.get("ids", []) or []) if str(x).strip()]
    live = [x for x in ids if not x.startswith("N")]
    if live:
        raise HTTPException(409, f"라이브(레거시) 자료는 삭제할 수 없습니다(id: {','.join(live)}).")
    nids = [int(x[1:]) for x in ids if x.startswith("N")]
    if not nids:
        return {"ok": True, "deleted": 0}
    nx = _nx(); cur = nx.cursor()
    try:
        ph = ",".join("?" * len(nids))
        cur.execute(f"DELETE FROM nx.scrap_raw WHERE id IN ({ph})", *nids)
        return {"ok": True, "deleted": cur.rowcount}
    finally:
        nx.close()

@router.post("/api/scrap/copy")
def scrap_copy(payload: dict = Body(...)):
    """가공스크랩 복사(원본 L/N → nx 신규 1행). 원본 필드 복제, 신규 채번."""
    rid = str(payload.get("id", "") or "").strip()
    usr = (str(payload.get("user", "")).strip() or "웹사용자")[:30]
    if not rid:
        raise HTTPException(400, "복사할 자료 id 필요")
    src = None
    if rid.startswith("L"):   # 라이브 원본 읽기(RO)
        cn = _conn(); c = cn.cursor()
        try:
            c.execute("""SELECT ERROR_YMD,ISNULL(ERROR_TAG,''),ISNULL(ITEM_CODE,''),ISNULL(ITEM_DESC,''),ISNULL(WORK_CODE,''),
                  ISNULL(WORK_CUST_CODE,''),ISNULL(PROC_CODE,''),ISNULL(MACH_CODE,''),ISNULL(ERROR_MEMBER_NAME,''),
                  ISNULL(ERROR_ITEM,''),ISNULL(ERROR_DESC,''),ISNULL(LOT_QTY,0),ISNULL(ERROR_QTY,0)
                FROM PARTNER_ERP_TEST3.nx.QA_T_RAW_ERROR WHERE SEQ=?""", int(rid[1:]))
            src = c.fetchone()
        finally: cn.close()
    elif rid.startswith("N"):
        nx0 = _nx(); c = nx0.cursor()
        try:
            c.execute("""SELECT error_ymd,ISNULL(error_tag,''),ISNULL(item_code,''),ISNULL(item_desc,''),ISNULL(work_code,''),
                  ISNULL(work_cust_code,''),ISNULL(proc_code,''),ISNULL(mach_code,''),ISNULL(error_member_name,''),
                  ISNULL(error_item,''),ISNULL(error_desc,''),ISNULL(lot_qty,0),ISNULL(error_qty,0)
                FROM nx.scrap_raw WHERE id=?""", int(rid[1:]))
            src = c.fetchone()
        finally: nx0.close()
    if not src:
        raise HTTPException(404, "복사 원본 없음")
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("""INSERT INTO nx.scrap_raw(error_ymd,error_tag,item_code,item_desc,work_code,work_cust_code,proc_code,mach_code,
              error_member_name,error_item,error_desc,lot_qty,error_qty,insert_user_id)
            OUTPUT INSERTED.id VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            str(src[0]), str(src[1]), str(src[2]), str(src[3]), str(src[4]), str(src[5]), str(src[6]), str(src[7]),
            str(src[8]), str(src[9]), str(src[10]), float(src[11] or 0), float(src[12] or 0), usr)
        nid = int(cur.fetchone()[0])
        return {"ok": True, "id": f"N{nid}"}
    finally:
        nx.close()
