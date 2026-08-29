# -*- coding: utf-8 -*-
"""naewon 내부원가 오라클 게이트 — 레거시 내부용 SP(SP_CS_견적서(내부용)_250704) diff0 검증.
   실원가 cost_oracle과 대칭. NAEWON_COSTGUBUN3_GAP_260829.md 참조.

   목적: cg3 가드제거 수정본(material_nae_fixed)이 레거시 내부용 SP와 반올림 이내 diff0인지 대규모 검증.
   ★옆에짓고 diff0: 엔진(cost_material_nae) 미변경. 수정본을 여기서 별도 재현해 대조.
   현엔진(버그·cg3 정지)도 함께 찍어 개선폭 표시.

   사용: python naewon_oracle_gate.py [N]   (N=표본수, 기본 200. 'ALL'=전 최상위제품)
   허용오차: FAIL = |gap|>10원 AND |gap|/legacy>0.1% (그 이하=반올림 PASS).
"""
import sys, io, time
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\_harness')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import cost_oracle
from nx_cost_engine import NxCostEngine

YMD = '260630'
ARG = sys.argv[1] if len(sys.argv) > 1 else '200'


def material_nae_fixed(eng, item, ymd):
    """수정본 = 현 cost_material_nae에 2개 교정:
       ①cg3 가드제거(cg5+자식없음에서만 정지) — cg3 서브ASSY 원소재까지 전개.
       ②EA단위 수량전파 — 레거시 재료 롤업 `IIF(부모.UNIT='EA', USE_QTY, 1)` 정합:
         내부노드로 내려갈 땐 qty를 unit='EA'일 때만 전파, 최말단은 use_qty 항상 적용(SP line308·771-773)."""
    ymcut = '20' + ymd[:4]
    def value(node, mult, seen):
        info = eng._load_item(node)
        if eng._expandable_nae(node, seen):          # ①cg3 가드 제거
            tot = 0.0
            for c, qty, cx, f, t, lx in eng.lines(node):
                if cx:
                    continue
                cinfo = eng._load_item(c)
                if eng._expandable_nae(c, seen | {node}):   # 내부노드 → ②EA일 때만 qty 전파
                    cm = mult * (qty if cinfo['unit'] == 'EA' else 1.0)
                else:                                        # 최말단 → use_qty 항상
                    cm = mult * qty
                tot += value(c, cm, seen | {node})
            return tot
        return eng._leaf_val_nae(node, info, mult, ymd, ymcut)
    return round(value(item, 1.0, set()), 2)


def is_rounding(gap, legacy):
    return abs(gap) <= 10.0 or abs(gap) / max(abs(legacy), 1.0) <= 0.001


def bom_drift_edges(eng, item, lcur):
    """item 트리에서 엔진(nx.bom_line non-except)과 레거시 CS_M_ITEM_BOM(라이브)의 엣지 불일치 수.
       불일치 = 레거시에 없음 OR use_qty 다름(중복/qty 드리프트 포함). >0 = FAIL이 BOM 소스차(naewon 로직 아님)."""
    hasbom = eng._load_hasbom()
    seen = set(); stack = [item]; drift = 0
    while stack:
        n = stack.pop()
        if n in seen: continue
        seen.add(n)
        if n not in hasbom: continue
        for c, qty, cx, f, t, lx in eng.lines(n):
            if cx: continue
            lcur.execute("""SELECT use_qty FROM CS_M_ITEM_BOM
                WHERE UPPER(LTRIM(RTRIM(item_code)))=? AND UPPER(LTRIM(RTRIM(mat_code)))=?
                  AND ISNULL(CS_CALC_EXCEPT_FLAG,'0')<>'1'""", n, c)
            r = lcur.fetchone()
            if r is None or abs(float(r[0] or 0) - qty) > 0.001:
                drift += 1
            stack.append(c)
    return drift


def main():
    eng = NxCostEngine()
    if ARG.upper() == 'ALL':
        eng.cur.execute("""SELECT UPPER(LTRIM(RTRIM(h.item_code))) FROM nx.bom_header h
            WHERE NOT EXISTS (SELECT 1 FROM nx.bom_line l WHERE UPPER(LTRIM(RTRIM(l.child_item)))=UPPER(LTRIM(RTRIM(h.item_code))))""")
    else:
        eng.cur.execute("""SELECT TOP (?) UPPER(LTRIM(RTRIM(h.item_code))) FROM nx.bom_header h
            WHERE NOT EXISTS (SELECT 1 FROM nx.bom_line l WHERE UPPER(LTRIM(RTRIM(l.child_item)))=UPPER(LTRIM(RTRIM(h.item_code))))
            ORDER BY NEWID()""", int(ARG))
    items = [r[0] for r in eng.cur.fetchall()]
    lcn = cost_oracle._conn(); lcur = lcn.cursor()   # 라이브 레거시(분류기 qty 대조용)

    n = err = skip_noleg = 0
    cur_diff = fix_diff = 0            # ≥1원 엄격
    fix_fail = fix_new_fail = closed = 0   # 반올림 허용 후
    fails = []
    t0 = time.time()
    for it in items:
        try:
            orc = cost_oracle.get_oracle(it, YMD)
            if orc.get('struct_n', 0) == 0:   # ★레거시 미보유(빈 SP결과)=그라운드트루스 없음=비교불가
                skip_noleg += 1; continue
            o = orc['nae']['jae']
            cur = eng.naewon(it, YMD)['jae']
            fix = material_nae_fixed(eng, it, YMD)
        except Exception as ex:
            err += 1
            if err <= 5: print('ERR', it, str(ex)[:50])
            continue
        n += 1
        gc = o - cur; gf = o - fix
        if abs(gc) >= 1.0: cur_diff += 1
        if abs(gf) >= 1.0: fix_diff += 1
        rc = is_rounding(gc, o); rf = is_rounding(gf, o)
        if not rf:
            fix_fail += 1
            drift = bom_drift_edges(eng, it, lcur)
            fails.append((it, round(o, 1), round(fix, 1), round(gf, 1), f'BOM드리프트{drift}' if drift else '★로직FAIL'))
            if not (not rc):  # 현엔진은 반올림OK였는데 수정이 깸
                fix_new_fail += 1
        if (not rc) and rf:  # 현엔진 실FAIL → 수정 PASS
            closed += 1
    dt = time.time() - t0
    print(f"\n===== naewon 오라클 게이트 (비교 {n}품목·레거시미보유제외 {skip_noleg}·err {err}·{dt:.0f}s) =====")
    print(f"[엄격 ≥1원]   현엔진≠레거시 {cur_diff} / 수정본≠레거시 {fix_diff}")
    print(f"[반올림허용]  수정이 닫은 실갭 {closed} / 수정 실FAIL {fix_fail} / ★수정이 새로깬 것 {fix_new_fail}")
    logic_fail = sum(1 for f in fails if f[4] == '★로직FAIL')
    print(f"\n결과: {'★PASS (수정본=레거시 diff0, 반올림 이내)' if fix_fail==0 else f'FAIL {fix_fail}건 (BOM드리프트 {fix_fail-logic_fail} + ★로직 {logic_fail})'}")
    print(f"      ★naewon 로직 FAIL(BOM소스 무관): {logic_fail} {'= 산식 완전정합' if logic_fail==0 else '= 추가 규명 필요'}")
    if fails:
        print("수정 후 실FAIL(레거시jae, 수정jae, 갭, 분류):")
        for r in sorted(fails, key=lambda x: -abs(x[3]))[:30]:
            print('  ', r)


if __name__ == '__main__':
    main()
