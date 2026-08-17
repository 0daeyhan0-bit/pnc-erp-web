# -*- coding: utf-8 -*-
"""가공 공정 마스터 라이브→nx 대량이관 (원본 충실 복제, 멱등). 컷오버 대량이관·델타 재사용.
  PR_M_ITEM_PROC_GAGONG → nx.item_proc (품목 공정순서, 9617)
  PR_M_WORK_SINGLE       → nx.work_single (표준작업, 450)
  PR_M_PROC_GAGONG       → nx.proc_gagong (가공공정 마스터, 23)
※SELECT * INTO = 스키마+데이터 그대로. 컬럼명 동일 → 프로그램 rewrite는 테이블명만 교체. 기존 nx.routing(원가엔진)은 별개 유지.
--commit 없으면 계획만."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
DRY = ('--commit' not in sys.argv)
def NX(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
MAP=[('nx.item_proc','PARTNER_ERP.dbo.PR_M_ITEM_PROC_GAGONG'),
     ('nx.work_single','PARTNER_ERP.dbo.PR_M_WORK_SINGLE'),
     ('nx.proc_gagong','PARTNER_ERP.dbo.PR_M_PROC_GAGONG')]
cn=NX(); c=cn.cursor()
for nxt, src in MAP:
    c.execute(f"SELECT COUNT(*) FROM {src}"); sc=c.fetchone()[0]
    short=nxt.split('.')[1]
    exists=c.execute("SELECT COUNT(*) FROM sys.tables WHERE schema_id=SCHEMA_ID('nx') AND name=?", short).fetchone()[0]
    if DRY:
        print(f"  계획: {src} ({sc}행) → {nxt} {'[교체]' if exists else '[신설]'}")
        continue
    if exists: c.execute(f"DROP TABLE {nxt}")
    c.execute(f"SELECT * INTO {nxt} FROM {src}")
    nc=c.execute(f"SELECT COUNT(*) FROM {nxt}").fetchone()[0]
    print(f"  {nxt}: {nc}행 적재 (원본 {sc}) {'✔' if nc==sc else '✖불일치'}")
if DRY: print("\nDRY_RUN (--commit 로 실행)")
else: print("\n가공 공정 마스터 nx 이관 완료")
cn.close()
