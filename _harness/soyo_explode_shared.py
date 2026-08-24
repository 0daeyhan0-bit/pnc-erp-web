# -*- coding: utf-8 -*-
"""소요 통일 Phase 1 — explode 공유 아키텍처 (옆에짓고 · SOYO_ENGINE_UNIFY §13-2).

★배포된 nx_soyo_engine.py(원가 #1/#2 운영중)는 절대 무변경. 여기서 explode 공유형 walker를 만들어
Phase 0 하네스(soyo_unify_verify)로 **현행 walker와 diff0** 증명한 뒤에만 통합.

핵심: explode()가 물리 BOM을 1회 전개(정지 안 함·full tree)하고 kids 맵(공유 트리 소스)을 만듦.
모드 walker는 그 공유 맵을 순회하며 자기 정지/필터/집계 적용(자기 재귀·eng.lines 재호출 제거).
"""


def explode(eng, item):
    """모드무관 full 전개(정지 안 함). RAC 용접봉은 eng.lines가 proc_weld로 이미 주입.
    반환: (nodes, kids).
      nodes = [{level,parent,child,unit_qty,cum_qty,cs_calc_except,lme_except,info}] (전 노드·태깅)
      kids[parent] = [(child, qty, cs_calc_except, lme_except)] — eng.lines 1회·부모별 dedup = 공유 트리 소스."""
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
    """원가 _expandable 재현(kids 공유맵 사용): 사내생산(INNER=1) & 직납(cg5) 아님 & non-cx 자식 존재."""
    if not eng._inner_prod(info) or info['cost_gubun'] == '5':
        return None
    if node not in kids or node in seen:
        return None
    k = [e for e in kids[node] if not e[2]]   # non-cs_calc_except 자식
    return k or None


def cost_material_ex(eng, item, ymd):
    """[원가 walker · explode 공유형] — nx_soyo_engine.cost_material 과 diff0 대상.
    자기 재귀(eng.lines) 대신 explode() 공유 kids 맵을 순회. 로직은 원가 규칙 그대로."""
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
    """[내부원가 walker · explode 공유형] — nx_soyo_engine.cost_material_nae 와 diff0 대상.
    내부원가 = 전개-all(cg3만 정지·직납/except만 정지)·LME 없음. kids 공유맵 순회."""
    ymcut = '20' + ymd[:4]
    _, kids = explode(eng, item)

    def _expandable_nae_ex(node, info, seen):
        # 엔진 _expandable_nae 재현: ★직납(cg5) 아님 & non-cx 자식 존재 (make_type/INNER 무관·전공정 가정)
        if info['cost_gubun'] == '5':
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


# ===================== 생산 walker (explode 공유형) =====================
# 생산축: nx.bom_line 직읽기(child·qty·except_flag, RAC 포함). 현행 prod_soyo는 v_pr_bom(USE_QTY_PR·except_flag).
# 이 _ex가 prod_soyo와 diff0면 → nx.bom_line이 v_pr_bom을 재현(소스 등가) = 단일소스 통일 가능.

def _lines_pr(eng, item):
    """생산축 nx.bom_line 직상위 [(child_upper, qty, except_flag '0'/'1')]. RAC 포함(walker 제외)."""
    bid = eng.bom_id(item)
    if bid is None:
        return []
    if not hasattr(eng, '_lines_pr_cache'):
        eng._lines_pr_cache = {}
    if bid not in eng._lines_pr_cache:
        # ★생산 소요 qty = qty_pr(=v_pr_bom.USE_QTY_PR) 우선, 없으면 qty(=USE_QTY). (2026-08-24 전수FAIL 12건 규명)
        eng.cur.execute("""SELECT UPPER(LTRIM(RTRIM(child_item))), ISNULL(qty_pr, qty), ISNULL(except_flag,0)
            FROM nx.bom_line WHERE bom_id=? ORDER BY seq""", bid)
        eng._lines_pr_cache[bid] = [(str(r[0]).strip(), float(r[1] or 0), '1' if r[2] else '0')
                                    for r in eng.cur.fetchall()]
    return eng._lines_pr_cache[bid]


def explode_pr(eng, item):
    """생산축 full 전개(nx.bom_line·except_flag 태깅). 반환 kids_pr[parent]=[(child,qty,except_flag)]."""
    kids = {}
    import nx_soyo_engine as _se
    hasvpr = _se._has_vpr(eng)   # 현행과 동일 '자식 있음' 판정 소스

    def walk(node, seen):
        if node in kids or node in seen:
            return
        ch = _lines_pr(eng, node)
        kids[node] = ch
        for c, q, ex in ch:
            walk(c, seen | {node})
    walk(item, set())
    return kids


def prod_soyo_ex(eng, item):
    """[생산 walker · explode 공유형] — nx_soyo_engine.prod_soyo 와 diff0 대상.
    nx.bom_line(except_flag) 공유맵 순회. except_flag=1 제외·최하위집계·용접봉(RAC) 제외."""
    import nx_soyo_engine as _se
    kids = explode_pr(eng, item)
    raw = {}

    def walk(node, cum_q, lvl, seen):
        ch = kids.get(node, []) if node not in seen else []
        ch = [(c, q, ex) for (c, q, ex) in ch if ex != '1']
        if ch:
            for c, q, ex in ch:
                walk(c, cum_q * q, lvl + 1, seen | {node})
        if not ch and lvl > 0:
            raw.setdefault(node, []).append((lvl, cum_q))
    walk(item, 1.0, 0, set())
    out = {}
    for mc, occ in raw.items():
        if _se._is_weldrod(eng, mc):
            continue
        out[mc] = round(sum(q for _, q in occ), 6)
    return out


# ===================== 중량 walker (explode 공유형) =====================
# ★중량도 이미 nx.bom_line 소스(_cs_lines_wt·sagub_default·RAC포함). 공유 kids맵으로 재현 → 현행 weight_explode와 diff0.
def explode_wt(eng, item):
    """중량축 kids 맵 (nx.bom_line·sagub·RAC포함), 부모 upper 키. 공유 트리 소스."""
    import nx_soyo_engine as _se
    kids = {}

    def build(node):
        u = node.strip().upper()
        if u in kids:
            return
        ch = _se._cs_lines_wt(eng, node)   # [(child, qty, sagub)]
        kids[u] = ch
        for c, q, s in ch:
            build(c)
    build(item)
    return kids


def weight_explode_ex(eng, item):
    """[중량 walker · explode 공유형] — nx_soyo_engine.weight_explode 와 diff0 대상.
    공유 kids_wt 순회. sagub_default=1 제외·COOP_SET/COOPB 폴백·geom leaf. (raw_kg, weld_kg)."""
    import nx_soyo_engine as _se
    COOP_SET, COOPB = _se._wt_coop(eng)
    kids = explode_wt(eng, item)
    memo = {}

    def walk(node):
        u = node.strip().upper()
        if u in memo:
            return memo[u]
        memo[u] = (0.0, 0.0)
        ch = kids.get(u, [])
        if ch:
            rk = wk = 0.0
            for c, q, sag in ch:
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


# ===================== ★통합 explode (생산+중량 단일 nx.bom_line raw) =====================
# 생산·중량 둘 다 nx.bom_line raw → 하나의 explode_bomline으로 통합(전 컬럼 1회 읽기·캐시).
# 원가는 RAC→proc_weld 차이(eng.lines)로 별도 유지. upper 키 일관.
def _lines_bl(eng, item):
    """통합 nx.bom_line raw 직상위 [(child_u, qty, qty_pr, except'0/1', sagub int)]. RAC포함·1회캐시."""
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


def prod_soyo_ex2(eng, item):
    """생산 walker(통합 explode_bomline) — qty_pr·except_flag. prod_soyo와 diff0 대상."""
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


def weight_explode_ex2(eng, item):
    """중량 walker(통합 explode_bomline) — qty·sagub_default. weight_explode와 diff0 대상."""
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
