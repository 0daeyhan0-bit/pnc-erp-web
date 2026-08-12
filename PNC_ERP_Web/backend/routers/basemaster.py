# -*- coding: utf-8 -*-
"""basemaster 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ============ 기준정보: 기준MASTER관리(생산 요청) — 부서·라인·조립공정·단품공정 (라이브 조회) ============
_BASEMASTER = {
    "dept":  {"t": "HR_M_DEPT", "title": "부서MASTER", "src": "HR_M_DEPT", "order": "SORT_KEY",
              "cols": [("DEPT_CODE", "부서코드"), ("DEPT_DESC", "부서명"), ("SORT_KEY", "정렬"),
                       ("ENTERPRISE_DEPT", "전사부서"), ("WH_CODE", "창고"), ("USE_FLAG", "사용")]},
    "line":  {"t": "PR_M_LINE_NO", "title": "LINE-NO MASTER", "src": "PR_M_LINE_NO", "order": "LINE_NO",
              "cols": [("LINE_NO", "라인번호"), ("APPLY_YMD", "적용일"), ("MAINT_DAY", "리드(일)"),
                       ("MAINT_HHMM", "시각"), ("LINK_CUST_CODE", "연계거래처"), ("CUST_MAINT_DAY", "거래처리드")]},
    "assem": {"t": "CS_M_ASSEM_PROC", "title": "조립공정MASTER", "src": "CS_M_ASSEM_PROC", "order": "SORT_SEQ",
              "cols": [("ASSEM_PROC_CODE", "공정코드"), ("ASSEM_PROC_DESC", "공정명"), ("STD_ST", "표준ST"),
                       ("SORT_SEQ", "정렬"), ("USE_FLAG", "사용")]},
    "proc":  {"t": "CS_M_PROC", "title": "단품공정MASTER", "src": "CS_M_PROC", "order": "SORT_SEQ",
              "cols": [("PROC_CODE", "공정코드"), ("PROC_DESC", "공정명"), ("ITEM_LGROUP", "대분류"),
                       ("SORT_SEQ", "정렬"), ("PROD_UPH", "표준UPH"), ("USE_FLAG", "사용")]},
}
def _basemaster_partner(q):
    """거래처MASTER(라이브 CM_M_CUST). 레거시 w_cm_master_055. 코드→이름: CUST_TYPE=PR011 거래처구분, 역할=IN/OUT/OUTSIDE 플래그."""
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("SELECT DETAIL_CODE, DETAIL_DESC FROM PARTNER_ERP_TEST3.nx.CM_M_MASTER_DETAIL WHERE KIND_CODE='PR011'")
        dec = {str(r[0]).strip(): str(r[1]).strip() for r in cur.fetchall()}
        w = ""; p = []
        if q.strip():
            w = " AND (CUST_CODE LIKE ? OR CUST_DESC LIKE ? OR ISNULL(OWNER_NAME,'') LIKE ?)"
            p = [f"%{q.strip()}%"] * 3
        cur.execute(f"""SELECT CUST_CODE, ISNULL(CUST_DESC,''), ISNULL(OWNER_NAME,''), ISNULL(BUSINESS_NO,''),
              ISNULL(CUST_TYPE,''), ISNULL(IN_FLAG,'0'), ISNULL(OUT_FLAG,'0'), ISNULL(OUTSIDE_FLAG,'0'),
              ISNULL(BUSI_TYPE,''), ISNULL(BUSI_KIND,''), ISNULL(CHARGE_USER_ID,''), ISNULL(PHONE_NO,''),
              ISNULL(FAX_NO,''), ISNULL(ADDRESS,''), ISNULL(DLVY_DAY,0), ISNULL(DLVY_DAY2,0),
              ISNULL(SET_IN_FLAG,'0'), ISNULL(SAGUB_OUT_FLAG,'0'), ISNULL(HEAT_LABEL_FLAG,'0'),
              ISNULL(USE_FLAG,'0'), ISNULL(REMARKS,'')
            FROM PARTNER_ERP_TEST3.nx.CM_M_CUST WHERE CUST_CODE>''{w} ORDER BY CUST_CODE""", *p)
        yn = lambda v: 'Y' if str(v).strip() == '1' else ''
        rows = []
        for r in cur.fetchall():
            roles = []
            if str(r[5]).strip() == '1': roles.append('매입')
            if str(r[6]).strip() == '1': roles.append('매출')
            if str(r[7]).strip() == '1': roles.append('외주')
            rows.append([
                str(r[0]).strip(), str(r[1]).strip(), str(r[2]).strip(), str(r[3]).strip(),
                dec.get(str(r[4]).strip(), str(r[4]).strip()), '·'.join(roles),
                str(r[8]).strip(), str(r[9]).strip(), str(r[10]).strip(), str(r[11]).strip(),
                str(r[12]).strip(), str(r[13]).strip(), str(int(r[14] or 0)), str(int(r[15] or 0)),
                yn(r[16]), yn(r[17]), yn(r[18]), '사용' if str(r[19]).strip() == '1' else '중지', str(r[20]).strip(),
            ])
        headers = ['거래처코드', '상호', '대표자', '사업자번호', '거래처구분', '역할', '업태', '종목', '담당자',
                   '전화', '팩스', '주소', '납기일', '납기일2', '세트입고', '사급출고', '열처리라벨', '사용', '비고']
        return {"kind": "partner", "title": "거래처MASTER", "table": "CM_M_CUST",
                "headers": headers, "rows": rows, "cnt": len(rows)}
    finally:
        cn.close()

@router.get("/api/basemaster/list")
def basemaster_list(kind: str = Query("dept"), q: str = Query("")):
    """기준MASTER 라이브 조회(읽기전용). kind=partner/dept/line/assem/proc."""
    if kind == "partner":
        return _basemaster_partner(q)
    m = _BASEMASTER.get(kind)
    if not m:
        raise HTTPException(400, "알 수 없는 마스터 종류")
    cn = _conn(); cur = cn.cursor()
    try:
        sel = ", ".join(f"ISNULL(CAST([{col}] AS NVARCHAR(120)),'') c{i}" for i, (col, _) in enumerate(m["cols"]))
        w = ""
        p = []
        if q.strip():
            code_col, nm_col = m["cols"][0][0], m["cols"][1][0]
            w = f" WHERE [{code_col}] LIKE ? OR [{nm_col}] LIKE ?"
            p = [f"%{q.strip()}%"] * 2
        cur.execute(f"SELECT {sel} FROM {m['t']}{w} ORDER BY [{m['order']}]", *p)
        rows = [list(r) for r in cur.fetchall()]
        return {"kind": kind, "title": m["title"], "table": m["src"],
                "headers": [h for _, h in m["cols"]], "rows": rows, "cnt": len(rows)}
    finally:
        cn.close()

# ---- 달력 마스터(근무/라인별/파트별) — 엔티티+기간 필터, 요일/근무 파생 ----
# 소스근거(w_pr_plan_020): work_stats in('1','2','5','6')=근무일, '4'=제외(비근무). WEEKLY 1=일~7=토.
_CAL = {
    "cal_work": {"t": "HR_M_CALENDAR", "title": "근무달력MASTER", "ent": "WORK_TEAM", "entlbl": "근무팀", "date": "CALENDAR_YYMD", "d8": True},
    "cal_line": {"t": "PR_M_LINE_CALENDAR", "title": "라인별 달력관리", "ent": "LINE_NO", "entlbl": "라인", "date": "CALENDAR_YMD", "d8": False},
    "cal_part": {"t": "PR_M_PART_CALENDAR", "title": "파트별 달력관리", "ent": "PART_CODE", "entlbl": "파트", "date": "CALENDAR_YMD", "d8": False},
}
_WEEKDAY = ["", "일", "월", "화", "수", "목", "금", "토"]
def _wstats(v):
    s = str(v).strip()
    return "근무" if s in ("1", "2", "5", "6") else ("휴무" if s == "4" else "기타")
@router.get("/api/basemaster/cal")
def basemaster_cal(kind: str = Query("cal_line"), ent: str = Query(""),
                   from_ymd: str = Query(""), to_ymd: str = Query("")):
    """달력 마스터 라이브 조회(읽기전용). 엔티티(팀/라인/파트)+기간 필터."""
    m = _CAL.get(kind)
    if not m:
        raise HTTPException(400, "알 수 없는 달력 종류")
    cn = _conn(); cur = cn.cursor()
    try:
        dcol, ecol = m["date"], m["ent"]
        cur.execute(f"SELECT DISTINCT [{ecol}] FROM {m['t']} WHERE [{ecol}] IS NOT NULL ORDER BY [{ecol}]")
        ents = [str(r[0]).strip() for r in cur.fetchall() if str(r[0]).strip()]
        def cvt(s):
            d = "".join(ch for ch in str(s or "") if ch.isdigit())[-8:]
            if m["d8"]:
                return d if len(d) == 8 else (("20" + d[-6:]) if len(d) >= 6 else d)
            return d[-6:] if len(d) >= 6 else d
        w = ["1=1"]; p = []
        if from_ymd: w.append(f"[{dcol}]>=?"); p.append(cvt(from_ymd))
        if to_ymd:   w.append(f"[{dcol}]<=?"); p.append(cvt(to_ymd))
        if ent.strip(): w.append(f"[{ecol}]=?"); p.append(ent.strip())
        cur.execute(f"""SELECT TOP 3000 [{ecol}] ent, [{dcol}] ymd, ISNULL(WEEKLY,0) wk,
              ISNULL(WORK_STATS,'') ws, ISNULL(REMARKS,'') remarks
            FROM {m['t']} WHERE {' AND '.join(w)} ORDER BY [{dcol}] DESC""", *p)
        rows = []
        for r in cur.fetchall():
            ymd = str(r[1] or ""); ymd6 = ymd[2:] if len(ymd) == 8 else ymd
            try: wk = int(r[2] or 0)
            except Exception: wk = 0
            rows.append({"ent": str(r[0] or "").strip(), "ymd": ymd6,
                         "weekday": _WEEKDAY[wk] if 1 <= wk <= 7 else "",
                         "ws": str(r[3] or "").strip(), "ws_nm": _wstats(r[3]),
                         "remarks": str(r[4] or "").strip()})
        work = sum(1 for r in rows if r["ws_nm"] == "근무")
        return {"kind": kind, "title": m["title"], "table": m["t"], "entlbl": m["entlbl"],
                "ents": ents, "rows": rows, "cnt": len(rows), "work_days": work}
    finally:
        cn.close()
