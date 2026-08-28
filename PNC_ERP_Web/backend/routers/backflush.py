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

WELD_WAREHOUSE = 'Q1000'   # ★용접봉 단일 생산창고 (대표 확정 2026-08-27). 공정별 창고 분리 안 함.

def _weld_proc_code(nxc, base_rac=None):
    """용접봉 투입공정(=생산창고 GAGONG_PROC_CODE) — ★단일창고 Q1000 (대표 확정 2026-08-27).
       전 용접봉을 하나의 생산창고(Q1000)로: 자재출고 불출·생산실적 차감·게이트 모두 Q1000 기준.
       (nx.bom_line.gagong_proc 실측 100% 미기입 → 공정별 분리 불가·불필요. 향후 분리 원하면 이 함수와 매핑을 함께 변경.)"""
    return WELD_WAREHOUSE

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

def _ring_collect(nxc, root):
    """용접링(sg230 활성) 소비 수집 = ★bom_line 정본(nx.bom엔 용접링 없음=LG재구축 누락).
       단위 EA. 반환 {ring_code: qty}. cs_calc_except=0만. 현 활성링은 root 직속(검증완, WELD_RING_DESIGN §15).
       ※제작SUB 깊은 링 재귀는 후속(활성 7종 전부 직속 확인). 봉↔링 중복 방지는 호출측(_backflush_core)에서 봉 skip."""
    c = nxc.cursor()
    c.execute("""SELECT bl.child_item, CAST(bl.qty AS float)
        FROM nx.bom_line bl JOIN nx.bom_header bh ON bh.bom_id = bl.bom_id
        JOIN nx.item i ON i.item_code = bl.child_item
        WHERE bh.item_code = ? AND i.item_name LIKE N'%용접링%' AND i.sgroup = '230'
          AND ISNULL(bl.cs_calc_except, 0) = 0""", root)
    ring = {}
    for ch, q in c.fetchall():
        ring[str(ch)] = ring.get(str(ch), 0.0) + (q or 0.0)
    return ring


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
    ring = _ring_collect(nx, item)                # ★용접링(bom_line 정본, nx.bom엔 없음) EA
    if ring and weld:                             # ★링 있는 노드 = 봉 대체 → 봉 skip(중복차감 방지, 노드단위·월30근사)
        weld = {}
    if not comps and not weld and not ring: return {"ok": False, "detail": "nx.bom 전개결과 없음(소비 BOM 없음)"}
    # ★자재 부족이면 생산실적 차단(사용자 확정 2026-08-19): "자재가 부족하면 생산실적이 잡히면 안돼."
    #   자재 현재고(mat_stock_daily=_mat_avail 정본) < BOM소요면 실적 거부 → 마이너스 원천차단. ★키팅과 무관(키팅=flag) — 실제 자재재고로만 판정.
    #   ★커버리지 인지: 자재재고 '관리품목'만 게이트 — 비키팅품(케이블타이·비닐)·사급포함품은 mat_stock_daily 미추적 → 제외(오차단 방지, 정본 §4-C 검증).
    #   ★한계: mat_stock_daily=레거시 일스냅샷 → 당일 입고/연속차감 미반영. 컷오버시 실시간 자재정본으로 승격 필요(§4 step4) — 그래야 당일 입고분 오차단 없음.
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
        for _rc, _rq in ring.items():                 # ★용접링 부족 게이트(mat_stock_daily 추적품만 — 미추적=입고체계 선결)
            _rneed = _rq * prod_qty
            if _rneed > 0 and _tracked(_rc):
                _av = _mat_avail(gc, _rc)
                if _rneed > _av + 1e-6:
                    short.append(f"용접링 {_rc}(가용 {_av:g} < 소요 {_rneed:g})")
        if short:
            more = f" 외 {len(short)-8}건" if len(short) > 8 else ""
            return {"ok": False, "detail": "자재부족으로 생산실적 불가 — " + "; ".join(short[:8]) + more}
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
    ring_consumed = 0.0                            # ★용접링 소비(−MAT, tag 'R', EA, 생산창고 Q1000): 완성공정 1회
    for ring_code, rq in ring.items():
        rneed = rq * prod_qty
        if abs(rneed) < 1e-9: continue
        _post('MAT', ring_code, -rneed * f, 'R', '백플러시 용접링소비', gpc_over=WELD_WAREHOUSE)
        ring_consumed += rneed
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
            "weld_kinds": len(weld), "weld_consumed": round(weld_consumed, 4),
            "ring_kinds": len(ring), "ring_consumed": round(ring_consumed, 4), "ref_key": ref_key}


def _weld_stock_at(cur, base_rac, gpc):
    """생산창고(투입공정 gpc, 예 Q1000) 용접봉 현재고 = SUM(stock_ledger MAT · 그 공정).
       ★실시간 원장sum(스냅샷 아님). Q1000은 웹전용(matissue 입 · backflush 출)이라 stock_ledger가 정확(§16 예외)."""
    cur.execute("""SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger
        WHERE STOCK_POINT='MAT' AND MAT_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=?""", base_rac, gpc)
    return float(cur.fetchone()[0] or 0)


def _weld_consume(cro, nx, item, signed_qty, wo, user, do_gate=True):
    """★용접봉 소비/복원 (부호수량, ⑦ 병렬) — 생산실적(procbc_save 완성공정) 결선용. 2026-08-27.
       모델(대표 확정): 자재출고(matissue)로 작업자가 용접봉을 자재→생산창고(Q1000) 불출(+Q1000) →
                        생산실적 시 생산창고 용접봉 −차감(−Q1000, tag W). 자재/생산품은 레거시가 처리(이중차감 없음).
       signed_qty>0=소비(−Q1000), <0=취소(+Q1000 복원). 스캔별 실적이라 멱등/로그 없음(⑦와 동일=부호수량 누적).
       ★게이트(소비=signed_qty>0만): 생산창고(Q1000=투입공정) 재고 < 소요 → shortage(⑦ _short 형식으로 반환,
         procbc_save가 자재부족과 합쳐 한 메시지로 표시). 재고=_weld_stock_at(실시간 stock_ledger sum).
       용접봉 소요=_backflush_bom weld(사내한정 _sanae 내장). base RAC 집계, INNER_PROD=1 사내만.
       반환 {ok, shortage:[{mat,part,need,have,lack}]?, weld_kinds, weld_consumed}."""
    nc = nx.cursor()
    if not item or signed_qty == 0:
        return {"ok": True, "weld_kinds": 0}
    if not _is_inner_prod(cro, item):
        return {"ok": True, "weld_kinds": 0}   # 사내생산 아님 = 용접봉 소비 없음(스킵)
    _comps, weld = _backflush_bom(nx, item, cro)   # 용접봉만 사용(자재/생산품은 레거시)
    ring = _ring_collect(nx, item)                 # ★용접링(bom_line 정본, nx.bom엔 없음) — 봉과 동일 Q1000 모델
    if ring and weld:                              # 링 있는 노드 = 봉 대체 → 봉 skip(중복차감 방지)
        weld = {}
    if not weld and not ring:
        return {"ok": True, "weld_kinds": 0, "weld_consumed": 0.0}
    import datetime as _d
    ymd6 = _d.datetime.now().strftime('%y%m%d')
    # ── 게이트(소비 signed_qty>0만): 생산창고 용접봉 재고 부족이면 실적거부(음수 원천차단) ──
    if do_gate and signed_qty > 0:
        gc = cro.cursor(); short = []
        for br, wq in weld.items():
            wneed = wq * signed_qty
            if wneed <= 0:
                continue
            gpc = _weld_proc_code(nx, br)                 # 투입공정(Q1000/Q2000)
            have = _weld_stock_at(gc, br, gpc)            # 생산창고 실시간 재고
            if wneed > have + 1e-6:
                gc.execute("SELECT TOP 1 ISNULL(item_name,'') FROM nx.item WHERE item_code=?", br)
                _r = gc.fetchone(); _nm = (str(_r[0]).strip() if _r and _r[0] else br)
                short.append({"mat": f"용접봉 {_nm}({br})", "part": gpc,
                              "need": round(wneed, 4), "have": round(have, 4), "lack": round(wneed - have, 4)})
        for rc, rq in ring.items():                   # ★용접링 게이트 = 생산창고(Q1000) 재고
            rneed = rq * signed_qty
            if rneed <= 0:
                continue
            have = _weld_stock_at(gc, rc, WELD_WAREHOUSE)
            if rneed > have + 1e-6:
                gc.execute("SELECT TOP 1 ISNULL(item_name,'') FROM nx.item WHERE item_code=?", rc)
                _r = gc.fetchone(); _nm = (str(_r[0]).strip() if _r and _r[0] else rc)
                short.append({"mat": f"용접링 {_nm}({rc})", "part": WELD_WAREHOUSE,
                              "need": round(rneed, 4), "have": round(have, 4), "lack": round(rneed - have, 4)})
        if short:
            return {"ok": False, "shortage": short}
    # ── 소비/복원: dq = −(원단위×부호수량) → tag W @ 투입공정 (소비=−, 취소=+) ──
    def _seq():
        nc.execute("SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.stock_ledger WHERE MAINT_YMD=?", ymd6)
        return int(nc.fetchone()[0] or 1)
    weld_consumed = 0.0
    for br, wq in weld.items():
        dq = -(wq * signed_qty)
        if abs(dq) < 1e-9:
            continue
        nc.execute("""INSERT INTO nx.stock_ledger(STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,ITEM_CODE,MAT_CODE,
              GAGONG_PROC_CODE,WORK_ORDER,MAINT_QTY,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
            VALUES('MAT',?,?,'W','Z99990',NULL,?,?,?,?,?,?,GETDATE())""",
            ymd6, _seq(), br, _weld_proc_code(nx, br), (wo or None), dq, '용접봉 생산소비(공정종속)', user)
        weld_consumed += wq * signed_qty
    ring_consumed = 0.0                            # ★용접링 소비/복원 (−R @ Q1000, 부호수량)
    for rc, rq in ring.items():
        dq = -(rq * signed_qty)
        if abs(dq) < 1e-9:
            continue
        nc.execute("""INSERT INTO nx.stock_ledger(STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,ITEM_CODE,MAT_CODE,
              GAGONG_PROC_CODE,WORK_ORDER,MAINT_QTY,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
            VALUES('MAT',?,?,'R','Z99990',NULL,?,?,?,?,?,?,GETDATE())""",
            ymd6, _seq(), rc, WELD_WAREHOUSE, (wo or None), dq, '용접링 생산소비(공정종속)', user)
        ring_consumed += rq * signed_qty
    return {"ok": True, "item": item, "weld_kinds": len(weld), "weld_consumed": round(weld_consumed, 4),
            "ring_kinds": len(ring), "ring_consumed": round(ring_consumed, 4)}


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
