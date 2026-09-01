# -*- coding: utf-8 -*-
"""salemagam 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _open_days, _ledger_return, _closed, _carry_win)

import weight_calc
router = APIRouter()

# ================= 매출마감처리 (w_pu_sale_020 재설계) — 협력사 매출(tag5) 업체별 마감·조정·사유 =================
def _dig4(s):
    d = "".join(ch for ch in str(s or "") if ch.isdigit())
    return d[2:6] if len(d) == 6 else d[:4]   # YYYYMM→YYMM, YYMM→그대로(방어적)

def _cur_ym():
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("SELECT FORMAT(GETDATE(),'yyMM')"); return cur.fetchone()[0]
    finally:
        cn.close()

_SALE_MAGAM = """WITH MAGAM(CUST_CODE,JUN_YYMM,JUN_MAGAM_DAY,MAGAM_DAY) AS (
  SELECT CUST_CODE, format(dateadd(MONTH,-1,convert(date,'{ym}'+'01',12)),'yyMM') JUN_YYMM,
    ISNULL((SELECT TOP 1 MAGAM_DAY FROM PARTNER_ERP_TEST3.nx.CM_M_CUST_MAGAM WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<=format(dateadd(MONTH,-1,convert(date,'{ym}'+'01',12)),'yyMM') ORDER BY APPLY_YYMM DESC),'31') JUN_MAGAM_DAY,
    ISNULL((SELECT TOP 1 MAGAM_DAY FROM PARTNER_ERP_TEST3.nx.CM_M_CUST_MAGAM WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<='{ym}' ORDER BY APPLY_YYMM DESC),'31') MAGAM_DAY
  FROM PARTNER_ERP_TEST3.nx.CM_M_CUST A)"""

def _sale_win():
    return "A.MAINT_YMD > mg.JUN_YYMM+mg.JUN_MAGAM_DAY AND A.MAINT_YMD <= '{ym}'+mg.MAGAM_DAY"

@router.get("/api/salemagam/list")
def salemagam_list(ym: str = Query("")):
    """매출마감 업체별 집계(협력사판매 tag5, 마감기준) + nx 마감상태·조정합."""
    y = _dig4(ym) or _cur_ym()
    _yy = int(y[:2]); _mm = int(y[2:]); _pm = _mm - 1; _py = _yy
    if _pm == 0: _pm = 12; _py -= 1
    prevym = f"{_py:02d}{_pm:02d}"   # ★조대 하한(전월) — 거래처별 마감일 범위는 전월~당월이므로 이 범위 밖은 스캔 불필요(MAINT_YMD 인덱스 프루닝)
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute(f"""{_SALE_MAGAM.format(ym=y)}
          SELECT A.CUST_CODE cc, MAX(C.CUST_DESC) nm, MAX(C.CUST_TYPE) ct,
            MAX(LTRIM(RTRIM(ISNULL(NULLIF(C.CHARGE_USER_ID,''),ISNULL(C.CHARGE_NAME,''))))) chg,
            SUM(-A.MAINT_QTY) qty, SUM(-A.MAINT_AMT) amt, SUM(-A.MAINT_VAT) vat, COUNT(DISTINCT A.MAT_CODE) items
          FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT A JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST C ON A.CUST_CODE=C.CUST_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
          WHERE A.MAINT_TAG='5' AND A.MAINT_YMD>='{prevym}00' AND A.MAINT_YMD<='{y}99' AND {_sale_win().format(ym=y)}
          GROUP BY A.CUST_CODE HAVING SUM(-A.MAINT_AMT)<>0 ORDER BY SUM(-A.MAINT_AMT) DESC""")
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        cn.close()
    nx = _nx(); nc = nx.cursor()
    try:
        nc.execute("SELECT cust_code,close_flag,bill_flag FROM nx.sale_close WHERE ym=?", y)
        st = {r[0]: (int(r[1] or 0), int(r[2] or 0)) for r in nc.fetchall()}
        nc.execute("SELECT cust_code, SUM(delta_amt) FROM nx.sale_adjust WHERE ym=? GROUP BY cust_code", y)
        adj = {r[0]: float(r[1] or 0) for r in nc.fetchall()}
    finally:
        nx.close()
    for r in rows:
        cc = r["cc"]; s = st.get(cc, (0, 0))
        r["qty"] = float(r["qty"] or 0); r["amt"] = float(r["amt"] or 0); r["vat"] = float(r["vat"] or 0); r["items"] = int(r["items"] or 0)
        r["close_flag"] = s[0]; r["bill_flag"] = s[1]
        r["adj_amt"] = adj.get(cc, 0.0); r["final_amt"] = round(r["amt"] + adj.get(cc, 0.0), 2)
    return {"ym": y, "rows": rows}

@router.get("/api/salemagam/detail")
def salemagam_detail(ym: str = Query(""), cc: str = Query(...)):
    """업체 마감상세: 품목×일자 피벗 + 저장된 조정내역."""
    y = _dig4(ym) or _cur_ym()
    _yy = int(y[:2]); _mm = int(y[2:]); _pm = _mm - 1; _py = _yy
    if _pm == 0: _pm = 12; _py -= 1
    prevym = f"{_py:02d}{_pm:02d}"   # ★조대 하한(전월)
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute(f"""{_SALE_MAGAM.format(ym=y)}
          SELECT A.MAT_CODE mat, MAX(M.item_name) nm, MAX(M.item_spec) spec, MAX(M.UNIT) unit, A.MAINT_COST cost,
            CAST(RIGHT(A.MAINT_YMD,2) AS INT) d, SUM(-A.MAINT_QTY) q, SUM(-A.MAINT_AMT) amt
          FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT A JOIN PARTNER_ERP_TEST3.nx.item M ON A.MAT_CODE=M.ITEM_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
          WHERE A.MAINT_TAG='5' AND A.CUST_CODE=? AND A.MAINT_YMD>='{prevym}00' AND A.MAINT_YMD<='{y}99' AND {_sale_win().format(ym=y)}
          GROUP BY A.MAT_CODE, A.MAINT_COST, CAST(RIGHT(A.MAINT_YMD,2) AS INT)""", cc)
        raw = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    finally:
        cn.close()
    items = {}; days = set()
    for r in raw:
        mat = str(r["mat"]).strip(); d = int(r["d"] or 0); days.add(d)
        it = items.setdefault(mat, {"mat": mat, "nm": r["nm"], "spec": r["spec"], "unit": r["unit"],
                                    "cost": float(r["cost"] or 0), "qty": 0.0, "amt": 0.0, "_bd": {}})
        qv = float(r["q"] or 0); av = float(r["amt"] or 0); cv = float(r["cost"] or 0)
        it["qty"] += qv; it["amt"] += av
        bd = it["_bd"].setdefault(d, {"d": d, "qty": 0.0, "amt": 0.0, "cost": cv})
        bd["qty"] += qv; bd["amt"] += av; bd["cost"] = cv
    for it in items.values():
        it["byday"] = sorted(it.pop("_bd").values(), key=lambda x: x["d"])
    items_list = sorted(items.values(), key=lambda x: -abs(x["amt"]))
    nx = _nx(); nc = nx.cursor()
    try:
        nc.execute("""SELECT adj_seq,adj_type,scope,mat_code,target_ymd,old_cost,new_cost,old_qty,new_qty,delta_amt,reason_code,reason_detail
                      FROM nx.sale_adjust WHERE ym=? AND cust_code=? ORDER BY adj_seq""", y, cc)
        adjs = [{"adj_type": r[1], "scope": r[2], "mat_code": r[3], "target_ymd": r[4],
                 "old_cost": (float(r[5]) if r[5] is not None else None), "new_cost": (float(r[6]) if r[6] is not None else None),
                 "old_qty": (float(r[7]) if r[7] is not None else None), "new_qty": (float(r[8]) if r[8] is not None else None),
                 "delta_amt": float(r[9] or 0), "reason_code": r[10], "reason_detail": r[11]} for r in nc.fetchall()]
        nc.execute("SELECT close_flag FROM nx.sale_close WHERE ym=? AND cust_code=?", y, cc)
        cr = nc.fetchone(); closed = int(cr[0]) if cr else 0
    finally:
        nx.close()
    return {"ym": y, "cc": cc, "days": sorted(days), "items": items_list, "adjustments": adjs, "close_flag": closed}

# ===== 이월·오픈일자·반품 (2026-09-01) — 이월=정산귀속·표시 / 반품=수불장 전표(매출반품=+재고복귀) =====
@router.get("/api/salemagam/carryover")
def salemagam_carryover(ym: str = Query(""), cc: str = Query("")):
    """이월 대상 = 협력사 마감일 이후~당월 말일 입고분(tag5). 이번 마감에서 빠져 차월로 이월(표시·확인용).
       cc 지정 시 품목별, 미지정 시 업체별 집계. 수불장 전표는 만들지 않는다(재고는 실일자로 이미 정확)."""
    y = _dig4(ym) or _cur_ym()
    cn = _conn(); cur = cn.cursor()
    carry = _carry_win().format(ym=y)
    try:
        if str(cc).strip():
            cur.execute(f"""{_SALE_MAGAM.format(ym=y)}
              SELECT A.MAT_CODE mat, MAX(M.item_name) nm, MAX(M.item_spec) spec, MAX(M.UNIT) unit,
                A.MAINT_YMD ymd, SUM(-A.MAINT_QTY) qty, SUM(-A.MAINT_AMT) amt, MAX(A.MAINT_COST) cost
              FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT A JOIN PARTNER_ERP_TEST3.nx.item M ON A.MAT_CODE=M.ITEM_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
              WHERE A.MAINT_TAG='5' AND A.CUST_CODE=? AND A.MAINT_YMD>='{y}00' AND A.MAINT_YMD<='{y}99' AND {carry}
              GROUP BY A.MAT_CODE, A.MAINT_YMD HAVING SUM(-A.MAINT_AMT)<>0 ORDER BY A.MAINT_YMD, A.MAT_CODE""", cc)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            for r in rows:
                r["qty"] = float(r["qty"] or 0); r["amt"] = float(r["amt"] or 0); r["cost"] = float(r["cost"] or 0)
        else:
            cur.execute(f"""{_SALE_MAGAM.format(ym=y)}
              SELECT A.CUST_CODE cc, MAX(C.CUST_DESC) nm, SUM(-A.MAINT_QTY) qty, SUM(-A.MAINT_AMT) amt, COUNT(DISTINCT A.MAT_CODE) items
              FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT A JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST C ON A.CUST_CODE=C.CUST_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
              WHERE A.MAINT_TAG='5' AND A.MAINT_YMD>='{y}00' AND A.MAINT_YMD<='{y}99' AND {carry}
              GROUP BY A.CUST_CODE HAVING SUM(-A.MAINT_AMT)<>0 ORDER BY SUM(-A.MAINT_AMT) DESC""")
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            for r in rows:
                r["qty"] = float(r["qty"] or 0); r["amt"] = float(r["amt"] or 0); r["items"] = int(r["items"] or 0)
    finally:
        cn.close()
    return {"ym": y, "cc": cc, "next_ym": _next_ym(y), "rows": rows}

@router.get("/api/salemagam/opendays")
def salemagam_opendays(ym: str = Query(""), months: int = Query(2)):
    """반품 반영 대상일 = 일마감(월마감) 안 된 일자(YYMMDD). ym부터 months개월."""
    y = _dig4(ym) or _cur_ym()
    return {"ym": y, "days": _open_days(y, months, "MAT")}

@router.post("/api/salemagam/return_save")
def salemagam_return_save(payload: dict = Body(...)):
    """매출반품 → 수불장 전표(MAINT_TAG='RT', +재고복귀). 선택 오픈일자(일마감 안 된 날)에 기록.
       payload: {ym, cust_code, ymd(YYMMDD), lines:[{mat_code, qty, cost, remarks}]}"""
    return _return_save(payload, sign=+1)   # 매출반품 = 재고 되돌아옴(+)

# 매출/매입 공용 반품 저장(부호만 다름) — sign +1=매출반품(재고복귀) / -1=매입반품(재고출고)
def _return_save(payload, *, sign):
    cc = str(payload.get("cust_code", "")).strip()
    ymd = "".join(ch for ch in str(payload.get("ymd", "")) if ch.isdigit())
    lines = payload.get("lines", []) or []
    if len(ymd) != 6:
        raise HTTPException(400, "반영일자(YYMMDD) 필요")
    if not lines:
        raise HTTPException(400, "반품 품목 필요")
    nx = _nx_tx(); nc = nx.cursor()
    try:
        if _closed(nc, ymd, "MAT"):
            return {"ok": False, "errors": [f"{ymd[2:4]}/{ymd[4:6]} 은 마감된 일자 — 마감 안 된 일자를 선택하세요"]}
        saved = 0; errs = []
        for i, ln in enumerate(lines, 1):
            mat = str(ln.get("mat_code", "")).strip()
            qty = abs(float(ln.get("qty") or 0))
            if not mat or qty <= 0:
                errs.append(f"{i}행: 품목·수량 필요"); continue
            _ledger_return(nc, ymd, mat, sign * qty, cost=float(ln.get("cost") or 0),
                           cust_code=(cc or None), remarks=(str(ln.get("remarks") or "").strip() or ("매출반품" if sign > 0 else "매입반품")))
            saved += 1
        if errs:
            nx.rollback(); return {"ok": False, "errors": errs}
        nx.commit()
        return {"ok": True, "saved": saved, "ymd": ymd}
    except Exception as e:
        nx.rollback(); raise HTTPException(500, f"반품 저장 실패: {e}")
    finally:
        nx.close()

def _next_ym(y):
    yy = int(y[:2]); mm = int(y[2:]) + 1
    if mm == 13: mm = 1; yy += 1
    return f"{yy:02d}{mm:02d}"

@router.get("/api/salemagam/lines")
def salemagam_lines(ym: str = Query(""), basis: str = Query("magam"), fr: str = Query(""), to: str = Query(""),
                    q: str = Query(""), cust: str = Query(""), cust_code: str = Query("")):
    """★2026-08-23 레거시 w_pu_sale_010 형태 = 집계를 P/No 단위로 펼친 목록(거래처×자도번×단가).
    basis='magam'(마감기준: 거래처별 마감일 창) | 'input'(입고기준: fr~to 일자범위, 기본 당월1일~오늘).
    일자별 수량 피벗(byday) 포함 → 프론트에서 일자 컬럼으로 전개. 거래처 그룹 소계는 프론트에서 계산."""
    y = _dig4(ym) or _cur_ym()
    if basis == "input":
        f6 = "".join(ch for ch in str(fr or "") if ch.isdigit())[:6]
        t6 = "".join(ch for ch in str(to or "") if ch.isdigit())[:6]
        if not (len(f6) == 6 and len(t6) == 6):
            raise HTTPException(400, "입고기준은 fr/to(YYMMDD) 필요")
        win = f"A.MAINT_YMD>='{f6}' AND A.MAINT_YMD<='{t6}'"
        lo, hi = f6, t6
    else:
        _yy = int(y[:2]); _mm = int(y[2:]); _pm = _mm - 1; _py = _yy
        if _pm == 0: _pm = 12; _py -= 1
        win = _sale_win().format(ym=y)
        lo, hi = f"{_py:02d}{_pm:02d}00", f"{y}99"
    where = [f"A.MAINT_TAG='5'", f"A.MAINT_YMD>='{lo}'", f"A.MAINT_YMD<='{hi}'", win]
    pf = []
    if cust_code.strip():
        where.append("A.CUST_CODE=?"); pf.append(cust_code.strip())
    elif cust.strip():
        where.append("(A.CUST_CODE=? OR C.CUST_DESC LIKE ?)"); pf += [cust.strip(), f"%{cust.strip()}%"]
    if q.strip():
        where.append("(A.MAT_CODE LIKE ? OR M.item_name LIKE ?)"); pf += [f"%{q.strip()}%", f"%{q.strip()}%"]
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute(f"""{_SALE_MAGAM.format(ym=y)}
          SELECT A.CUST_CODE cc, MAX(C.CUST_DESC) cnm, A.MAT_CODE mat, ISNULL(A.ITEM_CODE,'') moda,
            MAX(ISNULL(M.item_name,'')) nm, MAX(ISNULL(M.item_spec,'')) spec, MAX(ISNULL(M.UNIT,'')) unit,
            A.MAINT_COST cost, A.MAINT_YMD ymd, SUM(-A.MAINT_QTY) q, SUM(-A.MAINT_AMT) amt
          FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT A
            JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST C ON A.CUST_CODE=C.CUST_CODE
            JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.item M ON A.MAT_CODE=M.ITEM_CODE
          WHERE {' AND '.join(where)}
          GROUP BY A.CUST_CODE, A.MAT_CODE, ISNULL(A.ITEM_CODE,''), A.MAINT_COST, A.MAINT_YMD""", *pf)
        raw = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    finally:
        cn.close()
    return _magam_lines_shape(raw, y, basis)

def _magam_lines_shape(raw, y, basis):
    """(cc,모도번,자도번,단가) 단위로 묶고 일자별 수량 피벗. 거래처→금액순 정렬, 거래처 안은 모도번·자도번순.
    ★모도번(ITEM_CODE)이 다르면 별개 행 — 레거시 w_pu_sale_010 동일(같은 자도번이라도 상위품번별로 분리)."""
    keyed = {}; days = set()
    for r in raw:
        ymd = str(r["ymd"] or "")
        moda = str(r.get("moda") or "").strip()
        k = (r["cc"], moda, str(r["mat"] or "").strip(), float(r["cost"] or 0))
        days.add(ymd)
        it = keyed.setdefault(k, {"cc": r["cc"], "cnm": r["cnm"], "mat": k[2], "moda": moda,
                                  "nm": r["nm"], "spec": r["spec"], "unit": r["unit"],
                                  "cost": k[3], "qty": 0.0, "amt": 0.0, "byday": {}})
        qv = float(r["q"] or 0); av = float(r["amt"] or 0)
        it["qty"] += qv; it["amt"] += av
        it["byday"][ymd] = it["byday"].get(ymd, 0.0) + qv
    lines = list(keyed.values())
    for it in lines:
        it["qty"] = round(it["qty"], 2); it["amt"] = round(it["amt"], 2)
    # 거래처 정렬 = 금액 큰 순(집계화면과 동일), 거래처 안은 자도번순
    camt = {}
    for it in lines:
        camt[it["cc"]] = camt.get(it["cc"], 0.0) + it["amt"]
    # ★집계화면(HAVING SUM(amt)<>0)과 동일하게 금액 0원 거래처는 제외 — 펼침합=집계합 보장
    lines = [it for it in lines if round(camt.get(it["cc"], 0.0), 2) != 0]
    lines.sort(key=lambda x: (-abs(camt.get(x["cc"], 0)), x["cc"], x["moda"], x["mat"], x["cost"]))
    return {"ym": y, "basis": basis, "days": sorted(days), "rows": lines,
            "cnt": len(lines),
            "totqty": round(sum(i["qty"] for i in lines), 2),
            "totamt": round(sum(i["amt"] for i in lines), 2)}

@router.get("/api/salemagam/reasons")
def salemagam_reasons():
    nx = _nx(); nc = nx.cursor()
    try:
        nc.execute("SELECT reason_code,reason_name,category FROM nx.close_reason WHERE use_flag=1 ORDER BY sort_no")
        return {"rows": [{"code": r[0], "name": r[1], "cat": r[2]} for r in nc.fetchall()]}
    finally:
        nx.close()

@router.get("/api/salemagam/custsearch")
def salemagam_custsearch(q: str = Query("")):
    """거래처 단일선택 검색(코드로 구분 — 동명이인 방지). 삼화코리아 2건도 코드로 구분."""
    cn = _conn(); cur = cn.cursor()
    try:
        like = f"%{q.strip()}%"
        cur.execute("""SELECT TOP 30 CUST_CODE, CUST_DESC, CUST_TYPE FROM PARTNER_ERP_TEST3.nx.CM_M_CUST
                       WHERE CUST_CODE LIKE ? OR CUST_DESC LIKE ? ORDER BY CUST_DESC, CUST_CODE""", like, like)
        return {"rows": [{"cc": r[0], "nm": r[1], "ct": r[2]} for r in cur.fetchall()]}
    finally:
        cn.close()

@router.post("/api/salemagam/save")
def salemagam_save(payload: dict = Body(...)):
    """조정내역(단가변경/총액증감/품목무관) 저장 + 선택 시 마감. 이미 마감이면 거부."""
    y = _dig4(payload.get("ym")); cc = str(payload.get("cust_code", "")).strip()
    if not y or not cc:
        raise HTTPException(400, "ym/cust_code 필요")
    adjs = payload.get("adjustments", []) or []
    do_close = bool(payload.get("close"))
    base_amt = float(payload.get("base_amt") or 0)
    nx = _nx(); nc = nx.cursor()
    try:
        nc.execute("SELECT close_flag FROM nx.sale_close WHERE ym=? AND cust_code=?", y, cc)
        r = nc.fetchone()
        if r and r[0]:
            return {"ok": False, "errors": ["이미 마감된 업체 — 마감취소 후 수정하세요"]}
        # 사유 필수(조정이 있으면)
        errs = []
        for i, a in enumerate(adjs, 1):
            if not (a.get("reason_code") or (a.get("reason_detail") or "").strip()):
                errs.append(f"{i}행: 변경사유 필요")
        if errs:
            return {"ok": False, "errors": errs}
        nc.execute("DELETE FROM nx.sale_adjust WHERE ym=? AND cust_code=?", y, cc)
        tot = 0.0
        for i, a in enumerate(adjs, 1):
            d = float(a.get("delta_amt") or 0); tot += d
            nc.execute("""INSERT INTO nx.sale_adjust(ym,cust_code,adj_seq,adj_type,scope,mat_code,target_ymd,old_cost,new_cost,old_qty,new_qty,delta_amt,reason_code,reason_detail,ins_user)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       y, cc, i, str(a.get("adj_type") or "ITEM_ADJ"), (a.get("scope") or None), (a.get("mat_code") or None),
                       (str(a.get("target_ymd")) if a.get("target_ymd") else None),
                       (a.get("old_cost") if a.get("old_cost") is not None else None),
                       (a.get("new_cost") if a.get("new_cost") is not None else None),
                       (a.get("old_qty") if a.get("old_qty") is not None else None),
                       (a.get("new_qty") if a.get("new_qty") is not None else None),
                       d, (a.get("reason_code") or None), ((a.get("reason_detail") or "").strip() or None), "web")
        final = round(base_amt + tot, 2)
        cf = 1 if do_close else 0
        nc.execute("""MERGE nx.sale_close AS t USING (SELECT ? ym, ? cust_code) s ON t.ym=s.ym AND t.cust_code=s.cust_code
          WHEN MATCHED THEN UPDATE SET close_flag=?, base_amt=?, adj_amt=?, final_amt=?,
             close_user=CASE WHEN ?=1 THEN 'web' ELSE close_user END, close_dt=CASE WHEN ?=1 THEN GETDATE() ELSE close_dt END
          WHEN NOT MATCHED THEN INSERT(ym,cust_code,close_flag,base_amt,adj_amt,final_amt,close_user,close_dt)
             VALUES(?,?,?,?,?,?,CASE WHEN ?=1 THEN 'web' ELSE NULL END, CASE WHEN ?=1 THEN GETDATE() ELSE NULL END);""",
          y, cc, cf, base_amt, tot, final, cf, cf, y, cc, cf, base_amt, tot, final, cf, cf)
        return {"ok": True, "final_amt": final, "adj_amt": tot, "closed": do_close}
    finally:
        nx.close()

@router.post("/api/salemagam/reopen")
def salemagam_reopen(payload: dict = Body(...)):
    """마감 취소(재수정 허용)."""
    y = _dig4(payload.get("ym")); cc = str(payload.get("cust_code", "")).strip()
    nx = _nx(); nc = nx.cursor()
    try:
        nc.execute("UPDATE nx.sale_close SET close_flag=0, close_dt=NULL WHERE ym=? AND cust_code=?", y, cc)
        return {"ok": True, "reopened": nc.rowcount}
    finally:
        nx.close()

@router.post("/api/salemagam/recalc_cost")
def salemagam_recalc_cost(payload: dict = Body(...)):
    """매출기간 매출단가 재계산 — 레거시 w_pu_sale_020 'cost_calc' 이식.
    협력사판매(MAINT_TAG='5'), 매출단가(레거시 COST_TAG IN ('S','E') = 웹 'TAGS','TAGE').
    실행부·단가원천 주석은 purmagam._recalc_cost 참조(매입과 공통)."""
    from routers.purmagam import _recalc_cost, _COST_CLEAN
    return _recalc_cost(payload, cost_sql=_COST_CLEAN.format(types="'TAGS','TAGE'"),
                        maint_tags=("5",), window="w_pu_sale_020(web)")

@router.get("/api/salemagam/weight")
def salemagam_weight(ym: str = Query("")):
    """무게정산(중량조정): 업체별 원소재/용접봉 출고−업체가공입고=차액, ×(시세−사급가).
       기초 불필요·매월 증/차감. 출고=확정(tag5), 입고=마스터(PR_M_ITEM.ITEM_WEIGHT+CS_M_ITEM_BOM 잠정)."""
    y = _dig4(ym) or _cur_ym()
    # 시세·사급가(원소재/용접봉) — nx.mat_price_month
    px = {"원소재": (25000.0, 20000.0), "용접봉": (None, 21100.0)}
    try:
        nx = _nx(); nc = nx.cursor()
        nc.execute("SELECT category, real_price, sagub_price FROM nx.mat_price_month WHERE apply_ym=?", y)
        for cat, rp, sp in nc.fetchall():
            px[cat] = ((float(rp) if rp is not None else None), (float(sp) if sp is not None else px.get(cat, (None, None))[1]))
        nx.close()
    except Exception:
        pass
    rr, sr = px.get("원소재", (25000.0, 20000.0))
    rw, sw = px.get("용접봉", (None, 21100.0))
    try:
        data = weight_calc.compute(y, real_raw=(rr if rr is not None else 25000.0), sagub_raw=(sr if sr is not None else 20000.0),
                                   real_weld=rw, sagub_weld=(sw if sw is not None else 21100.0))
    except Exception as e:
        raise HTTPException(500, f"무게정산 계산 오류: {e}")
    return {"ym": y, "real_raw": (rr if rr is not None else 25000.0), "sagub_raw": (sr if sr is not None else 20000.0),
            "real_weld": rw, "sagub_weld": (sw if sw is not None else 21100.0), "rows": data}

@router.get("/api/salemagam/weight_quote")
def salemagam_weight_quote(ym: str = Query("")):
    """★규격별 LME 정산금액(견적기준): 규격(재질·외경)별 재고(출고−소요)×(현물가−사급가).
       현물가/사급가=nx.price_metal(해당월). 절삭 8개 협력사만. compute_quote_lme 사용."""
    y = _dig4(ym) or _cur_ym()
    try:
        data = weight_calc.compute_quote_lme(y)
    except Exception as e:
        raise HTTPException(500, f"LME 정산 계산 오류: {e}")
    ven = {'2142': '세광산업', '233': '썬텍코리아', '2148': '대원산업', '2096': '미래정밀',
           '2306': '명진산업', '2068': '이젠터', '2266': '케이비', '2048': '중앙정밀', '2250': '수테크'}
    rows = []
    for cc, d in data.items():
        rows.append({"cc": cc, "nm": ven.get(cc, cc), "raw_out": d["raw_out"], "raw_in": d["raw_in"],
                     "raw_diff": d["raw_diff"], "settle_amt": d["settle_amt"],
                     "unmapped_out": d.get("unmapped_out", 0), "soyo_only": d.get("soyo_only", False),
                     "weld_out": d.get("weld_out"), "weld_in": d.get("weld_in"),
                     "weld_diff": d.get("weld_diff"), "weld_amt": d.get("weld_amt"),
                     "specs": d.get("specs", [])})
    rows.sort(key=lambda r: (r["settle_amt"] if r["settle_amt"] is not None else 0))
    total = round(sum((r["settle_amt"] or 0) for r in rows))
    weld_total = round(sum((r["weld_amt"] or 0) for r in rows))
    return {"ym": y, "rows": rows, "total": total, "weld_total": weld_total,
            "weld_spot": 62700, "weld_sagub": 21100}

@router.get("/api/matprice/list")
def matprice_list(ym: str = Query("")):
    """월별 원소재/용접봉 시세·사급가 조회."""
    y = _dig4(ym) or _cur_ym()
    defaults = {"원소재": 20000.0, "용접봉": 21100.0}
    nx = _nx(); nc = nx.cursor()
    try:
        nc.execute("SELECT category, real_price, sagub_price, note FROM nx.mat_price_month WHERE apply_ym=?", y)
        rows = {r[0]: {"category": r[0], "real_price": (float(r[1]) if r[1] is not None else None),
                       "sagub_price": (float(r[2]) if r[2] is not None else defaults.get(r[0])), "note": r[3] or ""} for r in nc.fetchall()}
        for cat, sg in defaults.items():
            if cat not in rows:
                rows[cat] = {"category": cat, "real_price": None, "sagub_price": sg, "note": ""}
        return {"ym": y, "rows": [rows["원소재"], rows["용접봉"]]}
    finally:
        nx.close()

@router.post("/api/matprice/save")
def matprice_save(payload: dict = Body(...)):
    y = _dig4(payload.get("ym"))
    if not y:
        raise HTTPException(400, "ym 필요")
    nx = _nx(); nc = nx.cursor()
    try:
        for it in (payload.get("rows") or []):
            cat = str(it.get("category", "")).strip()
            if cat not in ("원소재", "용접봉"):
                continue
            rp = it.get("real_price"); sp = it.get("sagub_price")
            rp = float(rp) if rp not in (None, "") else None
            sp = float(sp) if sp not in (None, "") else None
            nc.execute("""MERGE nx.mat_price_month AS T USING (SELECT ? ym, ? cat) S ON T.apply_ym=S.ym AND T.category=S.cat
                WHEN MATCHED THEN UPDATE SET real_price=?, sagub_price=?, upd_user='web', upd_dt=GETDATE()
                WHEN NOT MATCHED THEN INSERT(apply_ym,category,real_price,sagub_price,upd_user,upd_dt) VALUES(?,?,?,?,'web',GETDATE());""",
                y, cat, rp, sp, y, cat, rp, sp)
        return {"ok": True}
    finally:
        nx.close()

# ===================== 품질 반성회의록 CRUD (nx.meeting ← 레거시 cm_user_meeting_1) =====================
# 근거: w_cm_user_meeting_200/205. 코드마스터 없음(순수 텍스트). 비용=(인원+1)×시간×358.3.
_MEETING_COLS = ["meeting_type", "meeting_ymd", "subject", "member", "member_count", "duration_min", "pay_amount",
                 "note", "note2", "organizer",
                 "action1_desc", "action1_person", "action1_due", "action2_desc", "action2_person", "action2_due",
                 "action3_desc", "action3_person", "action3_due", "action4_desc", "action4_person", "action4_due",
                 "action5_desc", "action5_person", "action5_due"]
_MEETING_INT = {"member_count", "duration_min", "pay_amount"}

# ⚠️ 2026-08-23: 품질 반성회의록 화면이 레거시 일지(w_pr_input_590/595, routers/qareview.py)로 교체되어
#    아래 /api/meeting/* 3종은 프론트에서 더 이상 호출하지 않는다(미사용). nx.meeting 데이터 보존을 위해 남겨둠.
@router.get("/api/meeting/list")
def meeting_list(q: str = Query(""), from_ymd: str = Query(""), to_ymd: str = Query(""), limit: int = Query(300)):
    """반성회의록 목록(nx.meeting). 제목/작성자/참석자 검색 + 회의일자 범위."""
    nx = _nx(); cur = nx.cursor()
    try:
        w = ["1=1"]; p = []
        if q.strip(): w.append("(subject LIKE ? OR organizer LIKE ? OR member LIKE ?)"); p += [f"%{q.strip()}%"] * 3
        if from_ymd.strip(): w.append("meeting_ymd >= ?"); p.append(from_ymd.strip())
        if to_ymd.strip(): w.append("meeting_ymd <= ?"); p.append(to_ymd.strip())
        cur.execute(f"""SELECT TOP {max(1,min(int(limit),2000))} meeting_id,meeting_type,meeting_ymd,subject,member,
            member_count,duration_min,pay_amount,note,note2,organizer,
            action1_desc,action1_person,action1_due,action2_desc,action2_person,action2_due,
            action3_desc,action3_person,action3_due,action4_desc,action4_person,action4_due,
            action5_desc,action5_person,action5_due
            FROM nx.meeting WHERE {' AND '.join(w)} ORDER BY meeting_ymd DESC, meeting_id DESC""", *p)
        cols = [d[0] for d in cur.description]
        rows = [{c: ("" if v is None else v) for c, v in zip(cols, r)} for r in cur.fetchall()]
        return {"rows": rows, "cnt": len(rows)}
    finally:
        nx.close()

@router.post("/api/meeting/save")
def meeting_save(payload: dict = Body(...)):
    """반성회의록 등록/수정. 제목 필수. 비용 서버 자동계산(방어)."""
    p = payload
    if not str(p.get("subject", "") or "").strip():
        raise HTTPException(400, "회의 제목은 필수입니다.")
    def s(k):
        v = p.get(k); return None if v in (None, "") else str(v).strip()
    def i(k):
        v = p.get(k)
        try: return int(float(v)) if v not in (None, "") else None
        except Exception: return None
    mc, du = i("member_count"), i("duration_min")
    pay = int(round((mc + 1) * du * 358.3)) if (mc is not None and du is not None) else i("pay_amount")
    vals = [pay if k == "pay_amount" else (i(k) if k in _MEETING_INT else s(k)) for k in _MEETING_COLS]
    mid = p.get("meeting_id")
    nx = _nx(); cur = nx.cursor()
    try:
        if mid:
            sets = ",".join(f"{k}=?" for k in _MEETING_COLS)
            cur.execute(f"UPDATE nx.meeting SET {sets},upd_user='web',upd_dt=GETDATE() WHERE meeting_id=?", *vals, int(mid))
            return {"ok": True, "mode": "update", "meeting_id": int(mid), "pay_amount": pay}
        cur.execute(f"INSERT INTO nx.meeting({','.join(_MEETING_COLS)},upd_user,upd_dt) OUTPUT INSERTED.meeting_id "
                    f"VALUES({','.join(['?']*len(_MEETING_COLS))},'web',GETDATE())", *vals)
        newid = cur.fetchone()[0]
        return {"ok": True, "mode": "insert", "meeting_id": int(newid), "pay_amount": pay}
    finally:
        nx.close()

@router.post("/api/meeting/delete")
def meeting_delete(payload: dict = Body(...)):
    ids = [int(x) for x in (payload.get("ids", []) or []) if str(x).strip().lstrip('-').isdigit()]
    if not ids: return {"ok": True, "deleted": 0}
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute(f"DELETE FROM nx.meeting WHERE meeting_id IN ({','.join('?'*len(ids))})", *ids)
        return {"ok": True, "deleted": cur.rowcount}
    finally:
        nx.close()
