# -*- coding: utf-8 -*-
"""공용 재고 테스트베드 사용 예제 = 용접봉 백플러시 검증 3시연 (2026-08-27 실제 사용분).
   stock_testbed 의 sandbox/seed/Tracker/read_stock 를 어떻게 쓰는지 보여준다. 전부 롤백(오염0).
   실행: python stock_testbed_examples.py
   다른 프로그램(자재입출고·영업출고 등)도 이 골격을 복사해 검증하면 된다."""
import sys, io
sys.path.insert(0, r'd:/피앤씨인더스트리/100_AI_AGENT/Projects/_wt_rdr/_harness')
sys.path.insert(0, r'd:/피앤씨인더스트리/100_AI_AGENT/Projects/_wt_rdr/PNC_ERP_Web/backend')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from stock_testbed import sandbox, seed, Tracker, read_stock, assert_delta
from routers.backflush import _weld_consume, _weld_proc_code, _backflush_bom

MULTI = 'AJR30004702'   # 용접봉 2종(RAC30599327·RAC30599303)
OUTSUB = 'ADL76734508'  # 하위에 외주서브+용접봉 → 사내한정 제외 대상


def demo1_realtime_deplete():
    """시연1) 실시간 연속소진 → 자동차단 (영구재고 = 스냅샷 모델론 불가)."""
    print("=" * 64 + "\n[시연1] 실시간 연속소진 → 자동차단")
    with sandbox() as (nx, cur):
        _, weld = _backflush_bom(nx, MULTI, nx)
        for b in weld:
            seed(cur, b, 0.04, gpc=_weld_proc_code(nx, b))   # 소량 시드(≈3개분)
        t = Tracker(cur)
        for b in weld: t.watch(b, 'PRODWH', b, _weld_proc_code(nx, b))
        print(f"  품목 {MULTI} 용접봉소요/개: {dict((k, round(v,4)) for k,v in weld.items())}")
        for n in range(1, 6):
            r = _weld_consume(nx, nx, MULTI, 1.0, f'EX_R{n}', 'TESTBED')
            if r.get('ok'):
                print(f"    {n}개째 OK · 생산창고재고={t.snap('s')}")
            else:
                s = r['shortage'][0]
                print(f"    {n}개째 ★차단! {s['mat']} 필요{s['need']}/재고{s['have']}"); break


def demo2_multi_partial():
    """시연2) 다종 용접봉 부분부족 — 한 종만 부족해도 그 종 지목해 차단."""
    print("=" * 64 + "\n[시연2] 다종 부분부족 → 부족한 종만 지목")
    with sandbox() as (nx, cur):
        _, weld = _backflush_bom(nx, MULTI, nx); ks = list(weld)
        seed(cur, ks[0], 100, gpc=_weld_proc_code(nx, ks[0]))     # 충분
        seed(cur, ks[1], 0.001, gpc=_weld_proc_code(nx, ks[1]))   # 부족
        print(f"  시드: {ks[0]}=100(충분) · {ks[1]}=0.001(부족)")
        r = _weld_consume(nx, nx, MULTI, 1.0, 'EX_MIX', 'TESTBED')
        print(f"  생산 1개 → ok={r.get('ok')}")
        for s in r.get('shortage', []):
            print(f"    부족지목: {s['mat']} 필요{s['need']}/재고{s['have']}")


def demo3_inner_only():
    """시연3) 사내한정 — 외주서브 용접봉은 미차감(사급출고로 이미 −재고, 이중차감 방지)."""
    print("=" * 64 + "\n[시연3] 사내한정 — 외주 용접봉 미차감")
    with sandbox() as (nx, cur):
        _, weld = _backflush_bom(nx, OUTSUB, nx)
        print(f"  품목 {OUTSUB}(하위에 외주서브+용접봉 존재)")
        print(f"  → 용접봉 수집결과: {dict((k, round(v,4)) for k,v in weld.items()) if weld else '없음(외주 용접봉 제외됨) ✓'}")


if __name__ == '__main__':
    demo1_realtime_deplete()
    demo2_multi_partial()
    demo3_inner_only()
    print("=" * 64 + "\n→ 전부 sandbox 롤백 (nx·실적 무변경)")
