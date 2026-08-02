# -*- coding: utf-8 -*-
import sys, io, os, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pyodbc, pandas as pd
from dotenv import load_dotenv
load_dotenv(r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP\.env")
S=os.getenv("DB_SERVER"); P=os.getenv("DB_PORT","10151"); U=os.getenv("DB_USER"); PW=os.getenv("DB_PASSWORD")

def q(db, sql):
    cs=f"DRIVER={{SQL Server}};SERVER={S},{P};DATABASE={db};UID={U};PWD={PW}"
    conn=pyodbc.connect(cs)
    try:
        return pd.read_sql(sql, conn)
    finally:
        conn.close()

db="ILSHIN_ERP_NEW"   # 신규 ERP용 기존 DB (→ PNC_ERP_NEW 로 명명 예정)
print(f"===== 신규 ERP DB (현 {db}) 상태 =====")
try:
    print("CREATE TABLE 허용:", q(db,"SELECT HAS_PERMS_BY_NAME(NULL,'DATABASE','CREATE TABLE') x").iloc[0,0])
    print("DENY 항목:")
    print(q(db,"""SELECT dp.state_desc, dp.permission_name, pr.name principal
                 FROM sys.database_permissions dp
                 JOIN sys.database_principals pr ON pr.principal_id=dp.grantee_principal_id
                 WHERE dp.state_desc='DENY'""").to_string(index=False))
    print("소속 역할:", ", ".join(q(db,"""SELECT r.name FROM sys.database_role_members m
                 JOIN sys.database_principals r ON r.principal_id=m.role_principal_id
                 JOIN sys.database_principals u ON u.principal_id=m.member_principal_id
                 WHERE u.name=USER_NAME()""")['name'].tolist()) or "(none)")
    cnt=q(db,"SELECT COUNT(*) c FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'").iloc[0,0]
    print("기존 테이블 수:", cnt)
    if cnt:
        print("샘플:", ", ".join(q(db,"SELECT TOP 20 TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME")['TABLE_NAME'].tolist()))
except Exception as e:
    print("ERR:", e)
