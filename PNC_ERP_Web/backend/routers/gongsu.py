# -*- coding: utf-8 -*-
"""gongsu 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ============ 일반업무: 공수등록(근무/지원) — HR_M_WORK_INFO(라이브)↔nx.hr_work_info ============
_HRCHK = {"1": "연차", "2": "오전반차", "8": "오후반차", "3": "조퇴",
          "20": "잔업1", "21": "잔업1.5", "22": "잔업2", "23": "잔업2.5", "24": "잔업3", "25": "잔업3.5"}
# 소스 dw_pr_worktime_001_t2(4~6은 빈 라벨=정상).
# ★2026-08-23 반차를 오전/오후로 분리. 레거시 HR_CHECK_POINT 는 4·5·6·7·10~14 를 이미
#   다른 의미로 쓰고 있어(4=38,374건 등) 그 코드는 못 쓴다. '2'(레거시 0건)=오전반차,
#   '8'(레거시 미사용)=오후반차 로 배정. 시간규칙 오전 0800~1200 / 오후 1300~1700(각 4h).
def _hrchk(v):
    return _HRCHK.get(str(v or "").strip(), "정상")
def _gongsu_web_rows(from_ymd, to_ymd, dept, gubun, user):
    """웹 편집행 (nx.hr_work_info) — editable."""
    nx = _nx(); cur = nx.cursor()
    try:
        w = ["1=1"]; p = []
        if from_ymd: w.append("work_ymd>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("work_ymd<=?"); p.append(_d6(to_ymd))
        if dept.strip(): w.append("dept_code=?"); p.append(dept.strip())
        if gubun.strip(): w.append("gubun=?"); p.append(gubun.strip())
        if user.strip(): w.append("user_id LIKE ?"); p.append(f"%{user.strip()}%")
        cur.execute(f"""SELECT h.id ID, h.gubun, h.work_ymd, ISNULL(h.dept_code,'') dept_code,
              COALESCE(NULLIF(G.GAGONG_PROC_DESC,''), h.dept_code) dept_nm,
              ISNULL(h.user_id,'') user_id, ISNULL(h.line,'') line,
              ISNULL(h.start_time,'') start_time, ISNULL(h.end_time,'') end_time, ISNULL(h.work_hr,0) work_hr,
              ISNULL(h.support_line,'') support_line, ISNULL(h.support_hr,0) support_hr, ISNULL(h.hr_check,'0') hr_check,
              ISNULL(h.remarks,'') remarks FROM nx.hr_work_info h
              LEFT JOIN nx.PR_M_PROC_GAGONG G ON G.GAGONG_PROC_CODE COLLATE DATABASE_DEFAULT=h.dept_code COLLATE DATABASE_DEFAULT
            WHERE {' AND '.join(w)}""", *p)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["src"] = "nx"; r["editable"] = True
            r["work_hr"] = float(r["work_hr"] or 0); r["support_hr"] = float(r["support_hr"] or 0)
            r["hr_check_nm"] = _hrchk(r["hr_check"])
        return rows
    finally:
        nx.close()

def _gongsu_mirror_rows(from_ymd, to_ymd, dept, gubun, user):
    """미러 이력행 (nx.HR_M_WORK_INFO, 델타싱크가 채운 nx) — 읽기전용."""
    cn = _conn(); cur = cn.cursor()
    try:
        w = ["1=1"]; p = []
        if from_ymd: w.append("A.WORK_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("A.WORK_YMD<=?"); p.append(_d6(to_ymd))
        if dept.strip(): w.append("A.DEPT_CODE=?"); p.append(dept.strip())
        if user.strip(): w.append("A.USER_ID LIKE ?"); p.append(f"%{user.strip()}%")
        if gubun == "지원": w.append("ISNULL(A.SUPPORT_SHEET_NO,0)>0")
        elif gubun == "근무": w.append("ISNULL(A.SUPPORT_SHEET_NO,0)=0")
        cur.execute(f"""SELECT TOP 5000
              CASE WHEN ISNULL(A.SUPPORT_SHEET_NO,0)>0 THEN '지원' ELSE '근무' END gubun,
              A.WORK_YMD work_ymd, ISNULL(A.DEPT_CODE,'') dept_code,
              COALESCE(NULLIF(D.DEPT_DESC,''), G.GAGONG_PROC_DESC, A.DEPT_CODE) dept_nm,
              ISNULL(A.USER_ID,'') user_id, ISNULL(A.CUST_CODE,'') line, ISNULL(A.START_TIME,'') start_time,
              ISNULL(A.END_TIME,'') end_time, ISNULL(A.WORK_HR,0) work_hr, ISNULL(A.SUPPORT_LINE,'') support_line,
              ISNULL(A.SUPPORT_HR,0) support_hr, ISNULL(A.HR_CHECK_POINT,'0') hr_check, ISNULL(A.REMARKS,'') remarks
            FROM PARTNER_ERP_TEST3.nx.HR_M_WORK_INFO A LEFT JOIN PARTNER_ERP_TEST3.nx.HR_M_DEPT D ON D.DEPT_CODE=A.DEPT_CODE
              LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG G ON G.GAGONG_PROC_CODE COLLATE DATABASE_DEFAULT=A.DEPT_CODE COLLATE DATABASE_DEFAULT
            WHERE {' AND '.join(w)} ORDER BY A.WORK_YMD DESC, A.DEPT_CODE, A.MAINT_SEQ""", *p)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["src"] = "legacy"; r["ID"] = None; r["editable"] = False
            r["work_hr"] = float(r["work_hr"] or 0); r["support_hr"] = float(r["support_hr"] or 0)
            r["remarks"] = str(r["remarks"]).strip(); r["hr_check_nm"] = _hrchk(r["hr_check"])
        return rows
    finally:
        cn.close()

@router.get("/api/gongsu/list")
def gongsu_list(from_ymd: str = Query(""), to_ymd: str = Query(""), dept: str = Query(""),
                gubun: str = Query(""), user: str = Query(""), src: str = Query("")):
    """공수 조회 = nx.hr_work_info(웹편집·editable) ∪ nx.HR_M_WORK_INFO 미러(읽기전용 이력). 컷오버: 레거시 라이브 없음.
       src='nx'=웹행만, src='legacy'=미러만(하위호환). 기본=통합."""
    rows = []
    if src != "legacy":
        rows += _gongsu_web_rows(from_ymd, to_ymd, dept, gubun, user)
    if src != "nx":
        rows += _gongsu_mirror_rows(from_ymd, to_ymd, dept, gubun, user)
    rows.sort(key=lambda r: (str(r.get("work_ymd") or ""), 1 if r["src"] == "nx" else 0), reverse=True)
    return {"rows": rows, "cnt": len(rows), "sum_hr": sum(r["work_hr"] + r["support_hr"] for r in rows)}

@router.get("/api/gongsu/persons")
def gongsu_persons(part: str = Query("", description="파트(GAGONG_PROC_CODE), 빈값=전체"),
                   ymd: str = Query(""), gubun: str = Query("근무")):
    """인원정보호출 (레거시 w_pr_worktime_010) — 파트별 등록작업자를 공수 프리필 행으로.
       원천 nx.PR_M_PROC_GAGONG_WORKER. 해당일 이미 등록된 (파트,작업자)는 exists=True 로 표시."""
    part = (part or "").strip(); ymd6 = _d6(ymd) if ymd else ""
    cn = _conn(); cur = cn.cursor()
    try:
        w = ["1=1"]; p = []
        if part: w.append("wk.GAGONG_PROC_CODE=?"); p.append(part)
        cur.execute(f"""SELECT wk.GAGONG_PROC_CODE part, ISNULL(g.GAGONG_PROC_DESC,'') part_nm,
              wk.WORKER_CODE worker, ISNULL(wk.WORK_FLAG,'') real_flag
            FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG_WORKER wk
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG g ON g.GAGONG_PROC_CODE=wk.GAGONG_PROC_CODE
            WHERE {' AND '.join(w)} ORDER BY wk.GAGONG_PROC_CODE, wk.WORK_FLAG DESC, wk.WORKER_CODE""", *p)
        workers = [{"part": str(r[0]).strip(), "part_nm": str(r[1]).strip(),
                    "worker": str(r[2]).strip(), "real": str(r[3]).strip() == '1'} for r in cur.fetchall()]
        # 해당일 이미 등록된 (파트,작업자) 집합 (웹행 기준)
        exist = set()
        if ymd6:
            nx = _nx(); ncur = nx.cursor()
            try:
                ncur.execute("SELECT ISNULL(dept_code,''), ISNULL(user_id,'') FROM nx.hr_work_info WHERE work_ymd=?", ymd6)
                exist = {(str(a).strip(), str(b).strip()) for a, b in ncur.fetchall()}
            finally:
                nx.close()
        rows = []
        for wkr in workers:
            rows.append({"gubun": gubun, "work_ymd": ymd6, "dept_code": wkr["part"], "dept_nm": wkr["part_nm"],
                         "user_id": wkr["worker"], "line": wkr["part"], "start_time": "0800", "end_time": "1700",
                         "work_hr": 8, "support_line": "", "support_hr": 0, "hr_check": "0", "remarks": "",
                         "real": wkr["real"], "exists": (wkr["part"], wkr["worker"]) in exist})
        return {"part": part, "ymd": ymd6, "rows": rows, "cnt": len(rows)}
    finally:
        cn.close()

@router.post("/api/gongsu/save_bulk")
def gongsu_save_bulk(payload: dict = Body(...)):
    """공수 여러 행 일괄 등록 (인원정보호출 후 저장). rows=[{...}], nx.hr_work_info INSERT."""
    rows = payload.get("rows") or []
    uuser = str(payload.get("uuser") or "웹사용자")[:40]
    if not rows: return {"ok": True, "ins": 0}
    def s(d, k, n): return str(d.get(k, "")).strip()[:n]
    def f(d, k):
        try: return float(d.get(k) or 0)
        except Exception: return 0.0
    nx = _nx(); cur = nx.cursor(); ins = 0
    try:
        for r in rows:
            ymd = _d6(str(r.get("work_ymd", "")))
            user = str(r.get("user_id", "")).strip()[:40]
            if not ymd or not user: continue
            cur.execute("""INSERT INTO nx.hr_work_info(gubun,work_ymd,dept_code,user_id,line,start_time,end_time,
                work_hr,support_line,support_start,support_end,support_hr,hr_check,remarks,upd_user)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (s(r,"gubun",4) or "근무"), ymd, s(r,"dept_code",20), user, s(r,"line",20), s(r,"start_time",6),
                s(r,"end_time",6), f(r,"work_hr"), s(r,"support_line",20), s(r,"support_start",6), s(r,"support_end",6),
                f(r,"support_hr"), (s(r,"hr_check",4) or "0"), s(r,"remarks",200), uuser)
            ins += 1
        nx.commit()
        return {"ok": True, "ins": ins}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        nx.close()

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


# ============ 지원공수등록 (레거시 w_pr_support_time_010) ============
# ★"어디 파트 사람이 어디 라인으로 지원 갔다" 를 기록한다(2026-09-04 신설).
#   레거시 실측(HR_M_WORK_INFO, WORK_YMD=260902, SUPPORT_SHEET_NO=6841)에서 확인한 구조 =
#   지원 1건이 **두 행**으로 저장되고, 같은 SUPPORT_SHEET_NO 로 묶인다.
#
#     ① 받은파트 행 : dept_code=지원파트(S4)  1430~1700  work_hr=+2.50  support_line=원소속(RAC)
#     ② 원소속 행   : dept_code=원소속(RAC)   0000~0000  work_hr=0
#                     support_line=지원파트(S4) support_start/end=1430/1700 support_hr=2.50
#
#   의미 — 받은 파트는 그만큼 **공수가 올라가고**(①), 원소속은 그 시간만큼 자기 근무에서
#   **빠져나간 것으로 기록된다**(②, 조회화면이 이 support_hr 를 차감으로 표시).
#   휴게(rest)도 양쪽에 같은 값이 붙는다(실측 0.16).
def _sup_rest(hr):
    """지원 구간의 휴게공수 — 레거시 실측 2.50h → 0.16. 시간비례(2.50*0.064)로 재현한다.
       ※정확한 레거시 산식이 확인되면 여기만 고치면 된다(호출측 불변)."""
    try: h = float(hr or 0)
    except Exception: h = 0.0
    return round(h * 0.064, 2) if h > 0 else 0.0


@router.get("/api/gongsu/worker_parts")
def gongsu_worker_parts(worker: str = Query("", description="작업자명(부분일치)")):
    """지원자 → 소속파트 조회. 레거시는 지원자를 넣으면 파트가 자동으로 채워진다.
       ★한 사람이 여러 파트에 등록될 수 있어(실측 19명) 목록으로 준다 — 화면은 첫 값을
         자동선택하되 드롭다운으로 바꿀 수 있게 한다(레거시 파트칸이 드롭다운인 이유)."""
    w = (worker or "").strip()
    cn = _conn(); cur = cn.cursor()
    try:
        sql = """SELECT wk.WORKER_CODE, wk.GAGONG_PROC_CODE, ISNULL(g.GAGONG_PROC_DESC,''),
                        ISNULL(wk.WORK_FLAG,'')
                   FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG_WORKER wk
                   LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG g
                          ON g.GAGONG_PROC_CODE=wk.GAGONG_PROC_CODE"""
        p = []
        if w:
            sql += " WHERE wk.WORKER_CODE LIKE ?"; p.append("%" + w + "%")
        sql += " ORDER BY wk.WORKER_CODE, wk.WORK_FLAG DESC, wk.GAGONG_PROC_CODE"
        cur.execute(sql, *p)
        rows = [{"worker": str(r[0]).strip(), "part": str(r[1]).strip(),
                 "part_nm": str(r[2]).strip(), "real": str(r[3]).strip() == '1'}
                for r in cur.fetchall()]
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close()


@router.post("/api/gongsu/support_save")
def gongsu_support_save(payload: dict = Body(...)):
    """지원공수 저장 — 행마다 2행(받은파트 +공수 / 원소속 지원기록)을 같은 sheet_no 로 INSERT.
       body {work_ymd, support_part, rows:[{part, worker, start, end, remarks}], uuser}
         · support_part = 지원받는 파트(팝업 상단, 전 행 공통)
         · part         = 지원자의 원소속 파트(행별)
       ★쓰기는 nx 만(§1-1). 라이브 HR_M_WORK_INFO 는 건드리지 않는다."""
    ymd = _d6(str(payload.get("work_ymd", "")))
    sup_part = str(payload.get("support_part", "")).strip()[:20]
    uuser = str(payload.get("uuser") or "웹사용자")[:40]
    rows = payload.get("rows") or []
    if not ymd: return {"ok": False, "detail": "기준일자가 없습니다."}
    if not sup_part: return {"ok": False, "detail": "지원파트를 선택하세요."}

    def _hm(v):
        s = "".join(ch for ch in str(v or "") if ch.isdigit())
        return s.zfill(4)[:4] if s else ""

    def _hr(st, et):
        """시작~종료 → 공수(h). 점심 12:00~13:00 · 저녁 17:00~17:30 공제, 15분 단위.
           프론트 calcHr 과 같은 규칙(화면 표시와 저장값이 어긋나지 않게)."""
        a, b = _hm(st), _hm(et)
        if len(a) < 4 or len(b) < 4: return 0.0
        am = int(a[:2]) * 60 + int(a[2:]); bm = int(b[:2]) * 60 + int(b[2:])
        if bm <= am: return 0.0
        mi = bm - am
        for p, q in ((12 * 60, 13 * 60), (17 * 60, 17 * 60 + 30)):
            mi -= max(0, min(bm, q) - max(am, p))
        return max(0.0, round(mi / 15.0) / 4.0)

    valid = []
    for r in rows:
        wkr = str(r.get("worker", "")).strip()[:40]
        org = str(r.get("part", "")).strip()[:20]
        st, et = _hm(r.get("start")), _hm(r.get("end"))
        if not wkr or not org or not st or not et: continue
        hr = _hr(st, et)
        if hr <= 0: continue
        valid.append({"worker": wkr, "org": org, "st": st, "et": et, "hr": hr,
                      "rest": _sup_rest(hr), "remarks": str(r.get("remarks", "")).strip()[:200]})
    if not valid: return {"ok": False, "detail": "저장할 행이 없습니다(지원자·파트·시간 확인)."}

    nx = _nx(); cur = nx.cursor()
    try:
        # sheet_no 채번 — nx 안에서만 증가(라이브와 번호가 겹쳐도 무방: 조인하지 않는다)
        cur.execute("SELECT ISNULL(MAX(support_sheet_no),0) FROM nx.hr_work_info")
        sheet = int(cur.fetchone()[0] or 0) + 1
        ins = 0
        for v in valid:
            # ① 받은파트 행 — 그 파트의 공수가 올라간다
            cur.execute("""INSERT INTO nx.hr_work_info
                (gubun,work_ymd,dept_code,user_id,line,start_time,end_time,work_hr,
                 support_line,support_start,support_end,support_hr,hr_check,remarks,upd_user,
                 support_sheet_no,org_work_code,rest_work_hr,support_rest_hr)
                VALUES('지원',?,?,?,?,?,?,?,?,'','',0,'0',?,?,?,?,?,0)""",
                ymd, sup_part, v["worker"], sup_part, v["st"], v["et"], v["hr"],
                v["org"], v["remarks"], uuser, sheet, v["org"], v["rest"])
            # ② 원소속 행 — 지원 나간 만큼이 여기 기록된다(조회화면이 차감으로 표시)
            cur.execute("""INSERT INTO nx.hr_work_info
                (gubun,work_ymd,dept_code,user_id,line,start_time,end_time,work_hr,
                 support_line,support_start,support_end,support_hr,hr_check,remarks,upd_user,
                 support_sheet_no,org_work_code,rest_work_hr,support_rest_hr)
                VALUES('지원',?,?,?,?,'0000','0000',0,?,?,?,?,'0',?,?,?,?,0,?)""",
                ymd, v["org"], v["worker"], v["org"],
                sup_part, v["st"], v["et"], v["hr"], v["remarks"], uuser, sheet, v["org"], v["rest"])
            ins += 2
        nx.commit()
        return {"ok": True, "ins": ins, "pairs": len(valid), "sheet_no": sheet}
    except Exception as e:
        try: nx.rollback()
        except Exception: pass
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        nx.close()


@router.post("/api/gongsu/support_delete")
def gongsu_support_delete(payload: dict = Body(...)):
    """지원 1건 삭제 — sheet_no 로 **짝 2행을 함께** 지운다.
       ★한쪽만 지우면 받은파트 공수와 원소속 차감이 어긋난 채 남는다."""
    sheet = payload.get("sheet_no")
    try: sheet = int(sheet)
    except Exception: return {"ok": False, "detail": "sheet_no 가 필요합니다."}
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("DELETE FROM nx.hr_work_info WHERE support_sheet_no=?", sheet)
        n = cur.rowcount
        nx.commit()
        return {"ok": True, "deleted": n}
    except Exception as e:
        try: nx.rollback()
        except Exception: pass
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        nx.close()
