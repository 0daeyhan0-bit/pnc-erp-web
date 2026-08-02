# -*- coding: utf-8 -*-
"""[이관] 근무달력 HR_M_CALENDAR→nx.work_calendar · 파트별달력 PR_M_PART_CALENDAR→nx.part_calendar
- WORK_STATS(PR004 근무구분). 날짜 8/6자리→DATE. 멱등(키 신규만)."""
import sys, io, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import db_client, pyodbc
cn = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)
c = cn.cursor()
def iso(s):
    d = ''.join(ch for ch in str(s or '') if ch.isdigit())
    if len(d) == 6: d = '20' + d
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else None
c.execute("IF OBJECT_ID('nx.work_calendar') IS NULL CREATE TABLE nx.work_calendar (team NVARCHAR(2), cal_ymd DATE, work_stats NVARCHAR(2), remarks NVARCHAR(100), upd_user NVARCHAR(40), upd_dt DATETIME DEFAULT GETDATE(), CONSTRAINT pk_wcal PRIMARY KEY(team,cal_ymd))")
c.execute("IF OBJECT_ID('nx.part_calendar') IS NULL CREATE TABLE nx.part_calendar (part_code NVARCHAR(20), cal_ymd DATE, work_stats NVARCHAR(2), remarks NVARCHAR(100), upd_user NVARCHAR(40), upd_dt DATETIME DEFAULT GETDATE(), CONSTRAINT pk_pcal PRIMARY KEY(part_code,cal_ymd))")
cn.commit()
# 근무달력
c.execute("SELECT COUNT(*) FROM nx.work_calendar"); wb=c.fetchone()[0]
c.execute("SELECT LTRIM(RTRIM(WORK_TEAM)),CALENDAR_YYMD,LTRIM(RTRIM(WORK_STATS)),ISNULL(REMARKS,'') FROM PARTNER_ERP.dbo.HR_M_CALENDAR")
wr=[(r[0],iso(r[1]),r[2],str(r[3]).strip()) for r in c.fetchall()]
c.execute("SELECT team+'|'+CONVERT(varchar(10),cal_ymd,120) FROM nx.work_calendar"); have=set(x[0] for x in c.fetchall())
ins=0
for tm,dt,ws,rm in wr:
    if dt and f"{tm}|{dt}" not in have:
        c.execute("INSERT INTO nx.work_calendar(team,cal_ymd,work_stats,remarks,upd_user) VALUES(?,?,?,?,'MIGRATION')",tm,dt,ws,rm); ins+=1
cn.commit(); c.execute("SELECT COUNT(*) FROM nx.work_calendar"); print(f"근무달력 nx.work_calendar {wb}→{c.fetchone()[0]} (+{ins})")
# 파트별달력
c.execute("SELECT COUNT(*) FROM nx.part_calendar"); pb=c.fetchone()[0]
c.execute("SELECT LTRIM(RTRIM(PART_CODE)),CALENDAR_YMD,LTRIM(RTRIM(WORK_STATS)),ISNULL(REMARKS,'') FROM PARTNER_ERP.dbo.PR_M_PART_CALENDAR")
pr=[(r[0],iso(r[1]),r[2],str(r[3]).strip()) for r in c.fetchall()]
c.execute("SELECT part_code+'|'+CONVERT(varchar(10),cal_ymd,120) FROM nx.part_calendar"); haveP=set(x[0] for x in c.fetchall())
ins2=0
for pc,dt,ws,rm in pr:
    if dt and f"{pc}|{dt}" not in haveP:
        c.execute("INSERT INTO nx.part_calendar(part_code,cal_ymd,work_stats,remarks,upd_user) VALUES(?,?,?,?,'MIGRATION')",pc,dt,ws,rm); ins2+=1
cn.commit(); c.execute("SELECT COUNT(*) FROM nx.part_calendar"); print(f"파트별달력 nx.part_calendar {pb}→{c.fetchone()[0]} (+{ins2})")
