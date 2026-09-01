# -*- coding: utf-8 -*-
"""purmagam 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes, _carry_win)

router = APIRouter()

# ================= 매입마감처리 (구매/자재, w_pu_sale_010) — 거래처별, 확정입고(매입) =================
def _pur_src(win):
    """확정입고(매입) 원천: 9/S/C/G/H(검사통과) + 수입(_C DIVISION=P). 금액 양수. win=마감기준 조건(mg 참조)."""
    return f"""
    SELECT A.CUST_CODE cc, A.MAT_CODE mat, A.MAINT_COST cost, A.MAINT_YMD ymd, A.MAINT_QTY qty, A.MAINT_AMT amt, A.MAINT_VAT vat
     FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT A JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
     WHERE {win} AND A.MAINT_TAG IN ('9','S','C','G','H')
       AND ((ISNULL(A.INSP_FLAG,'N') IN ('','N')) OR (ISNULL(A.INSP_FLAG,'N') IN ('S','F') AND A.INSP_PROC_YMD >= ''))
    UNION ALL
    SELECT A.CUST_CODE, A.MAT_CODE, ROUND(A.MAINT_COST*A.EXCHANGE_RATE,0,1), A.MAINT_YMD, A.MAINT_QTY, ROUND(A.MAINT_AMT*A.EXCHANGE_RATE,0,1), ISNULL(A.TAXPAYERS,0)
     FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT_C A JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
     WHERE {win} AND A.DIVISION='P'"""

@router.get("/api/purmagam/list")
def purmagam_list(ym: str = Query("")):
    """매입마감 거래처별 집계(확정입고, 마감기준) + nx 마감상태·조정합."""
    y = _dig4(ym) or _cur_ym()
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute(f"""{_SALE_MAGAM.format(ym=y)}
          SELECT S.cc cc, MAX(C.CUST_DESC) nm, MAX(C.CUST_TYPE) ct,
            MAX(LTRIM(RTRIM(ISNULL(NULLIF(C.CHARGE_USER_ID,''),ISNULL(C.CHARGE_NAME,''))))) chg,
            SUM(S.qty) qty, SUM(S.amt) amt, SUM(S.vat) vat, COUNT(DISTINCT S.mat) items
          FROM ({_pur_src(_sale_win().format(ym=y))}) S JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST C ON S.cc=C.CUST_CODE
          GROUP BY S.cc HAVING SUM(S.amt)<>0 ORDER BY SUM(S.amt) DESC""")
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        cn.close()
    nx = _nx(); nc = nx.cursor()
    try:
        nc.execute("SELECT cust_code,close_flag,bill_flag FROM nx.pur_close WHERE ym=?", y)
        st = {r[0]: (int(r[1] or 0), int(r[2] or 0)) for r in nc.fetchall()}
        nc.execute("SELECT cust_code, SUM(delta_amt) FROM nx.pur_adjust WHERE ym=? GROUP BY cust_code", y)
        adj = {r[0]: float(r[1] or 0) for r in nc.fetchall()}
    finally:
        nx.close()
    for r in rows:
        cc = r["cc"]; s = st.get(cc, (0, 0))
        r["qty"] = float(r["qty"] or 0); r["amt"] = float(r["amt"] or 0); r["vat"] = float(r["vat"] or 0); r["items"] = int(r["items"] or 0)
        r["close_flag"] = s[0]; r["bill_flag"] = s[1]
        r["adj_amt"] = adj.get(cc, 0.0); r["final_amt"] = round(r["amt"] + adj.get(cc, 0.0), 2)
    return {"ym": y, "rows": rows}

@router.get("/api/purmagam/detail")
def purmagam_detail(ym: str = Query(""), cc: str = Query(...)):
    """매입 거래처 마감상세: 품목×일자 + 저장된 조정."""
    y = _dig4(ym) or _cur_ym()
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute(f"""{_SALE_MAGAM.format(ym=y)}
          SELECT S.mat mat, MAX(M.item_name) nm, MAX(M.item_spec) spec, MAX(M.unit) unit, S.cost cost,
            CAST(RIGHT(S.ymd,2) AS INT) d, SUM(S.qty) q, SUM(S.amt) amt
          FROM ({_pur_src(_sale_win().format(ym=y))}) S JOIN PARTNER_ERP_TEST3.nx.item M ON S.mat=M.item_code
          WHERE S.cc=? GROUP BY S.mat, S.cost, CAST(RIGHT(S.ymd,2) AS INT)""", cc)
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
                      FROM nx.pur_adjust WHERE ym=? AND cust_code=? ORDER BY adj_seq""", y, cc)
        adjs = [{"adj_type": r[1], "scope": r[2], "mat_code": r[3], "target_ymd": r[4],
                 "old_cost": (float(r[5]) if r[5] is not None else None), "new_cost": (float(r[6]) if r[6] is not None else None),
                 "old_qty": (float(r[7]) if r[7] is not None else None), "new_qty": (float(r[8]) if r[8] is not None else None),
                 "delta_amt": float(r[9] or 0), "reason_code": r[10], "reason_detail": r[11]} for r in nc.fetchall()]
        nc.execute("SELECT close_flag FROM nx.pur_close WHERE ym=? AND cust_code=?", y, cc)
        cr = nc.fetchone(); closed = int(cr[0]) if cr else 0
    finally:
        nx.close()
    return {"ym": y, "cc": cc, "days": sorted(days), "items": items_list, "adjustments": adjs, "close_flag": closed}

# ===== 이월·오픈일자·반품 (2026-09-01) — 이월=정산귀속·표시 / 반품=수불장 전표(매입반품=-재고출고) =====
@router.get("/api/purmagam/carryover")
def purmagam_carryover(ym: str = Query(""), cc: str = Query("")):
    """이월 대상 = 거래처 마감일 이후~당월 말일 확정입고분. 이번 마감에서 빠져 차월로 이월(표시·확인용).
       cc 지정 시 품목·일자별, 미지정 시 거래처별 집계. 수불장 전표는 만들지 않는다."""
    y = _dig4(ym) or _cur_ym()
    carry = _carry_win().format(ym=y)
    cn = _conn(); cur = cn.cursor()
    try:
        if str(cc).strip():
            cur.execute(f"""{_SALE_MAGAM.format(ym=y)}
              SELECT S.mat mat, MAX(M.item_name) nm, MAX(M.item_spec) spec, MAX(M.unit) unit,
                S.ymd ymd, SUM(S.qty) qty, SUM(S.amt) amt, MAX(S.cost) cost
              FROM ({_pur_src(carry)}) S JOIN PARTNER_ERP_TEST3.nx.item M ON S.mat=M.item_code
              WHERE S.cc=? GROUP BY S.mat, S.ymd HAVING SUM(S.amt)<>0 ORDER BY S.ymd, S.mat""", cc)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            for r in rows:
                r["qty"] = float(r["qty"] or 0); r["amt"] = float(r["amt"] or 0); r["cost"] = float(r["cost"] or 0)
        else:
            cur.execute(f"""{_SALE_MAGAM.format(ym=y)}
              SELECT S.cc cc, MAX(C.CUST_DESC) nm, SUM(S.qty) qty, SUM(S.amt) amt, COUNT(DISTINCT S.mat) items
              FROM ({_pur_src(carry)}) S JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST C ON S.cc=C.CUST_CODE
              GROUP BY S.cc HAVING SUM(S.amt)<>0 ORDER BY SUM(S.amt) DESC""")
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            for r in rows:
                r["qty"] = float(r["qty"] or 0); r["amt"] = float(r["amt"] or 0); r["items"] = int(r["items"] or 0)
    finally:
        cn.close()
    yy = int(y[:2]); mm = int(y[2:]) + 1
    if mm == 13: mm = 1; yy += 1
    return {"ym": y, "cc": cc, "next_ym": f"{yy:02d}{mm:02d}", "rows": rows}

def _pur_src_moda(win):
    """_pur_src 와 동일 원천 + 모도번(ITEM_CODE) 컬럼 추가 — P/No 펼침 전용.
    수입(_C)은 상위품번 개념이 없어 ''. 집계 금액·수량은 _pur_src 와 동일해야 한다."""
    return f"""
    SELECT A.CUST_CODE cc, A.MAT_CODE mat, ISNULL(A.ITEM_CODE,'') moda, A.MAINT_COST cost, A.MAINT_YMD ymd, A.MAINT_QTY qty, A.MAINT_AMT amt, A.MAINT_VAT vat
     FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT A JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
     WHERE {win} AND A.MAINT_TAG IN ('9','S','C','G','H')
       AND ((ISNULL(A.INSP_FLAG,'N') IN ('','N')) OR (ISNULL(A.INSP_FLAG,'N') IN ('S','F') AND A.INSP_PROC_YMD >= ''))
    UNION ALL
    SELECT A.CUST_CODE, A.MAT_CODE, '', ROUND(A.MAINT_COST*A.EXCHANGE_RATE,0,1), A.MAINT_YMD, A.MAINT_QTY, ROUND(A.MAINT_AMT*A.EXCHANGE_RATE,0,1), ISNULL(A.TAXPAYERS,0)
     FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT_C A JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
     WHERE {win} AND A.DIVISION='P'"""

@router.get("/api/purmagam/lines")
def purmagam_lines(ym: str = Query(""), basis: str = Query("magam"), fr: str = Query(""), to: str = Query(""),
                   q: str = Query(""), cust: str = Query(""), cust_code: str = Query("")):
    """★2026-08-23 레거시 w_pu_sale_010 형태 = 집계를 P/No 단위로 펼친 목록(거래처×자도번×단가).
    basis='magam'(마감기준: 거래처별 마감일 창) | 'input'(입고기준: fr~to, 기본 당월1일~오늘)."""
    from routers.salemagam import _magam_lines_shape
    y = _dig4(ym) or _cur_ym()
    if basis == "input":
        f6 = "".join(ch for ch in str(fr or "") if ch.isdigit())[:6]
        t6 = "".join(ch for ch in str(to or "") if ch.isdigit())[:6]
        if not (len(f6) == 6 and len(t6) == 6):
            raise HTTPException(400, "입고기준은 fr/to(YYMMDD) 필요")
        win = f"A.MAINT_YMD>='{f6}' AND A.MAINT_YMD<='{t6}'"
    else:
        win = _sale_win().format(ym=y)
    where = ["1=1"]; pf = []
    if cust_code.strip():
        where.append("S.cc=?"); pf.append(cust_code.strip())
    elif cust.strip():
        where.append("(S.cc=? OR C.CUST_DESC LIKE ?)"); pf += [cust.strip(), f"%{cust.strip()}%"]
    if q.strip():
        where.append("(S.mat LIKE ? OR M.item_name LIKE ?)"); pf += [f"%{q.strip()}%", f"%{q.strip()}%"]
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute(f"""{_SALE_MAGAM.format(ym=y)}
          SELECT S.cc cc, MAX(C.CUST_DESC) cnm, S.mat mat, S.moda moda,
            MAX(ISNULL(M.item_name,'')) nm, MAX(ISNULL(M.item_spec,'')) spec, MAX(ISNULL(M.unit,'')) unit,
            S.cost cost, S.ymd ymd, SUM(S.qty) q, SUM(S.amt) amt
          FROM ({_pur_src_moda(win)}) S
            JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST C ON S.cc=C.CUST_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.item M ON S.mat=M.item_code
          WHERE {' AND '.join(where)}
          GROUP BY S.cc, S.mat, S.moda, S.cost, S.ymd""", *pf)
        raw = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    finally:
        cn.close()
    return _magam_lines_shape(raw, y, basis)

@router.post("/api/purmagam/save")
def purmagam_save(payload: dict = Body(...)):
    """매입 조정 replace-all + 선택시 마감. 가드: 사유필수·이미마감 거부."""
    y = _dig4(payload.get("ym")); cc = str(payload.get("cust_code", "")).strip()
    adjs = payload.get("adjustments", []) or []; do_close = bool(payload.get("close"))
    base = float(payload.get("base_amt", 0) or 0)
    if not y or not cc:
        raise HTTPException(400, "ym·cust_code 필요")
    nx = _nx(); nc = nx.cursor()
    try:
        nc.execute("SELECT close_flag FROM nx.pur_close WHERE ym=? AND cust_code=?", y, cc)
        cr = nc.fetchone()
        if cr and int(cr[0]) == 1:
            raise HTTPException(409, "이미 마감된 거래처입니다. 마감취소 후 수정하세요.")
        for a in adjs:
            if float(a.get("delta_amt", 0) or 0) != 0 and not (a.get("reason_code") or (a.get("reason_detail") or "").strip()):
                raise HTTPException(400, "사유(코드 또는 세부내역)가 필요한 조정이 있습니다.")
        nc.execute("DELETE FROM nx.pur_adjust WHERE ym=? AND cust_code=?", y, cc)
        for a in adjs:
            nc.execute("""INSERT INTO nx.pur_adjust(ym,cust_code,adj_type,scope,mat_code,target_ymd,old_cost,new_cost,old_qty,new_qty,delta_amt,reason_code,reason_detail,ins_user)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", y, cc, a.get("adj_type"), a.get("scope"), a.get("mat_code"),
                       a.get("target_ymd"), a.get("old_cost"), a.get("new_cost"), a.get("old_qty"), a.get("new_qty"),
                       float(a.get("delta_amt", 0) or 0), a.get("reason_code"), a.get("reason_detail"), "web")
        adj_sum = sum(float(a.get("delta_amt", 0) or 0) for a in adjs)
        nc.execute("""MERGE nx.pur_close AS T USING (SELECT ? ym, ? cc) AS S ON T.ym=S.ym AND T.cust_code=S.cc
                      WHEN MATCHED THEN UPDATE SET base_amt=?, adj_amt=?, final_amt=?, close_flag=?, close_user=?, close_dt=?
                      WHEN NOT MATCHED THEN INSERT(ym,cust_code,base_amt,adj_amt,final_amt,close_flag,close_user,close_dt)
                        VALUES(?,?,?,?,?,?,?,?);""",
                   y, cc, base, adj_sum, base+adj_sum, (1 if do_close else 0), ("web" if do_close else None), (None),
                   y, cc, base, adj_sum, base+adj_sum, (1 if do_close else 0), ("web" if do_close else None), None)
        if do_close:
            nc.execute("UPDATE nx.pur_close SET close_flag=1, close_user='web', close_dt=GETDATE() WHERE ym=? AND cust_code=?", y, cc)
        return {"ok": True, "closed": do_close, "adj_sum": adj_sum}
    finally:
        nx.close()

# ===== 단가 재계산 공통 (매입 w_pu_sale_010 / 매출 w_pu_sale_020 'cost_calc') =====
# 레거시 원문(PB): 체크한 행마다 (cust_code, mat_code, from~to) 로
#   UPDATE PU_T_STOCK_MAINT SET MAINT_COST = 단가마스터 최신단가
#                            , MAINT_AMT  = MAINT_QTY * 단가
#                            , MAINT_VAT  = floor(MAINT_QTY * 단가 * 0.1)
#    WHERE MAINT_TAG IN (...) AND 마스터단가 > 0     ← 0원이면 건드리지 않음
# 단가 = '적용일자 <= 원장일자' 중 가장 최근 1건.
#
# ★단가 원천 = 웹 정본 nx.price_item 단일 (CLAUDE.md §1-9 클린 단일화).
#   레거시는 PR_M_ITEM_COST(COST_TAG) 를 읽지만 웹은 price_item(price_type) 을 읽는다.
#     COST_TAG '1'→'매입' · 'S'→'TAGS' · 'E'→'TAGE'
#   2026-08-28 클린본이 레거시 등록분을 못 받아 매출단가 767건이 비어 있었고(그래서
#   매출은 미러가 최신, 매입은 클린이 최신이라는 엇갈림이 있었다) → 누락 1,910행을
#   price_item 에 보충해 양쪽을 일치시켰다(8월 매출 1,588행 불일치 0 확인).
#   nx.item 에 없는 고아품목 47종·단가 NULL 7건은 제외(재계산은 단가>0 만 대상이라 무영향).
# ★쓰기는 nx 만. 라이브 PARTNER_ERP 무변경.

# ★통화 가드 = 원화 단가만 채택.
#   레거시(w_pu_sale_020)는 WHERE 절 가드에만 CURRENCY='KRW' 를 두고 SET 절 서브쿼리엔
#   빠뜨려서, 외화 단가가 더 최신이면 가드는 통과시키고 SET 은 외화값을 넣는 구멍이 있다.
#   웹은 양쪽(단가 조회 = 대상 판정)에 동일 적용해 그 어긋남을 없앤다.
#   실측(2026년 매출 14,605행 · 매입 69,947행): 두 방식 결과 차이 0행 = 현 데이터엔 영향 없고
#   앞으로 외화 단가가 섞여 들어와도 원화만 쓰도록 하는 안전장치.
_COST_CLEAN = """ISNULL((SELECT TOP 1 p.price FROM nx.price_item p
                          WHERE p.item_code=A.MAT_CODE AND p.vendor_code=A.CUST_CODE
                            AND p.price_type IN ({types})
                            AND ISNULL(NULLIF(LTRIM(RTRIM(p.currency)),''),'KRW')='KRW'
                            AND p.apply_ymd<=A.MAINT_YMD
                          ORDER BY p.apply_ymd DESC), 0)"""

def _recalc_cost(payload, *, cost_sql, maint_tags, window):
    """단가 재계산 실행부. cost_sql=단가 서브쿼리, maint_tags=대상 MAINT_TAG."""
    fr = _d6(payload.get("fr")); to = _d6(payload.get("to"))
    if not (len(fr) == 6 and len(to) == 6):
        raise HTTPException(400, "조회기간(fr/to)이 필요합니다.")
    if fr > to:
        fr, to = to, fr
    items = payload.get("items") or []          # [{cc, mat}, ...] 체크한 행
    if not items:
        raise HTTPException(400, "재계산할 행을 먼저 선택하세요.")
    pairs = []
    for it in items:
        cc = str((it or {}).get("cc", "")).strip()
        mat = str((it or {}).get("mat", "")).strip()
        if cc and mat and (cc, mat) not in pairs:
            pairs.append((cc, mat))
    if not pairs:
        raise HTTPException(400, "거래처/자도번이 비어 있습니다.")
    tags = ",".join("'%s'" % t for t in maint_tags)
    nx = _nx_tx(); nc = nx.cursor()
    scanned = updated = 0; changed = []
    try:
        for cc, mat in pairs:
            base = f"""FROM nx.PU_T_STOCK_MAINT A
                       WHERE A.MAINT_YMD BETWEEN ? AND ? AND A.CUST_CODE=? AND A.MAT_CODE=?
                         AND A.MAINT_TAG IN ({tags}) AND {cost_sql} > 0"""
            p = (fr, to, cc, mat)
            # ① 변경 대상·전후값 채집(감사로그용) — 단가가 실제로 달라지는 행만
            nc.execute(f"""SELECT A.MAINT_YMD, A.MAINT_QTY, A.MAINT_COST, {cost_sql} {base}
                             AND A.MAINT_COST <> {cost_sql}""", *p)
            for ymd, qty, oldc, newc in nc.fetchall():
                if len(changed) < 200:
                    changed.append({"cc": cc, "mat": mat, "ymd": str(ymd or ""),
                                    "qty": float(qty or 0),
                                    "old": float(oldc or 0), "new": float(newc or 0)})
            nc.execute(f"SELECT COUNT(*) {base}", *p)
            scanned += int(nc.fetchone()[0] or 0)
            # ② 재계산 — 레거시와 동일하게 COST/AMT/VAT 3필드 동시 갱신
            nc.execute(f"""UPDATE A SET
                             A.MAINT_COST = {cost_sql},
                             A.MAINT_AMT  = A.MAINT_QTY * {cost_sql},
                             A.MAINT_VAT  = FLOOR(A.MAINT_QTY * {cost_sql} * 0.1),
                             A.UPDATE_DATETIME = GETDATE(),
                             A.UPDATE_WINDOW = ?
                           {base}""", window, *p)
            updated += max(0, nc.rowcount)
        nx.commit()
    except Exception:
        nx.rollback(); raise
    finally:
        nx.close()
    return {"ok": True, "fr": fr, "to": to, "pairs": len(pairs),
            "scanned": scanned, "updated": updated, "changed": changed}

@router.post("/api/purmagam/recalc_cost")
def purmagam_recalc_cost(payload: dict = Body(...)):
    """입고기간 매입단가 재계산 — 확정입고(9=개별, S=세트), 매입단가(클린본 '매입')."""
    return _recalc_cost(payload, cost_sql=_COST_CLEAN.format(types="'매입'"),
                        maint_tags=("9", "S"), window="w_pu_sale_010(web)")

@router.post("/api/purmagam/reopen")
def purmagam_reopen(payload: dict = Body(...)):
    y = _dig4(payload.get("ym")); cc = str(payload.get("cust_code", "")).strip()
    nx = _nx(); nc = nx.cursor()
    try:
        nc.execute("UPDATE nx.pur_close SET close_flag=0, close_dt=NULL WHERE ym=? AND cust_code=?", y, cc)
        return {"ok": True, "reopened": nc.rowcount}
    finally:
        nx.close()
