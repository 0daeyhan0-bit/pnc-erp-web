# -*- coding: utf-8 -*-
"""nx.item ↔ 레거시 PR_M_ITEM 전수 대조 — 원가엔진이 읽는 필드만 (2026-08-31)

왜
  §12·§13 은 BOM(`CS_M_ITEM_BOM` ↔ `nx.bom_line`/`nx.proc_weld`)만 봤다.
  대표 지적 — "nx item 이랑 BOM 을 보면서 검증하고 있는 거지?"
  ⟹ **`nx.item` 은 검증 축에서 빠져 있었다.** 원가엔진은 `_load_item()` 으로
     nx.item 에서 12개 필드를 읽어 전개·분해를 결정하므로, 여기가 어긋나도 원가가 갈린다.

엔진이 읽는 필드 (nx_cost_engine._load_item)
  in_cust · make_type · cost_gubun · metal_gubun · diam · thick · net_weight
  has_gagong · silver_flag · unit · lgroup · sgroup

레거시 대응 컬럼 (PR_M_ITEM)
  IN_CUST_CODE · MAKE_TYPE · COST_GUBUN · METAL_GUBUN · ITEM_DIAM · ITEM_THICK · NET_WEIGHT
  (has_gagong=PR_M_ITEM_PROC_GAGONG 존재여부 · silver_flag/unit/lgroup/sgroup 은 아래 주의)

★주의 — 소유권이 갈린 필드가 있다
  `sgroup`(소분류)은 **nx.item 이 정본**이고 sync 제외다(PR#84). 미러가 재분류를 못 따라온다.
  따라서 sgroup 차이는 **결함이 아닐 수 있다** — 방향을 함께 본다(어느 쪽이 최신인가).
  나머지 원가필드는 `r_item_sync.py` 가 동기화하므로 차이 = 드리프트.

★읽기 전용.
"""
import io
import os
import sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
R = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(R, "PNC_ERP_Web", "backend"))
os.chdir(os.path.join(R, "PNC_ERP_Web", "backend"))

from common import _nx                                     # noqa: E402

sq = lambda v: ''.join(str(v or '').split()).upper()
s_ = lambda v: str(v or '').strip()
f_ = lambda v: round(float(v or 0), 4)

cur = _nx().cursor()

print("=" * 96)
print("  nx.item ↔ 레거시 PR_M_ITEM 전수 대조 (원가엔진이 읽는 필드)")
print("=" * 96)

cur.execute("""SELECT LTRIM(RTRIM(item_code)), ISNULL(in_cust,''), ISNULL(make_type,''), ISNULL(cost_gubun,''),
                      ISNULL(metal_gubun,''), ISNULL(diam,0), ISNULL(thick,0), ISNULL(net_weight,0),
                      ISNULL(unit,''), ISNULL(lgroup,''), ISNULL(sgroup,'')
                 FROM nx.item""")
NX = {sq(r[0]): (s_(r[1]), s_(r[2]), s_(r[3]), s_(r[4]), f_(r[5]), f_(r[6]), f_(r[7]),
                 s_(r[8]), s_(r[9]), s_(r[10])) for r in cur.fetchall()}

cur.execute("""SELECT LTRIM(RTRIM(ITEM_CODE)), ISNULL(IN_CUST_CODE,''), ISNULL(MAKE_TYPE,''), ISNULL(COST_GUBUN,''),
                      ISNULL(METAL_GUBUN,''), ISNULL(ITEM_DIAM,0), ISNULL(ITEM_THICK,0), ISNULL(ITEM_WEIGHT,0),
                      ISNULL(UNIT,''), ISNULL(ITEM_LGROUP,''), ISNULL(ITEM_SGROUP,'')
                 FROM PARTNER_ERP.dbo.PR_M_ITEM""")
LG = {sq(r[0]): (s_(r[1]), s_(r[2]), s_(r[3]), s_(r[4]), f_(r[5]), f_(r[6]), f_(r[7]),
                 s_(r[8]), s_(r[9]), s_(r[10])) for r in cur.fetchall()}

F = ['in_cust', 'make_type', 'cost_gubun', 'metal_gubun', 'diam', 'thick', 'net_weight',
     'unit', 'lgroup', 'sgroup']

print("  nx.item {:,}종 · PR_M_ITEM {:,}종".format(len(NX), len(LG)))
only_nx = sorted(set(NX) - set(LG))
only_lg = sorted(set(LG) - set(NX))
both = sorted(set(NX) & set(LG))
print("  공통 {:,} · nx 에만 {:,} · 레거시에만 {:,}".format(len(both), len(only_nx), len(only_lg)))

diff = defaultdict(list)
for k in both:
    a, b = NX[k], LG[k]
    for i, fn in enumerate(F):
        if a[i] != b[i]:
            diff[fn].append((k, b[i], a[i]))       # (품번, 레거시, nx)

print("\n  ── 필드별 불일치 (레거시 → nx) ──")
print("  {:<14}{:>10}  {}".format("필드", "건수", "비고"))
NOTE = {
    'sgroup': "★nx.item 이 정본(sync 제외) — 차이가 정상일 수 있음",
    'in_cust': "매입처(품목당 1개 제약) — 확인 필요",
    'lgroup': "대분류",
}
for fn in F:
    n = len(diff[fn])
    if n:
        print("  {:<14}{:>10,}  {}".format(fn, n, NOTE.get(fn, "")))
if not any(diff.values()):
    print("  (불일치 없음)")

for fn in F:
    if not diff[fn]:
        continue
    print("\n  ── {} 상위 8 ──".format(fn))
    for k, lg, nx_ in diff[fn][:8]:
        print("    {:<20} 레거시 '{}' → nx '{}'".format(k, lg, nx_))

# 원가에 직접 영향 큰 필드만 추려 요약
CORE = ['make_type', 'cost_gubun', 'metal_gubun', 'diam', 'thick', 'net_weight']
core_items = set()
for fn in CORE:
    core_items |= set(k for k, _, _ in diff[fn])
print("\n" + "=" * 96)
print("  ⟹ 원가 핵심필드({}) 불일치 품목: {:,}종".format('·'.join(CORE), len(core_items)))
print("     sgroup 불일치: {:,}종 (정본이 nx 이므로 별도 판단)".format(len(diff['sgroup'])))
