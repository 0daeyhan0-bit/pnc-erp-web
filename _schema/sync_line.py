# -*- coding: utf-8 -*-
"""[프로그램 이관] LINE-NO MASTER  PR_M_LINE_NO(레거시 w_pr_master_190) → nx.line_no
- 전 업무컬럼 6개 구현(라인번호·적용일·리드일·시각·연결거래처·거래처리드). 멱등(line_no 신규만)."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import db_client, pyodbc
cn = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)
c = cn.cursor()
DDL="CREATE TABLE nx.line_no (line_no NVARCHAR(20) NOT NULL PRIMARY KEY, apply_ymd NVARCHAR(6), maint_day INT, maint_hhmm NVARCHAR(4), link_cust_code NVARCHAR(10), cust_maint_day INT, upd_user NVARCHAR(40), upd_dt DATETIME DEFAULT GETDATE())"
c.execute("IF OBJECT_ID('nx.line_no') IS NULL EXEC('"+DDL.replace("'","''")+"')"); cn.commit()
c.execute("SELECT COUNT(*) FROM nx.line_no"); before=c.fetchone()[0]
c.execute("""INSERT INTO nx.line_no(line_no,apply_ymd,maint_day,maint_hhmm,link_cust_code,cust_maint_day,upd_user)
  SELECT LTRIM(RTRIM(LINE_NO)),LTRIM(RTRIM(APPLY_YMD)),ISNULL(MAINT_DAY,0),LTRIM(RTRIM(MAINT_HHMM)),
    LTRIM(RTRIM(LINK_CUST_CODE)),CUST_MAINT_DAY,'MIGRATION'
  FROM PARTNER_ERP.dbo.PR_M_LINE_NO s
  WHERE LTRIM(RTRIM(s.LINE_NO)) NOT IN (SELECT line_no FROM nx.line_no)""")
ins=c.rowcount; cn.commit()
c.execute("SELECT COUNT(*) FROM nx.line_no"); after=c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM PARTNER_ERP.dbo.PR_M_LINE_NO"); leg=c.fetchone()[0]
print(f"삽입 {ins} → nx.line_no {before}→{after} · 검증 레거시 {leg} {'OK' if leg==after else '★불일치'}")
c.execute("SELECT TOP 4 line_no,apply_ymd,maint_day,maint_hhmm FROM nx.line_no ORDER BY line_no")
for r in c.fetchall(): print("  ",[str(x) for x in r])
