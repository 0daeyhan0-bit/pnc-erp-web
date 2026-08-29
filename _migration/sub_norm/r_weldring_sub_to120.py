# -*- coding: utf-8 -*-
"""용접링 포함 SUB(이름 '용접링')인데 sgroup≠120/230 → 120(SUB ASSY)로 교정.
   규칙(사용자 확정): 용접링을 포함한 가공품 = 서브(SUB=120). ITEM_MASTER_CLASSIFY_DESIGN §2·§5 step2 계열.
   안전: 백업 nx.item_bak_weldsub120 · 근거키(item_code) 스코프 · sgroup만 · --commit 없으면 DRY.
   sgroup은 nx.item 소유(sync 제외 완료·Step1). 원가엔진 미참조(표시/집계)나 적용 후 diff0 재확인 권장."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
DRY = ('--commit' not in sys.argv)
n = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c = n.cursor()
SEL = """SELECT item_code, item_name, ISNULL(sgroup,'(null)'), ISNULL(make_type,'')
  FROM nx.item WHERE item_name LIKE '%용접링%' AND ISNULL(sgroup,'') NOT IN ('120','230')"""
c.execute(SEL); rows = c.fetchall()
print(f"대상(용접링-이름 & sg≠120/230) = {len(rows)}건:")
for r in rows: print(f"  {r[0]} | {r[1][:26]} | sg={r[2]} → 120 | mk={r[3]}")
if DRY:
    print("DRY (--commit 로 적용)"); n.close(); sys.exit()
c.execute("IF OBJECT_ID('nx.item_bak_weldsub120','U') IS NULL SELECT item_code, sgroup INTO nx.item_bak_weldsub120 FROM nx.item WHERE item_name LIKE '%용접링%' AND ISNULL(sgroup,'') NOT IN ('120','230')")
print("백업: nx.item_bak_weldsub120")
r = c.execute("UPDATE nx.item SET sgroup='120' WHERE item_name LIKE '%용접링%' AND ISNULL(sgroup,'') NOT IN ('120','230')").rowcount
print(f"UPDATE sgroup→120: {r}행")
c.execute(SEL); left = c.fetchall()
print(f"검증: 잔여(sg≠120/230) = {len(left)} ({'★PASS' if len(left)==0 else 'FAIL'})")
n.close()
