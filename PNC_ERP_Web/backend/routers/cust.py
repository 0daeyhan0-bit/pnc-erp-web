# -*- coding: utf-8 -*-
"""cust 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ============ 기준정보: 거래처MASTER CRUD (nx.cust, 위하고정합) — 레거시 w_cm_master_055 ============
_BIZTAG = {"0": "개인", "1": "사업자", "2": "관공서", "3": "국외업체"}
def _valid_bizno(s):
    """사업자등록번호 체크섬(f_check_saupjano 대응). 빈값은 통과(선택)."""
    d = [c for c in str(s or "") if c.isdigit()]
    if not d: return True
    if len(d) != 10: return False
    d = [int(x) for x in d]; key = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    tot = sum(d[i] * key[i] for i in range(9)) + (d[8] * 5) // 10
    return (10 - (tot % 10)) % 10 == d[9]

@router.get("/api/cust/opts")
def cust_opts():
    """거래처 드롭다운 소스: 거래처구분(PR011)·사업자구분·역할·결제조건·은행(CM701)."""
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("SELECT DETAIL_CODE, DETAIL_DESC FROM PARTNER_ERP_TEST3.nx.CM_M_MASTER_DETAIL WHERE KIND_CODE='PR011' ORDER BY DETAIL_CODE")
        cust_type = [{"code": str(r[0]).strip(), "nm": str(r[1]).strip()} for r in cur.fetchall()]
        cur.execute("SELECT DETAIL_CODE, DETAIL_DESC FROM PARTNER_ERP_TEST3.nx.CM_M_MASTER_DETAIL WHERE KIND_CODE='CM701' ORDER BY DETAIL_CODE")
        banks = [{"code": str(r[0]).strip(), "nm": str(r[1]).strip()} for r in cur.fetchall()]
        return {"cust_type": cust_type,
                "biztag": [{"code": k, "nm": v} for k, v in _BIZTAG.items()],
                "yn": [{"code": "1", "nm": "예"}, {"code": "0", "nm": "아니오"}],
                "ue_date": [{"code": "0", "nm": "당월결제"}, {"code": "1", "nm": "1개월후"}, {"code": "2", "nm": "2개월후"}, {"code": "3", "nm": "3개월후"}, {"code": "4", "nm": "4개월후"}],
                "ue_week": [{"code": "10", "nm": "10일"}, {"code": "25", "nm": "25일"}, {"code": "31", "nm": "31일"}],
                "banks": banks}
    finally:
        cn.close()

@router.get("/api/cust/newcode")
def cust_newcode():
    """신규 거래처코드 = 숫자코드 최댓값+1 (레거시 wf_last_cust_code)."""
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("SELECT MAX(CAST(cust_code AS INT)) FROM nx.cust WHERE cust_code NOT LIKE '%[^0-9]%'")
        mx = cur.fetchone()[0] or 0
        return {"code": str(int(mx) + 1).zfill(6)}
    finally:
        nx.close()

@router.get("/api/cust/list")
def cust_list(q: str = Query(""), use: str = Query(""), ctype: str = Query("")):
    """거래처MASTER 목록(nx.cust). 코드→이름 디코드."""
    nx = _nx(); cur = nx.cursor()
    try:
        cur2 = _conn().cursor()
        cur2.execute("SELECT DETAIL_CODE, DETAIL_DESC FROM PARTNER_ERP_TEST3.nx.CM_M_MASTER_DETAIL WHERE KIND_CODE='PR011'")
        dec = {str(r[0]).strip(): str(r[1]).strip() for r in cur2.fetchall()}
        w = ["1=1"]; p = []
        if q.strip(): w.append("(cust_code LIKE ? OR cust_name LIKE ? OR owner_name LIKE ?)"); p += [f"%{q.strip()}%"] * 3
        if use in ("0", "1"): w.append("use_flag=?"); p.append(int(use))
        if ctype.strip(): w.append("cust_type=?"); p.append(ctype.strip())
        cur.execute(f"""SELECT cust_code,cust_name,biz_no,owner_name,biz_type,biz_item,cust_type,
            in_flag,out_flag,outside_flag,business_tag,tel,fax,address1,charge_name,charge_tel,charge_email,
            homepage,dlvy_day,dlvy_day2,ue_date,ue_week,use_flag,remarks,resident_no,bank_flag,
            recv_address,sagub_out_flag,set_in_flag,heat_label_flag,print_name,corp_no,charge_user_id,
            charge_rank,charge_hp,post_no,address2,credit_limit,collateral_amt,gc_gubun
            FROM nx.cust WHERE {' AND '.join(w)} ORDER BY cust_code""", *p)
        cols = [d[0] for d in cur.description]
        rows = []
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            roles = []
            if d["in_flag"]: roles.append("매입")
            if d["out_flag"]: roles.append("매출")
            if d["outside_flag"]: roles.append("외주")
            d["roles"] = "·".join(roles)
            d["cust_type_nm"] = dec.get(str(d["cust_type"] or "").strip(), str(d["cust_type"] or ""))
            d["biztag_nm"] = _BIZTAG.get(str(d["business_tag"] or "").strip(), "")
            rows.append(d)
        return {"rows": rows, "cnt": len(rows)}
    finally:
        nx.close()

@router.post("/api/cust/save")
def cust_save(payload: dict = Body(...)):
    """거래처 등록/수정(nx.cust). 검증: 사업자번호 체크섬·거래처구분 필수·역할 최소1·코드중복."""
    p = payload
    code = str(p.get("cust_code", "")).strip()[:10]
    name = str(p.get("cust_name", "")).strip()[:50]
    if not code or not name:
        raise HTTPException(400, "거래처코드·거래처명은 필수입니다.")
    if not str(p.get("cust_type", "")).strip():
        raise HTTPException(400, "거래처구분을 선택해야 합니다.")
    if not (p.get("in_flag") or p.get("out_flag") or p.get("outside_flag")):
        raise HTTPException(400, "역할(매입/매출/외주) 최소 하나를 선택해야 합니다.")
    if not _valid_bizno(p.get("biz_no")):
        raise HTTPException(400, "사업자등록번호가 올바르지 않습니다.")
    def s(k, n): return str(p.get(k, "") or "").strip()[:n]
    def bit(k): return 1 if p.get(k) in (1, "1", True, "true") else 0
    def num(k):
        try: return int(float(p.get(k) or 0))
        except Exception: return 0
    is_new = not p.get("_edit")
    nx = _nx(); cur = nx.cursor()
    try:
        if is_new:
            cur.execute("SELECT 1 FROM nx.cust WHERE cust_code=?", code)
            if cur.fetchone():
                raise HTTPException(400, "동일한 거래처코드가 이미 등록되어 있습니다.")
        vals = (name, s("biz_no", 12), s("resident_no", 13), s("owner_name", 30), s("biz_type", 50), s("biz_item", 100),
                s("post_no", 6), s("address1", 100), s("address2", 100), s("tel", 50), s("fax", 20), s("print_name", 50),
                s("trade_start", 8), s("trade_end", 8), bit("use_flag"), s("dept_name", 30), s("charge_name", 30), s("charge_rank", 20),
                s("charge_tel", 20), s("charge_hp", 20), s("charge_email", 40), s("homepage", 50), num("credit_limit"), num("collateral_amt"),
                s("cust_type", 2), bit("in_flag"), bit("out_flag"), bit("outside_flag"), bit("bank_flag"), s("business_tag", 1),
                s("charge_user_id", 20), s("corp_no", 13), s("recv_post_no", 6), s("recv_address", 100), s("recv_address_dtl", 100),
                bit("sagub_out_flag"), bit("set_in_flag"), bit("heat_label_flag"), bit("prod_check_flag"),
                num("dlvy_day"), num("dlvy_day2"), s("ue_date", 2), s("ue_week", 2), s("ue_day", 2), s("gc_gubun", 10),
                s("bank_code", 10), s("bank_bookno", 20), s("bank_person_name", 30), s("cms_no", 20), s("remarks", 255),
                (s("user", 40) or "웹사용자"))
        setcols = ("cust_name=?,biz_no=?,resident_no=?,owner_name=?,biz_type=?,biz_item=?,post_no=?,address1=?,address2=?,"
                   "tel=?,fax=?,print_name=?,trade_start=?,trade_end=?,use_flag=?,dept_name=?,charge_name=?,charge_rank=?,"
                   "charge_tel=?,charge_hp=?,charge_email=?,homepage=?,credit_limit=?,collateral_amt=?,cust_type=?,in_flag=?,"
                   "out_flag=?,outside_flag=?,bank_flag=?,business_tag=?,charge_user_id=?,corp_no=?,recv_post_no=?,recv_address=?,"
                   "recv_address_dtl=?,sagub_out_flag=?,set_in_flag=?,heat_label_flag=?,prod_check_flag=?,dlvy_day=?,dlvy_day2=?,"
                   "ue_date=?,ue_week=?,ue_day=?,gc_gubun=?,bank_code=?,bank_bookno=?,bank_person_name=?,cms_no=?,remarks=?,upd_user=?")
        if is_new:
            cur.execute(
                "INSERT INTO nx.cust(cust_code,cust_name,biz_no,resident_no,owner_name,biz_type,biz_item,post_no,address1,address2,"
                "tel,fax,print_name,trade_start,trade_end,use_flag,dept_name,charge_name,charge_rank,charge_tel,charge_hp,charge_email,"
                "homepage,credit_limit,collateral_amt,cust_type,in_flag,out_flag,outside_flag,bank_flag,business_tag,charge_user_id,"
                "corp_no,recv_post_no,recv_address,recv_address_dtl,sagub_out_flag,set_in_flag,heat_label_flag,prod_check_flag,"
                "dlvy_day,dlvy_day2,ue_date,ue_week,ue_day,gc_gubun,bank_code,bank_bookno,bank_person_name,cms_no,remarks,upd_user,upd_dt) "
                "VALUES(" + ",".join(["?"] * 52) + ",getdate())", code, *vals)
            return {"ok": True, "mode": "insert", "cust_code": code}
        cur.execute(f"UPDATE nx.cust SET {setcols},upd_dt=getdate() WHERE cust_code=?", *vals, code)
        return {"ok": True, "mode": "update", "cust_code": code}
    finally:
        nx.close()

@router.post("/api/cust/delete")
def cust_delete(payload: dict = Body(...)):
    codes = [str(x).strip() for x in (payload.get("codes", []) or []) if str(x).strip()]
    if not codes: return {"ok": True, "deleted": 0}
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute(f"DELETE FROM nx.cust WHERE cust_code IN ({','.join('?'*len(codes))})", *codes)
        return {"ok": True, "deleted": cur.rowcount}
    finally:
        nx.close()

# ---------- 부서MASTER CRUD (nx.dept, 레거시 w_hr_master_010) ----------
_DEPT_F = ["dept_desc", "sort_key", "dept_desch", "dept_from_ymd", "dept_to_ymd", "fin_dept_code",
           "fin_from_ymd", "fin_to_ymd", "enterprise_dept", "wh_code", "use_flag", "remarks"]
@router.get("/api/dept/list")
def dept_list(q: str = Query("")):
    nx = _nx(); cur = nx.cursor()
    try:
        w = ""; p = []
        if q.strip(): w = " WHERE dept_code LIKE ? OR dept_desc LIKE ?"; p = [f"%{q.strip()}%"] * 2
        cur.execute(f"SELECT dept_code,dept_desc,sort_key,dept_desch,dept_from_ymd,dept_to_ymd,fin_dept_code,fin_from_ymd,fin_to_ymd,enterprise_dept,wh_code,use_flag,remarks FROM nx.dept{w} ORDER BY sort_key,dept_code", *p)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        return {"rows": rows, "cnt": len(rows)}
    finally:
        nx.close()

@router.post("/api/dept/save")
def dept_save(payload: dict = Body(...)):
    p = payload
    code = str(p.get("dept_code", "")).strip()[:4]
    if not code or not str(p.get("dept_desc", "")).strip():
        raise HTTPException(400, "부서코드·부서명은 필수입니다.")
    def s(k, n): return str(p.get(k, "") or "").strip()[:n]
    def num(k):
        try: return int(float(p.get(k) or 0))
        except Exception: return 0
    vals = (s("dept_desc", 30), num("sort_key"), s("dept_desch", 30), s("dept_from_ymd", 8), s("dept_to_ymd", 8),
            s("fin_dept_code", 4), s("fin_from_ymd", 8), s("fin_to_ymd", 8), s("enterprise_dept", 2), s("wh_code", 2),
            1 if p.get("use_flag") in (1, "1", True) else 0, s("remarks", 100), s("user", 40) or "웹사용자")
    nx = _nx(); cur = nx.cursor()
    try:
        if not p.get("_edit"):
            cur.execute("SELECT 1 FROM nx.dept WHERE dept_code=?", code)
            if cur.fetchone(): raise HTTPException(400, "이미 등록된 부서코드입니다.")
            cur.execute("INSERT INTO nx.dept(dept_code,dept_desc,sort_key,dept_desch,dept_from_ymd,dept_to_ymd,fin_dept_code,fin_from_ymd,fin_to_ymd,enterprise_dept,wh_code,use_flag,remarks,upd_user,upd_dt) VALUES(?," + ",".join(["?"] * 13) + ",getdate())", code, *vals)
            return {"ok": True, "mode": "insert", "dept_code": code}
        cur.execute("UPDATE nx.dept SET dept_desc=?,sort_key=?,dept_desch=?,dept_from_ymd=?,dept_to_ymd=?,fin_dept_code=?,fin_from_ymd=?,fin_to_ymd=?,enterprise_dept=?,wh_code=?,use_flag=?,remarks=?,upd_user=?,upd_dt=getdate() WHERE dept_code=?", *vals, code)
        return {"ok": True, "mode": "update", "dept_code": code}
    finally:
        nx.close()

@router.post("/api/dept/delete")
def dept_delete(payload: dict = Body(...)):
    codes = [str(x).strip() for x in (payload.get("codes", []) or []) if str(x).strip()]
    if not codes: return {"ok": True, "deleted": 0}
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute(f"DELETE FROM nx.dept WHERE dept_code IN ({','.join('?'*len(codes))})", *codes)
        return {"ok": True, "deleted": cur.rowcount}
    finally:
        nx.close()

# ---------- LINE-NO MASTER CRUD (nx.line_no, 레거시 w_pr_master_190) ----------
def _valid_hhmm(s):
    d = str(s or "").strip()
    if not d: return True
    return len(d) == 4 and d.isdigit() and int(d[:2]) < 24 and int(d[2:]) < 60

@router.get("/api/line/list")
def line_list(q: str = Query("")):
    nx = _nx(); cur = nx.cursor()
    try:
        w = ""; p = []
        if q.strip(): w = " WHERE l.line_no LIKE ?"; p = [f"%{q.strip()}%"]
        cur.execute(f"""SELECT l.line_no,l.apply_ymd,l.maint_day,l.maint_hhmm,l.link_cust_code,
              ISNULL(c.cust_name,'') link_cust_name, l.cust_maint_day
            FROM nx.line_no l LEFT JOIN nx.cust c ON c.cust_code=l.link_cust_code{w} ORDER BY l.line_no""", *p)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        return {"rows": rows, "cnt": len(rows)}
    finally:
        nx.close()

# ==================================================================================
