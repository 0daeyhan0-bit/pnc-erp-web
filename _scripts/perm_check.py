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

show("현재 로그인/사용자/역할", """
SELECT SUSER_SNAME() login_name, USER_NAME() db_user
""")
show("DB 레벨 권한 (CREATE TABLE 포함 여부)", """
SELECT permission_name, state_desc
FROM fn_my_permissions(NULL, 'DATABASE')
WHERE permission_name IN ('CREATE TABLE','ALTER','CONTROL','INSERT','SELECT')
ORDER BY permission_name
""")
show("소속 DB 역할", """
SELECT r.name AS role_name
FROM sys.database_role_members m
JOIN sys.database_principals r ON r.principal_id = m.role_principal_id
JOIN sys.database_principals u ON u.principal_id = m.member_principal_id
WHERE u.name = USER_NAME()
""")
show("Gemini 테이블 현재 존재/건수", """
SELECT 'CM_ITEM_MST' t, COUNT(*) c FROM CM_ITEM_MST
""")
# who created / owns it
show("CM_ITEM_MST 스키마/소유", """
SELECT SCHEMA_NAME(schema_id) sch, name, create_date, modify_date
FROM sys.tables WHERE name='CM_ITEM_MST'
""")
