# -*- coding: utf-8 -*-
# ★Phase R1: nx.item item_source 컬럼 + 테스트_S 정리 + 정규 SUB 1203 등록(내부SUB). nx 쓰기·멱등.
import sys
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
def NX(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)
n=NX(); w=n.cursor()

# 1) item_source 컬럼(멱등)
w.execute("IF COL_LENGTH('nx.item','item_source') IS NULL ALTER TABLE nx.item ADD item_source nvarchar(20) NULL")
n.commit(); print("[1] item_source 컬럼 OK")

# 2) 테스트 잔재 삭제(_S01~06, 참조0 확인됨) — _S07 보존
junk=[f'AJR75563402_S0{i}' for i in range(1,7)]
# 안전 재확인: 참조 없나
del_ok=[]
for t in junk:
    ref=0
    for tbl,col in [('nx.bom','child_code'),('nx.bom','parent_code'),('nx.routing','item_code'),('nx.stock_ledger','ITEM_CODE'),('nx.sourcing_route_line','sub_item'),('nx.sourcing_route_line','child_item')]:
        w.execute(f"SELECT COUNT(*) FROM {tbl} WHERE {col}=?", t)
        ref+=w.fetchone()[0]
    if ref==0: del_ok.append(t)
for t in del_ok: w.execute("DELETE FROM nx.item WHERE item_code=?", t)
n.commit(); print(f"[2] 테스트 잔재 삭제: {del_ok} (참조0 확인) · _S07 보존")

# 3) 정규 canonical 등록 (NOT MATCHED 멱등)
w.execute("""SELECT canonical, MIN(real_base),
                MAX(CASE WHEN route_gubun='사내' THEN 1 ELSE 0 END),
                MAX(CASE WHEN route_gubun LIKE '외주%' THEN 1 ELSE 0 END),
                MAX(CASE WHEN route_gubun='매입' THEN 1 ELSE 0 END)
             FROM nx.sub_alias WHERE category IN ('SUB','SUB_SHARED') AND canonical IS NOT NULL
             GROUP BY canonical""")
cans=w.fetchall()
ins=0; skip=0
for canon, base, sanae, oj, mai in cans:
    w.execute("SELECT 1 FROM nx.item WHERE item_code=?", canon)
    if w.fetchone(): skip+=1; continue
    mk = '2' if oj else ('1' if sanae else ('3' if mai else ''))
    w.execute("""INSERT INTO nx.item(item_code,item_name,item_type,item_source,make_type,status,active)
                 VALUES(?,?,?,?,?,?,?)""", canon, f"SUB {base}", '반제품', 'NORM_SUB', mk, '사용', 1)
    ins+=1
n.commit()
print(f"[3] 정규 SUB 등록: 신규 {ins} · 기존스킵 {skip} (총 {len(cans)})")

# 검증
w.execute("SELECT COUNT(*) FROM nx.item WHERE item_source='NORM_SUB'")
print(f"[검증] nx.item item_source='NORM_SUB': {w.fetchone()[0]}")
w.execute("SELECT COUNT(*) FROM nx.item WHERE item_code LIKE '%[_]S[0-9][0-9]' AND item_code LIKE 'AJR75563402%'")
print(f"  AJR75563402_S 잔여(=_S07 등): {w.fetchone()[0]}")
w.execute("SELECT item_code,item_name,item_type,item_source,make_type FROM nx.item WHERE item_source='NORM_SUB' AND item_code LIKE 'AJR75563402%'")
for r in w.fetchall(): print("   샘플:", list(r))
n.close(); print("DONE")
