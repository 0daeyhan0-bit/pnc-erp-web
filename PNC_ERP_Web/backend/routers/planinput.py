# -*- coding: utf-8 -*-
"""생산계획추가입력(planinput)+준비재고조회(readystock) 도메인 라우터 — 수동 생산계획 CRUD·매트릭스.
   app.py에서 분리. 공유헬퍼는 common.py(_ITEM_WORK 포함)."""
from datetime import datetime
from fastapi import APIRouter, Query, Body, HTTPException
from common import _conn, _nx, _nx_tx, _b, _d6, _num, _ITEM_WORK

router = APIRouter()

# ===================== 생산계획추가입력 CRUD (nx.prod_plan_input ← PR_T_PLAN_INPUT) =====================
# 근거: w_pr_plan_060 / dw_pr_plan_060_1. 수동 추가 생산계획. work_code→이름(_ITEM_WORK).
_PPI_COLS = ["plan_ymd", "line_no", "item_code", "output_hm", "plan_qty", "work_order", "work_code", "prod_tag", "remarks"]

@router.get("/api/planinput/list")
def planinput_list(q: str = Query(""), line: str = Query(""), from_ymd: str = Query(""),
                   to_ymd: str = Query(""), limit: int = Query(500)):
    """생산계획추가입력 목록(nx.prod_plan_input). 품명·공정명 디코드."""
    nx = _nx(); cur = nx.cursor()
    try:
        w = ["1=1"]; p = []
        if q.strip(): w.append("(i.item_code LIKE ? OR i.work_order LIKE ?)"); p += [f"%{q.strip()}%"] * 2
        if line.strip(): w.append("i.line_no=?"); p.append(line.strip())
        if from_ymd.strip(): w.append("i.plan_ymd>=?"); p.append(from_ymd.strip())
        if to_ymd.strip(): w.append("i.plan_ymd<=?"); p.append(to_ymd.strip())
        cur.execute(f"""SELECT TOP {max(1,min(int(limit),3000))} i.ppi_id,i.plan_ymd,i.line_no,i.item_code,
              ISNULL(m.item_name,'') nm, i.output_hm,i.plan_qty,i.work_order,i.work_code,i.prod_tag,i.remarks
            FROM nx.prod_plan_input i LEFT JOIN nx.item m ON m.item_code=i.item_code
            WHERE {' AND '.join(w)} ORDER BY i.plan_ymd DESC, i.ppi_id DESC""", *p)
        rows = []
        for r in cur.fetchall():
            g = lambda k: str(r[k] if r[k] is not None else "").strip()
            rows.append({"ppi_id": r[0], "plan_ymd": g(1), "line_no": g(2), "item_code": g(3), "nm": g(4),
                         "output_hm": g(5), "plan_qty": r[6], "work_order": g(7),
                         "work_code": g(8), "work_nm": _ITEM_WORK.get(g(8), g(8)), "prod_tag": g(9), "remarks": g(10)})
        return {"rows": rows, "cnt": len(rows)}
    finally:
        nx.close()

@router.post("/api/planinput/save")
def planinput_save(payload: dict = Body(...)):
    """등록/수정. 검증: 일자 YYMMDD(6자리 숫자)·시각 HHMM·라인/품번 필수·수량>0."""
    p = payload
    ymd = str(p.get("plan_ymd", "") or "").strip()
    hm = str(p.get("output_hm", "") or "").strip()
    item = str(p.get("item_code", "") or "").strip()
    line = str(p.get("line_no", "") or "").strip()
    if not (ymd.isdigit() and len(ymd) == 6):
        raise HTTPException(400, "계획일자는 YYMMDD(6자리 숫자)여야 합니다.")
    if hm and not (hm.isdigit() and len(hm) == 4 and int(hm[:2]) < 24 and int(hm[2:]) < 60):
        raise HTTPException(400, "산출시각은 HHMM(4자리)여야 합니다.")
    if not item or not line:
        raise HTTPException(400, "라인·품번은 필수입니다.")
    try: qty = int(float(p.get("plan_qty") or 0))
    except Exception: qty = 0
    if qty <= 0:
        raise HTTPException(400, "계획수량은 0보다 커야 합니다.")
    def s(k): v = p.get(k); return None if v in (None, "") else str(v).strip()
    vals = (ymd, line, item, (hm or "2100"), qty, s("work_order"), s("work_code"), s("prod_tag"), s("remarks"))
    pid = p.get("ppi_id")
    nx = _nx(); cur = nx.cursor()
    try:
        if pid:
            cur.execute("""UPDATE nx.prod_plan_input SET plan_ymd=?,line_no=?,item_code=?,output_hm=?,plan_qty=?,
                work_order=?,work_code=?,prod_tag=?,remarks=?,upd_user='web',upd_dt=GETDATE() WHERE ppi_id=?""", *vals, int(pid))
            return {"ok": True, "mode": "update", "ppi_id": int(pid)}
        cur.execute("""INSERT INTO nx.prod_plan_input(plan_ymd,line_no,item_code,output_hm,plan_qty,work_order,
            work_code,prod_tag,remarks,src,upd_user,upd_dt) OUTPUT INSERTED.ppi_id
            VALUES(?,?,?,?,?,?,?,?,?,'web','web',GETDATE())""", *vals)
        return {"ok": True, "mode": "insert", "ppi_id": int(cur.fetchone()[0])}
    finally:
        nx.close()

@router.post("/api/planinput/delete")
def planinput_delete(payload: dict = Body(...)):
    ids = [int(x) for x in (payload.get("ids", []) or []) if str(x).strip().lstrip('-').isdigit()]
    if not ids: return {"ok": True, "deleted": 0}
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute(f"DELETE FROM nx.prod_plan_input WHERE ppi_id IN ({','.join('?'*len(ids))})", *ids)
        return {"ok": True, "deleted": cur.rowcount}
    finally:
        nx.close()

@router.get("/api/planinput/lines")
def planinput_lines():
    """라인(주문구분) 드롭다운 목록 = 코드+명칭.
    ★원천: CM_M_MASTER_DETAIL WHERE KIND_CODE='PR003' (라이브 PARTNER_ERP).
      - DETAIL_CODE=라인코드, DETAIL_DESC=명칭, SORT_SEQ=정렬. 레거시 w_pr_plan_060 라인 dddw와 동일 코드마스터
        (실측: AA=설치·KR=CKD(RAC)·KS=CKD(SAC)·DHZ=LG 콤프·GR=그린산업·EZ=이지링크·NG=불량대응 …, USE_FLAG=1 23건).
      - (구) PR_M_LINE_NO는 라인정비일 마스터일 뿐 명칭이 없어(공통/C1/C2…) 주문구분 드롭다운 소스로 부적합→PR003으로 교체.
    ② 실사용 병합: nx.prod_plan_input.line_no 중 PR003에 없는 코드(레거시 잔재 BB/IS/JN 등)는 코드=명칭으로 추가(누락 방지).
    정렬: PR003(SORT_SEQ,코드) 먼저, 그 뒤 PR003 밖 실사용코드(코드순)."""
    seen = set(); rows = []
    # ① 코드마스터(PR003) — 명칭 정본, SORT_SEQ 순
    try:
        cn = _conn(); c = cn.cursor()
        try:
            c.execute("""SELECT DETAIL_CODE, DETAIL_DESC FROM CM_M_MASTER_DETAIL
                          WHERE KIND_CODE='PR003' AND ISNULL(USE_FLAG,'1')<>'0'
                          ORDER BY SORT_SEQ, DETAIL_CODE""")
            for r in c.fetchall():
                code = str(r[0] or "").strip()
                nm = str(r[1] or "").strip() or code
                if code and code not in seen:
                    seen.add(code); rows.append({"code": code, "nm": nm})
        finally: cn.close()
    except Exception:
        pass
    # ② 실사용(nx) 중 PR003에 없는 코드(레거시 잔재) — 코드=명칭으로 병합
    try:
        nx = _nx(); cur = nx.cursor()
        try:
            cur.execute("SELECT DISTINCT line_no FROM nx.prod_plan_input WHERE ISNULL(line_no,'')<>'' ORDER BY line_no")
            extra = []
            for r in cur.fetchall():
                v = str(r[0] or "").strip()
                if v and v not in seen:
                    seen.add(v); extra.append({"code": v, "nm": v})
            rows.extend(extra)
        finally:
            nx.close()
    except Exception:
        pass
    return {"rows": rows, "cnt": len(rows)}

@router.post("/api/planinput/bulk")
def planinput_bulk(payload: dict = Body(...)):
    """엑셀 붙여넣기 일괄 등록. 공통값(기본 계획일자·라인·산출시각·생산구분·공정) + 행별(계획일자·품번·수량·제번·비고).
    ★계획일자: 행별 우선(엑셀 날짜열 붙여넣기), 없으면 공통 기본일자. 둘 다 없으면 skip.
    검증: 일자 YYMMDD(yyyymmdd 8자리는 앞2자리 절삭)·시각 HHMM·라인 필수, 각 행 품번 필수·수량>0. 유효행만 INSERT."""
    def _n6(v):
        s = "".join(ch for ch in str(v if v is not None else "") if ch.isdigit())
        if len(s) == 8: s = s[2:]          # yyyymmdd → yymmdd
        return s if (len(s) == 6) else ""
    p = payload
    ymd0 = _n6(p.get("plan_ymd"))          # 공통 기본일자(행에 일자 없을 때 채움). 없어도 됨(행별 지정 시).
    line = str(p.get("line_no", "") or "").strip()
    hm = str(p.get("output_hm", "") or "").strip() or "2100"
    tag = (str(p.get("prod_tag", "") or "").strip() or "1")
    wcode = str(p.get("work_code", "") or "").strip() or None
    if not (hm.isdigit() and len(hm) == 4 and int(hm[:2]) < 24 and int(hm[2:]) < 60):
        raise HTTPException(400, "산출시각은 HHMM(4자리)여야 합니다.")
    if not line:
        raise HTTPException(400, "라인은 필수입니다.")
    src = p.get("rows", []) or []
    recs = []
    skipped = 0
    for r in src:
        item = str(r.get("item_code", "") or "").strip()
        try: qty = int(float(r.get("plan_qty") or 0))
        except Exception: qty = 0
        rymd = _n6(r.get("plan_ymd")) or ymd0    # 행별 일자 우선, 없으면 공통
        if not item or qty <= 0 or not rymd:
            skipped += 1; continue
        wo = str(r.get("work_order", "") or "").strip() or None
        rm = str(r.get("remarks", "") or "").strip() or None
        recs.append((rymd, line, item, hm, qty, wo, wcode, tag, rm))
    if not recs:
        return {"ok": True, "inserted": 0, "skipped": skipped}
    nx = _nx(); cur = nx.cursor()
    try:
        cur.executemany("""INSERT INTO nx.prod_plan_input(plan_ymd,line_no,item_code,output_hm,plan_qty,work_order,
            work_code,prod_tag,remarks,src,upd_user,upd_dt)
            VALUES(?,?,?,?,?,?,?,?,?,'web-bulk','web',GETDATE())""", recs)
        return {"ok": True, "inserted": len(recs), "skipped": skipped}
    finally:
        nx.close()

_PROD_TAG = {"1": "양산", "2": "셀"}  # 근거: dw_pr_plan_030_c1 values="1:양산/2:셀" (전 화면 공통)

@router.get("/api/planinput/get")
def planinput_get(ppi_id: int = Query(...)):
    """단건 조회(매트릭스 셀 클릭 수정 프리필용). nx.prod_plan_input 1행."""
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("""SELECT i.ppi_id,i.plan_ymd,i.line_no,i.item_code,ISNULL(m.item_name,'') nm,
              i.output_hm,i.plan_qty,i.work_order,i.work_code,i.prod_tag,i.remarks
            FROM nx.prod_plan_input i LEFT JOIN nx.item m ON m.item_code=i.item_code
            WHERE i.ppi_id=?""", int(ppi_id))
        r = cur.fetchone()
        if not r:
            raise HTTPException(404, "행 없음")
        g = lambda k: str(r[k] if r[k] is not None else "").strip()
        return {"ppi_id": r[0], "plan_ymd": g(1), "line_no": g(2), "item_code": g(3), "nm": g(4),
                "output_hm": g(5), "plan_qty": r[6], "work_order": g(7),
                "work_code": g(8), "prod_tag": g(9), "remarks": g(10)}
    finally:
        nx.close()

@router.get("/api/planinput/matrix")
def planinput_matrix(base: str = Query(""), prevday: int = Query(0), days: int = Query(28),
                     q: str = Query(""), line: str = Query("")):
    """생산계획추가입력 매트릭스(레거시 w_pr_plan_060 / dw_pr_plan_030_t1 재현).
    좌측고정: WORK-ORDER·작업처(work_code:공정)·양산/셀(prod_tag)·라인·품번·품목구분(item.item_type)·생산수량·대체수량·출하수량·시간.
    우측: 기준일 기준 최근 N일(기본28≈4주) 일자매트릭스. ★기준일=마지막(우측 끝) 컬럼, 시작=기준일−(N−1).
      셀=해당일 SUM(plan_qty). 하단 일자합계.
    ★backward 창인 이유(실측): 등록된 추가계획은 기준일 이전(과거)에 집중 분포 → forward 창은 거의 공란(기준일=오늘 forward 28일=37행).
      레거시 w_pr_plan_060(dw_pr_plan_060_1)도 기준일에서 뒤로 약 2주 범위(≈725행)를 표시. backward로 맞춰 등록분 전부 노출.
    ★원천=nx.prod_plan_input 단일(=레거시 PR_T_PLAN_INPUT 이관본, src='legacy'/'web'). 라이브 병합시 이중계상되므로 병합 안함.
    ★대체수량/출하수량=PR_T_PLAN_INPUT/매트릭스源(dw_pr_plan_030_t1: lot_qty·plan_qty·prod_rate만)에 없음 → 공란(가정).
    전일기준(prevday): 우측 끝=OFF 기준일 / ON 전일(기준일−1)."""
    from datetime import datetime as _dt, timedelta as _td
    days = max(7, min(int(days), 60))
    b = (base or "").strip()
    try:
        d_end = _dt.strptime(b, "%y%m%d")
    except Exception:
        d_end = _dt.today()
    if prevday:
        d_end = d_end - _td(days=1)
    d0 = d_end - _td(days=days - 1)   # 시작=기준일−(N−1). 기준일이 마지막(우측 끝) 컬럼.
    dates = []  # [{ymd(YYMMDD), mmdd, dow(0=일..6=토), key}] — 오름차순(좌:과거 → 우:기준일)
    _dow = ["일", "월", "화", "수", "목", "금", "토"]
    for i in range(days):
        d = d0 + _td(days=i)
        y = d.strftime("%y%m%d")
        dates.append({"ymd": y, "mmdd": d.strftime("%m/%d"), "dow": _dow[(d.weekday() + 1) % 7],
                      "wd": d.weekday()})  # weekday 5=토 6=일
    d_from, d_to = dates[0]["ymd"], dates[-1]["ymd"]
    nx = _nx(); cur = nx.cursor()
    try:
        w = ["i.plan_ymd BETWEEN ? AND ?"]; p = [d_from, d_to]
        if q.strip(): w.append("(i.item_code LIKE ? OR i.work_order LIKE ?)"); p += [f"%{q.strip()}%"] * 2
        if line.strip(): w.append("i.line_no=?"); p.append(line.strip())
        cur.execute(f"""SELECT i.ppi_id,i.plan_ymd,i.line_no,i.item_code,ISNULL(m.item_name,'') nm,
              ISNULL(m.item_type,'') itype,i.output_hm,i.plan_qty,i.work_order,i.work_code,i.prod_tag,i.remarks,i.src
            FROM nx.prod_plan_input i LEFT JOIN nx.item m ON m.item_code=i.item_code
            WHERE {' AND '.join(w)}""", *p)
        gs = lambda v: str(v if v is not None else "").strip()
        groups = {}
        grand = {x["ymd"]: 0 for x in dates}
        for r in cur.fetchall():
            wo, ln, it, hm = gs(r[8]), gs(r[2]), gs(r[3]), gs(r[6])
            wc, tag = gs(r[9]), gs(r[10])
            ymd = gs(r[1]); qty = int(r[7] or 0)
            key = (wo, ln, it, wc, tag, hm)
            grp = groups.get(key)
            if grp is None:
                grp = groups[key] = {
                    "work_order": wo, "line_no": ln, "item_code": it, "nm": gs(r[4]),
                    "item_type": gs(r[5]), "work_code": wc, "work_nm": _ITEM_WORK.get(wc, wc),
                    "prod_tag": tag, "prod_nm": _PROD_TAG.get(tag, tag), "output_hm": hm,
                    "total": 0, "cells": {}, "ppids": [], "src": gs(r[12])}
            grp["total"] += qty
            grp["ppids"].append(r[0])
            c = grp["cells"].get(ymd)
            if c is None:
                c = grp["cells"][ymd] = {"qty": 0, "recs": []}
            c["qty"] += qty
            c["recs"].append({"ppi_id": r[0], "remarks": gs(r[11])})
            if ymd in grand:
                grand[ymd] += qty
        rows = sorted(groups.values(), key=lambda g: (g["item_code"], g["work_order"], g["line_no"]))
        return {"dates": dates, "rows": rows, "grandtot": grand,
                "total": sum(grand.values()), "cnt": len(rows),
                "note": "대체수량·출하수량은 PR_T_PLAN_INPUT/매트릭스源에 없어 공란(가정). 작업처=work_code(공정 P1용접/P2가공)."}
    finally:
        nx.close()

# ===================== 생산준비재고관리 — 준비(키팅) 재고 조회 (읽기전용, w_pu_ready_stock_010) =====================
# 근거: PU_T_READY_STOCK(잔량). 강제수정(자재복원 write)은 nx.ready원장 결정 필요→보류. 조회만 제공.
@router.get("/api/readystock/list")
def readystock_list(q: str = Query(""), proc: str = Query(""), limit: int = Query(1500)):
    """생산준비재고(키팅) 잔량 조회. 품명·공정명·거래처명 디코드. 라이브 읽기전용."""
    cn = _conn(); cur = cn.cursor()
    try:
        w = ["ISNULL(r.STOCK_QTY,0)<>0"]; p = []
        if q.strip(): w.append("(r.ITEM_CODE LIKE ? OR i.ITEM_DESC LIKE ?)"); p += [f"%{q.strip()}%"] * 2
        if proc.strip(): w.append("r.PROC_GUBUN=?"); p.append(proc.strip())
        cur.execute(f"""SELECT TOP {max(1,min(int(limit),5000))} r.ITEM_CODE, ISNULL(i.ITEM_DESC,'') nm, ISNULL(i.ITEM_SPEC,'') spec,
              ISNULL(r.PROC_GUBUN,'') proc_code, ISNULL(g.GAGONG_PROC_DESC,'') proc_nm,
              ISNULL(r.CUST_CODE,'') cust_code, ISNULL(c.CUST_DESC,'') cust_nm, r.STOCK_QTY, r.UPDATE_DATETIME
            FROM PU_T_READY_STOCK r
            LEFT JOIN PR_M_ITEM i ON i.ITEM_CODE=r.ITEM_CODE
            LEFT JOIN PR_M_PROC_GAGONG g ON g.GAGONG_PROC_CODE=r.PROC_GUBUN
            LEFT JOIN CM_M_CUST c ON c.CUST_CODE=r.CUST_CODE
            WHERE {' AND '.join(w)} ORDER BY r.ITEM_CODE, r.PROC_GUBUN""", *p)
        rows = []
        for r in cur.fetchall():
            g = lambda k: str(r[k] if r[k] is not None else "").strip()
            rows.append({"item_code": g(0), "nm": g(1), "spec": g(2), "proc_code": g(3),
                         "proc_nm": (g(4) or g(3)), "cust_code": g(5), "cust_nm": (g(6) or g(5)),
                         "stock_qty": float(r[7] or 0),
                         "upd_dt": (r[8].isoformat() if hasattr(r[8], "isoformat") else "")})
        # 공정 필터 목록(코드→이름)
        cur.execute("""SELECT DISTINCT r.PROC_GUBUN, ISNULL(g.GAGONG_PROC_DESC,'')
            FROM PU_T_READY_STOCK r LEFT JOIN PR_M_PROC_GAGONG g ON g.GAGONG_PROC_CODE=r.PROC_GUBUN
            WHERE ISNULL(r.STOCK_QTY,0)<>0 AND r.PROC_GUBUN>'' ORDER BY r.PROC_GUBUN""")
        procs = [{"code": str(a).strip(), "nm": (str(b).strip() or str(a).strip())} for a, b in cur.fetchall()]
        return {"rows": rows, "cnt": len(rows), "procs": procs,
                "total_qty": sum(x["stock_qty"] for x in rows)}
    finally:
        cn.close()
