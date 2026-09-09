# -*- coding: utf-8 -*-
"""item_sub 포장·작업자 4종 — 이관 잔여분 마무리 (2026-09-09)

■ 배경 (어제 9/8 §6-2, 커밋 2ccaddd)
  포장종류·포장수량·용접자(생산자)·검사자 4종을 클린 nx.item_sub 로 전환했고,
  조회는 COALESCE(클린, 미러) **한시적 폴백**을 두었다.
  당시 기록: "품목마스터 이관이 끝나면 폴백을 지운다. 지금은 FK 충돌(3,144 중 3,141)로 막혀 있다"

■ ★그 전제가 틀렸다 (2026-09-09 실측)
     · nx.item_sub 에 **FK 가 없다** — 이관을 막는 제약이 지금은 없다
     · 충돌 3,141건은 **미러·라이브 PR_M_ITEM 어디에도 없는 품목**(양쪽 0건)
       = 품목마스터에서 사라진 고아행. 품목 이관을 해도 생기지 않는다.
     · 그 품목들은 폐기품이다 —
          생산실적 최근1년 0종 · 출하 최근1년 0종
          생산스티커 최근일자 2023-09-06 (최근 1년 0건)

  ⟹ 폴백을 유지할 근거가 없다. 이관 가능한 잔여분만 옮기고 폴백을 제거한다(§1-9-1).

■ 이 스크립트가 하는 일
  미러에 4종 값이 있고 · nx.item 에 품목이 있고 · 클린 item_sub 에 아직 행이 없는 것만 INSERT.
  ★이미 클린에 행이 있으면 건드리지 않는다(어제 겪은 덮어쓰기 사고 방지 — DELETE→INSERT 금지).
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

SEL = """SELECT RTRIM(s.ITEM_CODE),
                RTRIM(ISNULL(CAST(s.PACK_KIND AS nvarchar(50)),'')),
                ISNULL(s.PACK_QTY,0),
                RTRIM(ISNULL(s.PROD_WORKER,'')),
                RTRIM(ISNULL(s.INSP_WORKER,''))
           FROM nx.PR_M_ITEM_SUB s
          WHERE (ISNULL(RTRIM(CAST(s.PACK_KIND AS nvarchar(50))),'')<>''
              OR ISNULL(s.PACK_QTY,0)<>0
              OR ISNULL(RTRIM(s.PROD_WORKER),'')<>''
              OR ISNULL(RTRIM(s.INSP_WORKER),'')<>'')
            AND EXISTS(SELECT 1 FROM nx.item i WHERE RTRIM(i.item_code)=RTRIM(s.ITEM_CODE))
            AND NOT EXISTS(SELECT 1 FROM nx.item_sub c WHERE RTRIM(c.item_code)=RTRIM(s.ITEM_CODE))
          ORDER BY s.ITEM_CODE"""
cur.execute(SEL)
rows = cur.fetchall()

print("=" * 92)
print(" 이관 대상 — 미러에 값 있고 · 품목 있고 · 클린에 행 없는 것")
print("=" * 92)
if not rows:
    print("   대상 없음 — 이미 이관 완료")
else:
    print("   {:<22s} {:<12s} {:>6s} {:<10s} {}".format("품번", "포장종류", "수량", "생산자", "검사자"))
    for a, b, c, d, e in rows:
        print("   {:<22s} {:<12s} {:>6} {:<10s} {}".format(a[:22], b[:12], c, d, e))
    print("\n   {}건".format(len(rows)))

if not A.commit:
    print("\n   [DRY-RUN] --commit 을 붙이면 반영한다.")
    nx.close(); sys.exit(0)

if rows:
    cur.execute("""IF OBJECT_ID('nx.bk_itemsub_finish_260909') IS NOT NULL
                   DROP TABLE nx.bk_itemsub_finish_260909""")
    cur.execute("""CREATE TABLE nx.bk_itemsub_finish_260909(
                     item_code varchar(30), bk_dt datetime DEFAULT getdate())""")
    for r in rows:
        cur.execute("INSERT INTO nx.bk_itemsub_finish_260909(item_code) VALUES(?)", r[0])
    nx.commit()
    print("\n   백업(대상 목록) nx.bk_itemsub_finish_260909 — {}행".format(len(rows)))

    n = 0
    for code, pk, pq, pw, iw in rows:
        cur.execute("""INSERT INTO nx.item_sub(item_code, pack_kind, pack_qty, prod_worker, insp_worker)
                       VALUES(?,?,?,?,?)""", code, (pk or None), (pq or None), (pw or None), (iw or None))
        n += cur.rowcount
    nx.commit()
    print("   이관 {}행".format(n))

cur.execute(SEL)
print("\n   재검증 — 남은 이관대상 {}건".format(len(cur.fetchall())))
cur.execute("""SELECT COUNT(*) FROM nx.item_sub
                WHERE ISNULL(RTRIM(CAST(pack_kind AS nvarchar(50))),'')<>''
                   OR ISNULL(pack_qty,0)<>0
                   OR ISNULL(RTRIM(prod_worker),'')<>''
                   OR ISNULL(RTRIM(insp_worker),'')<>''""")
print("   클린 4종 보유행 {:,}건".format(cur.fetchone()[0]))
nx.close()
