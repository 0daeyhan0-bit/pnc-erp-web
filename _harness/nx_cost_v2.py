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


_FB_CACHE = {}   # asof_ym(YYMM) -> {code: (price, spread)}  단가 fallback 맵


def build_fallback_map(cur, asof_ym):
    """단가 fallback 맵(§8): {code: price}. 우선순위 ②실매입(tag9 any cust 가중평균) > ③마스터 최신 tag='1'(any cust).
    in_cust 빈값/불일치·except_flag로 마스터 in_cust 조회가 0일 때 이걸로 우회. as-of(월)·캐시."""
    asof_ym = str(asof_ym)[:4] or '2608'
    if asof_ym in _FB_CACHE:
        return _FB_CACHE[asof_ym]
    m = {}
    # ③ 마스터 최신 tag='1'(cust 무관) — base로 깔고 ②로 덮음
    try:
        cur.execute("""SELECT it, item_cost FROM (
            SELECT LTRIM(RTRIM(item_code)) it, item_cost,
                   ROW_NUMBER() OVER(PARTITION BY LTRIM(RTRIM(item_code)) ORDER BY ISNULL(cost_apply_ymd,'') DESC) rn
            FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM_COST
            WHERE cost_tag='1' AND CONVERT(float,ISNULL(item_cost,0))>0 AND ISNULL(cost_apply_ymd,'')<=?
        ) t WHERE rn=1""", asof_ym + '32')
        for it, p in cur.fetchall():
            if p and float(p) > 0:
                m[str(it).strip()] = float(p)
    except Exception:
        pass
    # ② 실매입(tag9, any cust, 가중평균) — 우선(덮어씀)
    try:
        cur.execute("""SELECT mat_code,
            SUM(CONVERT(float,maint_cost)*CONVERT(float,maint_qty))/NULLIF(SUM(CONVERT(float,maint_qty)),0)
          FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT
          WHERE maint_tag='9' AND maint_ymd>='2601' AND maint_ymd<=?
            AND CONVERT(float,ISNULL(maint_cost,0))>0 AND CONVERT(float,ISNULL(maint_qty,0))>0
          GROUP BY mat_code""", asof_ym + '32')
        for mc, p in cur.fetchall():
            if p and float(p) > 0:
                m[str(mc).strip()] = float(p)
    except Exception:
        pass
    _FB_CACHE[asof_ym] = m
    return m


def patch_leaf(eng, rbmap, fbmap=None):
    """eng._leaf_val 인스턴스 패치: ①직거래 원소재→실매입가(단위인식) ②단가결손 fallback(§8, 조용한 0 방지). 원본 보존."""
    if fbmap is None:
        try:
            fbmap = build_fallback_map(eng.cur, '2608')
        except Exception:
            fbmap = {}
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
        base = orig(node, info, q, ymd, ymcut)
        # ★단가 결손 fallback(§8): 매입 leaf(구매)인데 base=0(in_cust 빈값/불일치·except_flag) → 조용한 0 방지.
        #   ②실매입/③마스터 최신(fbmap) → ④원소재=소재단가 / 전개제외=0(정당). 원소재(inner cg3)는 엔진 소재단가라 대상 아님.
        if base == 0 and not eng._inner_prod(info) and info.get('cost_gubun', '') != '5':
            fb = float(fbmap.get(node, 0.0) or 0.0)
            if fb > 0:
                return round(fb * q, 2)                              # ②/③ 실매입·마스터 (매입단위 per-unit × qty)
            metal = str(info.get('metal', '')).strip()
            if metal:                                                # ④ 원소재 → 소재단가(사급가, per kg × 중량)
                sp = eng.std_metal_price(info['metal'], info['diam'], info['thick'], ymcut)
                if sp > 0:
                    return round(sp * info['wt'] * q, 2)
        return base

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
        fb = build_fallback_map(e2.cur, ymd[:4])
        patch_leaf(e2, rb, fb)
        patch_recovery(e2, recovery)   # ★가공비 회수율(효율) 곱셈. 기본 100=no-op.
        v2 = e2.silwon(item, ymd)
    finally:
        e2.close()
    return {
        "v1": v1, "v2": v2,
        "delta": round(float(v2["silwon"]) - float(v1["silwon"]), 2),
        "sonik_delta": round(float(v2["sonik"]) - float(v1["sonik"]), 2),
    }
