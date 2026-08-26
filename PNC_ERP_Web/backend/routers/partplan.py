# -*- coding: utf-8 -*-
"""partplan 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ================= 협력사 계획 편성 엔진 (생산계획업로드 → 자도번 라우팅) =================
# 레거시 SP_PR_CREATE_PLAN_협력사계획_생성 정렬(98% 재현): PR_M_ITEM_BOM(except≠1) + 가공처(work_code‖in_cust)
#  + charindex 중복제거(조상에 같은 가공처면 컷) + 조달프로파일 오버레이(유효기간·배분).
def _compose_maps():
    cn = _nx(); cur = cn.cursor()   # ★nx전환: nx 충실복제 읽기
    try:
        cur.execute("SELECT ITEM_CODE, LTRIM(RTRIM(ISNULL(WORK_CODE,''))), ISNULL(in_cust,'') FROM nx.item")
        WCEN = {}
        for ic, wc, inc in cur.fetchall():
            WCEN[ic] = wc if wc > '' else str(inc).strip()
        cur.execute("""SELECT ITEM_CODE, MAT_CODE, USE_QTY FROM nx.v_pr_bom
            WHERE ISNULL(EXCEPT_FLAG,'0')<>'1' AND FROM_APPLY_YMD<='991231' AND TO_APPLY_YMD>='260101'""")
        CH = {}
        for p, c, q in cur.fetchall():
            CH.setdefault(p, []).append((c, float(q or 0)))
        return WCEN, CH
    finally:
        cn.close()

def _compose_assy(assy, WCEN, CH, memo):
    """assy → {(part, work_center): cum_qty}. 레거시 앵커(ASSY 자신=level0 파트) + charindex 중복제거."""
    if assy in memo:
        return memo[assy]
    out = {}
    root_wc = WCEN.get(assy, '')
    out[(assy, root_wc)] = 1.0   # ★앵커멤버: ASSY 자신을 파트로(레거시 bom_level 0)
    def rec(item, cq, path):
        for c, q in CH.get(item, []):
            wc = WCEN.get(c, ''); nq = cq * q
            if wc not in path:
                k = (c, wc); out[k] = out.get(k, 0.0) + nq
            rec(c, nq, path | {wc})
    rec(assy, 1.0, {root_wc})
    memo[assy] = out
    return out

@router.post("/api/plan/compose")
def plan_compose(payload: dict = Body(...)):
    """nx.plan_dtl 전량 편성 → nx.plan_part. 조달프로파일(현행,유효기간,배분) 오버레이."""
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("IF OBJECT_ID('nx.plan_part') IS NULL CREATE TABLE nx.plan_part(PLAN_YMD varchar(6),WORK_ORDER varchar(20),ASSY_ITEM_CODE varchar(20),PART_CODE varchar(20),WORK_CENTER varchar(20),SUPPLY_GUBUN varchar(10),PROFILE_ID int,USE_QTY decimal(18,6),PLAN_QTY decimal(18,3),COMPOSE_DT datetime DEFAULT getdate())")
        # ★STEP M 신규모델생성 (레거시 ue_make_model 재현): 주문(nx.recv_dtl) ⋈ 계획(nx.plan_dtl)을 제번(WORK_ORDER)으로 조인
        #   → model→AJR(ASSY) 매핑을 nx.model_bom에 동적생성. use_qty=CEILING(발주/LOT), 3중제외(모델BOM·중복·EXCEPT).
        cur.execute("DELETE FROM nx.model_bom WHERE REMARKS='신규모델자동'")
        cur.execute("""INSERT INTO nx.model_bom(MODEL_NO,C_ITEM_CODE,USE_QTY,APPLY_FROM,APPLY_TO,REMARKS,INS_DT)
            SELECT p.model_no, r.item_code,
               MAX(CASE WHEN r.order_qty<p.lot THEN 1 ELSE CEILING(CAST(r.order_qty AS float)/NULLIF(p.lot,0)) END),
               MIN(p.plan_ymd),'999999','신규모델자동',getdate()
            FROM (SELECT RTRIM(MODEL_NO) model_no,WORK_ORDER,MAX(TOTAL_QTY) lot,MIN(PLAN_YMD) plan_ymd
                  FROM nx.plan_dtl WHERE ISNULL(MODEL_NO,'')>'' GROUP BY RTRIM(MODEL_NO),WORK_ORDER) p
            JOIN (SELECT RTRIM(ITEM_CODE) item_code,WORK_ORDER,SUM(ORDER_QTY) order_qty
                  FROM nx.recv_dtl WHERE ISNULL(ITEM_CODE,'')>'' GROUP BY RTRIM(ITEM_CODE),WORK_ORDER) r
              ON p.WORK_ORDER=r.WORK_ORDER
            WHERE NOT EXISTS(SELECT 1 FROM nx.PR_M_MODEL_BOM b WHERE b.MODEL_NO=p.model_no AND b.C_ITEM_CODE=r.item_code)
              AND NOT EXISTS(SELECT 1 FROM nx.model_bom m WHERE m.MODEL_NO=p.model_no AND m.C_ITEM_CODE=r.item_code)
              AND NOT EXISTS(SELECT 1 FROM nx.PR_M_MODEL_BOM_EXCEPT e WHERE e.MODEL_NO=p.model_no AND e.C_ITEM_CODE=r.item_code)
            GROUP BY p.model_no,r.item_code""")
        # ASSY 매핑: ①모델BOM(MODEL→[ASSY×use_qty], 유효일자 버전) ②주문 fallback. + 제외조건.
        mbom = {}
        cur.execute("SELECT MODEL_NO, C_ITEM_CODE, USE_QTY, MAKE_YMD, TO_APPLY_YMD FROM nx.PR_M_MODEL_BOM")
        for m, ci, uq, my, ty in cur.fetchall():
            mbom.setdefault(str(m).strip(), []).append((str(ci).strip(), float(uq or 1), str(my or '').strip(), str(ty or '').strip()))
        try:  # 우리 신규등록 모델BOM(nx) union
            cur.execute("SELECT MODEL_NO, C_ITEM_CODE, USE_QTY, APPLY_FROM, APPLY_TO FROM nx.model_bom")
            for m, ci, uq, my, ty in cur.fetchall():
                mbom.setdefault(str(m).strip(), []).append((str(ci).strip(), float(uq or 1), str(my or '').strip(), str(ty or '').strip()))
        except Exception:
            pass
        mbexcept = set()  # 모델BOM제외조건
        cur.execute("SELECT MODEL_NO, C_ITEM_CODE FROM nx.PR_M_MODEL_BOM_EXCEPT")
        for m, ci in cur.fetchall(): mbexcept.add((str(m).strip(), str(ci).strip()))
        recvmap = {}
        cur.execute("SELECT DISTINCT WORK_ORDER, ITEM_CODE FROM nx.SA_T_RECV_DTL WHERE WORK_ORDER>''")
        for wo, ic in cur.fetchall(): recvmap.setdefault(str(wo).strip(), set()).add(str(ic).strip())
        # 조달프로파일(현행 활성): item→[(sg,vc,alloc,af,at)]
        cur.execute("""SELECT item_code, supply_gubun, ISNULL(vendor_code,''), ISNULL(alloc_ratio,100),
            CONVERT(varchar(10),apply_from,23), CONVERT(varchar(10),apply_to,23), profile_id
            FROM nx.sourcing_profile WHERE is_active=1 AND is_internal=0""")
        prof = {}
        for ic, sg, vc, al, af, at, pid in cur.fetchall():
            prof.setdefault(ic, []).append((sg, str(vc).strip(), float(al or 100), af, at, pid))
        WCEN, CH = _compose_maps()
        cur.execute("SELECT WORK_ORDER, PLAN_YMD, PLAN_QTY, MODEL_NO FROM nx.plan_dtl WHERE PLAN_QTY>0")
        plan = cur.fetchall()
        memo = {}; rows = []; mapped = unmapped = 0
        for wo, ymd, q, model in plan:
            wos = str(wo).strip(); mk = str(model).strip()
            cand = mbom.get(mk)                            # [(assy, use_qty, make_ymd, to_apply_ymd)]
            assys = None
            if cand:                                       # 유효일자(plan날짜)만. ★MODEL_BOM_EXCEPT는 STEP M(신규모델생성)전용 —
                assys = [(a, mq) for (a, mq, my, ty) in cand   #   전개에 적용 금지(레거시 STEP5 품목별생성은 EXCEPT 미적용).
                         if (not my or my <= ymd) and (not ty or ty >= ymd)]  #   대원산업 외주완성 서포터(EXCEPT=1) 드롭 방지.
            if not assys:
                rc = recvmap.get(wos)
                assys = [(a, 1.0) for a in rc] if rc else None
            if not assys: unmapped += 1; continue
            mapped += 1
            d = f"20{ymd[:2]}-{ymd[2:4]}-{ymd[4:6]}"
            for assy, mq in assys:
                base = float(q) * mq
                for (part, wc), soyo in _compose_assy(assy, WCEN, CH, memo).items():
                    ps = [p for p in prof.get(part, []) if (not p[3] or p[3] <= d) and (not p[4] or p[4] >= d)]
                    if ps:
                        for sg, vc, al, af, at, pid in ps:
                            who = vc if (sg in ('유상사급', '매입') and vc) else wc
                            rows.append((ymd, wos, assy, part, who, sg, pid, soyo, base * soyo * al / 100.0))
                    else:
                        rows.append((ymd, wos, assy, part, wc, None, None, soyo, base * soyo))
        cur.execute("DELETE FROM nx.plan_part")
        cur.fast_executemany = True
        cur.executemany("INSERT INTO nx.plan_part(PLAN_YMD,WORK_ORDER,ASSY_ITEM_CODE,PART_CODE,WORK_CENTER,SUPPLY_GUBUN,PROFILE_ID,USE_QTY,PLAN_QTY) VALUES(?,?,?,?,?,?,?,?,?)", rows)
        return {"ok": True, "mapped": mapped, "unmapped": unmapped, "part_lines": len(rows)}
    finally:
        nx.close()
