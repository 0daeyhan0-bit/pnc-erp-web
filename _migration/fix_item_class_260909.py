# -*- coding: utf-8 -*-
"""품목 클린(nx.item) 결손 보정 — item_class 빈 값 (2026-09-09)

■ 왜
  PR_M_ITEM → nx.item 전환 준비 중 실측:
     IN_CUST_CODE → in_cust      24,154/24,154 (100%)
     WORK_CODE    → work_code    24,154/24,154 (100%)
     SAGUB_STOCK_FLAG            24,154/24,154 (100%)
     ★ITEM_CLASS  → item_class   24,143/24,154  ← 11건이 클린만 빈 값

  라이브·미러에는 값이 있는데 클린만 비었다 = 이관 결손.
     AJR30012012-S1-2 · AJR30012012-SUB · AJR30167201-SUB   L
     EAP00689102 · EAP00689104                              A
     MEV00261112 ~ MEV00261117 (6건)                        T

  move580web.py 가 item_class 를 화면 표시(item_class_desc)에 쓴다 —
  L368·L384·L407·L427 에서 SELECT 하고 L730 에서 라벨로 변환한다.
  그대로 전환하면 이 11건의 구분 라벨이 화면에서 빈칸이 된다.

■ 안전
  · 쓰기 대상 = nx.item (§1-1 준수). 라이브는 읽기만.
  · 근거키 스코프 = "라이브에 값이 있고 클린이 빈 것" 만. 대량 UPDATE 아님.
  · --commit 없으면 조회만.
"""
import sys, os, io, argparse
BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

ap = argparse.ArgumentParser()
ap.add_argument("--commit", action="store_true", help="실제 반영")
A = ap.parse_args()

nx = _nx(); cur = nx.cursor()

SEL = """SELECT RTRIM(c.item_code), RTRIM(ISNULL(c.item_name,'')),
                RTRIM(ISNULL(CAST(l.ITEM_CLASS AS nvarchar(20)),''))
           FROM nx.item c
           JOIN PARTNER_ERP.dbo.PR_M_ITEM l ON RTRIM(l.ITEM_CODE)=RTRIM(c.item_code)
          WHERE RTRIM(ISNULL(CAST(c.item_class AS nvarchar(20)),'')) = ''
            AND RTRIM(ISNULL(CAST(l.ITEM_CLASS AS nvarchar(20)),'')) <> ''
          ORDER BY c.item_code"""
cur.execute(SEL)
rows = cur.fetchall()

print("=" * 92)
print(" 보정 대상 — nx.item.item_class (클린만 빈 값)")
print("=" * 92)
if not rows:
    print("   대상 없음 — 이미 정합")
    nx.close(); sys.exit(0)
print("   {:<20s} {:<30s} {}".format("품번", "품명", "라이브 값"))
for a, b, c in rows:
    print("   {:<20s} {:<30s} {}".format(a, b[:30], c))
print("\n   {}건".format(len(rows)))

if not A.commit:
    print("\n   [DRY-RUN] --commit 을 붙이면 반영한다.")
    nx.close(); sys.exit(0)

# ── 백업(근거키 스코프)
cur.execute("IF OBJECT_ID('nx.bk_item_class_260909') IS NOT NULL DROP TABLE nx.bk_item_class_260909")
cur.execute("""SELECT item_code, item_name, item_class INTO nx.bk_item_class_260909
                 FROM nx.item WHERE RTRIM(item_code) IN ({})""".format(
    ",".join("'" + str(r[0]) + "'" for r in rows)))
nx.commit()
print("\n   백업 nx.bk_item_class_260909 — {}행".format(len(rows)))

n = 0
for code, _, val in rows:
    cur.execute("UPDATE nx.item SET item_class=? WHERE RTRIM(item_code)=?", val, code)
    n += cur.rowcount
nx.commit()
print("   반영 {}행".format(n))

cur.execute(SEL)
left = len(cur.fetchall())
print("\n   재검증 — 남은 결손 {}건 {}".format(left, "✔" if left == 0 else "★"))
nx.close()
