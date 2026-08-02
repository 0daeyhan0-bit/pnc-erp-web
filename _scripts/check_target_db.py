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

for db in ["ILSHIN_ERP_NEW","PARTNER_ERP_TEST","PARTNER_ERP_TEST3"]:
    print(f"\n===== {db} =====")
    try:
        perm=q(db,"SELECT HAS_PERMS_BY_NAME(NULL,'DATABASE','CREATE TABLE') can_create")
        cnt=q(db,"SELECT COUNT(*) tbls FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'")
        print(f"CREATE TABLE 허용: {perm.iloc[0,0]}  |  기존 테이블 수: {cnt.iloc[0,0]}")
        sample=q(db,"SELECT TOP 15 TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME")
        if len(sample): print("샘플 테이블:", ", ".join(sample['TABLE_NAME'].tolist()))
    except Exception as e:
        print("ERR:", e)
