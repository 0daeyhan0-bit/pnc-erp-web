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

db="PARTNER_ERP_TEST2"
print(f"===== {db} =====")
try:
    print("CREATE TABLE 허용:", q(db,"SELECT HAS_PERMS_BY_NAME(NULL,'DATABASE','CREATE TABLE') x").iloc[0,0])
    print("DENY 항목:", q(db,"""SELECT dp.permission_name FROM sys.database_permissions dp
        JOIN sys.database_principals pr ON pr.principal_id=dp.grantee_principal_id
        WHERE dp.state_desc='DENY' AND pr.name=USER_NAME()""")['permission_name'].tolist())
    print("역할:", q(db,"""SELECT r.name FROM sys.database_role_members m
        JOIN sys.database_principals r ON r.principal_id=m.role_principal_id
        JOIN sys.database_principals u ON u.principal_id=m.member_principal_id
        WHERE u.name=USER_NAME()""")['name'].tolist())
    print("총 테이블 수:", q(db,"SELECT COUNT(*) c FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'").iloc[0,0])
    # 마이그레이션 원본 테이블 존재 여부
    srcs=['PR_M_ITEM','PR_M_ITEM_COST','CM_M_CUST','품목별_매입처정보2','LG_UNIT_PRICE_DOOSUNG']
    inlist=",".join(f"N'{s}'" for s in srcs)
    have=q(db,f"""SELECT TABLE_NAME, (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES) dummy
        FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME IN ({inlist})""")['TABLE_NAME'].tolist()
    print("원본 테이블 존재:", have)
    if 'PR_M_ITEM' in have:
        print("PR_M_ITEM 건수:", q(db,"SELECT COUNT(*) c FROM PR_M_ITEM").iloc[0,0])
    # 이미 v2 테이블 있는지
    print("기존 CM_ITEM_MST 존재:", q(db,"SELECT COUNT(*) c FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='CM_ITEM_MST'").iloc[0,0])
except Exception as e:
    print("ERR:", e)
