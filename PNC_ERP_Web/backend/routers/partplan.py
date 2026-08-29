# -*- coding: utf-8 -*-
"""partplan 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ================= 협력사 계획 편성 엔진 (생산계획업로드 → 자도번 라우팅) =================
# ★DEPRECATED(2026-08-23, PLAN_PROGRAM_MASTER §P1): 소요 전개기 #3 retire. 이 아래 _compose_maps/_compose_assy는
#   /api/plan/compose(nx.plan_part) 전용이었으나 該 엔드포인트가 no-op화되어 현재 미사용. 정본=soyo.py STEP5→6→7(compose_mat).
#   (구 로직 참고용으로 코드 보존. 삭제는 후속 정리에서.)
# [구주석] 레거시 SP_PR_CREATE_PLAN_협력사계획_생성 정렬(98% 재현): PR_M_ITEM_BOM(except≠1) + 가공처(work_code‖in_cust)
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
    """★DEPRECATED(2026-08-23, PLAN_PROGRAM_MASTER §P1): 소요 전개기 #3 retire.
    이 엔드포인트는 nx.plan_part(구 단일패스 98%)를 재생성했으나 — 실측 결과 **nx.plan_part를 읽는 코드 0건**(死테이블).
    정본 소요 = `/api/plan/compose_mat`(soyo.py STEP5→6→7 → nx.plan_part_mat, 수량 100% 검증). compose_mat이 STEP M(신규모델생성)까지 상위집합이라 이 함수의 기능은 전부 포함됨.
    → 순수 중복 전개기 제거. no-op으로 유지(호출해도 무해·엔드포인트 수 유지). nx.plan_part 테이블은 후속 정리 대상(현재 freeze).
    구 로직 원본은 git 이력(이 커밋 직전) 참조. 하위 헬퍼 _compose_maps/_compose_assy도 미사용화됨."""
    return {"ok": True, "deprecated": True, "note": "소요 전개기 #3 retire. 정본=/api/plan/compose_mat(nx.plan_part_mat). nx.plan_part는 死테이블(읽는코드 0)."}
