# -*- coding: utf-8 -*-
"""전 백엔드 파일 라이브테이블 전수스캔 → 복제필요 테이블 + 교체필요 파일. coopquote/coopquote2·이미완료 제외."""
import sys, io, os, re, glob
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BE=r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\PNC_ERP_Web\backend'
DONE={'partplan','backflush','item','sourcing','cost','salemagam','gagong','weight_calc','common','app','soyo'}
SKIP={'coopquote','coopquote2'}
LIVE_RE=re.compile(r'\b((?:PR|CS|CM|PU|SA|FI|QA|GG|HR)_[A-Z]_?[A-Z0-9_]+)\b')
DBO_RE=re.compile(r'PARTNER_ERP\.dbo\.([A-Za-z0-9_]+)', re.I)
ro=pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD};ApplicationIntent=ReadOnly').cursor()
ro.execute("SELECT name FROM sys.tables"); LIVETAB=set(x[0].upper() for x in ro.fetchall())
n=pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}').cursor()
n.execute("SELECT name FROM sys.tables WHERE schema_id=SCHEMA_ID('nx')"); NXCOPIED=set(x[0].upper() for x in n.fetchall())
files=glob.glob(os.path.join(BE,'*.py'))+glob.glob(os.path.join(BE,'routers','*.py'))
alltab={}; needfiles=[]
for fp in files:
    stem=os.path.splitext(os.path.basename(fp))[0]
    if stem in DONE or stem in SKIP: continue
    txt=open(fp,encoding='utf-8').read()
    tabs=set()
    for m in LIVE_RE.findall(txt):
        if m.upper() in LIVETAB: tabs.add(m.upper())
    for m in DBO_RE.findall(txt):
        if m.upper() in LIVETAB: tabs.add(m.upper())
    if tabs:
        needfiles.append((stem,len(tabs)))
        for t in tabs: alltab.setdefault(t,0); alltab[t]+=1
need=sorted(t for t in alltab if t not in NXCOPIED)
print(f"=== 교체필요 파일 {len(needfiles)} ===")
print(", ".join(f"{s}({n})" for s,n in sorted(needfiles,key=lambda x:-x[1])))
print(f"\n=== 복제필요 테이블 {len(need)} (이미복제 {len([t for t in alltab if t in NXCOPIED])}) ===")
print(need)
