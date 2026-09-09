# -*- coding: utf-8 -*-
"""BOM 정본 결손 보정 — set_except (세트입고 제외) 145건 (2026-09-09)

■ 왜 — 세트입고에 "나오면 안 되는 자재가 나온다"
  PR_M_ITEM_BOM → v_pr_bom 전환 검증 중 실측:

     SET_EXCEPT_FLAG='1'   라이브 1,899 · 미러 1,899 · 뷰 1,762   (-137)

     공통행 대조   미러 vs 라이브  42,547/42,547 (100.00%)
                  뷰   vs 라이브  42,788/42,933 ( 99.66%)  ★145건 어긋남

     방향: 라이브='1'(제외) 인데 뷰='0'(제외아님)  145건
           반대 방향(뷰만 제외)                      0건

  즉 클린 bom_line.set_except 가 라이브를 못 따라갔다.
  세트입고 제외는 레거시 정합을 맞춰둔 영역이라(협력사 세트입고) 틀리면
  **입고요청 목록에 제외 대상 자재가 섞인다.**

  표본: 5211A20459E ← RAC30599301-1 · RAC30599327 (라이브 제외, 클린 미제외)
        RAC30599301-1 / RAC30599327 계열이 반복 등장 — 특정 자재군의 누락으로 보인다.

■ 안전
  · 쓰기 대상 = nx.bom_line (§1-1 준수). 라이브는 읽기만.
  · 근거키 스코프 = "라이브가 '1' 이고 클린이 '1' 이 아닌 것" 만. 대량 UPDATE 아님.
  · 반대 방향(클린만 제외)은 0건이라 건드리지 않는다.
  · --commit 없으면 조회만.
"""
import sys, os, io, argparse
BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

ap = argparse.ArgumentParser()
ap.add_argument("--commit", action="store_true")
A = ap.parse_args()

nx = _nx(); cur = nx.cursor()

SEL = """SELECT b.bom_id, b.seq, RTRIM(h.item_code), RTRIM(b.child_item),
                b.set_except, RTRIM(ISNULL(CAST(l.SET_EXCEPT_FLAG AS nvarchar(5)),''))
           FROM nx.bom_line b
           JOIN nx.bom_header h ON h.bom_id = b.bom_id
           JOIN PARTNER_ERP.dbo.PR_M_ITEM_BOM l
             ON RTRIM(l.ITEM_CODE)=RTRIM(h.item_code)
            AND RTRIM(l.MAT_CODE)=RTRIM(b.child_item)
          WHERE ISNULL(l.SET_EXCEPT_FLAG,'0')='1'
            AND ISNULL(b.set_except,0) <> 1
          ORDER BY h.item_code, b.child_item"""
cur.execute(SEL)
rows = cur.fetchall()

print("=" * 96)
print(" 보정 대상 — nx.bom_line.set_except (라이브=제외, 클린=미제외)")
print("=" * 96)
if not rows:
    print("   대상 없음 — 이미 정합")
    nx.close(); sys.exit(0)
print("   {:<22s} {:<22s} {:<8s} {}".format("부모", "자재", "클린", "라이브"))
for r in rows[:15]:
    print("   {:<22s} {:<22s} {:<8s} {}".format(r[2], r[3], str(r[4]), r[5]))
if len(rows) > 15:
    print("   … 외 {}건".format(len(rows) - 15))
print("\n   총 {}건".format(len(rows)))

if not A.commit:
    print("\n   [DRY-RUN] --commit 을 붙이면 반영한다.")
    nx.close(); sys.exit(0)

# ── 백업(근거키 스코프)
cur.execute("IF OBJECT_ID('nx.bk_bomline_setexc_260909') IS NOT NULL DROP TABLE nx.bk_bomline_setexc_260909")
cur.execute("""CREATE TABLE nx.bk_bomline_setexc_260909(
                 bom_id int, seq int, item_code varchar(30), child_item varchar(30),
                 old_set_except bit, bk_dt datetime DEFAULT getdate())""")
nx.commit()
for r in rows:
    cur.execute("""INSERT INTO nx.bk_bomline_setexc_260909(bom_id,seq,item_code,child_item,old_set_except)
                   VALUES(?,?,?,?,?)""", r[0], r[1], r[2], r[3], r[4])
nx.commit()
print("\n   백업 nx.bk_bomline_setexc_260909 — {}행".format(len(rows)))

n = 0
for r in rows:
    cur.execute("UPDATE nx.bom_line SET set_except=1 WHERE bom_id=? AND seq=?", r[0], r[1])
    n += cur.rowcount
nx.commit()
print("   반영 {}행".format(n))

# ── 재검증
cur.execute(SEL)
left = len(cur.fetchall())
print("\n   재검증 — 남은 결손 {}건 {}".format(left, "✔" if left == 0 else "★"))

cur.execute("""SELECT COUNT(*),
      SUM(CASE WHEN RTRIM(ISNULL(CAST(v.SET_EXCEPT_FLAG AS nvarchar(5)),'0'))
                = RTRIM(ISNULL(CAST(l.SET_EXCEPT_FLAG AS nvarchar(5)),'0')) THEN 1 ELSE 0 END)
   FROM nx.v_pr_bom v
   JOIN PARTNER_ERP.dbo.PR_M_ITEM_BOM l
     ON RTRIM(l.ITEM_CODE)=RTRIM(v.ITEM_CODE) AND RTRIM(l.MAT_CODE)=RTRIM(v.MAT_CODE)""")
t, s = cur.fetchone()
print("   뷰 vs 라이브 SET_EXCEPT_FLAG 일치 {:,}/{:,} ({:.2f}%)".format(
    s or 0, t, 100.0 * (s or 0) / t if t else 0))
nx.close()
