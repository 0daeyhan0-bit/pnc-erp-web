# -*- coding: utf-8 -*-
"""modelbom 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ================= 모델BOM 관리 (w_pr_master_060/020) — 모델→도번 매핑(신규모델 등록) =================
# 조회=PR_M_MODEL_BOM(라이브 62762) ∪ nx.model_bom(우리 신규등록). 편성이 둘 다 사용.
def _ensure_modelbom(cur):
    cur.execute("""IF OBJECT_ID('nx.model_bom') IS NULL CREATE TABLE nx.model_bom(
        MODEL_NO varchar(30) NOT NULL, C_ITEM_CODE varchar(20) NOT NULL, USE_QTY decimal(18,4) DEFAULT 1,
        APPLY_FROM varchar(6) DEFAULT '000000', APPLY_TO varchar(6) DEFAULT '999999',
        REMARKS varchar(100), INS_USER varchar(20), INS_DT datetime DEFAULT getdate(),
        CONSTRAINT PK_nx_model_bom PRIMARY KEY(MODEL_NO,C_ITEM_CODE))""")

@router.get("/api/modelbom/search")
def modelbom_search(q: str = Query(""), by: str = Query("model")):
    """by=model: 모델검색 / by=item: 도번(역방향) 검색."""
    cn = _conn(); cur = cn.cursor()
    try:
        like = f"%{q.strip()}%"
        if by == "item":
            cur.execute("""SELECT TOP 100 C_ITEM_CODE cd, COUNT(DISTINCT MODEL_NO) n FROM PARTNER_ERP_TEST3.nx.PR_M_MODEL_BOM
                WHERE C_ITEM_CODE LIKE ? GROUP BY C_ITEM_CODE ORDER BY C_ITEM_CODE""", like)
            return {"by": "item", "rows": [{"code": r[0], "n": r[1]} for r in cur.fetchall()]}
        cur.execute("""SELECT TOP 100 MODEL_NO cd, COUNT(*) n FROM PARTNER_ERP_TEST3.nx.PR_M_MODEL_BOM
            WHERE MODEL_NO LIKE ? GROUP BY MODEL_NO ORDER BY MODEL_NO""", like)
        return {"by": "model", "rows": [{"code": r[0], "n": r[1]} for r in cur.fetchall()]}
    finally:
        cn.close()

@router.get("/api/modelbom/get")
def modelbom_get(model: str = Query(""), item: str = Query("")):
    """모델→도번(정방향) 또는 도번→모델(역방향). 라이브 ∪ nx.model_bom."""
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_modelbom(cur)
        if item.strip():  # 역방향
            cur.execute("""SELECT MODEL_NO, C_ITEM_CODE, USE_QTY, CONVERT(varchar,MAKE_YMD), CONVERT(varchar,TO_APPLY_YMD), 'live'
                  FROM PARTNER_ERP_TEST3.nx.PR_M_MODEL_BOM WHERE C_ITEM_CODE=?
                UNION ALL SELECT MODEL_NO, C_ITEM_CODE, USE_QTY, APPLY_FROM, APPLY_TO, 'nx' FROM nx.model_bom WHERE C_ITEM_CODE=?
                ORDER BY 1""", item.strip(), item.strip())
        else:
            cur.execute("""SELECT MODEL_NO, C_ITEM_CODE, USE_QTY, CONVERT(varchar,MAKE_YMD), CONVERT(varchar,TO_APPLY_YMD), 'live'
                  FROM PARTNER_ERP_TEST3.nx.PR_M_MODEL_BOM WHERE MODEL_NO=?
                UNION ALL SELECT MODEL_NO, C_ITEM_CODE, USE_QTY, APPLY_FROM, APPLY_TO, 'nx' FROM nx.model_bom WHERE MODEL_NO=?
                ORDER BY 2""", model.strip(), model.strip())
        rows = []
        for r in cur.fetchall():
            rows.append({"model": r[0], "item": r[1], "use_qty": float(r[2] or 1),
                         "from": str(r[3] or ''), "to": str(r[4] or ''), "src": r[5]})
        # 도번 품명
        codes = list({r["item"] for r in rows})
        nm = {}
        if codes:
            for i in range(0, len(codes), 900):
                ch = codes[i:i+900]; ph = ",".join("?" * len(ch))
                cur.execute(f"SELECT ITEM_CODE, ISNULL(item_name,''), ISNULL(in_cust,''), LTRIM(RTRIM(ISNULL(WORK_CODE,''))) FROM PARTNER_ERP_TEST3.nx.item WHERE ITEM_CODE IN ({ph})", *ch)
                for x in cur.fetchall(): nm[x[0]] = {"nm": x[1], "wc": (x[3] if x[3] else x[2])}
        for r in rows:
            info = nm.get(r["item"], {}); r["nm"] = info.get("nm", ""); r["wc"] = info.get("wc", "")
        return {"model": model, "item": item, "rows": rows}
    finally:
        nx.close()

@router.post("/api/modelbom/save")
def modelbom_save(payload: dict = Body(...)):
    """신규 모델→도번 등록/수정(nx.model_bom). 라이브 PR_M_MODEL_BOM은 읽기전용."""
    model = str(payload.get("model", "")).strip()
    rows = payload.get("rows", []) or []
    if not model:
        raise HTTPException(400, "model 필요")
    nx = _nx(); cur = nx.cursor()
    try:
        _ensure_modelbom(cur)
        cur.execute("DELETE FROM nx.model_bom WHERE MODEL_NO=?", model)
        saved = 0
        for r in rows:
            it = str(r.get("item", "")).strip()
            if not it: continue
            cur.execute("""INSERT INTO nx.model_bom(MODEL_NO,C_ITEM_CODE,USE_QTY,APPLY_FROM,APPLY_TO,REMARKS,INS_USER)
                VALUES(?,?,?,?,?,?,'web')""", model, it, float(r.get("use_qty") or 1),
                _d6(r.get("from")) or "000000", _d6(r.get("to")) or "999999", (r.get("remarks") or None))
            saved += 1
        return {"ok": True, "count": saved}
    finally:
        nx.close()
