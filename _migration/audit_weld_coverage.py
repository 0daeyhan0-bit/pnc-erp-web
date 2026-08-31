# -*- coding: utf-8 -*-
"""용접봉(RAC*) 커버리지 철저 검증 (2026-08-31)

왜
  §12 에서 "용접봉 차이는 설계상 정상" 이라고 **코드 한 줄만 읽고 단정**했다.
  대표 지적("성급한 일반화는 금물") 후 데이터로 확인하니 **5,103건 중 3건은 진짜 누락**이었다.
  ⟹ 전 방향을 다 본다. 한 방향만 보면 반대쪽이 숨는다.

설계 전제 (코드 확인)
  nx_cost_engine.py:143  bom_line 에서 `child_item NOT LIKE 'RAC%'` 로 용접봉을 뺀다
  nx_cost_engine.py:152  `nx.proc_weld`(공정)에서 따로 주입한다
  ⟹ 용접봉의 정본은 **CS_M_ITEM_BOM ↔ nx.proc_weld** 대조여야 한다(bom_line 아님).

검증 6방향
  ① CS 에만(bom_line 없음) 중 proc_weld 로 커버되나        ← 누락 탐지
  ② CS ↔ proc_weld 수량 일치하나
  ③ proc_weld 에만 있는 것(CS 원천 없음)
  ④ bom_line 에 남아 있는 RAC 행(빠졌어야 하는데 남은 것)
  ⑤ CS 에 있고 bom_line 에도 있는 RAC (양쪽 다 — 이중계상 위험)
  ⑥ cs_calc_except 플래그 차이가 실제 계산에 영향 있나

★읽기 전용.
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
R = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(R, "PNC_ERP_Web", "backend"))
os.chdir(os.path.join(R, "PNC_ERP_Web", "backend"))

from common import _nx                                     # noqa: E402

sq = lambda v: ''.join(str(v or '').split()).upper()
cur = _nx().cursor()

cur.execute("""SELECT LTRIM(RTRIM(ITEM_CODE)), LTRIM(RTRIM(MAT_CODE)),
                      CONVERT(float,ISNULL(USE_QTY,0)), ISNULL(CS_CALC_EXCEPT_FLAG,'0')
                 FROM PARTNER_ERP.dbo.CS_M_ITEM_BOM WHERE LTRIM(RTRIM(MAT_CODE)) LIKE 'RAC%'""")
CS = {(sq(a), sq(b)): (c, '1' if str(d).strip() == '1' else '0') for a, b, c, d in cur.fetchall()}

cur.execute("""SELECT LTRIM(RTRIM(h.item_code)), LTRIM(RTRIM(l.child_item)),
                      CONVERT(float,ISNULL(l.qty,0)), ISNULL(l.cs_calc_except,0)
                 FROM nx.bom_line l JOIN nx.bom_header h ON h.bom_id=l.bom_id
                WHERE LTRIM(RTRIM(l.child_item)) LIKE 'RAC%'""")
BL = {(sq(a), sq(b)): (c, '1' if d in (1, True, '1') else '0') for a, b, c, d in cur.fetchall()}

cur.execute("""SELECT LTRIM(RTRIM(parent_item)), LTRIM(RTRIM(weld_item)),
                      CONVERT(float,ISNULL(use_qty,0)), ISNULL(cs_calc_except,0)
                 FROM nx.proc_weld""")
PW = {(sq(a), sq(b)): (c, '1' if d in (1, True, '1') else '0') for a, b, c, d in cur.fetchall()}

print("=" * 92)
print("  용접봉(RAC*) 커버리지 철저 검증")
print("=" * 92)
print("  CS_M_ITEM_BOM(RAC) {:,} · nx.bom_line(RAC) {:,} · nx.proc_weld {:,}".format(len(CS), len(BL), len(PW)))

def show(t, ks, fmt, n=10, warn=True):
    mark = "★" if (ks and warn) else "  "
    print("\n  {}{} : {:,}건".format(mark, t, len(ks)))
    for k in sorted(ks)[:n]:
        print("      " + fmt(k))
    if len(ks) > n:
        print("      … 외 {:,}건".format(len(ks) - n))

# ① CS 에만(bom_line 없음) 중 proc_weld 미커버
only_cs = set(CS) - set(BL)
miss = [k for k in only_cs if k not in PW]
show("① CS 에 있는데 bom_line·proc_weld **둘 다 없음**(진짜 누락)", miss,
     lambda k: "{:<26} ← {:<18} CS qty {:g}".format(k[0], k[1], CS[k][0]))

# ② 수량 불일치
qd = [k for k in (only_cs & set(PW)) if abs(CS[k][0] - PW[k][0]) > 1e-6]
show("② CS ↔ proc_weld 수량 다름", qd,
     lambda k: "{:<26} ← {:<18} CS {:g} / pw {:g}".format(k[0], k[1], CS[k][0], PW[k][0]))

# ③ proc_weld 에만
show("③ proc_weld 에만 있음(CS 원천 없음)", list(set(PW) - set(CS)),
     lambda k: "{:<26} ← {:<18} pw qty {:g}".format(k[0], k[1], PW[k][0]))

# ④ bom_line 에 남은 RAC
show("④ bom_line 에 남아 있는 RAC 행(엔진이 NOT LIKE 'RAC%' 로 거르므로 무해하나 잔재)",
     list(BL), lambda k: "{:<26} ← {:<18} qty {:g}".format(k[0], k[1], BL[k][0]), n=5, warn=False)

# ⑤ CS·bom_line·proc_weld 세 곳 다 있는 것(이중계상 위험 점검)
tri = [k for k in set(CS) & set(BL) & set(PW)]
show("⑤ CS·bom_line·proc_weld 세 곳 모두 있음(이중계상 위험 점검 대상)", tri,
     lambda k: "{:<26} ← {}".format(k[0], k[1]), n=5)

# ⑥ 플래그 차이(CS vs proc_weld)
fd = [k for k in (set(CS) & set(PW)) if CS[k][1] != PW[k][1]]
show("⑥ CS ↔ proc_weld cs_calc_except 다름", fd,
     lambda k: "{:<26} ← {:<18} CS={} / pw={}".format(k[0], k[1], CS[k][1], PW[k][1]))

print("\n" + "=" * 92)
print("  ⟹ 용접봉 실제 결함 = ①{} + ②{} + ⑥{} = {}건  (③{} · ④{} 는 별도 판단)".format(
    len(miss), len(qd), len(fd), len(miss) + len(qd) + len(fd), len(set(PW) - set(CS)), len(BL)))
