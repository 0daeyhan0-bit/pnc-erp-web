# -*- coding: utf-8 -*-
"""procbc 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ================= 가공바코드실적처리 (w_pr_input_018) — 스캔조회 + nx미러 실적등록/취소 =================
# ★018 원본 미발견: 데이터모델·필드매핑은 라이브확정, 쓰기는 nx미러(라이브 직접커밋 금지). durable=_legacy_analysis/BARCODE_RESULT_018_ANALYSIS.md
def _bc_box(barcode):
    """바코드 → box_no. 접두어(CT/GP/가공) 무시, 뒤 숫자 추출."""
    import re
    m = re.search(r'(\d+)\s*$', str(barcode if barcode is not None else '').strip())
    return int(m.group(1)) if m else None

@router.get("/api/gagong/barcode/scan")
def gagong_bc_scan(barcode: str = Query("")):
    """바코드 스캔 → 전표(BOX_NO) 정보 조회(읽기전용 라이브 + nx미러 기등록분)."""
    box = _bc_box(barcode)
    if not box: return {"ok": False, "msg": "바코드 형식 오류(숫자 없음)"}
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("""SELECT ISNULL(ic.ASSY_ITEM_CODE,''), ISNULL(ic.MAT_CODE,''), ISNULL(ic.ITEM_CODE,''),
              ISNULL(ic.PLAN_QTY,0), ISNULL(ic.PROD_QTY,0), ISNULL(ic.PROD_FLAG,'0'),
              ISNULL(ic.WH_GAGONG_PROC_CODE,''), ISNULL(pg.GAGONG_PROC_DESC, ic.WH_GAGONG_PROC_CODE), ISNULL(im.ITEM_DESC,'')
            FROM PARTNER_ERP_TEST3.nx.PR_T_INDI_CUTTING ic
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG pg ON pg.GAGONG_PROC_CODE=ic.WH_GAGONG_PROC_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM im ON im.ITEM_CODE=ic.MAT_CODE
            WHERE ic.BOX_NO=?""", box)
        r = cur.fetchone()
        if not r: return {"ok": False, "msg": f"전표(바코드 {box})가 존재하지 않습니다."}
        cur.execute("SELECT ISNULL(SUM(CAST(ISNULL(ERROR_QTY,0) AS int)),0), COUNT(*) FROM PARTNER_ERP_TEST3.nx.QA_T_ERROR WHERE BOX_NO=?", box)
        er = cur.fetchone(); err_qty = int(er[0] or 0); err_cnt = int(er[1] or 0)
        cur.execute("SELECT GOOD_QTY, BAD_QTY, ISNULL(REG_USER,''), CONVERT(varchar(19),REG_DATETIME,120) FROM PARTNER_ERP_TEST3.nx.gagong_barcode_result WHERE BOX_NO=?", box)
        nxr = cur.fetchone()
        return {"ok": True, "box_no": box, "assy": r[0], "mat": r[1], "matnm": r[8], "plan_qty": int(r[3] or 0),
                "prod_qty": int(r[4] or 0) + (int(nxr[0]) if nxr else 0), "prod_flag": r[5], "wh": r[7],
                "err_qty": err_qty, "err_cnt": err_cnt, "already": bool(nxr),
                "reg_good": (int(nxr[0]) if nxr else 0), "reg_bad": (int(nxr[1]) if nxr else 0),
                "reg_user": (nxr[2] if nxr else ""), "reg_dt": (nxr[3] if nxr else "")}
    finally:
        cn.close()

@router.post("/api/gagong/barcode/register")
def gagong_bc_register(payload: dict = Body(...)):
    """처리바코드 2회 일치 검증 → nx미러 실적등록(양품/불량). 라이브 직접커밋 안 함."""
    box = _bc_box(payload.get("box_no") or payload.get("scan1"))
    scan2 = _bc_box(payload.get("scan2"))
    good = int(float(payload.get("good_qty") or 0)); bad = int(float(payload.get("bad_qty") or 0))
    user = str(payload.get("user") or "웹")[:30]
    if not box: return {"ok": False, "msg": "바코드 오류"}
    if scan2 != box: return {"ok": False, "msg": "처리바코드가 스캔바코드와 일치하지 않습니다."}
    if good <= 0 and bad <= 0: return {"ok": False, "msg": "양품/불량 수량을 입력하세요."}
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("SELECT ISNULL(ASSY_ITEM_CODE,''), ISNULL(MAT_CODE,''), ISNULL(WH_GAGONG_PROC_CODE,''), ISNULL(PROD_FLAG,'0'), ISNULL(PLAN_QTY,0) FROM PARTNER_ERP_TEST3.nx.PR_T_INDI_CUTTING WHERE BOX_NO=?", box)
        lr = cur.fetchone()
        if not lr: return {"ok": False, "msg": f"전표(바코드 {box}) 없음"}
        ymd = _d6(str(payload.get("ymd") or "")) or None
        cur.execute("DELETE FROM PARTNER_ERP_TEST3.nx.gagong_barcode_result WHERE BOX_NO=?", box)
        cur.execute("""INSERT INTO PARTNER_ERP_TEST3.nx.gagong_barcode_result(BOX_NO,ASSY_ITEM_CODE,MAT_CODE,GOOD_QTY,BAD_QTY,REG_YMD,REG_USER,REG_DATETIME,WH_GAGONG_PROC_CODE)
            VALUES(?,?,?,?,?,?,?,getdate(),?)""", box, lr[0], lr[1], good, bad, ymd, user, lr[2])
        cn.commit()
        return {"ok": True, "box_no": box, "good_qty": good, "bad_qty": bad, "msg": "실적 등록 완료(nx 미러)"}
    finally:
        cn.close()

@router.post("/api/gagong/barcode/cancel")
def gagong_bc_cancel(payload: dict = Body(...)):
    """실적 취소 — nx미러 등록분 삭제."""
    box = _bc_box(payload.get("box_no"))
    if not box: return {"ok": False, "msg": "바코드 오류"}
    cn = _conn(); cur = cn.cursor()
    try:
        n = cur.execute("DELETE FROM PARTNER_ERP_TEST3.nx.gagong_barcode_result WHERE BOX_NO=?", box).rowcount
        cn.commit()
        return {"ok": True, "box_no": box, "deleted": n, "msg": ("실적 취소 완료" if n else "등록분 없음")}
    finally:
        cn.close()
