# -*- coding: utf-8 -*-
"""원가 100%(nx.item 마스터 stale): nx.item의 원가관련 필드를 live PR_M_ITEM와 동기화.
엔진은 nx.item(cg·metal·치수·make_type)으로 재료비·전개 판정. SP는 live 사용 → 낡으면 갭.
동기화 필드: cost_gubun·metal_gubun·make_type·diam·thick·length (객관적 마스터, SP정합).
백업 nx.item_costfld_bak. --commit 없으면 규모만. ※nature/prod_group 등 재설계 필드는 미변경."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
DRY=('--commit' not in sys.argv)
n=pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c=n.cursor()
J="""nx.item i JOIN PARTNER_ERP.dbo.PR_M_ITEM p ON p.ITEM_CODE COLLATE DATABASE_DEFAULT=i.item_code COLLATE DATABASE_DEFAULT"""
where=("""ISNULL(LTRIM(RTRIM(i.cost_gubun)),'')<>ISNULL(LTRIM(RTRIM(p.COST_GUBUN)),'')
 OR ISNULL(LTRIM(RTRIM(i.metal_gubun)),'')<>ISNULL(LTRIM(RTRIM(p.METAL_GUBUN)),'')
 OR ISNULL(LTRIM(RTRIM(i.make_type)),'')<>ISNULL(LTRIM(RTRIM(p.MAKE_TYPE)),'')
 OR ABS(ISNULL(i.diam,0)-ISNULL(p.ITEM_DIAM,0))>0.001
 OR ABS(ISNULL(i.thick,0)-ISNULL(p.ITEM_THICK,0))>0.001
 OR ABS(ISNULL(i.length,0)-ISNULL(p.ITEM_LENGTH,0))>0.001""")
mis=c.execute(f"SELECT COUNT(*) FROM {J} WHERE {where}").fetchone()[0]
print(f"nx.item 원가필드 불일치: {mis}건")
if DRY: print("DRY (--commit 실행)"); n.close(); sys.exit()
c.execute("IF OBJECT_ID('nx.item_costfld_bak','U') IS NOT NULL DROP TABLE nx.item_costfld_bak")
c.execute("SELECT item_code, cost_gubun, metal_gubun, make_type, diam, thick, length INTO nx.item_costfld_bak FROM nx.item")
print("백업 nx.item_costfld_bak:", c.execute("SELECT COUNT(*) FROM nx.item_costfld_bak").fetchone()[0])
c.execute(f"""UPDATE i SET
   cost_gubun=LTRIM(RTRIM(p.COST_GUBUN)), metal_gubun=LTRIM(RTRIM(p.METAL_GUBUN)), make_type=LTRIM(RTRIM(p.MAKE_TYPE)),
   diam=p.ITEM_DIAM, thick=p.ITEM_THICK, length=p.ITEM_LENGTH
   FROM {J} WHERE {where}""")
print("동기화 완료. 되돌리기: nx.item_costfld_bak")
n.close()
