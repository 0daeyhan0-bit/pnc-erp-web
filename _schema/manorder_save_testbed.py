# -*- coding: utf-8 -*-
"""수동발주 발주저장 테스트베드 (무커밋 롤백·오염0).
검증: 발주 저장(nx.manual_order) → 기발주(po_qty) 증가 → 추가발주 재계산 정확. 다양 케이스.
추가발주 = max(0, round(plan_qty*(1+buf/100) − stock_qty − po_qty)) (프론트 산식).
실제 핸들러 manorder_save·manorder_items 호출. 전 롤백(라이브 무접촉)."""
import sys, os, io
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'PNC_ERP_Web', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'New_ERP'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import common
import routers.manorder as M

real = common._nx_tx()
class Tx:
    def __init__(s, cn): object.__setattr__(s, '_cn', cn)
    def cursor(s): return object.__getattribute__(s, '_cn').cursor()
    def commit(s): pass
    def rollback(s): pass
    def close(s): pass
    def __getattr__(s, n): return getattr(object.__getattribute__(s, '_cn'), n)
proxy = Tx(real)
M._nx = lambda: proxy; M._nx_tx = lambda: proxy   # nx 쓰기/읽기 = 샌드박스(무커밋). _conn(라이브 RO)은 그대로.

PASS = []; FAIL = []
def chk(n, c, d=""):
    (PASS if c else FAIL).append(n); print(("  [OK] " if c else "  [FAIL] ") + n + ("" if c else " :: " + d))

BUF = 20
def add_of(it, po=None):
    p = float(it['plan_qty'] or 0); s = float(it['stock_qty'] or 0); q = float(it['po_qty'] if po is None else po)
    return max(0, round(p * (1 + BUF / 100.0) - s - q))

CC = '2337'  # FONE THAI
base = M.manorder_items(cc=CC, ym='')
rows = {r['ic']: r for r in base['rows']}
print(f"매입처 {CC} · 품목 {len(rows)} · lead_days {base.get('lead_days')}")
# 추가발주>0 인 품목(발주 필요) 3개
need = [r for r in base['rows'] if add_of(r) > 0][:3]
print(f"추가발주>0 품목: {len([r for r in base['rows'] if add_of(r)>0])} · 테스트 {len(need)}개")

# ── T1: 추가발주의 일부만 발주 → 기발주 그만큼 증가·추가발주 그만큼 감소 ──
print("\n=== T1: 부분 발주 → 기발주↑·추가발주↓ ===")
it = need[0]; base_po = float(it['po_qty']); base_add = add_of(it); Q = round(base_add / 2) or 1
r = M.manorder_save({"cust_code": CC, "items": [{"item_code": it['ic'], "qty": Q}], "lead_days": base.get('lead_days') or 0})
chk("T1 저장됨", r.get('ok') and r.get('saved') == 1, str(r))
after = {x['ic']: x for x in M.manorder_items(cc=CC, ym='')['rows']}
a = after[it['ic']]
chk("T1 기발주 = 기존+발주량", abs(float(a['po_qty']) - (base_po + Q)) < 0.01, f"{base_po}+{Q} vs {a['po_qty']}")
chk("T1 추가발주 = 기존−발주량", add_of(a) == max(0, base_add - Q), f"기존{base_add}−{Q} vs {add_of(a)}")

# ── T2: 추가발주 전량 발주 → 추가발주 0 ──
print("\n=== T2: 전량 발주 → 추가발주 0 ===")
it2 = need[1]; add2 = add_of(it2)
M.manorder_save({"cust_code": CC, "items": [{"item_code": it2['ic'], "qty": add2}], "lead_days": 0})
a2 = {x['ic']: x for x in M.manorder_items(cc=CC, ym='')['rows']}[it2['ic']]
chk("T2 전량발주 후 추가발주=0", add_of(a2) == 0, f"add={add_of(a2)} (발주 {add2})")

# ── T3: 다품목 동시 발주 ──
print("\n=== T3: 다품목 발주 → 각각 반영 ===")
its = [{"item_code": r['ic'], "qty": round(add_of(r)/2) or 1} for r in need]
r3 = M.manorder_save({"cust_code": CC, "items": its, "lead_days": 0})
chk("T3 다품목 저장", r3.get('saved') == len(its), str(r3))

# ── T4: qty<=0 은 저장 안 함 ──
print("\n=== T4: qty<=0 무시 ===")
r4 = M.manorder_save({"cust_code": CC, "items": [{"item_code": need[0]['ic'], "qty": 0}, {"item_code": need[0]['ic'], "qty": -5}]})
chk("T4 qty<=0 저장 0", r4.get('saved') == 0, str(r4))

# ── T5: 예정입고 = 발주일+리드타임 ──
print("\n=== T5: 예정입고일 = 발주일+리드타임 ===")
r5 = M.manorder_save({"cust_code": CC, "items": [{"item_code": need[0]['ic'], "qty": 1}], "lead_days": 30})
chk("T5 expect_ymd 반환·발주일과 다름(리드30)", r5.get('expect_ymd') and r5.get('expect_ymd') != r5.get('order_ymd'), str(r5))

M._nx = common._nx; M._nx_tx = common._nx_tx
real.rollback(); real.close()
print(f"\n=== 결과 === PASS {len(PASS)} · FAIL {len(FAIL)}")
if FAIL: print("실패:", FAIL)
print("✓전 롤백(nx.manual_order 저장분 제거·라이브 무접촉)")
