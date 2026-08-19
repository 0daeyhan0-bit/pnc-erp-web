# -*- coding: utf-8 -*-
"""backflush 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes, _lock_msg, _stock_short_msg, _mat_avail)

router = APIRouter()

# ================= ★Phase2: 생산실적 백플러시 엔진 (실사용BOM×생산량 소비, 회수율 제외) =================
def _is_inner_prod(cro, item):
    """사내생산(INNER_PROD=1) 판정: MAKE_TYPE='1' 또는 가공공정(PR_M_ITEM_PROC_GAGONG) 보유. 라이브 RO."""
    c = cro.cursor()
    try:
        c.execute("SELECT ISNULL(MAKE_TYPE,'') FROM nx.PR_M_ITEM WHERE ITEM_CODE=?", item)
        r = c.fetchone()
        if r and str(r[0]).strip() == '1': return True
        c.execute("SELECT COUNT(*) FROM nx.PR_M_ITEM_PROC_GAGONG WHERE ITEM_CODE=?", item)
        return (c.fetchone()[0] or 0) > 0
    except Exception:
        return False

def _backflush_bom(nxc, root, cro=None):
    """실사용BOM 전개(nx.bom): 제작서브(children보유·is_lowest≠Y) 전개, 최말단 자재/구매품 소비.
       용접봉(role='용접봉')=공정종속 → ★별도수집(완성공정 1회 함께 소비, base RAC 코드별 종류별. 정본 qty=nx.bom 재빌드된 CS_M_ITEM_BOM.USE_QTY=ITEM_USE_QTY×1.5).
       ★사내한정 가드: 용접봉 −W는 사내 용접(부모노드 root=INNER_PROD 또는 MAKE_TYPE='1' 제작)만. 외주 용접봉은 사급출고(tag5)로 이미 −재고 → 이중차감 방지(결정 I). cro=라이브RO(사내판정), None=전량(하위호환).
       반환 (comps[(child,cum_qty)], weld{base_rac:cum_qty}). 회수율 미개입."""
    c = nxc.cursor()
    c.execute("SELECT parent_code, child_code, CAST(qty AS float), ISNULL(role,''), ISNULL(is_lowest,'') FROM nx.bom")
    kids = {}
    for p, ch, q, role, low in c.fetchall():
        kids.setdefault(p, []).append((ch, q or 0.0, role, low))
    _mkc = {}
    def _sanae(node):   # 사내 용접 판정: root(INNER_PROD 게이트) 또는 부모 MAKE_TYPE='1'(제작)
        if node == root: return True
        if cro is None: return True
        n = str(node).strip()
        if n not in _mkc:
            cc = cro.cursor(); cc.execute("SELECT ISNULL(MAKE_TYPE,'') FROM nx.PR_M_ITEM WHERE ITEM_CODE=?", n)
            r = cc.fetchone(); _mkc[n] = bool(r and str(r[0]).strip() == '1')
        return _mkc[n]
    out = {}; weld = {}
    def walk(node, mult, depth):
        if depth > 15: return
        for ch, q, role, low in kids.get(node, []):
            cq = mult * q
            if '용접봉' in (role or ''):                    # ★용접봉=공정종속
                if str(ch).upper().startswith('RAC') and _sanae(node):   # RAC + 사내용접만 −W(외주=사급출고 이미 −재고)
                    weld[str(ch).split('-')[0]] = weld.get(str(ch).split('-')[0], 0.0) + cq
                continue                                    # 그 외 role=용접봉(3H·용접SUB)·외주용접봉 = 스킵
            if ch in kids and str(low) != 'Y':             # 제작 서브 → 전개
                walk(ch, cq, depth + 1)
            else:                                          # 소비 leaf(자재/구매품)
                out[ch] = out.get(ch, 0.0) + cq
    walk(root, 1.0, 0)
    return list(out.items()), weld

def _weld_proc_code(nxc, base_rac):
    """용접봉 투입공정(GAGONG_PROC_CODE) — nx.bom_line 대표값(Q1000/Q2000 용접봉창고), 없으면 'Q1000' 기본."""
    c = nxc.cursor()
    c.execute("SELECT TOP 1 ISNULL(gagong_proc,'') FROM nx.bom_line WHERE child_item LIKE ? AND ISNULL(gagong_proc,'')<>'' ORDER BY seq", base_rac + '%')
    r = c.fetchone()
    return (str(r[0]).strip() if r and r[0] else 'Q1000')

def _final_proc_code(cro, item):
    """완성공정(최종) gagong_proc_code = MAX(PROC_SEQ). method 무관·PROC_SEQ 최댓값. 라이브 RO."""
    c = cro.cursor()
    try:
        c.execute("SELECT TOP 1 ISNULL(GAGONG_PROC_CODE,'') FROM nx.PR_M_ITEM_PROC_GAGONG WHERE ITEM_CODE=? ORDER BY PROC_SEQ DESC", item)
        r = c.fetchone()
        return str(r[0]).strip() if r and r[0] else ""
    except Exception:
        return ""

def _is_final_product(nxc, item):
    """최종제품(ASY) 판정: nx.bom에 child로 없으면 최상위=제품(ASY), child면 반제품(PRD)."""
    c = nxc.cursor()
    c.execute("SELECT COUNT(*) FROM nx.bom WHERE child_code=?", item)
    return (c.fetchone()[0] or 0) == 0

def _backflush_core(cro, nx, item, prod_qty, wo, gpc, mode, user, ref_key, ref_bc=None):
    """★백플러시 코어(트랜잭션 미관리 — 호출측 commit/rollback). cro=RO conn, nx=쓰기 tx conn.
       완성공정 1회 전체BOM×생산량 소비(−P4: RDY 우선 없으면 MAT) + 생산품 +ASY(최종제품)/+PRD(반제품, tag P7).
       회수율 제외. INNER_PROD=1만. 멱등=ref_key(바코드=BC:{barcode}:{proc} / 수기=wo|item|ymd)."""
    nc = nx.cursor()
    if not item or prod_qty <= 0: return {"ok": False, "detail": "item·생산량(>0) 필수"}
    if not _is_inner_prod(cro, item): return {"ok": False, "detail": "사내생산(INNER_PROD=1) 아님 — 백플러시 제외(사급회수·매입·직납)"}
    import datetime as _d
    ymd6 = _d.datetime.now().strftime('%y%m%d')
    nc.execute("SELECT bf_id FROM nx.backflush_log WHERE ref_key=? AND state='posted'", ref_key)
    ex = nc.fetchone()
    if mode == "post" and ex: return {"ok": False, "detail": f"이미 백플러시됨(중복방지) — ref {ref_key}"}
    if mode == "reverse" and not ex: return {"ok": False, "detail": "되돌릴 백플러시 없음"}
    f = -1.0 if mode == "reverse" else 1.0
    comps, weld = _backflush_bom(nx, item, cro)   # ★cro=라이브RO(용접봉 사내한정 판정)
    if not comps and not weld: return {"ok": False, "detail": "nx.bom 전개결과 없음(소비 BOM 없음)"}
    # ★생산실적은 항상 기록 가능해야 함(사용자 확정 2026-08-19) — 키팅과 무관·재고부족으로 실적을 막지 않는다.
    #   자재 현재고(mat_stock_daily=_mat_avail) < BOM소요면 '경고(stock_warn)'로만 surface(마이너스 신호=상류 입고 누락 등), ★실적 차단 안 함.
    #   커버리지 인지: 자재재고 관리품목만 판정 — 비키팅품(케이블타이·비닐)·사급포함품은 mat_stock_daily 미추적 → 경고대상서도 제외(오탐 방지).
    #   ★한계: mat_stock_daily는 레거시 일스냅샷 → 당일 연속분 미반영(관찰용). 마이너스 원천차단의 하드 게이트는 실적이 아니라 출고(ASY/완성재고)에 둔다.
    stock_warn = None
    if mode == "post":
        gc = cro.cursor(); short = []
        def _tracked(code):
            gc.execute("SELECT COUNT(*) FROM nx.mat_stock_daily WHERE UPPER(mat_code)=?", str(code or "").strip().upper())
            return (gc.fetchone()[0] or 0) > 0
        for _ch, _cq in comps:
            _need = _cq * prod_qty
            if _need > 0 and _tracked(_ch):
                _av = _mat_avail(gc, _ch)
                if _need > _av + 1e-6:
                    short.append(f"{_ch}(가용 {_av:g} < 소요 {_need:g})")
        for _br, _wq in weld.items():
            _wneed = _wq * prod_qty
            if _wneed > 0 and _tracked(_br):
                _av = _mat_avail(gc, _br)
                if _wneed > _av + 1e-6:
                    short.append(f"용접봉 {_br}(가용 {_av:g} < 소요 {_wneed:g})")
        if short:
            more = f" 외 {len(short)-8}건" if len(short) > 8 else ""
            stock_warn = "자재부족 경고(실적은 기록됨) — " + "; ".join(short[:8]) + more   # ★차단 아님
    out_sp = 'ASY' if _is_final_product(nx, item) else 'PRD'   # ★완성=최종제품 ASY / 반제품 PRD
    def _seq():
        nc.execute("SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.stock_ledger WHERE MAINT_YMD=?", ymd6)
        return int(nc.fetchone()[0] or 1)
    def _post(sp, child, qty, tag, remk, gpc_over=None):
        if abs(qty) < 1e-9: return
        nc.execute("""INSERT INTO nx.stock_ledger(STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,ITEM_CODE,MAT_CODE,
              GAGONG_PROC_CODE,WORK_ORDER,MAINT_QTY,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
            VALUES(?,?,?,?,'Z99990',?,?,?,?,?,?,?,GETDATE())""",
            sp, ymd6, _seq(), tag, (child if sp in ('PRD','ASY','RDY') else None),
            (child if sp == 'MAT' else None), (gpc_over or gpc or None), (wo or None), qty, remk, user)
            # ★RDY도 ITEM_CODE축(키팅 예약과 정합) / MAT만 MAT_CODE축 — −RDY가 키팅 +RDY를 정확히 상쇄
    seq_from = _seq(); consumed = 0.0
    for child, cq in comps:                       # 소비(−P4): RDY 우선 없으면 MAT
        need = cq * prod_qty
        nc.execute("SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger WHERE STOCK_POINT='RDY' AND ITEM_CODE=?", child)
        rdy = max(float(nc.fetchone()[0] or 0), 0.0)
        from_rdy = min(need, rdy); from_mat = need - from_rdy
        _post('RDY', child, -from_rdy * f, 'P4', '백플러시소비(준비)')
        _post('MAT', child, -from_mat * f, 'P4', '백플러시소비(자재)')
        consumed += need
    weld_consumed = 0.0                            # ★용접봉 소비(−MAT, tag 'W', base RAC, 투입공정): 완성공정 1회 자재와 함께
    for base_rac, wq in weld.items():
        wneed = wq * prod_qty
        if abs(wneed) < 1e-9: continue
        _post('MAT', base_rac, -wneed * f, 'W', '백플러시 용접봉소비', gpc_over=_weld_proc_code(nx, base_rac))
        weld_consumed += wneed
    _post(out_sp, item, prod_qty * f, 'P7', f'백플러시 생산입고({out_sp})')   # 생산품 +ASY/+PRD
    nc.execute("SELECT ISNULL(MAX(MAINT_SEQ),0) FROM nx.stock_ledger WHERE MAINT_YMD=?", ymd6)
    seq_to = int(nc.fetchone()[0] or 0)
    if mode == "post":
        nc.execute("""INSERT INTO nx.backflush_log(prod_ymd,work_order,item_code,gpc,prod_qty,ref_key,ref_bc,state,maint_ymd,seq_from,seq_to,ins_user)
            VALUES(?,?,?,?,?,?,?, 'posted', ?,?,?,?)""",
            ymd6, (wo or None), item, (gpc or None), prod_qty, ref_key, ref_bc, ymd6, seq_from, seq_to, user)
    else:
        nc.execute("UPDATE nx.backflush_log SET state='reversed' WHERE bf_id=?", ex[0])
    # 협력사 용접봉 무게정산(weight_calc) 연계는 후속(TODO) — 여기선 물리적 재고소비만.
    return {"ok": True, "mode": mode, "item": item, "prod_qty": prod_qty, "out_point": out_sp,
            "components": len(comps), "consumed_qty": round(consumed, 3),
            "weld_kinds": len(weld), "weld_consumed": round(weld_consumed, 4), "ref_key": ref_key,
            "stock_warn": stock_warn}   # ★소프트 재고게이트 경고(자재부족·비차단). 하드=enforce=true(컷오버)

@router.post("/api/backflush/post")
def backflush_post(payload: dict = Body(...)):
    """수기 백플러시(테스트/보정). 실운영 자동트리거=바코드생산실적(procbc_save 완성공정). mode=post/reverse. INNER_PROD=1만. 쓰기 nx만."""
    item = (payload.get("item") or "").strip(); wo = (payload.get("work_order") or payload.get("wo") or "").strip()
    gpc = (payload.get("gpc") or "").strip(); prod_qty = float(payload.get("prod_qty") or 0)
    mode = str(payload.get("mode", "post")).strip()
    user = (str(payload.get("user", "") or "").strip() or "웹사용자")[:20]
    import datetime as _d
    ref_key = f"{wo}|{item}|{_d.datetime.now().strftime('%y%m%d')}"   # 수기 멱등키(WO·품목·일자)
    cn = _nx(); nx = _nx_tx()   # ★nx전환: 읽기도 nx 충실복제. 원자성: 소비(−P4)+생산입고(+P7/ASY)+backflush_log 동일 트랜잭션
    try:
        lm = _lock_msg(cn.cursor(), _d.datetime.now().strftime('%y%m%d'))   # ★공통 마감잠금(생산일=당월)
        if lm: return {"ok": False, "detail": lm}
        r = _backflush_core(cn, nx, item, prod_qty, wo, gpc, mode, user, ref_key)   # ★실적은 재고부족으로 차단 안 함(경고 stock_warn만)
        nx.commit() if r.get("ok") else nx.rollback()
        return r
    except Exception as e:
        try: nx.rollback()
        except Exception: pass
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        cn.close(); nx.close()
