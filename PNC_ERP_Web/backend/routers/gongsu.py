# -*- coding: utf-8 -*-
"""gongsu 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ============ 일반업무: 공수등록(근무/지원) — HR_M_WORK_INFO(라이브)↔nx.hr_work_info ============
_HRCHK = {"1": "연차", "2": "반차", "3": "조퇴"}  # 소스 dw_pr_worktime_001_t2(4~6은 빈 라벨=정상)
def _hrchk(v):
    return _HRCHK.get(str(v or "").strip(), "정상")
@router.get("/api/gongsu/list")
def gongsu_list(from_ymd: str = Query(""), to_ymd: str = Query(""), dept: str = Query(""),
                gubun: str = Query(""), user: str = Query(""), src: str = Query("legacy")):
    """공수 조회. src=legacy(HR_M_WORK_INFO)/nx(nx.hr_work_info). gubun=근무/지원."""
    if src == "nx":
        nx = _nx(); cur = nx.cursor()
        try:
            w = ["1=1"]; p = []
            if from_ymd: w.append("work_ymd>=?"); p.append(_d6(from_ymd))
            if to_ymd:   w.append("work_ymd<=?"); p.append(_d6(to_ymd))
            if dept.strip(): w.append("dept_code=?"); p.append(dept.strip())
            if gubun.strip(): w.append("gubun=?"); p.append(gubun.strip())
            if user.strip(): w.append("user_id LIKE ?"); p.append(f"%{user.strip()}%")
            cur.execute(f"""SELECT id ID, gubun, work_ymd, dept_code, ISNULL(user_id,'') user_id, ISNULL(line,'') line,
                  ISNULL(start_time,'') start_time, ISNULL(end_time,'') end_time, ISNULL(work_hr,0) work_hr,
                  ISNULL(support_line,'') support_line, ISNULL(support_hr,0) support_hr, ISNULL(hr_check,'0') hr_check,
                  ISNULL(remarks,'') remarks FROM nx.hr_work_info WHERE {' AND '.join(w)}
                ORDER BY work_ymd DESC, id DESC""", *p)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            for r in rows:
                r["src"] = "nx"; r["work_hr"] = float(r["work_hr"] or 0); r["support_hr"] = float(r["support_hr"] or 0)
                r["dept_nm"] = ""; r["hr_check_nm"] = _hrchk(r["hr_check"])
            return {"rows": rows, "cnt": len(rows), "sum_hr": sum(r["work_hr"] + r["support_hr"] for r in rows)}
        finally:
            nx.close()
    cn = _conn(); cur = cn.cursor()
    try:
        w = ["1=1"]; p = []
        if from_ymd: w.append("A.WORK_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("A.WORK_YMD<=?"); p.append(_d6(to_ymd))
        if dept.strip(): w.append("A.DEPT_CODE=?"); p.append(dept.strip())
        if user.strip(): w.append("A.USER_ID LIKE ?"); p.append(f"%{user.strip()}%")
        if gubun == "지원": w.append("ISNULL(A.SUPPORT_SHEET_NO,0)>0")
        elif gubun == "근무": w.append("ISNULL(A.SUPPORT_SHEET_NO,0)=0")
        cur.execute(f"""SELECT TOP 3000
              CASE WHEN ISNULL(A.SUPPORT_SHEET_NO,0)>0 THEN '지원' ELSE '근무' END gubun,
              A.WORK_YMD work_ymd, ISNULL(A.DEPT_CODE,'') dept_code,
              COALESCE(NULLIF(D.DEPT_DESC,''), G.GAGONG_PROC_DESC, A.DEPT_CODE) dept_nm,
              ISNULL(A.USER_ID,'') user_id, ISNULL(A.CUST_CODE,'') line, ISNULL(A.START_TIME,'') start_time,
              ISNULL(A.END_TIME,'') end_time, ISNULL(A.WORK_HR,0) work_hr, ISNULL(A.SUPPORT_LINE,'') support_line,
              ISNULL(A.SUPPORT_HR,0) support_hr, ISNULL(A.HR_CHECK_POINT,'0') hr_check, ISNULL(A.REMARKS,'') remarks
            FROM HR_M_WORK_INFO A LEFT JOIN HR_M_DEPT D ON D.DEPT_CODE=A.DEPT_CODE
              LEFT JOIN PR_M_PROC_GAGONG G ON G.GAGONG_PROC_CODE COLLATE DATABASE_DEFAULT=A.DEPT_CODE COLLATE DATABASE_DEFAULT
            WHERE {' AND '.join(w)} ORDER BY A.WORK_YMD DESC, A.DEPT_CODE, A.MAINT_SEQ""", *p)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["src"] = "legacy"; r["ID"] = None
            r["work_hr"] = float(r["work_hr"] or 0); r["support_hr"] = float(r["support_hr"] or 0)
            r["remarks"] = str(r["remarks"]).strip(); r["hr_check_nm"] = _hrchk(r["hr_check"])
        return {"rows": rows, "cnt": len(rows), "sum_hr": sum(r["work_hr"] + r["support_hr"] for r in rows)}
    finally:
        cn.close()

@router.post("/api/gongsu/save")
def gongsu_save(payload: dict = Body(...)):
    p = payload
    ymd = _d6(str(p.get("work_ymd", "")))
    user = str(p.get("user_id", "")).strip()[:40]
    if not ymd or not user:
        raise HTTPException(400, "근무일·작업자는 필수입니다.")
    def s(k, n): return str(p.get(k, "")).strip()[:n]
    def f(k):
        try: return float(p.get(k) or 0)
        except Exception: return 0.0
    vals = ((s("gubun", 4) or "근무"), ymd, s("dept_code", 20), user, s("line", 20), s("start_time", 6),
            s("end_time", 6), f("work_hr"), s("support_line", 20), s("support_start", 6), s("support_end", 6),
            f("support_hr"), (s("hr_check", 4) or "0"), s("remarks", 200), (s("uuser", 40) or "웹사용자"))
    mid = p.get("id")
    nx = _nx(); cur = nx.cursor()
    try:
        if mid:
            cur.execute("""UPDATE nx.hr_work_info SET gubun=?,work_ymd=?,dept_code=?,user_id=?,line=?,start_time=?,
                end_time=?,work_hr=?,support_line=?,support_start=?,support_end=?,support_hr=?,hr_check=?,
                remarks=?,upd_user=?,upd_dt=getdate() WHERE id=?""", *vals, int(mid))
            return {"ok": True, "id": int(mid), "mode": "update"}
        cur.execute("""INSERT INTO nx.hr_work_info(gubun,work_ymd,dept_code,user_id,line,start_time,end_time,
            work_hr,support_line,support_start,support_end,support_hr,hr_check,remarks,upd_user)
            OUTPUT INSERTED.id VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", *vals)
        return {"ok": True, "id": int(cur.fetchone()[0]), "mode": "insert"}
    finally:
        nx.close()

@router.post("/api/gongsu/delete")
def gongsu_delete(payload: dict = Body(...)):
    ids = [int(x) for x in (payload.get("ids", []) or []) if str(x).strip()]
    if not ids: return {"ok": True, "deleted": 0}
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute(f"DELETE FROM nx.hr_work_info WHERE id IN ({','.join('?'*len(ids))})", *ids)
        return {"ok": True, "deleted": cur.rowcount}
    finally:
        nx.close()
