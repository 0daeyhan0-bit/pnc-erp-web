# -*- coding: utf-8 -*-
"""품목별 원가분석 V2 — 직거래 원소재 실매입가 override 래퍼.

엔진(NxCostEngine) 원본 무변경. `_leaf_val` 인스턴스 패치로 직거래 원소재 leaf 단가를
직구매 실매입가로 대체 → 엔진 롤업이 일반관리비·이윤 전파(ilban=율91×(재료+가공),
profit=율93×(가공+일반))를 자동 반영하므로 정확.

검증·규칙 정본: _schema/COSTANALYSIS_V2_DESIGN.md §5A~§6P.
규칙:
 - 직거래 원소재 = 직구매(사급vendor 2237/2238·CUST_TYPE=1 제외) tag9 매입 실매입가 존재 노드.
 - 단위인식 override: 매입=jik×qty · 원소재(cg3)KG=jik×중량×qty · 원소재(cg3)EA=jik×qty.
 - spread guard: maint hi/lo>3 → 스킵(엔진값 유지, fallback §5F).
 - 사급 원소재(직구매 매입 없음)=엔진값(사급가) 유지 → 사급품 V2=V1(diff0).
"""

SPREAD_GUARD = 3.0
_MAP_CACHE = {}   # asof_ym(YYMM) -> {mat_code: (jik_wavg, spread=hi/lo)}


def _sagub_vendors(cur):
    """사급 거래처 집합 = mgmt_vendor_gubun('사급') ∪ CM_M_CUST.cust_type='1'(유상사급·LG)."""
    cur.execute("SELECT cust_code FROM nx.mgmt_vendor_gubun WHERE override_gubun LIKE N'%사급%'")
    s = set(str(r[0]).strip() for r in cur.fetchall())
    cur.execute("SELECT cust_code FROM nx.CM_M_CUST WHERE cust_type='1'")
    s |= set(str(r[0]).strip() for r in cur.fetchall())
    return s


def build_realbuy_map(cur, asof_ym):
    """직구매 실매입가 맵(as-of 월 누적, tag9 매입, 사급vendor 제외 가중평균).
    반환 {mat_code: (jik_wavg, spread=hi/lo)}. 캐시(월별)."""
    asof_ym = str(asof_ym)[:4] or '2608'
    if asof_ym in _MAP_CACHE:
        return _MAP_CACHE[asof_ym]
    sag = _sagub_vendors(cur)
    sl = "','".join(sag)
    cur.execute(f"""SELECT mat_code,
        SUM(CASE WHEN cust_code NOT IN ('{sl}') THEN CONVERT(float,maint_cost)*CONVERT(float,maint_qty) END)
          /NULLIF(SUM(CASE WHEN cust_code NOT IN ('{sl}') THEN CONVERT(float,maint_qty) END),0),
        MIN(CASE WHEN cust_code NOT IN ('{sl}') THEN CONVERT(float,maint_cost) END),
        MAX(CASE WHEN cust_code NOT IN ('{sl}') THEN CONVERT(float,maint_cost) END)
      FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT
      WHERE maint_tag='9' AND maint_ymd>='2601' AND maint_ymd<=?
        AND CONVERT(float,ISNULL(maint_cost,0))>0 AND CONVERT(float,ISNULL(maint_qty,0))>0
      GROUP BY mat_code""", asof_ym + '32')
    m = {}
    for mat, jik, lo, hi in cur.fetchall():
        mat = str(mat).strip()
        if jik and float(jik) > 0:
            spread = (float(hi) / float(lo)) if (lo and float(lo) > 0) else 999.0
            m[mat] = (float(jik), spread)
    _MAP_CACHE[asof_ym] = m
    return m


def patch_leaf(eng, rbmap):
    """eng._leaf_val 인스턴스 패치: 직거래 원소재 reliable leaf → 실매입가(단위인식). 원본 함수 보존."""
    orig = eng._leaf_val

    def v2_leaf(node, info, q, ymd, ymcut):
        ent = rbmap.get(node)
        # ★원소재 한정 필터(2026-08-22): SUB/조립품은 metal_gubun 빈값·용접봉(910)/사급(310) 제외.
        #   tag9 매입이력만으론 SUB(AJR*-N-M)·용접봉도 걸려 orig=0을 실매입가로 오적재(+42000 사고). 원소재(metal채움)만 override.
        if (ent and ent[1] <= SPREAD_GUARD and ent[0] > 0
                and str(info.get('metal', '')).strip() != ''
                and str(info.get('sgroup', '')).strip() not in ('910', '310')):
            jik = ent[0]
            inner = eng._inner_prod(info)
            if inner and info.get('cost_gubun', '') == '3':          # 원소재(소재단가 계상)
                if str(info.get('unit', '')).strip() == 'KG':
                    return round(jik * info['wt'] * q, 2)            # jik=kg당
                return round(jik * q, 2)                             # jik=EA당
            if not inner:                                            # 매입(구매단가 계상)
                return round(jik * q, 2)
        return orig(node, info, q, ymd, ymcut)

    eng._leaf_val = v2_leaf
    return eng


def patch_recovery(eng, recovery_pct):
    """★가공비 ST 회수율(효율) 반영 — 하드코딩 아님, 곱셈 로직.
    실 가공비 = 표준가공비 × (100/효율). 효율<100이면 가공비 gross-up(일반관리비·이윤도 엔진 롤업으로 전파).
    현재=화면 입력값(전역). 추후=라인별(nx.item.prod_line × nx.line_efficiency, 생산실적 기반). 정본 §7A.
    효율 100(또는 무효값)이면 no-op(V2 가공비=V1)."""
    try:
        rp = float(recovery_pct)
    except (TypeError, ValueError):
        return eng
    if rp <= 0 or abs(rp - 100.0) < 1e-9:
        return eng
    k = 100.0 / rp
    orig = eng.gagong_u
    def g2(item, ymd, parent):
        return orig(item, ymd, parent) * k
    eng.gagong_u = g2
    return eng


def cost_v2(item, ymd, v1_engine=None, engine_factory=None, recovery=100):
    """V1(엔진 그대로) + V2(직거래 원소재 실매입 override) 실원가·손익 산출.

    v1_engine: 기존(공유) 엔진 재사용(V1용, 읽기만). 없으면 새로 생성.
    engine_factory: NxCostEngine 생성자(V2 전용 격리 인스턴스 — 패치가 V1 오염 안 하게).
    반환: {v1, v2, delta(실원가), sonik_delta}
    """
    item = item.strip(); ymd = ymd.strip()
    if engine_factory is None:
        from nx_cost_engine import NxCostEngine
        engine_factory = NxCostEngine
    # V1 (공유엔진 있으면 재사용)
    if v1_engine is not None:
        v1 = v1_engine.silwon(item, ymd)
    else:
        e1 = engine_factory()
        try:
            v1 = e1.silwon(item, ymd)
        finally:
            e1.close()
    # V2 — 반드시 격리 인스턴스(패치)
    e2 = engine_factory()
    try:
        rb = build_realbuy_map(e2.cur, ymd[:4])
        patch_leaf(e2, rb)
        patch_recovery(e2, recovery)   # ★가공비 회수율(효율) 곱셈. 기본 100=no-op.
        v2 = e2.silwon(item, ymd)
    finally:
        e2.close()
    return {
        "v1": v1, "v2": v2,
        "delta": round(float(v2["silwon"]) - float(v1["silwon"]), 2),
        "sonik_delta": round(float(v2["sonik"]) - float(v1["sonik"]), 2),
    }
