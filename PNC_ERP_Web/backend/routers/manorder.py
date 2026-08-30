# -*- coding: utf-8 -*-
"""manorder 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form, Request
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes, _route01_ratio)

router = APIRouter()

# ================= 수동발주 (구매/자재, w_pr_input_410 시나리오) =================
@router.get("/api/manorder/vendors")
def manorder_vendors(q: str = Query("")):
    """매입처 검색(그 업체가 납품하는 품목 보유=IN_CUST_CODE). 단일선택 코드 구분."""
    cn = _conn(); cur = cn.cursor()
    try:
        like = f"%{q.strip()}%"
        cur.execute("""SELECT TOP 30 C.CUST_CODE, MAX(C.CUST_DESC) nm, MAX(C.CUST_TYPE) ct, COUNT(M.item_code) items
          FROM PARTNER_ERP_TEST3.nx.CM_M_CUST C JOIN PARTNER_ERP_TEST3.nx.item M ON M.in_cust=C.CUST_CODE AND ISNULL(M.item_status,'1') IN ('1','2')
          WHERE (C.CUST_CODE LIKE ? OR C.CUST_DESC LIKE ?)
          GROUP BY C.CUST_CODE HAVING COUNT(M.item_code)>0
          ORDER BY COUNT(M.item_code) DESC""", like, like)
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
        or_main = f" OR M.item_code IN ({eph})" if extra else ""
        or_itm = f" OR item_code IN ({eph})" if extra else ""
        # 계획수량: 부품 접미사 제거한 부모 도번 기준(부모별 1회 집계 후 조인=고속). 기발주=PU_T_PURCHASE_DTL 미입고잔량.
        cur.execute(f"""
          WITH PLANP AS (
            SELECT LEFT(C_ITEM_CODE, CASE WHEN CHARINDEX('-',C_ITEM_CODE)>0 THEN CHARINDEX('-',C_ITEM_CODE)-1 ELSE LEN(C_ITEM_CODE) END) parent, SUM(PLAN_QTY) pq
            FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_ITEM_DTL WHERE PLAN_YMD BETWEEN ? AND ?
            GROUP BY LEFT(C_ITEM_CODE, CASE WHEN CHARINDEX('-',C_ITEM_CODE)>0 THEN CHARINDEX('-',C_ITEM_CODE)-1 ELSE LEN(C_ITEM_CODE) END))
          SELECT M.item_code ic, M.item_name nm, ISNULL(M.item_spec,'') spec, ISNULL(M.unit,'EA') unit,
            ISNULL(PP.pq,0) plan_qty, ISNULL(S.sq,0) stock_qty, ISNULL(PO.remain,0) po_qty
          FROM PARTNER_ERP_TEST3.nx.item M
          LEFT JOIN PLANP PP ON PP.parent = LEFT(M.item_code, CASE WHEN CHARINDEX('-',M.item_code)>0 THEN CHARINDEX('-',M.item_code)-1 ELSE LEN(M.item_code) END)
          LEFT JOIN (SELECT MAT_CODE, SUM(STOCK_QTY) sq FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH WHERE STOCK_YYMM=? GROUP BY MAT_CODE) S ON S.MAT_CODE=M.item_code
          LEFT JOIN (SELECT ITEM_CODE, SUM(PUR_QTY-ISNULL(IN_QTY,0)-ISNULL(CANCEL_QTY,0)) remain
             FROM PARTNER_ERP_TEST3.nx.PU_T_PURCHASE_DTL WHERE CUST_CODE=? AND ISNULL(IN_FINISH_FLAG,'N')<>'Y'
             GROUP BY ITEM_CODE HAVING SUM(PUR_QTY-ISNULL(IN_QTY,0)-ISNULL(CANCEL_QTY,0))>0) PO ON PO.ITEM_CODE=M.item_code
          WHERE (M.in_cust=?{or_main}) AND ISNULL(M.item_status,'1') IN ('1','2')
          ORDER BY ISNULL(PP.pq,0) DESC, M.item_code""", from6, to6, smax, cc, cc, *extra)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["plan_qty"] = float(r["plan_qty"] or 0); r["stock_qty"] = float(r["stock_qty"] or 0)
            r["po_qty"] = float(r["po_qty"] or 0)  # 기발주 = PU_T_PURCHASE_DTL 미입고 발주잔량
        # ★우측 협력사 일자별 계획 = 좌측과 동일 소스(PR_T_PLAN_ITEM_DTL). 부모 도번별 PLAN_YMD 분포 → 일자별 합 = 좌측 계획수량.
        cur.execute(f"""
          WITH ITM AS (SELECT DISTINCT LEFT(ITEM_CODE, CASE WHEN CHARINDEX('-',ITEM_CODE)>0 THEN CHARINDEX('-',ITEM_CODE)-1 ELSE LEN(ITEM_CODE) END) parent
                       FROM PARTNER_ERP_TEST3.nx.item WHERE (in_cust=?{or_itm}) AND ISNULL(item_status,'1') IN ('1','2'))
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
        # ── ★5~8주 LG물동 참고 소요(2026-08-30, 컷오버-안전 nx 소스) ──
        #   물동수량 × PR_M_MODEL_BOM(모델→ASSY) × item_mat_soyo(ASSY→자재 per_unit·소요엔진 캐시, §10).
        #   4주=생산계획(위 plan_qty), 5~8주=물동(다음~다다음달). ★참고용 컬럼 — 추가발주 계산 미반영·자동발주 금지·담당 판단.
        #   ★레거시 TT_T_MODEL_PLAN 직독 안 함 = nx.lg_muldong(우리 업로드) 사용 → 컷오버 후 무수정 작동(§9-1).
        cur.execute("SELECT FORMAT(DATEADD(MONTH,1,GETDATE()),'yyMM'), FORMAT(DATEADD(MONTH,2,GETDATE()),'yyMM')")
        mt1, mt2 = cur.fetchone()   # 5~8주 = 다음달·다다음달 물동
        mul_soyo = {}
        vic = sorted({str(r["ic"]).strip() for r in rows})
        rn2 = _nx(); rc2 = rn2.cursor()
        try:
            for i in range(0, len(vic), 800):
                chunk = vic[i:i+800]; iph = ",".join("?" * len(chunk))
                rc2.execute(f"""SELECT im.mat_code, SUM(mul.qty*mb.USE_QTY*im.per_unit)
                    FROM nx.lg_muldong mul
                    JOIN nx.PR_M_MODEL_BOM mb ON LTRIM(RTRIM(mb.MODEL_NO))=LTRIM(RTRIM(mul.model))
                    JOIN nx.item_mat_soyo im ON LTRIM(RTRIM(im.item_code))=LTRIM(RTRIM(mb.C_ITEM_CODE))
                    WHERE mul.plan_yymm IN (?,?) AND im.mat_code IN ({iph})
                    GROUP BY im.mat_code""", mt1, mt2, *chunk)
                for mc, sq in rc2.fetchall():
                    mul_soyo[(mc or '').strip()] = float(sq or 0)
        except Exception:
            mul_soyo = {}
        finally:
            rn2.close()
        for r in rows:
            r["muldong_soyo"] = round(mul_soyo.get(str(r["ic"]).strip(), 0.0), 1)
        # ★기발주 = PU 미입고잔량(레거시) + nx.manual_order 미입고(신규 발주저장) 합산 → 컷오버 후 nx만(§9-1)
        rn3 = _nx(); rc3 = rn3.cursor()
        try:
            _ensure_mo(rc3)
            mo_open = _mo_open_by_cust(rc3, cc)
        except Exception:
            mo_open = {}
        finally:
            rn3.close()
        for r in rows:
            r["po_qty"] = round(float(r.get("po_qty") or 0) + mo_open.get(str(r["ic"]).strip(), 0.0), 3)
        cn2 = _conn(); c2 = cn2.cursor()
        try:
            c2.execute("SELECT CUST_DESC FROM PARTNER_ERP_TEST3.nx.CM_M_CUST WHERE CUST_CODE=?", cc)
            rr = c2.fetchone(); nm = rr[0] if rr else cc
        finally:
            cn2.close()
        # ★거래처 리드타임(nx.cust.lead_time_days) — 반영일수 기본값(장리드 정비 2026-08-30). 0/없으면 프론트 현행 14.
        lead_days = 0
        cn3 = _nx(); c3 = cn3.cursor()
        try:
            c3.execute("SELECT ISNULL(lead_time_days,0) FROM nx.cust WHERE cust_code=?", cc)
            _lr = c3.fetchone(); lead_days = int(_lr[0] or 0) if _lr else 0
        except Exception:
            lead_days = 0
        finally:
            cn3.close()
        ymlbl = f"{from6[0:2]}/{from6[2:4]}/{from6[4:6]}~{to6[0:2]}/{to6[2:4]}/{to6[4:6]}"
        return {"cc": cc, "cust_name": nm, "ym": ymlbl, "from_ymd": from6, "to_ymd": to6, "stock_ym": smax,
                "rows": rows, "dates": dates, "lead_days": lead_days,
                "muldong_ym": f"{mt1[0:2]}/{mt1[2:4]}~{mt2[0:2]}/{mt2[2:4]}"}
    finally:
        cn.close()


# ================= 발주 저장 (nx.manual_order) — 신규 쓰기(장리드 선발주·미착 소스, 2026-08-30) =================
_MO_DDL = """IF OBJECT_ID('nx.manual_order','U') IS NULL
CREATE TABLE nx.manual_order(
  order_id INT IDENTITY(1,1) PRIMARY KEY,
  cust_code NVARCHAR(20) NOT NULL, item_code NVARCHAR(60) NOT NULL,
  order_qty FLOAT NOT NULL, order_ymd VARCHAR(6), expect_ymd VARCHAR(6),
  in_qty FLOAT DEFAULT 0, cancel_flag BIT DEFAULT 0, status NVARCHAR(10) DEFAULT N'발주',
  memo NVARCHAR(200), ins_user NVARCHAR(30), ins_dt DATETIME DEFAULT getdate())"""

def _ensure_mo(cur):
    for s in _MO_DDL.split(";"):
        if s.strip():
            cur.execute(s)

def _mo_open_by_cust(cur, cc):
    """이 매입처의 nx.manual_order 미입고 발주잔량 = Σ(order_qty−in_qty), cancel_flag=0. {item_code: 잔량}."""
    out = {}
    try:
        cur.execute("""SELECT item_code, SUM(order_qty-ISNULL(in_qty,0)) FROM nx.manual_order
                       WHERE cust_code=? AND ISNULL(cancel_flag,0)=0
                       GROUP BY item_code HAVING SUM(order_qty-ISNULL(in_qty,0))>0""", cc)
        for it, q in cur.fetchall():
            out[(it or '').strip()] = float(q or 0)
    except Exception:
        pass
    return out

@router.post("/api/manorder/save")
def manorder_save(payload: dict = Body(...)):
    """발주 저장 → nx.manual_order. body {cust_code, order_ymd?(YYMMDD·기본 오늘), lead_days?(예정입고=발주일+리드), items:[{item_code,qty}], user?}.
       qty>0만 저장(품목별 append=발주 이력). 저장 후 기발주 증가(_mo_open_by_cust). ★수량 발주만·단가 미기록(§1-2)."""
    cc = str(payload.get("cust_code", "")).strip()
    items = payload.get("items", []) or []
    if not cc or not items:
        raise HTTPException(400, "cust_code·items 필요")
    lead = int(payload.get("lead_days") or 0)
    usr = (str(payload.get("user", "")).strip() or "web")[:30]
    nx = _nx_tx(); cur = nx.cursor()
    try:
        _ensure_mo(cur)
        cur.execute("SELECT FORMAT(GETDATE(),'yyMMdd'), FORMAT(DATEADD(DAY,?,GETDATE()),'yyMMdd')", lead)
        today6, exp6 = cur.fetchone()
        oymd = (str(payload.get("order_ymd", "")).strip() or today6)[:6]
        saved = 0
        for it in items:
            ic = str(it.get("item_code", "")).strip()
            q = float(it.get("qty", 0) or 0)
            if not ic or q <= 0:
                continue
            cur.execute("""INSERT INTO nx.manual_order(cust_code,item_code,order_qty,order_ymd,expect_ymd,ins_user)
                           VALUES(?,?,?,?,?,?)""", cc, ic, q, oymd, exp6, usr)
            saved += 1
        nx.commit()
        return {"ok": True, "saved": saved, "cust_code": cc, "order_ymd": oymd, "expect_ymd": exp6}
    except Exception:
        nx.rollback(); raise
    finally:
        nx.close()


# ================= 협력사 발주현황 (협력사 포털·조회전용, 2026-08-30) =================
@router.get("/api/coopporder/items")
def coopporder_items(request: Request, cust: str = Query("")):
    """협력사가 로그인해 보는 발주현황. ★소속강제(협력사 계정=자기 업체만). 수동발주 items 재사용(같은 소스).
       컬럼: 품목·품명·현재재고·기발주(PNC가 나에게 발주)·계획수량(4주 생산계획)·LG물동(5~8주·제외분). 조회전용."""
    from routers.auth import require_user, scope_cust
    cc = scope_cust(require_user(request), cust)
    if not cc:
        raise HTTPException(400, "매입처 필요(협력사 로그인 또는 cust 지정).")
    r = manorder_items(cc=cc, ym="")
    out = [{"ic": x["ic"], "nm": x["nm"], "unit": x.get("unit", "EA"),
            "stock_qty": x["stock_qty"], "po_qty": x["po_qty"],           # 기발주=PNC 발주(PU+manual_order)
            "plan_qty": x["plan_qty"], "muldong_soyo": x["muldong_soyo"]}  # 계획=4주, 물동=5~8주(제외분)
           for x in r["rows"]]
    out.sort(key=lambda z: (str(z["ic"]).split('-')[0], str(z["ic"])))
    return {"cc": cc, "cust_name": r["cust_name"], "ym": r["ym"], "stock_ym": r["stock_ym"],
            "muldong_ym": r["muldong_ym"], "rows": out}
