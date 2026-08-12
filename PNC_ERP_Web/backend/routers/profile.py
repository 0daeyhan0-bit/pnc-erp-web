# -*- coding: utf-8 -*-
"""profile 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ================= 조달 프로파일 관리 (발주규칙: 유효기간 1순위 + 다중시 배분) — nx.sourcing_profile =================
def _d(s):  # 'yyyy-mm-dd' → date str or None
    s = str(s or "").strip()
    return s[:10] if len(s) >= 10 and s[4] == '-' else None

@router.get("/api/profile/search")
def profile_search(q: str = Query("")):
    nx = _nx(); cur = nx.cursor()
    try:
        like = f"%{q.strip()}%"
        cur.execute("""SELECT TOP 80 sp.item_code, MAX(ISNULL(i.item_name,'')) nm, COUNT(*) profiles,
              SUM(CASE WHEN sp.is_active=1 THEN 1 ELSE 0 END) actives,
              MAX(CASE WHEN sp.supply_gubun='유상사급' THEN 1 ELSE 0 END) has_sagub
            FROM nx.sourcing_profile sp LEFT JOIN nx.item i ON i.item_code=sp.item_code
            WHERE sp.item_code LIKE ? OR i.item_name LIKE ?
            GROUP BY sp.item_code ORDER BY sp.item_code""", like, like)
        cols = [d[0] for d in cur.description]
        return {"rows": [dict(zip(cols, r)) for r in cur.fetchall()]}
    finally:
        nx.close()

@router.get("/api/profile/get")
def profile_get(item: str = Query(...)):
    item = item.strip()
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("SELECT item_name FROM nx.item WHERE item_code=?", item)
        r = cur.fetchone(); nm = r[0] if r else ""
        cur.execute("""SELECT sp.profile_id, sp.profile_name, sp.supply_gubun, ISNULL(sp.vendor_code,'') vendor_code,
              ISNULL(c.CUST_DESC,'') vendor_name, sp.lme_flag, CONVERT(varchar(10),sp.apply_from,23) apply_from,
              CONVERT(varchar(10),sp.apply_to,23) apply_to, sp.is_active, sp.is_internal,
              sp.alloc_ratio, sp.priority
            FROM nx.sourcing_profile sp
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=sp.vendor_code
            WHERE sp.item_code=? ORDER BY sp.is_internal DESC, sp.supply_gubun, sp.profile_id""", item)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["lme_flag"] = bool(r["lme_flag"]); r["is_active"] = bool(r["is_active"]); r["is_internal"] = bool(r["is_internal"])
            r["alloc_ratio"] = float(r["alloc_ratio"]) if r["alloc_ratio"] is not None else None
        return {"item": item, "item_name": nm, "rows": rows}
    finally:
        nx.close()

def _validate_alloc(profs):
    """profs=[(af,at,alloc)] 활성 비내부 프로파일. 유효기간 겹치는 모든 구간에서 배분합=100% 강제.
       단독(그 구간에 1개, alloc=None)은 암묵 100%. 반환: 위반 메시지 리스트(빈=정상)."""
    FAR = "2099-12-31"
    norm = [(af, at or FAR, alloc) for (af, at, alloc) in profs]
    pts = sorted({p[0] for p in norm} | {p[1] for p in norm})
    errs = []
    for seg in pts:
        cover = [al for (af, at, al) in norm if af <= seg <= at]
        if not cover:
            continue
        if len(cover) == 1 and cover[0] is None:
            continue  # 단독=암묵 100%
        total = sum((al or 0) for al in cover)
        if abs(total - 100.0) > 0.01:
            errs.append(f"{seg} 시점 배분합 {total:g}% — 정확히 100%가 되어야 합니다 (활성 프로파일 {len(cover)}개)")
    return list(dict.fromkeys(errs))

@router.post("/api/profile/save")
def profile_save(payload: dict = Body(...)):
    """발주규칙 저장: 유효기간(1순위)·활성·배분(2개이상). 검증: 겹치는 구간마다 배분합=100% 강제(위반시 저장차단·미기록)."""
    rows = payload.get("rows", []) or []
    item = str(payload.get("item", "")).strip()
    nx = _nx(); cur = nx.cursor()
    try:
        # is_internal 맵(내부용은 계획배분에서 제외 = 참조전용)
        internal = {}
        if item:
            cur.execute("SELECT profile_id, is_internal FROM nx.sourcing_profile WHERE item_code=?", item)
            internal = {r[0]: bool(r[1]) for r in cur.fetchall()}
        norm = []; active_non_internal = []
        for r in rows:
            pid = int(r.get("profile_id"))
            af = _d(r.get("apply_from")) or "2000-01-01"
            at = _d(r.get("apply_to"))
            act = bool(r.get("is_active"))
            ratio = r.get("alloc_ratio"); ratio = float(ratio) if (ratio not in (None, "", "null")) else None
            prio = r.get("priority"); prio = int(prio) if (prio not in (None, "", "null")) else None
            norm.append((pid, af, at, 1 if act else 0, ratio, prio))
            if act and not internal.get(pid, False):
                active_non_internal.append((af, at, ratio))
        # ★검증 먼저(쓰기 전) — 위반시 미기록
        errs = _validate_alloc(active_non_internal)
        if errs:
            return {"ok": False, "errors": errs}
        for (pid, af, at, act, ratio, prio) in norm:
            cur.execute("""UPDATE nx.sourcing_profile SET apply_from=?, apply_to=?, is_active=?, alloc_ratio=?, priority=?
                WHERE profile_id=?""", af, at, act, ratio, prio, pid)
        return {"ok": True, "count": len(norm)}
    finally:
        nx.close()
