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
