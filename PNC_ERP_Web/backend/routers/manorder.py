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
        # ── ★소요엔진 기반 협력사 계획 (2026-08-30 사용자 확정, 정본 PROCUREMENT_ALLOCATION_RULES·matexpect 재사용) ──
        #   crude PR_T_PLAN_ITEM_DTL(부모도번 prefix 매칭) 폐기 → nx.plan_part_mat(소요엔진 전개·날짜별) × nx.plan_mat_source(업체배분).
        #   ★실발주비율(R01경로 × 업체배분)이 plan_mat_source에 **이미 반영** → 재스케일 안 함(이중계상 방지·§10).
        #   계획수량 = 이 협력사(cc)에 배분된 4주 자재소요. 일자별 = plan_ymd 분포. 품목 = 소요 자재 ∪ 기발주 품목.
        soyo_day = {}   # UPPER(mat) -> {ymd: qty}  (이 협력사 배분 소요)
        nxn = _nx(); ncur = nxn.cursor()
        try:
            ncur.execute("""
                SELECT UPPER(LTRIM(RTRIM(ppm.mat_code))) mat, ppm.plan_ymd ymd,
                       SUM(CAST(ppm.part_plan_qty AS float) * ISNULL(r.ratio,1.0)) qty
                FROM nx.plan_part_mat ppm
                LEFT JOIN (
                    SELECT s.work_order, UPPER(LTRIM(RTRIM(s.mat_code))) mat_code, s.vendor_code,
                           CAST(s.qty AS float)/NULLIF(t.tot,0) ratio
                    FROM nx.plan_mat_source s
                    JOIN (SELECT work_order, UPPER(LTRIM(RTRIM(mat_code))) mat_code, SUM(CAST(qty AS float)) tot
                          FROM nx.plan_mat_source GROUP BY work_order, UPPER(LTRIM(RTRIM(mat_code)))) t
                      ON t.work_order=s.work_order AND t.mat_code=UPPER(LTRIM(RTRIM(s.mat_code)))
                ) r ON r.work_order=ppm.work_order AND r.mat_code=UPPER(LTRIM(RTRIM(ppm.mat_code)))
                WHERE ppm.plan_ymd BETWEEN ? AND ? AND r.vendor_code=?
                GROUP BY UPPER(LTRIM(RTRIM(ppm.mat_code))), ppm.plan_ymd""", from6, to6, cc)
            for mat, ymd, qty in ncur.fetchall():
                soyo_day.setdefault((mat or '').strip(), {})[str(ymd).strip()] = float(qty or 0)
        finally:
            nxn.close()
        # 기발주(PU 미입고) — 이 매입처
        po_pu = {}
        cur.execute("""SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), SUM(PUR_QTY-ISNULL(IN_QTY,0)-ISNULL(CANCEL_QTY,0))
             FROM PARTNER_ERP_TEST3.nx.PU_T_PURCHASE_DTL WHERE CUST_CODE=? AND ISNULL(IN_FINISH_FLAG,'N')<>'Y'
             GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE))) HAVING SUM(PUR_QTY-ISNULL(IN_QTY,0)-ISNULL(CANCEL_QTY,0))>0""", cc)
        for ic, q in cur.fetchall():
            po_pu[(ic or '').strip()] = float(q or 0)
        # 품목 유니버스 = 소요 자재 ∪ 기발주 품목
        universe = sorted(set(soyo_day.keys()) | set(po_pu.keys()))
        stock = {}; info = {}
        for i in range(0, len(universe), 900):
            ch = universe[i:i+900]; ph = ",".join("?" * len(ch))
            cur.execute(f"SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), SUM(STOCK_QTY) FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH WHERE STOCK_YYMM=? AND UPPER(LTRIM(RTRIM(MAT_CODE))) IN ({ph}) GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE)))", smax, *ch)
            for mc, sq in cur.fetchall():
                stock[(mc or '').strip()] = float(sq or 0)
            cur.execute(f"SELECT UPPER(LTRIM(RTRIM(item_code))), ISNULL(item_name,''), ISNULL(item_spec,''), ISNULL(unit,'EA') FROM PARTNER_ERP_TEST3.nx.item WHERE UPPER(LTRIM(RTRIM(item_code))) IN ({ph})", *ch)
            for ic, nm2, sp, un in cur.fetchall():
                info[(ic or '').strip()] = {"nm": nm2, "spec": sp, "unit": un}
        dset = set()
        for d in soyo_day.values():
            dset |= set(d.keys())
        dates = sorted(dset)
        # ★주별 경계(오늘 기준 7일 버킷) — 계획수량을 1~4주로 분할
        cur.execute("SELECT FORMAT(DATEADD(DAY,6,GETDATE()),'yyMMdd'), FORMAT(DATEADD(DAY,13,GETDATE()),'yyMMdd'), FORMAT(DATEADD(DAY,20,GETDATE()),'yyMMdd')")
        w1b, w2b, w3b = cur.fetchone()
        def _wk(ymd):
            if ymd <= w1b: return 0
            if ymd <= w2b: return 1
            if ymd <= w3b: return 2
            return 3
        rows = []
        for mat in universe:
            days = soyo_day.get(mat, {}); meta = info.get(mat, {})
            wk = [0.0, 0.0, 0.0, 0.0]
            for ymd, q in days.items():
                wk[_wk(ymd)] += q
            rows.append({"ic": mat, "nm": meta.get("nm", ""), "spec": meta.get("spec", ""), "unit": meta.get("unit", "EA"),
                         "plan_qty": round(sum(days.values()), 3), "week_qty": [round(x, 1) for x in wk],
                         "stock_qty": stock.get(mat, 0.0), "po_qty": po_pu.get(mat, 0.0), "days": days, "alloc_note": ""})
        rows.sort(key=lambda r: (-r["plan_qty"], r["ic"]))
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
                rc2.execute(f"""SELECT UPPER(LTRIM(RTRIM(im.mat_code))) mat, SUM(mul.qty*mb.USE_QTY*im.per_unit)
                    FROM nx.lg_muldong mul
                    JOIN nx.PR_M_MODEL_BOM mb ON LTRIM(RTRIM(mb.MODEL_NO))=LTRIM(RTRIM(mul.model))
                    JOIN nx.item_mat_soyo im ON LTRIM(RTRIM(im.item_code))=LTRIM(RTRIM(mb.C_ITEM_CODE))
                    WHERE mul.plan_yymm IN (?,?) AND UPPER(LTRIM(RTRIM(im.mat_code))) IN ({iph})
                    GROUP BY UPPER(LTRIM(RTRIM(im.mat_code)))""", mt1, mt2, *chunk)
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
            mo_open = {k.upper(): v for k, v in _mo_open_by_cust(rc3, cc).items()}
        except Exception:
            mo_open = {}
        finally:
            rn3.close()
        for r in rows:
            r["po_qty"] = round(float(r.get("po_qty") or 0) + mo_open.get(str(r["ic"]).strip().upper(), 0.0), 3)
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
    u = require_user(request)
    cc = scope_cust(u, cust)
    if cc == "__NONE__":
        raise HTTPException(403, "협력사 계정에 거래처코드가 없습니다.")
    if not cc:
        # ★내부직원(협력사 아님)이 cust 미지정 = 검색 유도(에러 아님). 협력사는 위에서 자기코드 강제됨.
        return {"cc": "", "need_search": True, "rows": []}
    r = manorder_items(cc=cc, ym="")
    out = [{"ic": x["ic"], "nm": x["nm"], "unit": x.get("unit", "EA"),
            "stock_qty": x["stock_qty"], "po_qty": x["po_qty"],           # 기발주=PNC 발주(PU+manual_order)
            "plan_qty": x["plan_qty"], "week_qty": x.get("week_qty", [0, 0, 0, 0]),  # 계획 4주 총·주별
            "muldong_soyo": x["muldong_soyo"]}                            # 물동=5~8주(제외분)
           for x in r["rows"]]
    out.sort(key=lambda z: (str(z["ic"]).split('-')[0], str(z["ic"])))
    return {"cc": cc, "cust_name": r["cust_name"], "ym": r["ym"], "stock_ym": r["stock_ym"],
            "muldong_ym": r["muldong_ym"], "rows": out}
