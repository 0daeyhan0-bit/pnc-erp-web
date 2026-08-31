# -*- coding: utf-8 -*-
"""nx.bom_line ↔ CS_M_ITEM_BOM 전수 대조 (2026-08-31)

왜
  원가 전수 대조(§11)에서 실질 불일치 27건의 뿌리 두 가지가 **미러 부채**였다.
    ① cs_calc_except 플래그 반전 (AJR30007102~06 · AJR30167201-SUB)
    ② nx.bom_line 미러 누락      (AJR33796526 — CS 자식 18개인데 헤더 자체가 없음)
  원가로 잡힌 건 **금액 차이가 난 것만**이다. 플래그가 반전됐어도 단가가 같으면 안 잡힌다.
  ⟹ 진짜 규모를 알려면 **BOM 자체를 전수 대조**해야 한다.

무엇을
  정의역 = 두 소스의 (상위품목, 자식품목) 합집합 전체.
  비교 항목: 존재 여부 · USE_QTY · CS_CALC_EXCEPT_FLAG
  ※nx.bom_line 은 bom_header 를 거쳐 item_code 로 잇는다(bom_id 는 숫자키).

★읽기 전용. 아무것도 쓰지 않는다.
★nx.bom_line 은 소요·계획도 쓴다 — 이 결과는 **규모 측정**이지 수정 지시가 아니다.
"""
import io
import os
import sys
import time
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
R = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(R, "PNC_ERP_Web", "backend"))
os.chdir(os.path.join(R, "PNC_ERP_Web", "backend"))

from common import _nx                                     # noqa: E402

f = lambda v: float(v or 0)
sq = lambda v: ''.join(str(v or '').split()).upper()       # ★품번에 줄바꿈이 섞인 것이 있다(§11-3)

nx = _nx(); cur = nx.cursor()
t0 = time.time()

print("=" * 92)
print("  nx.bom_line ↔ CS_M_ITEM_BOM 전수 대조   (읽기 전용)")
print("=" * 92)

cur.execute("""SELECT LTRIM(RTRIM(ITEM_CODE)), LTRIM(RTRIM(MAT_CODE)),
                      CONVERT(float,ISNULL(USE_QTY,0)), ISNULL(CS_CALC_EXCEPT_FLAG,'0')
                 FROM PARTNER_ERP.dbo.CS_M_ITEM_BOM""")
CS = {}
cs_raw = 0
for p, c, q, x in cur.fetchall():
    cs_raw += 1
    CS[(sq(p), sq(c))] = (q, '1' if str(x).strip() == '1' else '0')

cur.execute("""SELECT LTRIM(RTRIM(h.item_code)), LTRIM(RTRIM(l.child_item)),
                      CONVERT(float,ISNULL(l.qty,0)), ISNULL(l.cs_calc_except,0)
                 FROM nx.bom_line l JOIN nx.bom_header h ON h.bom_id = l.bom_id""")
NB = {}
nb_raw = 0
for p, c, q, x in cur.fetchall():
    nb_raw += 1
    NB[(sq(p), sq(c))] = (q, '1' if (x in (1, True, '1')) else '0')

print("  CS_M_ITEM_BOM {:,}행 → 키 {:,}개".format(cs_raw, len(CS)))
print("  nx.bom_line   {:,}행 → 키 {:,}개".format(nb_raw, len(NB)))

only_cs = sorted(set(CS) - set(NB))
only_nb = sorted(set(NB) - set(CS))
both = set(CS) & set(NB)
qty_d = [(k, CS[k][0], NB[k][0]) for k in both if abs(CS[k][0] - NB[k][0]) > 1e-6]
flg_d = [(k, CS[k][1], NB[k][1]) for k in both if CS[k][1] != NB[k][1]]

print("\n" + "=" * 92)
print("  ── 결과 ──")
print("=" * 92)
print("  공통 키                  {:>8,}".format(len(both)))
print("  ★CS 에만 있음(미러 누락)  {:>8,}".format(len(only_cs)))
print("  ★nx 에만 있음(원천 없음)  {:>8,}".format(len(only_nb)))
print("  ★수량 다름               {:>8,}".format(len(qty_d)))
print("  ★cs_calc_except 다름     {:>8,}".format(len(flg_d)))

print("\n  ── cs_calc_except 방향별 ──")
inv = defaultdict(int)
for k, a, b in flg_d:
    inv[(a, b)] += 1
for (a, b), n in sorted(inv.items(), key=lambda x: -x[1]):
    print("    CS={} → nx={}   {:>6,}건 {}".format(a, b, n,
          "★엔진이 계상(원가 과다 위험)" if (a, b) == ('1', '0') else
          "★엔진이 제외(원가 과소 위험)" if (a, b) == ('0', '1') else ""))

def head(t, rows, fmt, n=10):
    print("\n  ── {} 상위 {} ──".format(t, n))
    for r in rows[:n]:
        print("    " + fmt(r))

head("CS 에만 있는 (상위,자식)", only_cs, lambda k: "{:<24} ← {}".format(k[0], k[1]))
head("nx 에만 있는 (상위,자식)", only_nb, lambda k: "{:<24} ← {}".format(k[0], k[1]))
head("수량 다름", sorted(qty_d, key=lambda x: -abs(x[1] - x[2])),
     lambda r: "{:<24} ← {:<18} CS {:g} / nx {:g}".format(r[0][0], r[0][1], r[1], r[2]))
head("플래그 다름", flg_d, lambda r: "{:<24} ← {:<18} CS={} / nx={}".format(r[0][0], r[0][1], r[1], r[2]))

# 상위품목 단위 요약 — 원가/소요에 영향받는 제품이 몇 개인가
aff = set(k[0] for k, _, _ in flg_d) | set(k[0] for k, _, _ in qty_d) | set(k[0] for k in only_cs) | set(k[0] for k in only_nb)
print("\n  ⟹ 영향 상위품목 {:,}종 (CS 상위 {:,}종 중 {:.1f}%) · {:.0f}초".format(
    len(aff), len(set(k[0] for k in CS)), len(aff) * 100.0 / max(1, len(set(k[0] for k in CS))), time.time() - t0))

# 품번 오염(공백/줄바꿈) 전수 — §11-3 ③
cur.execute("""SELECT COUNT(*) FROM PARTNER_ERP.dbo.CS_M_ITEM_BOM
                WHERE ITEM_CODE <> LTRIM(RTRIM(ITEM_CODE)) OR MAT_CODE <> LTRIM(RTRIM(MAT_CODE))
                   OR ITEM_CODE LIKE '%' + CHAR(10) + '%' OR MAT_CODE LIKE '%' + CHAR(10) + '%'
                   OR ITEM_CODE LIKE '%' + CHAR(13) + '%' OR MAT_CODE LIKE '%' + CHAR(13) + '%'""")
print("  품번 오염(공백/줄바꿈 포함) CS_M_ITEM_BOM: {:,}행".format(cur.fetchone()[0]))
nx.close()
