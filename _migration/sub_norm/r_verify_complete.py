# -*- coding: utf-8 -*-
"""ERP가 참조하는 전 레거시테이블 완전성·신선도 검증 + 목록. 코드에서 PARTNER_ERP_TEST3.nx.<T> / nx.<대문자T> 추출.
출력: 참조테이블 → nx존재? 라이브대비 행수Δ(신선도). --refresh시 노후/누락분 재복제."""
import sys, io, os, re, glob
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
REFRESH='--refresh' in sys.argv
BE=r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\PNC_ERP_Web\backend'
HARNESS=r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\_harness'
# 참조 패턴: PARTNER_ERP_TEST3.nx.<T> 또는 nx.<대문자_언더스코어T>(라이브명)
PAT=re.compile(r'(?:PARTNER_ERP_TEST3\.)?nx\.([A-Z][A-Z0-9_]{3,})\b')
ro=pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD};ApplicationIntent=ReadOnly')
roc=ro.cursor(); roc.execute("SELECT name FROM sys.tables"); LIVE=set(x[0].upper() for x in roc.fetchall())
cn=pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c=cn.cursor(); c.execute("SELECT name FROM sys.tables WHERE schema_id=SCHEMA_ID('nx')"); NXT=set(x[0].upper() for x in c.fetchall())
refs=set()
for fp in glob.glob(os.path.join(BE,'*.py'))+glob.glob(os.path.join(BE,'routers','*.py'))+glob.glob(os.path.join(HARNESS,'*.py')):
    txt=open(fp,encoding='utf-8').read()
    for m in PAT.findall(txt):
        if m.upper() in LIVE: refs.add(m.upper())   # 라이브 실테이블명인 것만(nx-native 제외)
refs=sorted(refs)
print(f"ERP 참조 레거시테이블 {len(refs)}종\n")
missing=[]; stale=[]; ok=0
for t in refs:
    innx = t in NXT
    if not innx: missing.append(t); print(f"  ✖ {t}: nx 없음!"); continue
    lc=roc.execute(f"SELECT COUNT(*) FROM PARTNER_ERP.dbo.{t}").fetchone()[0]
    nc=c.execute(f"SELECT COUNT(*) FROM nx.{t}").fetchone()[0]
    if lc==nc: ok+=1
    else: stale.append((t,lc,nc)); print(f"  △ {t}: 라이브 {lc} vs nx {nc} (Δ{lc-nc})")
print(f"\n일치 {ok} / 노후 {len(stale)} / 누락 {len(missing)}")
if REFRESH and (missing or stale):
    print("\n--refresh: 노후/누락 재복제")
    for t in missing+[x[0] for x in stale]:
        try:
            c.execute(f"IF OBJECT_ID('nx.{t}','U') IS NOT NULL DROP TABLE nx.{t}")
            c.execute(f"SELECT * INTO nx.{t} FROM PARTNER_ERP.dbo.{t}")
            print(f"   {t}: {c.execute(f'SELECT COUNT(*) FROM nx.{t}').fetchone()[0]}행 재복제")
        except Exception as e: print(f"   ✖ {t}: {str(e)[:60]}")
cn.close()
