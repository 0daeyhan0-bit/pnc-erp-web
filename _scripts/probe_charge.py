# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
def show(t,q):
    print(f"\n== {t} ==")
    try: print(db_client.run_query(q).to_string(index=False))
    except Exception as e: print("ERR:", str(e)[:150])

show("CHARGE_NAME/USER_ID 채워짐 통계", "SELECT SUM(CASE WHEN ISNULL(CHARGE_NAME,'')<>'' THEN 1 ELSE 0 END) has_name, SUM(CASE WHEN ISNULL(CHARGE_USER_ID,'')<>'' THEN 1 ELSE 0 END) has_uid, COUNT(*) tot FROM cm_m_cust")
show("CM_M_USERS_INFO 컬럼", "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='CM_M_USERS_INFO' AND (COLUMN_NAME LIKE '%USER%' OR COLUMN_NAME LIKE '%NAME%' OR COLUMN_NAME LIKE '%EMP%')")
show("샘플: 매입처→담당ID→담당명", """
SELECT TOP 8 c.cust_code, c.cust_desc, c.CHARGE_USER_ID, c.CHARGE_NAME, u.USER_NAME
FROM cm_m_cust c LEFT JOIN CM_M_USERS_INFO u ON u.USER_ID=c.CHARGE_USER_ID
WHERE ISNULL(c.CHARGE_USER_ID,'')<>'' ORDER BY c.cust_code
""")
