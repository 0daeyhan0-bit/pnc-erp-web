# -*- coding: utf-8 -*-
"""backflush 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes, _lock_msg, _stock_short_msg, _mat_avail)

router = APIRouter()

# ===================== 생산실적 재고 게이트 (예외 없음) =====================
# ★대표 지시 2026-08-28: "생산실적도 막아라. 우리 시스템은 예외가 없다.
#   대신 경고 메시지를 주고 왜 안 되는지 알려줘라."
#   이전 게이트는 mat_stock_daily 에 없는 품목(=nx.bom 소비대상 자식의 70.2%, 대부분
#   사내 가공품 sgroup 130)을 **통째로 건너뛰었다** → 그 품목들은 음수가 그대로 났다.
#   그 예외를 제거하고, 판정축을 **백플러시가 실제로 빼가는 축**과 일치시킨다.
#     소비 1순위 RDY(준비재고, 원장) → 2순위 MAT(자재재고)
#   ★생산창고(PR_T_MAT_STOCK_WH)는 백플러시 소비축이 아니다. 여기 재고가 있어도
#     가용으로 세지 않는다 — 대신 사유 메시지에 실어 "어디에 있는데 왜 못 쓰는지"를 알린다.
def _avail_axes(nx, code):
    """소비 가능 재고를 축별로 집계. 반환 (rdy, mat, prd_wh, mat_src).
         rdy    준비재고 = nx.stock_ledger STOCK_POINT='RDY' 잔량   ← 소비 1순위
         mat    자재재고 = mat_stock_daily(정본), 미등록이면 자재창고 미러 PU_T_MAT_STOCK_WH ← 소비 2순위
         prd_wh 생산창고 PR_T_MAT_STOCK_WH 잔량                      ← 소비축 아님(안내용)
       ★mat_stock_daily 미등록을 '무제한'으로 보지 않는다(그게 종전 예외의 정체)."""
    c = nx.cursor(); code = str(code or "").strip().upper()
    if not code:
        return 0.0, 0.0, 0.0, "-"
    c.execute("SELECT ISNULL(SUM(CAST(MAINT_QTY AS float)),0) FROM nx.stock_ledger "
              "WHERE STOCK_POINT='RDY' AND UPPER(ITEM_CODE)=?", code)
    rdy = max(float(c.fetchone()[0] or 0), 0.0)
    c.execute("SELECT TOP 1 CAST(stock_qty AS float) FROM nx.mat_stock_daily "
              "WHERE UPPER(mat_code)=? ORDER BY ymd DESC", code)
    r = c.fetchone()
    if r:
        mat, src = float(r[0] or 0), "자재일마감"
    else:
        c.execute("SELECT ISNULL(SUM(CAST(STOCK_QTY AS float)),0) FROM nx.PU_T_MAT_STOCK_WH "
                  "WHERE UPPER(MAT_CODE)=?", code)
        mat, src = float(c.fetchone()[0] or 0), "자재창고"
    c.execute("SELECT ISNULL(SUM(CAST(STOCK_QTY AS float)),0) FROM nx.PR_T_MAT_STOCK_WH "
              "WHERE UPPER(MAT_CODE)=?", code)
    prd_wh = float(c.fetchone()[0] or 0)
    return rdy, max(mat, 0.0), prd_wh, src


def _short_reason(code, need, rdy, mat, prd_wh, src, label=""):
    """부족 사유 1줄 — **왜 안 되는지**가 보이게 축별로 밝힌다."""
    avail = rdy + mat
    msg = (f"{label}{code}: 소요 {need:g} > 가용 {avail:g}"
           f" (준비재고 {rdy:g} + 자재재고 {mat:g}[{src}])")
    if prd_wh > 0:
        msg += f" · 생산창고에 {prd_wh:g} 있으나 백플러시 소비축이 아님"
    elif avail <= 0:
        msg += " · 어느 창고에도 재고 없음(입고·키팅 먼저)"
    return msg


def _prod_shortages(nx, comps, weld, qty):
    """생산량 qty 에 대한 부족 목록. comps=[(child,unit_qty)] · weld={base:unit_qty}.
       ★예외 없음 — 모든 자식·용접봉을 판정한다."""
    out = []
    for code, unit in list(comps) + [(k, v) for k, v in (weld or {}).items()]:
        need = float(unit) * float(qty)
        if need <= 0:
            continue
        lbl = "용접봉 " if (weld and code in weld) else ""
        rdy, mat, prd_wh, src = _avail_axes(nx, code)
        if need > rdy + mat + 1e-6:
            out.append(_short_reason(code, need, rdy, mat, prd_wh, src, lbl))
    return out


# ================= ★Phase2: 생산실적 백플러시 엔진 (실사용BOM×생산량 소비, 회수율 제외) =================
def _is_inner_prod(cro, item):
    """사내생산(INNER_PROD=1) 판정: MAKE_TYPE='1' 또는 가공공정(PR_M_ITEM_PROC_GAGONG) 보유. 라이브 RO."""
    c = cro.cursor()
    try:
        c.execute("SELECT ISNULL(make_type,'') FROM nx.item WHERE item_code=?", item)
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
            cc = cro.cursor(); cc.execute("SELECT ISNULL(make_type,'') FROM nx.item WHERE item_code=?", n)
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

def _sub_footprints_by_jadoban(nxc, product):
    """★다리 C(SUB 원소재 풋프린트·읽기전용·2026-08-26): 제품의 backflush 원소재 소비를 SUB(jadoban)별로 분해.
       ★_backflush_bom 과 동일 walk 규칙(제작서브 is_lowest≠'Y'·자식보유 전개 / leaf 소비 / 용접봉 별도)로
       전개하되, 각 소비 leaf를 그 경로 최상위 jadoban(제품 직속 엣지 라벨)으로 귀속 → SUB grain.
       ∴ Σ(전 jadoban) == _backflush_bom comps(자재) = 구조적 diff0(총량 불변). SUB grain은 귀속 라벨만 추가.
       근거=SUB_MATERIAL_INTEGRATION §14. nx.bom flat(SUB노드 없음)·jadoban=그룹라벨·is_lowest=VARCHAR 'Y'.
       반환 {jadoban(또는 '(직속)'): {원소재: cum_qty}}. #2 재고 backfill·#3 backflush SUB-grain 결선 기반."""
    c = nxc.cursor()
    c.execute("SELECT parent_code, child_code, CAST(qty AS float), ISNULL(role,''), ISNULL(is_lowest,''), ISNULL(jadoban,'') FROM nx.bom")
    kids = {}
    for p, ch, q, role, low, jad in c.fetchall():
        kids.setdefault(str(p).strip(), []).append((str(ch).strip(), q or 0.0, str(role).strip(), str(low).strip(), str(jad).strip()))
    g = {}
    def walk(node, mult, top_jad, depth):
        if depth > 15:
            return
        for ch, q, role, low, jad in kids.get(node, []):
            cq = mult * q
            if '용접봉' in (role or ''):                       # 용접봉=공정종속(backflush 별도수집) → 자재풋프린트 제외
                continue
            label = top_jad or (jad if jad else '(직속)')       # 경로 최상위 jadoban 전파(제품 직속 엣지 라벨)
            if ch in kids and low != 'Y':                      # 제작 서브 → 전개(라벨 유지)
                walk(ch, cq, label, depth + 1)
            else:                                              # 소비 leaf → 그 SUB(label)에 귀속
                g.setdefault(label, {})[ch] = g.get(label, {}).get(ch, 0.0) + cq
    walk(str(product).strip(), 1.0, None, 0)
    return g

def _sub_raw_footprint(nxc, product, jadoban):
    """다리 C 단건: 제품 내 특정 SUB(jadoban)의 원소재 풋프린트 {원소재: qty}. _sub_footprints_by_jadoban 파생."""
    return _sub_footprints_by_jadoban(nxc, product).get(str(jadoban).strip(), {})

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
    # ★생산실적 재고 게이트 — **예외 없음**(정본 STOCK_GATING_CLOSE_LOCK_RULES.md §0-★, 2026-08-28)
    #   종전엔 mat_stock_daily 미등록 품목을 _tracked() 로 **판정 없이 통과**시켰다.
    #   실측 결과 그 예외가 nx.bom 소비대상 자식의 70.2%(6,988/9,955, 대부분 사내 가공품)를
    #   덮어 게이트가 사실상 무효였다 → 예외 제거. 판정할 수 없으면 통과가 아니라 차단이다.
    #   판정축 = 실제 소비축(RDY 준비재고 → MAT 자재재고). 생산창고는 소비축이 아니므로
    #   가용으로 세지 않되 **사유 메시지에 실어** 어디에 있는지 알린다(규칙 A-0-1 사유 고지).
    if mode == "post":
        short = _prod_shortages(nx, comps, weld, prod_qty)
        if short:
            more = f" 외 {len(short)-8}건" if len(short) > 8 else ""
            return {"ok": False, "shortage": short,
                    "detail": "자재부족으로 생산실적 불가 — " + "; ".join(short[:8]) + more}
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
            "weld_kinds": len(weld), "weld_consumed": round(weld_consumed, 4), "ref_key": ref_key}

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
        r = _backflush_core(cn, nx, item, prod_qty, wo, gpc, mode, user, ref_key)   # ★재고부족이면 차단됨(예외 없음 §0-★) — 사유는 r['shortage']
        nx.commit() if r.get("ok") else nx.rollback()
        return r
    except Exception as e:
        try: nx.rollback()
        except Exception: pass
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        cn.close(); nx.close()
