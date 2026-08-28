# -*- coding: utf-8 -*-
"""LG BOM 소요 엔진 (★별도 운영, 사용자 확정 2026-08-29).

우리 BOM 소요엔진(nx_soyo_engine)과 **별개 엔진** — LG BOM은 LG 전자의 별도 권위·구조(LG품번·Assembly Pull)라 별도로 둔다.
LG BOM(Assembly Pull) 동 원소재 소요를 **다단계 트리전개(롤업)** 로 산출. 여러 프로그램이 공유(LG사급현황 리시빙비교(동)·사급 정산·LME·원소재사급전환율 등).

★규칙(CLAUDE.md §1-10 / [[feedback-soyo-engine-only]]): LG BOM 소요는 이 엔진으로만. ad-hoc `nx.lg_bom` 직접 전개 금지.

전개 규칙(검증됨, LG_BOM_VERSION_SAGUB_SOYO_DESIGN.md §7):
- 동 원소재 = matkl='MJU0631'(Tube,Raw 전접두사 통합) · supply_type='Assembly Pull' · ALUMINUM 제외.
- **다단계 롤업**: 동이 L2(서브 밑)면 L1 서브 수량(EA)을 곱해 누적(구 flat합은 L1 수량 미곱=과소).
- **q=1.0 플레이스홀더 제외**(LG 데이터 노이즈 6모델, 정상 0.008~0.5인데 1.0).
- **werks 다중이면 전개합 MAX**(양공장 중복방지). point-in-time = model·werks별 ver_from<=ver_date 최신.
- 규격/재질 = nx.item 우선, 없으면 child_spec 파싱. root = model(STUFE1 부모=model).

함수:
  lg_ap_all(cur, ver_date, models=None)             → {model: {(metal,diam,thick): per_unit_kg}}  (전체 사급 동)
  lg_ap_split(cur, ver_date, models=None, jjset=None) → {model: {'our':{spec:kg}, 'coop':{spec:kg}}}
      분할 = 각 동의 부모(절단관)가 우리 제작동관(bom_flat role='제작동관')이면 '우리절삭', 아니면(사급SUB=협력사 절삭·우리 소재사급) '협력사사급'. 전체=우리+협력사(2중계상 0).
"""
import re as _re
from collections import defaultdict as _dd


def model_in_sql(models):
    """models(set/iterable) → ' AND UPPER(LTRIM(RTRIM(model))) IN (...)' 조각. 성능: 필요 모델만 전개.
       코드 안전문자(영숫자·-_)만 통과(인젝션 방지). 비면 빈문자."""
    if not models:
        return ""
    safe = [str(m).strip().upper() for m in models if m and all(c.isalnum() or c in '-_' for c in str(m).strip())]
    if not safe:
        return ""
    return " AND UPPER(LTRIM(RTRIM(model))) IN (" + ",".join("'" + m + "'" for m in safe) + ")"


def _key(spec, mg, idiam, ithick):
    """동 규격키 (metal, diam, thick). nx.item 값 우선, 없으면 child_spec의 P##/T## 파싱."""
    od = idiam if idiam > 0 else None
    thk = ithick if ithick > 0 else None
    if od is None:
        m = _re.search(r'P(\d+(?:\.\d+)?)', spec); od = float(m.group(1)) if m else 0.0
    if thk is None:
        m = _re.search(r'T(\d+(?:\.\d+)?)', spec); thk = float(m.group(1)) if m else 0.0
    metal = mg if mg else ('고강도' if '고강도' in spec else 'CU')
    return (metal, float(od), float(thk))


def _load_edges(cur, ver_date, models):
    """point-in-time LG BOM 엣지 로드 → {model: {werks: [(parent,child,matkl,sup,spec,qty,mg,diam,thick)]}}."""
    minl = model_in_sql(models)
    cur.execute(f"""
      WITH latest AS (
        SELECT model, ISNULL(werks,'') w, MAX(ver_from) mv
        FROM nx.lg_bom_ver WHERE ver_from<=? {minl} GROUP BY model, ISNULL(werks,''))
      SELECT UPPER(LTRIM(RTRIM(r.model))), ISNULL(r.werks,''),
             UPPER(LTRIM(RTRIM(r.parent_code))), UPPER(LTRIM(RTRIM(r.child_code))),
             r.matkl, LTRIM(RTRIM(ISNULL(r.supply_type,''))), ISNULL(r.child_spec,''), CONVERT(float,ISNULL(r.qty,0)),
             ISNULL(ic.metal_gubun,''), ISNULL(ic.diam,0), ISNULL(ic.thick,0)
      FROM nx.lg_bom_ver r
      JOIN latest l ON l.model=r.model AND l.w=ISNULL(r.werks,'') AND r.ver_from=l.mv
      LEFT JOIN nx.item ic ON UPPER(LTRIM(RTRIM(ic.item_code)))=UPPER(LTRIM(RTRIM(r.child_code)))
    """, ver_date)
    MW = _dd(lambda: _dd(list))
    for md, w, p, c, mk, sup, spec, q, mg, idiam, ithick in cur.fetchall():
        MW[md][w].append((p, c, mk, sup, spec, float(q or 0), (mg or '').strip(), float(idiam or 0), float(ithick or 0)))
    return MW


def _is_ap_dong(mk, sup, spec, q):
    """계상 대상 동 = matkl MJU0631 · Assembly Pull · ALUMINUM 아님 · q=1.0 플레이스홀더 아님."""
    return mk == 'MJU0631' and sup == 'Assembly Pull' and 'ALUMINUM' not in spec.upper() and abs(q - 1.0) > 1e-9


def lg_ap_all(cur, ver_date, models=None):
    """LG BOM 사급(Assembly Pull) 동 원소재 소요(전체) = {model: {(metal,diam,thick): per_unit_kg}}. 다단계 롤업."""
    MW = _load_edges(cur, ver_date, models)
    out = {}
    for md, wmap in MW.items():
        best = None; best_tot = -1.0
        for w, edges in wmap.items():
            ch = _dd(list)
            for e in edges:
                ch[e[0]].append(e)
            acc = _dd(float); tot = [0.0]

            def dfs(node, mult, depth, path):
                if depth > 25:
                    return
                for (p, c, mk, sup, spec, q, mg, idiam, ithick) in ch.get(node, ()):
                    if _is_ap_dong(mk, sup, spec, q):
                        cv = q * mult
                        acc[_key(spec, mg, idiam, ithick)] += cv; tot[0] += cv
                    if c != node and c not in path:       # EA 중간노드=수량 곱해 관통, 동 leaf=자식없어 종료, cycle 방지
                        dfs(c, mult * q, depth + 1, path | {c})
            dfs(md, 1.0, 0, {md})
            if tot[0] > best_tot:
                best_tot = tot[0]; best = dict(acc)
        if best:
            out[md] = best
    return out


def _jjset_load(cur):
    """우리 제작동관 코드집합(우리가 직접 깎는 절단관) = bom_flat role='제작동관'."""
    cur.execute("SELECT DISTINCT UPPER(LTRIM(RTRIM(leaf_code))) FROM nx.bom_flat WHERE role=N'제작동관'")
    return set(r[0] for r in cur.fetchall())


def lg_ap_split(cur, ver_date, models=None, jjset=None):
    """전체 사급 동을 우리절삭/협력사사급으로 분할 = {model: {'our':{spec:kg}, 'coop':{spec:kg}}}. 2중계상 없음(전체=our+coop).
       분할 = 동의 부모(절단관)가 우리 제작동관이면 our, 아니면 coop. jjset 넘기면 재사용(월별 반복 성능)."""
    if jjset is None:
        jjset = _jjset_load(cur)
    MW = _load_edges(cur, ver_date, models)
    out = {}
    for md, wmap in MW.items():
        best = None; best_tot = -1.0
        for w, edges in wmap.items():
            ch = _dd(list)
            for e in edges:
                ch[e[0]].append(e)
            our = _dd(float); coop = _dd(float); tot = [0.0]

            def dfs(node, mult, depth, path):
                if depth > 25:
                    return
                for (p, c, mk, sup, spec, q, mg, idiam, ithick) in ch.get(node, ()):
                    if _is_ap_dong(mk, sup, spec, q):
                        cv = q * mult; k = _key(spec, mg, idiam, ithick)
                        (our if node in jjset else coop)[k] += cv    # node=이 동의 부모(절단관)
                        tot[0] += cv
                    if c != node and c not in path:
                        dfs(c, mult * q, depth + 1, path | {c})
            dfs(md, 1.0, 0, {md})
            if tot[0] > best_tot:
                best_tot = tot[0]; best = {'our': dict(our), 'coop': dict(coop)}
        if best:
            out[md] = best
    return out
