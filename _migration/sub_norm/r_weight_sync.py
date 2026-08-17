# -*- coding: utf-8 -*-
"""원가 100%(원소재 무게): nx.item.net_weight를 레거시 PR_M_ITEM.ITEM_WEIGHT와 동기화(SP가 쓰는 무게).
엔진은 net_weight로 원소재비=소재단가×무게 계산. 레거시 SP=ITEM_WEIGHT(수기저장, 기하와 미세차). 데이터 정합.
백업 nx.item_netweight_bak(item_code,net_weight). --commit 없으면 규모만."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
DRY=('--commit' not in sys.argv)
n=pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c=n.cursor()
LW="""(SELECT TOP 1 CAST(pi.ITEM_WEIGHT AS decimal(18,6)) FROM PARTNER_ERP.dbo.PR_M_ITEM pi
   WHERE pi.ITEM_CODE COLLATE DATABASE_DEFAULT=i.item_code COLLATE DATABASE_DEFAULT AND ISNULL(pi.ITEM_WEIGHT,0)<>0)"""
mis=c.execute(f"SELECT COUNT(*) FROM nx.item i WHERE {LW} IS NOT NULL AND ABS(ISNULL(i.net_weight,0)-{LW})>0.00001").fetchone()[0]
print(f"net_weight 불일치(라이브 ITEM_WEIGHT<>0): {mis}건")
if DRY: print("DRY (--commit 실행)"); n.close(); sys.exit()
c.execute("IF OBJECT_ID('nx.item_netweight_bak','U') IS NOT NULL DROP TABLE nx.item_netweight_bak")
c.execute("SELECT item_code, net_weight INTO nx.item_netweight_bak FROM nx.item")
print("백업 nx.item_netweight_bak:", c.execute("SELECT COUNT(*) FROM nx.item_netweight_bak").fetchone()[0])
c.execute(f"UPDATE i SET net_weight={LW} FROM nx.item i WHERE {LW} IS NOT NULL AND ABS(ISNULL(i.net_weight,0)-{LW})>0.00001")
print("동기화 완료. 되돌리기: nx.item_netweight_bak 로 net_weight 복원")
n.close()
