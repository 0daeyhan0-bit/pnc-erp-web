# -*- coding: utf-8 -*-
"""소요 통일 — explode 공유 아키텍처 (SOYO_ENGINE_UNIFY §13).

★배포된 nx_soyo_engine.py(원가 #1/#2 운영중)는 절대 무변경. 여기서 explode 공유형 walker를 만들어
Phase 0 하네스(soyo_unify_verify)로 **현행 walker와 전수 diff0** 증명한 뒤에만 프로덕션 전환(Phase 3).

핵심(§13): 물리 BOM을 explode로 1회 전개(전 노드/엣지 태깅) → 모드 walker가 공유 트리를 순회하며
자기 정지/필터/집계 적용. 모드마다 소요 다른 게 정상(원가=INNER경계·생산=사급경계·중량=sagub).

★2 explode 트랙 (2026-08-24 전수 diff0 확정, 통합):
  - `explode`      : 원가/내부원가축. eng.lines(nx.bom_line, RAC→proc_weld 주입, cs_calc_except).
  - `explode_bomline`: 생산+중량축. nx.bom_line raw 1회(qty·qty_pr·except_flag·sagub_default·RAC포함).
  원가는 용접봉=공정(proc_weld), 생산/중량은 용접봉=BOM(RAC)이라는 진짜 차이로 트랙 분리.
검증: 원가/내부/생산/중량 전부 사용중 완제품 2081 전수 diff0.
"""


# ===================== 원가·내부원가 트랙 (explode = eng.lines·cs_calc_except) =====================
def explode(eng, item):
    """원가축 full 전개. RAC 용접봉은 eng.lines가 proc_weld로 주입. 반환 (nodes, kids).
      kids[parent] = [(child, qty, cs_calc_except, lme_except)] — eng.lines 1회·부모별 dedup."""
    nodes = []
    kids = {}
    hasbom = eng._load_hasbom()

    def walk(node, cum_q, lvl, parent, uq, cxe, lxe, seen):
        nodes.append({'level': lvl, 'parent': parent, 'child': node, 'unit_qty': uq,
                      'cum_qty': cum_q, 'cs_calc_except': cxe, 'lme_except': lxe,
                      'info': eng._load_item(node)})
        if node in hasbom and node not in seen:
            if node not in kids:
                kids[node] = [(str(c).strip(), float(qty), bool(cx), bool(lx))
                              for c, qty, cx, f, t, lx in eng.lines(node)]
            for c, qty, cx, lx in kids[node]:
                walk(c, cum_q * qty, lvl + 1, node, qty, cx, lx, seen | {node})

    walk(item, 1.0, 0, '', 1.0, False, False, set())
    return nodes, kids


def _expandable_ex(eng, node, info, kids, seen):
    """원가 _expandable 재현: 사내생산(INNER=1) & 직납(cg5) 아님 & non-cs_calc_except 자식 존재."""
    if not eng._inner_prod(info) or info['cost_gubun'] == '5':
        return None
    if node not in kids or node in seen:
        return None
    k = [e for e in kids[node] if not e[2]]
    return k or None


def cost_material_ex(eng, item, ymd):
    """[원가 walker · explode 공유] — nx_soyo_engine.cost_material 과 전수 diff0."""
    ymcut = '20' + ymd[:4]
    _, kids = explode(eng, item)

    def value(node, q, seen):
        info = eng._load_item(node)
        expandable = (info['cost_gubun'] != '3' or info['make_type'] == '1') and _expandable_ex(eng, node, info, kids, seen)
        if expandable:
            tot = 0.0
            for c, qty, cx, lx in kids.get(node, []):
                if cx:
                    continue
                tot += value(c, qty * q, seen | {node})
            return tot
        return eng._leaf_val(node, info, q, ymd, ymcut)

    base = value(item, 1.0, set())
    return round(base + eng.lme_u(item, ymd), 2)


def cost_material_nae_ex(eng, item, ymd):
    """[내부원가 walker · explode 공유] — nx_soyo_engine.cost_material_nae 과 전수 diff0.
    내부원가 = 전개-all(직납 cg5·cg3만 정지·make_type/INNER 무관)·LME 없음."""
    ymcut = '20' + ymd[:4]
    _, kids = explode(eng, item)

    def _expandable_nae_ex(node, info, seen):
        if info['cost_gubun'] == '5':   # ★직납만 정지(엔진 _expandable_nae)
            return None
        if node not in kids or node in seen:
            return None
        k = [e for e in kids[node] if not e[2]]
        return k or None

    def value(node, q, seen):
        info = eng._load_item(node)
        if info['cost_gubun'] != '3' and _expandable_nae_ex(node, info, seen):
            return sum(value(c, qty * q, seen | {node}) for c, qty, cx, lx in kids.get(node, []) if not cx)
        return eng._leaf_val_nae(node, info, q, ymd, ymcut)

    return round(value(item, 1.0, set()), 2)


# ===================== 생산·중량 트랙 (explode_bomline = nx.bom_line raw) =====================
def _lines_bl(eng, item):
    """통합 nx.bom_line raw 직상위 [(child_u, qty, qty_pr, except'0/1', sagub int)]. RAC포함·1회캐시.
    ★생산 qty=qty_pr(=v_pr_bom.USE_QTY_PR) / 중량 qty=qty(=USE_QTY). (전수FAIL 12건 규명 2026-08-24)."""
    bid = eng.bom_id(item)
    if bid is None:
        return []
    if not hasattr(eng, '_lines_bl_cache'):
        eng._lines_bl_cache = {}
    if bid not in eng._lines_bl_cache:
        eng.cur.execute("""SELECT UPPER(LTRIM(RTRIM(child_item))), qty, ISNULL(qty_pr, qty),
            ISNULL(except_flag,0), ISNULL(sagub_default,0)
            FROM nx.bom_line WHERE bom_id=? ORDER BY seq""", bid)
        eng._lines_bl_cache[bid] = [(str(r[0]).strip(), float(r[1] or 0), float(r[2] or 0),
                                     '1' if r[3] else '0', int(r[4] or 0)) for r in eng.cur.fetchall()]
    return eng._lines_bl_cache[bid]


def explode_bomline(eng, item):
    """★통합 explode(생산+중량) — nx.bom_line raw 1회. kids[u]=[(child_u,qty,qty_pr,except,sagub)]. upper키."""
    kids = {}

    def build(node):
        u = node.strip().upper()
        if u in kids:
            return
        ch = _lines_bl(eng, node)
        kids[u] = ch
        for c, q, qp, ex, sag in ch:
            build(c)
    build(item)
    return kids


def prod_soyo_ex(eng, item):
    """[생산 walker · explode_bomline] — nx_soyo_engine.prod_soyo(v_pr_bom) 과 전수 diff0.
    qty_pr·except_flag=1 제외·최하위집계·용접봉(RAC) 제외. 반환 {mat_code_u: qty}."""
    import nx_soyo_engine as _se
    kids = explode_bomline(eng, item)
    raw = {}

    def walk(node, cum_q, lvl, seen):
        u = node.strip().upper()
        ch = kids.get(u, []) if u not in seen else []
        ch = [(c, qp) for (c, q, qp, ex, sag) in ch if ex != '1']
        if ch:
            for c, qp in ch:
                walk(c, cum_q * qp, lvl + 1, seen | {u})
        if not ch and lvl > 0:
            raw.setdefault(u, []).append((lvl, cum_q))
    walk(item, 1.0, 0, set())
    out = {}
    for mc, occ in raw.items():
        if _se._is_weldrod(eng, mc):
            continue
        out[mc] = round(sum(q for _, q in occ), 6)
    return out


def weight_explode_ex(eng, item):
    """[중량 walker · explode_bomline] — nx_soyo_engine.weight_explode 과 전수 diff0.
    qty·sagub_default=1 제외·COOP_SET/COOPB 폴백·geom leaf. 반환 (raw_kg, weld_kg)."""
    import nx_soyo_engine as _se
    COOP_SET, COOPB = _se._wt_coop(eng)
    kids = explode_bomline(eng, item)
    memo = {}

    def walk(node):
        u = node.strip().upper()
        if u in memo:
            return memo[u]
        memo[u] = (0.0, 0.0)
        ch = kids.get(u, [])
        if ch:
            rk = wk = 0.0
            for c, q, qp, ex, sag in ch:
                if sag == 1:
                    continue
                cr, cw = walk(c)
                rk += cr * q; wk += cw * q
            if rk > 0 or wk > 0:
                memo[u] = (rk, wk); return memo[u]
            if u in COOP_SET:
                memo[u] = (COOP_SET[u], 0.0); return memo[u]
            cb = COOPB.get(u)
            if cb:
                rk = wk = 0.0
                for c, q in cb:
                    cr, cw = walk(c); rk += cr * q; wk += cw * q
                memo[u] = (rk, wk); return memo[u]
            return memo[u]
        cb = COOPB.get(u)
        if cb and u not in COOP_SET:
            rk = wk = 0.0
            for c, q in cb:
                cr, cw = walk(c); rk += cr * q; wk += cw * q
            memo[u] = (rk, wk); return memo[u]
        if u in COOP_SET:
            memo[u] = (COOP_SET[u], 0.0); return memo[u]
        w, cls = _se._wt_meta(eng, node)
        memo[u] = (w, 0.0) if cls == 'raw' else ((0.0, w) if cls == 'weld' else (0.0, 0.0))
        return memo[u]

    rk, wk = walk(item)
    return (round(rk, 6), round(wk, 6))
