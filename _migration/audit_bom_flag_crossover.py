# -*- coding: utf-8 -*-
"""BOM 플래그 엇갈림 전수 진단 (2026-08-30)

배경
  LG사급 부품수불에서 MJX62771713 이 소요만 1,812·입고 190 으로 −1,622 였다.
  파보니 같은 상위(AJR30007102~06) 아래 체크밸브가 **두 품번** 걸려 있고 플래그가 엇갈렸다.
    MJX62771704  EXCEPT_FLAG=1  CS_CALC_EXCEPT_FLAG=0   ← LG가 실제 공급
    MJX62771713  EXCEPT_FLAG=0  CS_CALC_EXCEPT_FLAG=1

  두 엔진이 서로 다른 플래그를 본다 (실측·코드 확인):
    소요엔진 sagub_parts_soyo : EXCEPT_FLAG=1 이면 건너뜀. CS_CALC_EXCEPT_FLAG 는 **안 봄**
    원가엔진 NxCostEngine     : CS_CALC_EXCEPT_FLAG=1 이면 노드 생성 안 함
  ⟹ 소요는 713 을, 원가는 704 를 계상한다. **같은 Assy 에서 서로 다른 품번을 본다.**

정본
  EXCEPT_FLAG=1  = 전개제외(우리가 안 내보냄·상위 SUB 거래처 귀속)  — EXCEPT_FLAG_VENDOR_RULE.md
  CS_CALC_EXCEPT_FLAG=1 = 원가계산 제외(변형SUB 대체된 직접행 중복방지) — CS_CALC_EXCEPT_HANDOFF.md
  둘은 원래 **다른 목적**이라 엇갈림 자체가 곧 오류는 아니다. 그래서 **패턴별로 센다.**

읽기 전용.
"""
import io
import os
import sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
_BE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PNC_ERP_Web", "backend")
sys.path.insert(0, os.path.abspath(_BE))
os.chdir(os.path.abspath(_BE))

from common import _nx                                            # noqa: E402

f = lambda v: float(v or 0)
nx = _nx(); cur = nx.cursor()

cur.execute("""SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), UPPER(LTRIM(RTRIM(MAT_CODE))),
                      ISNULL(EXCEPT_FLAG,'0'), ISNULL(CS_CALC_EXCEPT_FLAG,'0'),
                      ISNULL(SAGUB_FLAG,'0'), CONVERT(float,ISNULL(USE_QTY,0))
                 FROM nx.v_pr_bom""")
rows = [(r[0], r[1], str(r[2]).strip(), str(r[3]).strip(), str(r[4]).strip(), f(r[5]))
        for r in cur.fetchall()]
print("=" * 96)
print("  BOM 플래그 조합 분포 (nx.v_pr_bom 전 {:,}행)".format(len(rows)))
print("=" * 96)
comb = defaultdict(int)
for p, c, ex, cs, sg, q in rows:
    comb[(ex, cs, sg)] += 1
print("  {:<8}{:<12}{:<8}{:>12}".format("EXCEPT", "CS_EXCEPT", "SAGUB", "행수"))
for k in sorted(comb, key=lambda k: -comb[k]):
    print("  {:<8}{:<12}{:<8}{:>12,}".format(k[0], k[1], k[2], comb[k]))

# ── 엇갈림 = 같은 상위 아래 (EXCEPT=1,CS=0) 와 (EXCEPT=0,CS=1) 이 공존 ──
byp = defaultdict(list)
for p, c, ex, cs, sg, q in rows:
    byp[p].append((c, ex, cs, sg, q))
cross = {}
for p, ch in byp.items():
    a = [x for x in ch if x[1] == '1' and x[2] != '1']      # 전개제외 · 원가포함
    b = [x for x in ch if x[1] != '1' and x[2] == '1']      # 전개포함 · 원가제외
    if a and b:
        cross[p] = (a, b)
print("\n" + "=" * 96)
print("  ★엇갈림 상위 = (전개제외·원가포함) 과 (전개포함·원가제외) 가 한 상위에 공존")
print("=" * 96)
print("  상위 {:,}곳 / 전체 상위 {:,}곳".format(len(cross), len(byp)))

# 사급부품(OSP) 영향
cur.execute("""SELECT UPPER(LTRIM(RTRIM(item_code))) FROM nx.lg_sagub_actual
                WHERE UPPER(item_name) NOT LIKE '%TUBE%' GROUP BY UPPER(LTRIM(RTRIM(item_code)))""")
osp = {r[0] for r in cur.fetchall()}
cnt_osp = 0; pair_osp = []
for p, (a, b) in cross.items():
    ao = [x for x in a if x[0] in osp]; bo = [x for x in b if x[0] in osp]
    if ao and bo:
        cnt_osp += 1
        pair_osp.append((p, ao, bo))
print("  그 중 **양쪽 다 LG 사급부품**인 상위: {:,}곳".format(cnt_osp))

# 소요만 잡히는 쪽(전개포함·원가제외) 품번별 집계
victim = defaultdict(set)     # 소요에만 잡히는 사급부품 -> 상위들
winner = defaultdict(set)     # 원가에만 잡히는 사급부품
for p, ao, bo in pair_osp:
    for x in bo: victim[x[0]].add(p)
    for x in ao: winner[x[0]].add(p)
print("\n  소요에만 잡히는 사급부품 {:,}종 / 원가에만 잡히는 사급부품 {:,}종".format(len(victim), len(winner)))

cur.execute("SELECT UPPER(LTRIM(RTRIM(item_code))), item_name FROM nx.item")
nm = {r[0]: str(r[1] or '') for r in cur.fetchall()}
print("\n  ── 소요에만 잡히는(=입고 없이 소요만 나는) 사급부품 상위 15 ──")
print("  {:<15}{:<26}{:>8}".format("품번", "품명", "상위수"))
for k in sorted(victim, key=lambda k: -len(victim[k]))[:15]:
    print("  {:<15}{:<26}{:>8}".format(k, nm.get(k, '')[:24], len(victim[k])))

print("\n  ── 대표 사례(상위별 짝) 상위 8 ──")
for p, ao, bo in pair_osp[:8]:
    print("  [{}] {}".format(p, nm.get(p, '')[:36]))
    for x in ao: print("      원가만 계상  {:<15} {}".format(x[0], nm.get(x[0], '')[:24]))
    for x in bo: print("      소요만 계상  {:<15} {}".format(x[0], nm.get(x[0], '')[:24]))
nx.close()
