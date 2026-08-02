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

# 1) 현재 DB 목록
print("===== 서버 DB 목록 =====")
try:
    print(q("master","SELECT name FROM sys.databases ORDER BY name").to_string(index=False))
except Exception as e:
    print("ERR:", e)

# 2) CREATE DATABASE 서버권한 여부
print("\n===== ilshin 서버 권한 (CREATE DATABASE 가능?) =====")
try:
    print(q("master","""
    SELECT permission_name, state_desc
    FROM sys.server_permissions sp
    JOIN sys.server_principals pr ON pr.principal_id=sp.grantee_principal_id
    WHERE pr.name=SUSER_SNAME() AND permission_name LIKE '%DATABASE%'
    """).to_string(index=False))
    print("IS sysadmin:", q("master","SELECT IS_SRVROLEMEMBER('sysadmin') a, IS_SRVROLEMEMBER('dbcreator') b").to_string(index=False))
except Exception as e:
    print("ERR:", e)

# 3) PNC_ERP_NEW 존재/권한 확인
print("\n===== PNC_ERP_NEW 상태 =====")
try:
    exists = q("master","SELECT COUNT(*) c FROM sys.databases WHERE name='PNC_ERP_NEW'").iloc[0,0]
    print("존재:", exists)
    if exists:
        print("CREATE TABLE 허용:", q("PNC_ERP_NEW","SELECT HAS_PERMS_BY_NAME(NULL,'DATABASE','CREATE TABLE') x").iloc[0,0])
        print("기존 테이블 수:", q("PNC_ERP_NEW","SELECT COUNT(*) c FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'").iloc[0,0])
except Exception as e:
    print("ERR:", e)
