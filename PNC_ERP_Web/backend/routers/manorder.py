# -*- coding: utf-8 -*-
"""manorder 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes, _route01_ratio)

router = APIRouter()

# ================= 수동발주 (구매/자재, w_pr_input_410 시나리오) =================
@router.get("/api/manorder/vendors")
def manorder_vendors(q: str = Query("")):
    """매입처 검색(그 업체가 납품하는 품목 보유=IN_CUST_CODE). 단일선택 코드 구분."""
    cn = _conn(); cur = cn.cursor()
    try:
        like = f"%{q.strip()}%"
        cur.execute("""SELECT TOP 30 C.CUST_CODE, MAX(C.CUST_DESC) nm, MAX(C.CUST_TYPE) ct, COUNT(M.ITEM_CODE) items
          FROM PARTNER_ERP_TEST3.nx.CM_M_CUST C JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM M ON M.IN_CUST_CODE=C.CUST_CODE AND ISNULL(M.ITEM_STATUS,'1') IN ('1','2')
          WHERE (C.CUST_CODE LIKE ? OR C.CUST_DESC LIKE ?)
          GROUP BY C.CUST_CODE HAVING COUNT(M.ITEM_CODE)>0
          ORDER BY COUNT(M.ITEM_CODE) DESC""", like, like)
        return {"rows": [{"cc": r[0], "nm": r[1], "ct": r[2], "items": r[3]} for r in cur.fetchall()]}
    finally:
        cn.close()

@router.get("/api/manorder/items")
def manorder_items(cc: str = Query(...), ym: str = Query("")):
    """선택 업체 품목별 계획수량·현재고. ★계획 윈도우 = 오늘~+1개월(from6~to6). 좌측 계획수량·우측 일자별 동일 윈도우 → 계=계획수량. ym(YYMM) 지정 시 해당 월 전체."""
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("SELECT FORMAT(GETDATE(),'yyMMdd'), FORMAT(DATEADD(MONTH,1,GETDATE()),'yyMMdd')")
        from6, to6 = cur.fetchone()
        y = _dig4(ym)
        if y:                       # 특정 월 지정 시 그 달 전체
            from6, to6 = y + "01", y + "99"
        cur.execute("SELECT MAX(STOCK_YYMM) FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH")
        smax = cur.fetchone()[0]
        # ── 조달 프로파일 배분(후보내 업체 배분, nx.sourcing_profile) + 발주업체 지정(nx.order_vendor) 적용 ──
        #   ★이 매입처(cc)의 발주 몫 = 소요 × 배분율. 배분 미설정/단일=100%(현행 그대로 → 회귀0).
        #   배분 설정된 품목은 이 매입처 몫만 계상(다른 매입처 몫은 그 매입처 선택 시 계상).
        #   ★route_alloc(경로 R01/R02 배분)은 조립품(assy)키 → 부품(ic)엔 직접 없으므로 plan_part_mat에서 '부품→assy R01 경로계수'
        #     (부품이 속한 assy들의 R01% 수요가중)를 산출해 곱함. 이 매입처(R01 업체) 몫 = 소요 × 업체비율 × R01경로계수.
        #     자동발주(plan_mat_source 경로대안행)·협력사계획현황과 R01 업체 수량 정합(규칙 §8·§9).
        wdate = f"20{from6[0:2]}-{from6[2:4]}-{from6[4:6]}"     # 배분 유효일자 판정(계획 윈도우 시작일)
        prof = {}   # item -> [(vendor, ratio)] 활성·비내부·업체지정·유효
        ovr = {}    # item -> [(vendor, ratio)]  (order_vendor 발주업체 지정 ★다중업체 배분)
        nxn = _nx(); ncur = nxn.cursor()
        try:
            ncur.execute("""SELECT LTRIM(RTRIM(item_code)), LTRIM(RTRIM(ISNULL(vendor_code,''))), ISNULL(alloc_ratio,100),
                  CONVERT(varchar(10),apply_from,23), CONVERT(varchar(10),apply_to,23)
                FROM nx.sourcing_profile WHERE is_active=1 AND is_internal=0 AND ISNULL(vendor_code,'')<>''""")
            for ic, vc, al, af, at in ncur.fetchall():
                if af and af > wdate: continue
                if at and at < wdate: continue
                prof.setdefault(str(ic).strip(), []).append((str(vc).strip(), float(al or 0)))
            try:
                ncur.execute("IF OBJECT_ID('nx.order_vendor','U') IS NULL SELECT 1 WHERE 1=0")
                _has = (ncur.execute("SELECT COL_LENGTH('nx.order_vendor','alloc_ratio')").fetchone()[0] is not None)
                _rc = "ISNULL(alloc_ratio,100)" if _has else "100"
                ncur.execute(f"SELECT LTRIM(RTRIM(item_code)), LTRIM(RTRIM(ISNULL(vendor_code,''))), {_rc} FROM nx.order_vendor WHERE ISNULL(vendor_code,'')<>''")
                for ic, vc, al in ncur.fetchall():
                    ovr.setdefault(str(ic).strip(), []).append((str(vc).strip(), float(al if al is not None else 100)))
            except Exception:
                pass
        finally:
            nxn.close()
        def _share(ic):
            """이 매입처(cc)의 배분율(0~100). 발주업체지정(다중배분) > 프로파일 > 현행100(미설정)."""
            ic = str(ic).strip()
            ov = ovr.get(ic)
            if ov:
                if len(ov) == 1:
                    return 100.0 if ov[0][0] == cc else 0.0        # 단일=100/0(현행 그대로 → 회귀0)
                return sum((r or 0) for (v, r) in ov if v == cc)    # cc 몫(다중 배분%)
            ps = prof.get(ic)
            if ps:
                return sum(r for (v, r) in ps if v == cc)   # cc 몫(cc 미포함이면 0 = 이 매입처 발주 아님)
            return 100.0
        # cc가 프로파일/발주업체지정 대상인 품목(마스터 IN_CUST≠cc여도 노출) → 다중 매입처 커버
        extra = sorted({ic for ic, ps in prof.items() if any(v == cc for (v, r) in ps)} |
                       {ic for ic, ov in ovr.items() if any(v == cc for (v, r) in ov)})
        eph = ",".join("?" * len(extra)) if extra else ""
        or_main = f" OR M.ITEM_CODE IN ({eph})" if extra else ""
        or_itm = f" OR ITEM_CODE IN ({eph})" if extra else ""
        # 계획수량: 부품 접미사 제거한 부모 도번 기준(부모별 1회 집계 후 조인=고속). 기발주=PU_T_PURCHASE_DTL 미입고잔량.
        cur.execute(f"""
          WITH PLANP AS (
            SELECT LEFT(C_ITEM_CODE, CASE WHEN CHARINDEX('-',C_ITEM_CODE)>0 THEN CHARINDEX('-',C_ITEM_CODE)-1 ELSE LEN(C_ITEM_CODE) END) parent, SUM(PLAN_QTY) pq
            FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_ITEM_DTL WHERE PLAN_YMD BETWEEN ? AND ?
            GROUP BY LEFT(C_ITEM_CODE, CASE WHEN CHARINDEX('-',C_ITEM_CODE)>0 THEN CHARINDEX('-',C_ITEM_CODE)-1 ELSE LEN(C_ITEM_CODE) END))
          SELECT M.ITEM_CODE ic, M.ITEM_DESC nm, ISNULL(M.ITEM_SPEC,'') spec, ISNULL(M.UNIT,'EA') unit,
            ISNULL(PP.pq,0) plan_qty, ISNULL(S.sq,0) stock_qty, ISNULL(PO.remain,0) po_qty
          FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM M
          LEFT JOIN PLANP PP ON PP.parent = LEFT(M.ITEM_CODE, CASE WHEN CHARINDEX('-',M.ITEM_CODE)>0 THEN CHARINDEX('-',M.ITEM_CODE)-1 ELSE LEN(M.ITEM_CODE) END)
          LEFT JOIN (SELECT MAT_CODE, SUM(STOCK_QTY) sq FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH WHERE STOCK_YYMM=? GROUP BY MAT_CODE) S ON S.MAT_CODE=M.ITEM_CODE
          LEFT JOIN (SELECT ITEM_CODE, SUM(PUR_QTY-ISNULL(IN_QTY,0)-ISNULL(CANCEL_QTY,0)) remain
             FROM PARTNER_ERP_TEST3.nx.PU_T_PURCHASE_DTL WHERE CUST_CODE=? AND ISNULL(IN_FINISH_FLAG,'N')<>'Y'
             GROUP BY ITEM_CODE HAVING SUM(PUR_QTY-ISNULL(IN_QTY,0)-ISNULL(CANCEL_QTY,0))>0) PO ON PO.ITEM_CODE=M.ITEM_CODE
          WHERE (M.IN_CUST_CODE=?{or_main}) AND ISNULL(M.ITEM_STATUS,'1') IN ('1','2')
          ORDER BY ISNULL(PP.pq,0) DESC, M.ITEM_CODE""", from6, to6, smax, cc, cc, *extra)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["plan_qty"] = float(r["plan_qty"] or 0); r["stock_qty"] = float(r["stock_qty"] or 0)
            r["po_qty"] = float(r["po_qty"] or 0)  # 기발주 = PU_T_PURCHASE_DTL 미입고 발주잔량
        # ★우측 협력사 일자별 계획 = 좌측과 동일 소스(PR_T_PLAN_ITEM_DTL). 부모 도번별 PLAN_YMD 분포 → 일자별 합 = 좌측 계획수량.
        cur.execute(f"""
          WITH ITM AS (SELECT DISTINCT LEFT(ITEM_CODE, CASE WHEN CHARINDEX('-',ITEM_CODE)>0 THEN CHARINDEX('-',ITEM_CODE)-1 ELSE LEN(ITEM_CODE) END) parent
                       FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM WHERE (IN_CUST_CODE=?{or_itm}) AND ISNULL(ITEM_STATUS,'1') IN ('1','2'))
          SELECT LEFT(D.C_ITEM_CODE, CASE WHEN CHARINDEX('-',D.C_ITEM_CODE)>0 THEN CHARINDEX('-',D.C_ITEM_CODE)-1 ELSE LEN(D.C_ITEM_CODE) END) parent,
                 D.PLAN_YMD ymd, SUM(D.PLAN_QTY) pq
          FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_ITEM_DTL D
          JOIN ITM ON ITM.parent = LEFT(D.C_ITEM_CODE, CASE WHEN CHARINDEX('-',D.C_ITEM_CODE)>0 THEN CHARINDEX('-',D.C_ITEM_CODE)-1 ELSE LEN(D.C_ITEM_CODE) END)
          WHERE D.PLAN_YMD BETWEEN ? AND ?
          GROUP BY LEFT(D.C_ITEM_CODE, CASE WHEN CHARINDEX('-',D.C_ITEM_CODE)>0 THEN CHARINDEX('-',D.C_ITEM_CODE)-1 ELSE LEN(D.C_ITEM_CODE) END), D.PLAN_YMD""", cc, *extra, from6, to6)
        daily = {}; dset = set()
        for pr, ymd, pq in cur.fetchall():
            ymd = str(ymd).strip(); dset.add(ymd)
            daily.setdefault(str(pr).strip(), {})[ymd] = float(pq or 0)
        dates = sorted(dset)
        def _par(ic):
            ic = str(ic or ""); i = ic.find("-"); return ic[:i] if i > 0 else ic
        # ── 이 매입처(cc) 배분율 적용: 계획수량·일자별을 이 매입처 몫으로 스케일(배분율<100=badge, 0=제외) ──
        #   ★실발주비율 = R01 경로비율 × 업체비율. 재고/기발주는 미스케일(po_qty는 CUST_CODE=cc 스코프, stock_qty는 물리재고).
        rn = _nx(); rc = rn.cursor()
        try: route01 = _route01_ratio(rc, [str(r["ic"]).strip() for r in rows])   # ★R01 경로 계수(현재 100)
        finally: rn.close()
        out = []
        for r in rows:
            r["days"] = daily.get(_par(r["ic"]), {})
            ic = str(r["ic"]).strip()
            ratio = _share(ic) * (route01.get(ic, 100.0) / 100.0)   # 실발주비율 = 업체비율 × route01
            if ratio <= 0:
                continue                        # 이 매입처 발주 아님(배분/발주업체지정/경로에서 제외)
            r["alloc_ratio"] = round(ratio, 4)
            r["alloc_note"] = ((f"발주업체지정 {ratio:g}%" if len(ovr.get(ic, [])) > 1 else "발주업체지정") if ic in ovr else
                               (f"배분 {ratio:g}%" if (ratio != 100.0 or len(prof.get(ic, [])) > 1) else ""))
            if ratio != 100.0:
                f = ratio / 100.0
                r["plan_qty"] = round(r["plan_qty"] * f, 3)
                r["days"] = {d: round(q * f, 3) for d, q in (r["days"] or {}).items()}
            out.append(r)
        rows = out
        cn2 = _conn(); c2 = cn2.cursor()
        try:
            c2.execute("SELECT CUST_DESC FROM PARTNER_ERP_TEST3.nx.CM_M_CUST WHERE CUST_CODE=?", cc)
            rr = c2.fetchone(); nm = rr[0] if rr else cc
        finally:
            cn2.close()
        ymlbl = f"{from6[0:2]}/{from6[2:4]}/{from6[4:6]}~{to6[0:2]}/{to6[2:4]}/{to6[4:6]}"
        return {"cc": cc, "cust_name": nm, "ym": ymlbl, "from_ymd": from6, "to_ymd": to6, "stock_ym": smax, "rows": rows, "dates": dates}
    finally:
        cn.close()
