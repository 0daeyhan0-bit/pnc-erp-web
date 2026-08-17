# -*- coding: utf-8 -*-
# 미상 잔여 = 미운영(해체) SUB → 하위 단품. nx.sub_alias category='DISSOLVED', route='단품' 표시
import sys
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
def NX(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)
n=NX(); w=n.cursor()
# category 컬럼은 nvarchar(20) — 값 확장 가능
w.execute("SELECT variant, canonical, item_desc FROM nx.sub_alias WHERE route_gubun='미상' ORDER BY variant")
before=[(r[0],r[1],r[2]) for r in w.fetchall()]
print(f"미운영(해체) 대상 {len(before)}건:")
for v,cn,d in before: print(f"  {v:<22} canon={cn}  {d[:34]}")
w.execute("UPDATE nx.sub_alias SET category='DISSOLVED', route_gubun='단품' WHERE route_gubun='미상'")
n.commit()
print(f"\nUPDATE {w.rowcount}건 → category=DISSOLVED, route=단품(하위 단품 운영)")
# 최종 요약
w.execute("SELECT category, COUNT(*) FROM nx.sub_alias GROUP BY category ORDER BY COUNT(*) DESC")
print("\n최종 category:", [tuple(x) for x in w.fetchall()])
w.execute("SELECT route_gubun, COUNT(*) FROM nx.sub_alias GROUP BY route_gubun ORDER BY COUNT(*) DESC")
print("최종 route:", [tuple(x) for x in w.fetchall()])
w.execute("SELECT COUNT(DISTINCT canonical) FROM nx.sub_alias WHERE category IN ('SUB','SUB_SHARED')")
print("운영 SUB 정규코드 수:", w.fetchone()[0])
n.close(); print("DONE")
