# -*- coding: utf-8 -*-
"""통일 소요 엔진 (SOYO ENGINE UNIFY) — 1회 전개 + 모드별 walker.

설계 정본: _schema/SOYO_ENGINE_UNIFY_DESIGN.md. 원칙: 정확도 최우선, 각 walker는 현행과 diff0.
1차 = nx.bom_line 위에서(현행 diff0 보존, 데이터층=NxCostEngine 프리미티브 공유), 클린(nx.bom 정규SUB)은 후속.

핵심: explode()가 전 BOM 트리를 1회 전개(전 노드 태깅) → 모드 walker가 자기 정지/필터/집계 적용.
소비자: 내부원가·실원가 R01~Rnn·중량정산·용접봉수불·자재소요/매입검증·OSP비교·발주·실제손익.
"""


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
    if not hasattr(eng, '_incc'):
        eng._incc = {}
    if code not in eng._incc:
        eng.cur.execute("SELECT ISNULL(in_cust,'') FROM nx.item WHERE item_code=?", code)
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
