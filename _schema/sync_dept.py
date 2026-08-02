# -*- coding: utf-8 -*-
"""[프로그램 이관] 부서MASTER  HR_M_DEPT(레거시 w_hr_master_010) → nx.dept
- 전 업무컬럼 구현(빈 다국어명/remarks 4종은 이관제외 제안). 멱등(dept_code 신규만).
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import db_client, pyodbc
cn = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)
c = cn.cursor()
DDL = """CREATE TABLE nx.dept (
  dept_code NVARCHAR(4) NOT NULL PRIMARY KEY, dept_desc NVARCHAR(30), sort_key INT,
  dept_desch NVARCHAR(30), dept_from_ymd NVARCHAR(8), dept_to_ymd NVARCHAR(8),
  fin_dept_code NVARCHAR(4), fin_from_ymd NVARCHAR(8), fin_to_ymd NVARCHAR(8),
  enterprise_dept NVARCHAR(2), wh_code NVARCHAR(2), use_flag BIT DEFAULT 1,
  remarks NVARCHAR(100), upd_user NVARCHAR(40), upd_dt DATETIME DEFAULT GETDATE())"""
c.execute("IF OBJECT_ID('nx.dept') IS NULL BEGIN EXEC('"+DDL.replace("'","''").replace(chr(10)," ")+"') END")
cn.commit()
c.execute("SELECT COUNT(*) FROM nx.dept"); before=c.fetchone()[0]
c.execute("""INSERT INTO nx.dept(dept_code,dept_desc,sort_key,dept_desch,dept_from_ymd,dept_to_ymd,
    fin_dept_code,fin_from_ymd,fin_to_ymd,enterprise_dept,wh_code,use_flag,remarks,upd_user)
  SELECT LTRIM(RTRIM(DEPT_CODE)),LTRIM(RTRIM(DEPT_DESC)),ISNULL(SORT_KEY,0),LTRIM(RTRIM(DEPT_DESCH)),
    LTRIM(RTRIM(DEPT_FROM_YYMD)),LTRIM(RTRIM(DEPT_TO_YYMD)),LTRIM(RTRIM(FIN_DEPT_CODE)),
    LTRIM(RTRIM(FIN_FROM_YYMD)),LTRIM(RTRIM(FIN_TO_YYMD)),LTRIM(RTRIM(ENTERPRISE_DEPT)),LTRIM(RTRIM(WH_CODE)),
    CASE WHEN LTRIM(RTRIM(ISNULL(USE_FLAG,'1')))='0' THEN 0 ELSE 1 END, LTRIM(RTRIM(REMARKS)),'MIGRATION'
  FROM PARTNER_ERP.dbo.HR_M_DEPT s
  WHERE LTRIM(RTRIM(s.DEPT_CODE)) NOT IN (SELECT dept_code FROM nx.dept)""")
ins=c.rowcount; cn.commit()
c.execute("SELECT COUNT(*) FROM nx.dept"); after=c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM PARTNER_ERP.dbo.HR_M_DEPT"); leg=c.fetchone()[0]
print(f"삽입 {ins} → nx.dept {before}→{after} · 검증 레거시 {leg} {'OK' if leg==after else '★불일치'}")
c.execute("SELECT TOP 4 dept_code,dept_desc,sort_key,use_flag FROM nx.dept ORDER BY sort_key")
for r in c.fetchall(): print("  ",[str(x) for x in r])
