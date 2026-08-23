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
