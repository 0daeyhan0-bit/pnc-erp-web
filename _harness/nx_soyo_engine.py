# -*- coding: utf-8 -*-
"""통일 소요 엔진 (SOYO ENGINE UNIFY) — 1회 전개 + 모드별 walker.

설계 정본: _schema/SOYO_ENGINE_UNIFY_DESIGN.md. 원칙: 정확도 최우선, 각 walker는 현행과 diff0.
1차 = nx.bom_line 위에서(현행 diff0 보존, 데이터층=NxCostEngine 프리미티브 공유), 클린(nx.bom 정규SUB)은 후속.

핵심: explode()가 전 BOM 트리를 1회 전개(전 노드 태깅) → 모드 walker가 자기 정지/필터/집계 적용.
소비자: 내부원가·실원가 R01~Rnn·중량정산·용접봉수불·자재소요/매입검증·OSP비교·발주·실제손익.
"""
import math


def explode(eng, item, ymd):
    """전 BOM 트리 전개. eng=NxCostEngine(데이터층 공유: lines()/_load_item, 용접봉 proc_weld 이미 주입).
    cs_calc_except=1 자식은 원가축 트리에서 제외(현행 원가엔진과 동일). cycle 방지 seen.
    반환: 노드 dict 리스트 — {level,parent,child,unit_qty,cum_qty,cs_calc_except,lme_except,info}.
    info = eng._load_item(child) (cost_gubun/make_type/metal/wt/unit/sgroup/in_cust ...).
    """
    nodes = []
    hasbom = eng._load_hasbom()

    def walk(node, cum_q, lvl, parent, uq, seen):
        info = eng._load_item(node)
        nodes.append({
            'level': lvl, 'parent': parent, 'child': node,
            'unit_qty': uq, 'cum_qty': cum_q, 'info': info,
        })
        if node in hasbom and node not in seen:
            for c, qty, cx, f, t, lx in eng.lines(node):
                nodes_cx = bool(cx)
                if nodes_cx:
                    continue  # cs_calc_except=1 자식 = 원가 노드 아님(생산 walker는 except_flag 별도 트리)
                walk(c, cum_q * qty, lvl + 1, node, qty, seen | {node})

    walk(item, 1.0, 0, '', 1.0, set())
    return nodes


def cost_material(eng, item, ymd):
    """[원가 walker] 실원가 재료비 — explode 트리에 원가 규칙 적용.
    현행 nx_cost_engine.material()과 diff0 대상: INNER_PROD=0/cg5 정지, cg3fix(제작SUB cg3도 전개),
    leaf=_leaf_val(소재단가×중량 or 매입가), + LME(전서브트리 lme_total).
    ※1차 구현은 엔진 material() 로직을 트리 위에서 재현. 검증 통과 후 엔진이 이걸 호출하도록 전환.
    """
    ymcut = '20' + ymd[:4]

    def value(node, q, seen):
        info = eng._load_item(node)
        # 전개 조건(엔진 _value_node와 동일): (cg!=3 or make=1) & _expandable
        expandable = (info['cost_gubun'] != '3' or info['make_type'] == '1') and _expandable(eng, node, info, seen)
        if expandable:
            tot = 0.0
            for c, qty, cx, f, t, lx in eng.lines(node):
                if cx:
                    continue
                tot += value(c, qty * q, seen | {node})
            return tot
        return eng._leaf_val(node, info, q, ymd, ymcut)

    base = value(item, 1.0, set())
    return round(base + eng.lme_u(item, ymd), 2)


def _expandable(eng, node, info, seen):
    """엔진 _expandable 재현: 사내생산(INNER=1) & 직납(5) 아님 & cs_calc_except=0 자식 존재."""
    if not eng._inner_prod(info) or info['cost_gubun'] == '5':
        return None
    if node not in eng._load_hasbom() or node in seen:
        return None
    kids = [l for l in eng.lines(node) if not l[2]]
    return kids or None


def cost_material_nae(eng, item, ymd):
    """[내부원가 walker] 전공정 자체 가정 — INNER_PROD 무관 전개(매입/외주도 뚫음), LME 없음.
    현행 nx_cost_engine.material_nae()와 diff0 대상. explode()가 이미 full 깊이라 지원.
    엔진 _value_node_nae 재현: cg!=3 & _expandable_nae면 전개, else _leaf_val_nae."""
    ymcut = '20' + ymd[:4]

    def value(node, q, seen):
        info = eng._load_item(node)
        if info['cost_gubun'] != '3' and eng._expandable_nae(node, seen):
            return sum(value(c, qty * q, seen | {node}) for c, qty, cx, f, t, lx in eng.lines(node) if not cx)
        return eng._leaf_val_nae(node, info, q, ymd, ymcut)

    return round(value(item, 1.0, set()), 2)


# ============================ 생산 소요 walker ============================
# soyo STEP5~7(nx.v_pr_bom, except_flag)의 BOM 전개를 explode 트리 위에서 재현.
# 정지=사급/최하위, 필터=except_flag(생산·PR축), 용접봉(RAC)=자재소요 제외.
# ★1차=per-unit BOM 전개 정합(v_pr_bom 재귀와 diff0). 계획통합(STEP5/6 시드·plan_part_mat)은 후속.

def _vpr_lines(eng, item):
    """nx.v_pr_bom 직상위 자식 + 플래그(생산축). 반환 [(child, qty, except_flag)].
    소요 정본 소스=nx.v_pr_bom(=nx.bom_line 위 생산 호환뷰, USE_QTY_PR·except_flag). RAC(용접봉) 포함(walker가 제외)."""
    if not hasattr(eng, '_vprc'):
        eng._vprc = {}
    if item not in eng._vprc:
        eng.cur.execute("""SELECT UPPER(LTRIM(RTRIM(mat_code))), ISNULL(USE_QTY_PR, USE_QTY), ISNULL(except_flag,'0')
            FROM nx.v_pr_bom WHERE UPPER(LTRIM(RTRIM(item_code)))=? ORDER BY BOM_SEQ""", item.strip().upper())
        eng._vprc[item] = [(str(r[0]).strip(), float(r[1] or 0), str(r[2]).strip()) for r in eng.cur.fetchall()]
    return eng._vprc[item]


def prod_soyo(eng, item):
    """[생산 walker] per-unit 자재소요 {mat_code: qty}. except_flag=1 제외, 최하위집계, 용접봉(RAC) 제외.
    STEP7 규칙: 자식 있으면 전개(제작SUB 관통), 최하위 leaf만 집계, 같은 mat_code는 가장 깊은 레벨."""
    hasvpr = _has_vpr(eng)
    raw = {}   # mat_code -> list of (level, qty)
    def walk(node, cum_q, lvl, seen):
        kids = _vpr_lines(eng, node) if (node in hasvpr and node not in seen) else []
        kids = [(c, q, ex) for (c, q, ex) in kids if ex != '1']   # except_flag 제외
        if kids:
            for c, q, ex in kids:
                walk(c, cum_q * q, lvl + 1, seen | {node})
        # 최하위(자식 없음) = leaf 소요
        if not kids and lvl > 0:
            raw.setdefault(node, []).append((lvl, cum_q))
    walk(item, 1.0, 0, set())
    # 최하위 집계: 같은 mat_code 여러 경로면 합산(STEP7 SUM). 용접봉(RAC 접두, 용접링 제외)은 소요 제외.
    out = {}
    for mc, occ in raw.items():
        if _is_weldrod(eng, mc):
            continue
        out[mc] = round(sum(q for _, q in occ), 6)
    return out


# ===================== 생산계획 walker (STEP6/7 재현) =====================
# plan_part_mat = 가공공정 전이 grain. Stage1=plan_part_temp(CTE_BOM), Stage2=가공공정JOIN, Stage3=전이+최하위.

def _prmmat_set(eng):
    if not hasattr(eng, '_prmmat'):
        eng.cur.execute("SELECT UPPER(LTRIM(RTRIM(mat_code))) FROM nx.PR_M_MAT")
        eng._prmmat = set(r[0].strip() for r in eng.cur.fetchall())
    return eng._prmmat


def _vpr_full(eng, item):
    """v_pr_bom 직상위 자식 (mat_code, USE_QTY_PR, except_flag, vir_item_flag). 캐시."""
    if not hasattr(eng, '_vprf'):
        eng._vprf = {}
    k = item.strip().upper()
    if k not in eng._vprf:
        eng.cur.execute("""SELECT UPPER(LTRIM(RTRIM(mat_code))), ISNULL(USE_QTY_PR,USE_QTY), ISNULL(except_flag,'0'), ISNULL(vir_item_flag,'0')
            FROM nx.v_pr_bom WHERE UPPER(LTRIM(RTRIM(item_code)))=? ORDER BY BOM_SEQ""", k)
        eng._vprf[k] = [(str(r[0]).strip(), float(r[1] or 0), str(r[2]).strip(), str(r[3]).strip()) for r in eng.cur.fetchall()]
    return eng._vprf[k]


def plan_explode(eng, item):
    """[생산계획 stage1] STEP6 CTE_BOM 재현 → plan_part_temp(per-unit).
    v_pr_bom 재귀, except_flag≠1, level<10, PR_M_MAT 경계(추가는 하되 재귀 정지). vir_item 추적.
    반환 dict {mat_code: cum_use_qty 합} (레벨별 SUM 후 mat_code 집계 = plan_part_temp GROUP BY 대응)."""
    inmat = _prmmat_set(eng)
    agg = {}   # (level, mat_code) -> cum
    def walk(mat, cum, lvl, seen):
        agg[(lvl, mat)] = agg.get((lvl, mat), 0.0) + cum
        if lvl >= 10 or mat in inmat or mat in seen:
            return
        for c, q, ex, vf in _vpr_full(eng, mat):
            if ex == '1':
                continue
            walk(c, cum * q, lvl + 1, seen | {mat})
    walk(item, 1.0, 0, set())
    # plan_part_temp는 (level, item_code, mat_code) GROUP BY SUM(cum_use_qty). 여기선 (level, mat) 집계로 대조.
    out = {}
    for (lvl, mat), cum in agg.items():
        out[(lvl, mat)] = round(cum, 5)
    return out


def plan_explode_full(eng, item):
    """[생산계획] STEP6 CTE_BOM 노드 상세 재현 → plan_part_temp 그레인 (level, item_code=parent, mat_code=child).
    반환 dict {(level, parent, child): {'cum','vir','inc'}} — GROUP BY 대응(SUM cum, MAX vir, in_cust)."""
    inmat = _prmmat_set(eng)
    agg = {}
    def walk(mat, cum, lvl, parent, vir, inc, seen):
        k = (lvl, parent, mat)
        e = agg.get(k)
        if e is None:
            agg[k] = {'cum': cum, 'vir': vir, 'inc': inc}
        else:
            e['cum'] += cum
        if lvl >= 10 or mat in inmat or mat in seen:
            return
        for c, q, ex, vf in _vpr_full(eng, mat):
            if ex == '1':
                continue
            # plan_part_temp/gagong의 item_code = 직접 부모(mat). vir 로직은 p_item_code(별도컬럼)용이라 이 그레인엔 무영향.
            walk(c, cum * q, lvl + 1, mat, vf, _incust(eng, c), seen | {mat})
    walk(item, 1.0, 0, item, '0', _incust(eng, item), set())
    return agg


def _incust(eng, code):
    # ★소스=nx.PR_M_ITEM.in_cust_code (STEP6 CTE_BOM와 동일). nx.item.in_cust는 dbo값(2068 등)이라 갈림 → 561전수 FAIL2 원인이었음.
    if not hasattr(eng, '_incc'):
        eng._incc = {}
    if code not in eng._incc:
        eng.cur.execute("SELECT ISNULL(in_cust_code,'') FROM nx.PR_M_ITEM WHERE item_code=?", code)
        r = eng.cur.fetchone()
        eng._incc[code] = (str(r[0]).strip() if r else '')
    return eng._incc[code]


def _has_gagong(eng, code):
    """가공공정 보유(PR_M_ITEM_PROC_GAGONG). plan_part_gagong JOIN 조건."""
    if not hasattr(eng, '_gag'):
        eng.cur.execute("SELECT DISTINCT UPPER(LTRIM(RTRIM(item_code))) FROM nx.PR_M_ITEM_PROC_GAGONG")
        eng._gag = set(r[0].strip() for r in eng.cur.fetchall())
    return code.upper() in eng._gag


def plan_gagong(eng, item):
    """[생산계획 Stage2] plan_part_gagong 재현: plan_part_temp 노드 중 가공공정 보유 & vir='0' & in_cust∈('','2228').
    반환 dict {(level, parent, mat): cum}."""
    full = plan_explode_full(eng, item)
    out = {}
    for (lvl, parent, mat), e in full.items():
        if e['vir'] == '0' and e['inc'] in ('', '2228') and _has_gagong(eng, mat):
            out[(lvl, parent, mat)] = round(e['cum'], 5)
    return out


def _has_vpr(eng):
    if not hasattr(eng, '_hasvpr'):
        eng.cur.execute("SELECT DISTINCT UPPER(LTRIM(RTRIM(item_code))) FROM nx.v_pr_bom")
        eng._hasvpr = set(r[0].strip() for r in eng.cur.fetchall())
    return eng._hasvpr


def _is_weldrod(eng, code):
    """용접봉(RAC 접두, 단 용접링은 자재유지) = 자재소요 제외(공정처리). STEP7 정본 규칙."""
    if not code.upper().startswith('RAC'):
        return False
    if not hasattr(eng, '_weldrod'):
        eng._weldrod = {}
    if code not in eng._weldrod:
        eng.cur.execute("SELECT ISNULL(item_name,'') FROM nx.item WHERE item_code=?", code)
        r = eng.cur.fetchone()
        nm = (str(r[0]) if r else '')
        eng._weldrod[code] = ('용접링' not in nm)   # 용접링 아니면 용접봉→제외
    return eng._weldrod[code]


# ========================= 중량 walker (=weight_calc._explode 재현) =========================
# ★소스 등가 검증(2026-08-23): nx.bom_line 엣지 ≡ v_cs_bom(멤버·qty·sagub_default 0차), nx.item leaf ≡ PR_M_ITEM(동중량 0차).
#   → weight_calc(v_cs_bom+PR_M_ITEM)를 통일엔진 트리(nx.bom_line+nx.item)로 diff0 재현 가능.
#   같은 BOM 다른 필터: 원가=cs_calc_except / 중량=SAGUB(sagub_default=1 업체가공 제외). RAC 포함(폴백조건 raw==0 AND weld==0 보존).
_WT_COPPER = {'CU', '고강도'}


def _wt_meta(eng, code):
    """중량 leaf META: (w, cls). raw=동(ITEM_WEIGHT 우선 else geom π(D−T)T·L·8.94/1e6), weld=용접봉, None. weight_calc _load_maps 재현.
    ★소스=nx.PR_M_ITEM(중량 정본). nx.item은 일부품목 net_weight=geom·length 드리프트(3H00627M 0.3332→0.2907 등) → PR_M_ITEM 직독으로 diff0."""
    if not hasattr(eng, '_wtm'):
        eng._wtm = {}
    u = code.strip().upper()
    if u not in eng._wtm:
        eng.cur.execute("""SELECT ISNULL(ITEM_WEIGHT,0),ISNULL(ITEM_DIAM,0),ISNULL(ITEM_THICK,0),ISNULL(ITEM_LENGTH,0),
            ISNULL(METAL_GUBUN,''),ISNULL(ITEM_DESC,'') FROM nx.PR_M_ITEM WHERE ITEM_CODE=?""", code)
        r = eng.cur.fetchone()
        w = 0.0
        cls = None
        if r:
            mg = str(r[4]).strip()
            nm = str(r[5])
            if mg in _WT_COPPER:
                cls = 'raw'
                iw = float(r[0] or 0)
                if iw > 0:
                    w = iw
                else:
                    d, t, L = float(r[1] or 0), float(r[2] or 0), float(r[3] or 0)
                    if d > 0 and t > 0 and L > 0:
                        w = math.pi * (d - t) * t * L * 8.94 / 1e6
            elif '용접봉' in nm:
                cls = 'weld'
        eng._wtm[u] = (w, cls)
    return eng._wtm[u]


def _cs_lines_wt(eng, item):
    """중량축 BOM 엣지 (child, qty, sagub) = nx.bom_line (★RAC 포함=weight_calc CH 등가, sagub_default 유지)."""
    if not hasattr(eng, '_cslw'):
        eng._cslw = {}
    u = item.strip().upper()
    if u not in eng._cslw:
        bid = eng.bom_id(item)
        if bid is None:
            eng._cslw[u] = []
        else:
            eng.cur.execute("SELECT child_item,qty,ISNULL(sagub_default,0) FROM nx.bom_line WHERE bom_id=? ORDER BY seq", bid)
            eng._cslw[u] = [(str(r[0]).strip(), float(r[1] or 0), int(r[2])) for r in eng.cur.fetchall()]
    return eng._cslw[u]


def _wt_coop(eng):
    """협력사 정산기준: coop_raw_spec(COOP_SET 리프=자기중량 override) + coop_bom(CS전개결손 폴백). weight_calc와 동일 소스."""
    if hasattr(eng, '_wtcoop'):
        return eng._wtcoop
    cs = {}
    cb = {}
    try:
        eng.cur.execute("SELECT item_code, unit_weight FROM nx.coop_raw_spec WHERE unit_weight IS NOT NULL AND unit_weight>0")
        for ic, uw in eng.cur.fetchall():
            cs[str(ic).strip().upper()] = float(uw)
    except Exception:
        pass
    try:
        eng.cur.execute("SELECT parent, child, use_qty FROM nx.coop_bom")
        for p, c, u in eng.cur.fetchall():
            cb.setdefault(str(p).strip().upper(), []).append((str(c).strip().upper(), float(u or 1)))
    except Exception:
        pass
    eng._wtcoop = (cs, cb)
    return eng._wtcoop


def weight_explode(eng, item):
    """[중량 walker] 1개 → (raw_kg, weld_kg): 업체가공(sagub_default≠1) 경로의 동/용접봉 중량. weight_calc._explode 완전재현.
    COOP_SET(coop_raw_spec) 리프=자기중량(하위 사급 전개 안함)·CS전개0이면 coop_bom 폴백. raw_kg=협력사 동 중량정산 소요 정본."""
    COOP_SET, COOPB = _wt_coop(eng)
    memo = {}

    def walk(node):
        u = node.strip().upper()
        if u in memo:
            return memo[u]
        memo[u] = (0.0, 0.0)   # cycle guard
        ch = _cs_lines_wt(eng, node)
        if ch:
            rk = wk = 0.0
            for c, q, sag in ch:
                if sag == 1:      # 사급(업체에 우리가 공급) 제외 — 업체가공만 인정
                    continue
                cr, cw = walk(c)
                rk += cr * q
                wk += cw * q
            if rk > 0 or wk > 0:
                memo[u] = (rk, wk)
                return memo[u]
            # 전개 0(자식 전부 사급/비동) → coop 단품이면 자기중량, 아니면 협력사BOM 폴백
            if u in COOP_SET:
                memo[u] = (COOP_SET[u], 0.0)
                return memo[u]
            cb = COOPB.get(u)
            if cb:
                rk = wk = 0.0
                for c, q in cb:
                    cr, cw = walk(c)
                    rk += cr * q
                    wk += cw * q
                memo[u] = (rk, wk)
                return memo[u]
            return memo[u]        # (0,0)
        # CS 자식 없음 = 리프
        cb = COOPB.get(u)
        if cb and u not in COOP_SET:
            rk = wk = 0.0
            for c, q in cb:
                cr, cw = walk(c)
                rk += cr * q
                wk += cw * q
            memo[u] = (rk, wk)
            return memo[u]
        if u in COOP_SET:
            memo[u] = (COOP_SET[u], 0.0)
            return memo[u]
        w, cls = _wt_meta(eng, node)
        memo[u] = (w, 0.0) if cls == 'raw' else ((0.0, w) if cls == 'weld' else (0.0, 0.0))
        return memo[u]

    rk, wk = walk(item)
    return (round(rk, 6), round(wk, 6))


def _wt_spec(eng, code):
    """중량 leaf 규격 (metal_gubun, diam, thick) — 절삭재료비(CS_M_METERIAL_COST) 규격별 단가 조회용. 캐시."""
    if not hasattr(eng, '_wtspec'):
        eng._wtspec = {}
    u = code.strip().upper()
    if u not in eng._wtspec:
        eng.cur.execute("SELECT ISNULL(METAL_GUBUN,''),ISNULL(ITEM_DIAM,0),ISNULL(ITEM_THICK,0) FROM nx.PR_M_ITEM WHERE ITEM_CODE=?", code)
        r = eng.cur.fetchone()
        eng._wtspec[u] = (str(r[0]).strip(), float(r[1] or 0), float(r[2] or 0)) if r else ('', 0.0, 0.0)
    return eng._wtspec[u]


def copper_by_spec(eng, item):
    """[중량 walker·규격분해] 완제품 1개 → {(metal,diam,thick): 동중량kg}. weight_explode와 동일 walk(사급 sag=1 제외)이나
    규격별로 분해(절삭재료비 규격별 단가 곱하기용). ★coop 폴백 미적용 = 순수 BOM 동관 leaf(규격 있는 것만·단가매칭용)."""
    memo = {}

    def walk(node):
        u = node.strip().upper()
        if u in memo:
            return memo[u]
        memo[u] = {}   # cycle guard
        ch = _cs_lines_wt(eng, node)
        if ch:
            acc = {}
            for c, q, sag in ch:
                if sag == 1:
                    continue
                for spec, w in walk(c).items():
                    acc[spec] = acc.get(spec, 0.0) + w * q
            memo[u] = acc
            return acc
        w, cls = _wt_meta(eng, node)
        if cls == 'raw' and w > 0:
            memo[u] = {_wt_spec(eng, node): w}
        return memo[u]

    return walk(item)


# ========================= 용접봉 소요 (geom/원가/재고 트랙, =weight_calc._load_weld 재현) =========================
# 용접봉 소요(CS_T_ITEM_WELD.ITEM_USE_QTY 관경별 × 1.5, 품목별 flat) = ★원가/재고소비 트랙 primitive. 15/15검증(레거시 w_cs_esti ×1.5룰).
#   ★주의: 협력사 "수불정산"의 용접봉 소요 정본은 이게 아님 — **협력사 견적서 기준**(coop_quote_part_v2 ptype_v2='용접봉' soyo, compute_quote).
#   3트랙 구분: ①견적서=협력사 수불정산 정본 ②CS_T_ITEM_WELD×1.5=원가/재고 ③proc_weld(용접ST×원단위×1.5)=사내 재고차감.
def _weld_soyo_map(eng):
    if hasattr(eng, '_wsm'):
        return eng._wsm
    eng.cur.execute("SELECT UPPER(LTRIM(RTRIM(P_ITEM_CODE))), ISNULL(SUM(CAST(ITEM_USE_QTY AS float)),0) FROM nx.CS_T_ITEM_WELD GROUP BY P_ITEM_CODE")
    eng._wsm = {str(r[0]).strip(): round(float(r[1] or 0) * 1.5, 4) for r in eng.cur.fetchall()}
    return eng._wsm


def weld_soyo(eng, item):
    """[원가 용접봉 소요] 품목 1개당 용접봉 소요량 = Σ(CS_T_ITEM_WELD.ITEM_USE_QTY) × 1.5. flat(입고품번 직접).
    ★원가 계산식의 용접봉 소요(1.5배). 협력사 수불정산(원소재+용접봉)은 별개=견적서 기준. weight_calc._load_weld diff0(3588/3588)."""
    return _weld_soyo_map(eng).get(item.strip().upper(), 0.0)
