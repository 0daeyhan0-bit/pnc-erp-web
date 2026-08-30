# -*- coding: utf-8 -*-
"""nx.item.has_gagong 정합: 정본 = nx.PR_M_ITEM_PROC_GAGONG 멤버십(소요엔진 _has_gagong가 쓰는 그 소스).
   has_gagong는 여러 빌드/드리프트정합 INSERT 시점 스냅샷(일부 0 하드코딩)이라 PROC_GAGONG 변경에 재싱크 안 됨 → 드리프트.
   규칙: nx.item에 존재하는 품목에 대해 has_gagong = 1 if 품목 in PROC_GAGONG else 0.
   (PROC_GAGONG에만 있고 어느 마스터에도 없는 고아 레코드는 nx.item 대상 아님=미변경.)
   --commit 없으면 변경목록만(DRY). 백업 nx.item_has_gagong_bak."""
import sys, io, os
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
DRY = ('--commit' not in sys.argv)
n = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c = n.cursor()

c.execute("SELECT DISTINCT UPPER(LTRIM(RTRIM(item_code))) FROM nx.PR_M_ITEM_PROC_GAGONG")
PROC = set(r[0] for r in c.fetchall())
# nx.item 현행 has_gagong
c.execute("SELECT UPPER(LTRIM(RTRIM(item_code))), ISNULL(has_gagong,0), ISNULL(use_flag,0), ISNULL(item_name,'') FROM nx.item")
rows = c.fetchall()
to1 = []  # 0->1 (공정있는데 플래그0)
to0 = []  # 1->0 (공정없는데 플래그1)
for code, hg, uf, nm in rows:
    want = 1 if code in PROC else 0
    cur = 1 if hg else 0                 # ★has_gagong=bit(True/False) → bool 판정(str 비교 금지)
    if want != cur:
        (to1 if want == 1 else to0).append((code, uf, nm))
print(f"has_gagong 정합(정본=PROC_GAGONG 멤버십):")
print(f"  0→1(공정보유·플래그누락) {len(to1)}건 (사용중 {sum(1 for x in to1 if x[1]==1)})")
print(f"  1→0(공정없음·플래그과표시) {len(to0)}건 (사용중 {sum(1 for x in to0 if x[1]==1)})")
print("  [1→0 전량]:")
for x in to0: print(f"     {x[0]} use={x[1]} {x[2][:30]}")
print("  [0→1 사용중만]:")
for x in [y for y in to1 if y[1]==1]: print(f"     {x[0]} use={x[1]} {x[2][:30]}")
if DRY:
    print(f"\nDRY (총 변경 {len(to1)+len(to0)}건). --commit 로 적용.")
    n.close(); sys.exit()
# 백업(멱등: 최초1회) + 적용
c.execute("IF OBJECT_ID('nx.item_has_gagong_bak','U') IS NULL SELECT item_code, has_gagong INTO nx.item_has_gagong_bak FROM nx.item")
u1 = c.execute("""UPDATE i SET has_gagong=1 FROM nx.item i
   WHERE EXISTS(SELECT 1 FROM nx.PR_M_ITEM_PROC_GAGONG g WHERE UPPER(LTRIM(RTRIM(g.item_code)))=UPPER(LTRIM(RTRIM(i.item_code))))
     AND ISNULL(i.has_gagong,0) NOT IN (1)""").rowcount
u0 = c.execute("""UPDATE i SET has_gagong=0 FROM nx.item i
   WHERE NOT EXISTS(SELECT 1 FROM nx.PR_M_ITEM_PROC_GAGONG g WHERE UPPER(LTRIM(RTRIM(g.item_code)))=UPPER(LTRIM(RTRIM(i.item_code))))
     AND ISNULL(i.has_gagong,0)=1""").rowcount
print(f"COMMIT: 0→1 {u1}건 / 1→0 {u0}건. 백업 nx.item_has_gagong_bak.")
# 검증: nx.item 내 불일치 0
mis = c.execute("""SELECT COUNT(*) FROM nx.item i WHERE
   (CASE WHEN EXISTS(SELECT 1 FROM nx.PR_M_ITEM_PROC_GAGONG g WHERE UPPER(LTRIM(RTRIM(g.item_code)))=UPPER(LTRIM(RTRIM(i.item_code)))) THEN 1 ELSE 0 END)
   <> (CASE WHEN ISNULL(i.has_gagong,0)=1 THEN 1 ELSE 0 END)""").fetchone()[0]
print(f"검증: nx.item has_gagong vs PROC_GAGONG 불일치={mis} ({'★PASS' if mis==0 else 'FAIL'})")
n.close()
