# -*- coding: utf-8 -*-
"""소요 통일 Phase 0 — 검증 하네스 (SOYO_ENGINE_UNIFY §13-1).

목적: 각 모드 walker의 **현행(자기재귀) 출력 vs 신(explode-공유) 출력**을 diff0 비교.
Phase 1~4 모든 전환의 게이트 = 통과 못 하면 전환 금지·롤백.

원칙(이 세션 하드룰): 읽기전용·생산계획 미접촉·성급한 일반화 금지·검증기록.
스코프 = 사용중 BOM(리시빙/use_flag). baseline_fn/candidate_fn 둘 다 (eng, item, ymd)->출력.

사용:
    from nx_cost_engine import NxCostEngine
    import nx_soyo_engine as se, soyo_unify_verify as V
    eng=NxCostEngine(); items=V.scope(eng.cur, 30)
    r=V.verify('cost_material', lambda e,it,y: se.cost_material(e,it,y),
                                lambda e,it,y: se_new.cost_material(e,it,y), eng, items)
    print(r.summary())
"""


def scope(cur, n=30):
    """검증 스코프 = 사용중 완제품(bom_header ∩ use_flag=1, 변형SUB 제외) 결정적 분산 n개. 체리픽 금지."""
    cur.execute("""SELECT h.item_code
        FROM PARTNER_ERP_TEST3.nx.bom_header h
        JOIN PARTNER_ERP_TEST3.nx.item i ON i.item_code=h.item_code AND i.use_flag=1
        WHERE h.item_code NOT LIKE '%-%' ORDER BY h.item_code""")
    allitems = [str(r[0]).strip() for r in cur.fetchall()]
    if len(allitems) <= n:
        return allitems
    step = len(allitems) // n
    return [allitems[i * step] for i in range(n)]


def _flat(v):
    """출력을 {키:float} 로 정규화 — float/int·tuple/list·dict 모두 대응."""
    if v is None:
        return {'_none': 0.0}
    if isinstance(v, (int, float)):
        return {'_': float(v)}
    if isinstance(v, (tuple, list)):
        return {i: float(x) for i, x in enumerate(v) if isinstance(x, (int, float))}
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            if isinstance(x, (int, float)):
                out[str(k)] = float(x)
        return out
    return {'_repr': hash(repr(v)) % 1.0}


def _equal(a, b, tol):
    fa, fb = _flat(a), _flat(b)
    keys = set(fa) | set(fb)
    for k in keys:
        if abs(fa.get(k, 0.0) - fb.get(k, 0.0)) > tol:
            return False, k, fa.get(k, 0.0), fb.get(k, 0.0)
    return True, None, None, None


class Result:
    def __init__(self, mode):
        self.mode = mode; self.pas = 0; self.fail = 0; self.err = 0; self.fails = []
    def summary(self):
        v = 'PASS' if (self.fail == 0 and self.err == 0 and self.pas > 0) else 'FAIL'
        s = '[%s] %s : PASS=%d FAIL=%d ERR=%d' % (self.mode, v, self.pas, self.fail, self.err)
        for f in self.fails[:8]:
            s += '\n    %s' % str(f)
        return s
    @property
    def ok(self):
        return self.fail == 0 and self.err == 0 and self.pas > 0


def verify(mode, baseline_fn, candidate_fn, eng, items, ymd='260630', tol=0.01):
    """baseline vs candidate 를 items 전수 diff0 비교. Result 반환."""
    r = Result(mode)
    for it in items:
        try:
            a = baseline_fn(eng, it, ymd)
            b = candidate_fn(eng, it, ymd)
            eq, k, va, vb = _equal(a, b, tol)
            if eq:
                r.pas += 1
            else:
                r.fail += 1; r.fails.append((it, 'key=%s' % k, round(va, 4), round(vb, 4)))
        except Exception as e:
            r.err += 1; r.fails.append((it, 'ERR', str(e)[:60]))
    return r
