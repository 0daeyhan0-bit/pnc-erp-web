# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client

def show(title, q):
    print(f"\n===== {title} =====")
    try:
        print(db_client.run_query(q).to_string(index=False))
    except Exception as e:
        print("ERR:", e)

show("HAS_PERMS: CREATE TABLE (1=허용,0=거부)", """
SELECT HAS_PERMS_BY_NAME(NULL,'DATABASE','CREATE TABLE') AS can_create_table,
       HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','CONTROL') AS db_control
""")

show("DB 권한 중 DENY 항목 (주체별)", """
SELECT dp.state_desc, dp.permission_name,
       pr.name AS principal_name, pr.type_desc
FROM sys.database_permissions dp
JOIN sys.database_principals pr ON pr.principal_id = dp.grantee_principal_id
WHERE dp.state_desc = 'DENY'
ORDER BY pr.name, dp.permission_name
""")

show("기존 CM_ITEM_MST 에 대한 내 권한(INSERT/DELETE/ALTER)", """
SELECT HAS_PERMS_BY_NAME('dbo.CM_ITEM_MST','OBJECT','INSERT') can_insert,
       HAS_PERMS_BY_NAME('dbo.CM_ITEM_MST','OBJECT','DELETE') can_delete,
       HAS_PERMS_BY_NAME('dbo.CM_ITEM_MST','OBJECT','ALTER')  can_alter
""")

show("다른 DB 목록(신규 ERP용 별도 DB 후보 확인)", """
SELECT name FROM sys.databases ORDER BY name
""")
