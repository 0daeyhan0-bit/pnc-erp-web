# -*- coding: utf-8 -*-
# 마무리: 미정규 변형2 sub_alias+nx.item 추가 + 용접링 결합코드 사급플래그 기록. nx 쓰기·멱등.
import sys
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
def RO(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD};ApplicationIntent=ReadOnly')
def NX(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)
c=RO().cursor(); n=NX(); w=n.cursor()

# 1) 미정규 변형2 → sub_alias(SUB, 이젠터2068) + nx.item
adds=[('AJJ74578301-3-1','AJJ74578301-S2-1','AJJ74578301-S2-1_S01'),
      ('AJJ74578301-3-2','AJJ74578301-S2-1','AJJ74578301-S2-1_S02')]
for variant, base, canon in adds:
    w.execute("DELETE FROM nx.sub_alias WHERE variant=?", variant)
    w.execute("""INSERT INTO nx.sub_alias(variant,real_base,category,canonical,is_shared,n_ref_base,route_gubun,route_vendor,sig,item_desc)
                 VALUES(?,?,?,?,?,?,?,?,?,?)""", variant, base, 'SUB', canon, 0, 1, '외주','2068','', '이젠터 SUB(미정규보강)')
    w.execute("SELECT 1 FROM nx.item WHERE item_code=?", canon)
    if not w.fetchone():
        w.execute("""INSERT INTO nx.item(item_code,item_name,item_type,item_source,make_type,status,active)
                     VALUES(?,?,?,?,?,?,?)""", canon, f"SUB {base}", '반제품','NORM_SUB','2','사용',1)
n.commit()
print("미정규 변형2 sub_alias+nx.item 추가 완료:", [a[0] for a in adds])

# 2) 용접링 결합/순수 코드 사급 플래그 표시 = nx.sub_alias에 참고행? → 별도 마킹 테이블(멱등)
c.execute("SELECT DISTINCT MAT_CODE FROM PR_M_ITEM_BOM WHERE ISNULL(EXCEPT_FLAG,'0')<>'1' AND MAT_CODE LIKE '%용접링%'")
rings=[x[0].strip() for x in c.fetchall()]
w.execute("IF OBJECT_ID('nx.weldring_sagub','U') IS NOT NULL DROP TABLE nx.weldring_sagub")
w.execute("CREATE TABLE nx.weldring_sagub(item_code nvarchar(60) PRIMARY KEY, kind nvarchar(20), note nvarchar(120), load_dt datetime DEFAULT getdate())")
for cd in rings:
    kind='관+링결합' if '+용접링' in cd else '순수링'
    w.execute("INSERT INTO nx.weldring_sagub(item_code,kind,note) VALUES(?,?,?)", cd, kind, '용접링=사급부품(BOM유지·사급출고→삽입→입고)')
n.commit()
print(f"용접링 사급플래그: {len(rings)}개 (nx.weldring_sagub). 관+링 결합 {sum(1 for c in rings if '+용접링' in c)}·순수링 {sum(1 for c in rings if '+용접링' not in c)}")

# 검증: 미정규 잔여 0?
w.execute("SELECT COUNT(*) FROM nx.sub_alias WHERE variant IN ('AJJ74578301-3-1','AJJ74578301-3-2')")
print("보강 확인:", w.fetchone()[0], "/ 2")
n.close(); print("DONE")
