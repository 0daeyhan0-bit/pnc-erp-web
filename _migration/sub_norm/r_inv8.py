# -*- coding: utf-8 -*-
"""8개 프로그램 타겟 인벤토리: 각 파일의 라이브 테이블 참조(bare + PARTNER_ERP.dbo.) 추출 → nx 복제 목록.
이미 복제된 것/nx 대응 표시. 참조 스타일(_conn bare vs PARTNER_ERP.dbo.)도 파악."""
import sys, io, os, re
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BE=r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\PNC_ERP_Web\backend'
FILES={'partplan':'routers/partplan.py','gagong':'routers/gagong.py','sourcing':'routers/sourcing.py',
       'backflush':'routers/backflush.py','item':'routers/item.py','salemagam':'routers/salemagam.py',
       'weight_calc':'weight_calc.py','cost':'routers/cost.py'}
LIVE_RE=re.compile(r'\b((?:PR|CS|CM|PU|SA|FI|QA|GG|HR|SY|BA|MA|MM|SD|CO)_[A-Z]_?[A-Z0-9_]+)\b', re.I)
n=pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}').cursor()
n.execute("SELECT name FROM sys.tables WHERE schema_id=SCHEMA_ID('nx')"); NXCOPIED=set(x[0].upper() for x in n.fetchall())
ro=pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD};ApplicationIntent=ReadOnly').cursor()
ro.execute("SELECT name FROM sys.tables"); LIVETAB=set(x[0].upper() for x in ro.fetchall())
alltabs={}
for prog, rel in FILES.items():
    fp=os.path.join(BE, rel)
    if not os.path.exists(fp): print(f"[{prog}] 파일없음 {rel}"); continue
    txt=open(fp,encoding='utf-8').read()
    tabs=set()
    for m in LIVE_RE.findall(txt):
        u=m.upper()
        if u in LIVETAB: tabs.add(u)
    # 연결스타일
    styles=[]
    if '_conn(' in txt: styles.append('_conn(라이브bare)')
    if 'PARTNER_ERP.dbo.' in txt: styles.append('PARTNER_ERP.dbo.명시')
    if '_P' in txt and re.search(r'_P\s*=', txt): styles.append('_P프리픽스')
    print(f"\n[{prog}] {rel}  스타일={styles}")
    print(f"   라이브테이블 {len(tabs)}: {sorted(tabs)}")
    for t in tabs: alltabs.setdefault(t,[]).append(prog)
# 복제 필요(아직 nx에 없는)
need=sorted(t for t in alltabs if t not in NXCOPIED)
have=sorted(t for t in alltabs if t in NXCOPIED)
print(f"\n=== 이미 nx복제됨 {len(have)}: {have}")
print(f"=== 신규 복제필요 {len(need)}:")
for t in need: print(f"   {t:<28} ← {alltabs[t]}")
print("DONE")
