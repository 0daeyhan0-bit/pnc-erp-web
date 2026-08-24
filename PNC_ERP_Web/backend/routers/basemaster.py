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
    # ★2026-08-23 assem/proc 은 웹에서 등록·수정·삭제하므로 조회도 nx 로(쓰기와 같은 원장).
    #   라이브만 보면 웹 추가분이 목록에 안 나온다(실측 CS_M_PROC nx 116 vs 라이브 95).
    "assem": {"t": "PARTNER_ERP_TEST3.nx.CS_M_ASSEM_PROC", "title": "조립공정MASTER", "src": "nx.CS_M_ASSEM_PROC", "order": "SORT_SEQ",
              "cols": [("ASSEM_PROC_CODE", "공정코드"), ("ASSEM_PROC_DESC", "공정명"), ("STD_ST", "표준ST"),
                       ("SORT_SEQ", "정렬"), ("USE_FLAG", "사용")]},
    "proc":  {"t": "PARTNER_ERP_TEST3.nx.CS_M_PROC", "title": "단품공정MASTER", "src": "nx.CS_M_PROC", "order": "SORT_SEQ",
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
        # ★2026-08-23 mstCrud(공용 편집 UI)는 행을 객체로 다루므로 c0..cN 키를 함께 준다.
        #   기존 화면(배열 그대로 그리는 조회탭)과 호환 위해 rows 는 유지하고 orows 를 추가.
        orows = [{f"c{i}": v for i, v in enumerate(r)} for r in rows]
        return {"kind": kind, "title": m["title"], "table": m["src"],
                "headers": [h for _, h in m["cols"]], "rows": rows, "orows": orows, "cnt": len(rows)}
    finally:
        cn.close()

# ============ 조립/단품 공정 마스터 등록·수정·삭제 (2026-08-23) ============
# 쓰기는 nx 만(CLAUDE.md §1). 조회 basemaster_list 는 라이브를 보므로,
# 웹에서 추가한 건이 목록에 보이려면 아래 _PROCM 의 t(=nx)로 저장한 뒤
# 조회도 nx 를 보도록 _BASEMASTER 의 assem/proc 테이블을 nx 로 지정해 둔다.
_PROCM = {
    "assem": {"t": "PARTNER_ERP_TEST3.nx.CS_M_ASSEM_PROC", "key": "ASSEM_PROC_CODE",
              "flds": [("ASSEM_PROC_DESC", "s", 30), ("STD_ST", "f", 0),
                       ("SORT_SEQ", "i", 0), ("USE_FLAG", "s", 1)]},
    # ★flds 순서 = 프론트 목록 컬럼(c1..cN) 순서와 반드시 일치시킬 것.
    #   proc: c1=공정명 c2=대분류 c3=정렬 c4=표준UPH c5=사용  (REMARKS 는 목록에 없어 맨 뒤)
    "proc":  {"t": "PARTNER_ERP_TEST3.nx.CS_M_PROC", "key": "PROC_CODE",
              "flds": [("PROC_DESC", "s", 30), ("ITEM_LGROUP", "s", 10), ("SORT_SEQ", "i", 0),
                       ("PROD_UPH", "f", 0), ("USE_FLAG", "s", 1), ("REMARKS", "s", 255)]},
}

def _pm_val(kind_fld, v):
    _, ty, ln = kind_fld
    if ty == "s":
        return str(v if v is not None else "").strip()[:ln]
    try:
        return (int(float(v or 0)) if ty == "i" else float(v or 0))
    except Exception:
        return 0

@router.post("/api/procmaster/save")
def procmaster_save(payload: dict = Body(...)):
    """조립(assem)/단품(proc) 공정마스터 등록·수정. 코드 있으면 UPDATE, 없으면 INSERT."""
    kind = str(payload.get("kind", "")).strip()
    m = _PROCM.get(kind)
    if not m:
        raise HTTPException(400, "kind 는 assem/proc 만 가능합니다.")
    # 프론트 mstCrud 는 keyField(c0)로 코드를 담는다. code / c0 둘 다 허용.
    code = (str(payload.get("code", "")).strip() or str(payload.get("c0", "")).strip())[:10]
    if not code:
        raise HTTPException(400, "공정코드는 필수입니다.")
    # 값은 c1..cN(프론트 폼 키) 우선, 없으면 컬럼명 소문자로도 받는다.
    vals = [_pm_val(f, payload.get(f"c{i+1}", payload.get(f[0].lower())))
            for i, f in enumerate(m["flds"])]
    user = str(payload.get("uuser", "") or "웹사용자")[:20]
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute(f"SELECT COUNT(*) FROM {m['t']} WHERE [{m['key']}]=?", code)
        exists = cur.fetchone()[0] > 0
        cols = [f[0] for f in m["flds"]]
        if exists:
            setp = ", ".join(f"[{c}]=?" for c in cols)
            cur.execute(f"""UPDATE {m['t']} SET {setp}, UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(),
                            UPDATE_WINDOW='web_procmaster' WHERE [{m['key']}]=?""", *vals, user, code)
            return {"ok": True, "code": code, "mode": "update"}
        ph = ",".join("?" * (len(cols) + 1))
        cur.execute(f"""INSERT INTO {m['t']} ([{m['key']}],{','.join('['+c+']' for c in cols)},
                        INSERT_USER_ID, INSERT_DATETIME, INSERT_WINDOW)
                        VALUES({ph}, ?, GETDATE(), 'web_procmaster')""", code, *vals, user)
        return {"ok": True, "code": code, "mode": "insert"}
    finally:
        nx.close()

@router.post("/api/procmaster/delete")
def procmaster_delete(payload: dict = Body(...)):
    """조립/단품 공정마스터 삭제(nx만). 사용중이면 USE_FLAG='N' 을 권장."""
    kind = str(payload.get("kind", "")).strip()
    m = _PROCM.get(kind)
    if not m:
        raise HTTPException(400, "kind 는 assem/proc 만 가능합니다.")
    # 프론트 mstCrud 는 체크박스 다건삭제라 codes 배열로 보낸다(단건 code 도 허용).
    codes = [str(x).strip() for x in (payload.get("codes") or []) if str(x).strip()]
    one = str(payload.get("code", "")).strip()
    if one and one not in codes:
        codes.append(one)
    if not codes:
        raise HTTPException(400, "삭제할 공정코드가 없습니다.")
    nx = _nx(); cur = nx.cursor()
    try:
        n = 0
        for c in codes:
            cur.execute(f"DELETE FROM {m['t']} WHERE [{m['key']}]=?", c)
            n += int(cur.rowcount or 0)
        return {"ok": True, "deleted": n}
    finally:
        nx.close()

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
