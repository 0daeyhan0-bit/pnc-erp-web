# -*- coding: utf-8 -*-
# route미상 재해소(품명 업체명 + 코드 사내접미사) → nx.sub_alias UPDATE
import sys, re
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
def RO(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD};ApplicationIntent=ReadOnly')
def NX(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)
c=RO().cursor()
# 거래처 이름 컬럼 탐색
c.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='CM_M_CUST'")
cols=[r[0] for r in c.fetchall()]
namecol=[x for x in cols if 'NAME' in x.upper() or x.upper() in ('CUST_NM','CUST_DESC','BIZ_NAME')]
namecol=namecol[0] if namecol else None
name2code={}
if namecol:
    c.execute(f"SELECT CUST_CODE, {namecol} FROM CM_M_CUST WHERE {namecol} IS NOT NULL")
    for r in c.fetchall():
        nm=(r[1] or '').strip()
        if nm: name2code[nm]=(r[0] or '').strip()
print(f"거래처명 컬럼={namecol}, {len(name2code)}개")
# 축약명 → 코드 (품명에 나오는 약칭)
def vendor_by_name(desc):
    for nm,code in name2code.items():
        key=nm.replace('(주)','').replace('㈜','').replace(' ','')[:4]
        if key and key in desc.replace(' ',''): return code, nm
    # 흔한 약칭 수동
    for k,code in [('이젠터','2068'),('대원','2148'),('명진','2306'),('미래','2096'),('중앙','2048'),('두진','2012'),('케이비','2266')]:
        if k in desc: return code, k
    return None,None
SANAE=re.compile(r'은납|저압|고압|고주파|도장|선행|체결|용접|컷팅|성형|절단|사내')

n=NX(); w=n.cursor()
w.execute("SELECT variant, item_desc, category FROM nx.sub_alias WHERE route_gubun='미상'")
rows=w.fetchall()
upd=[]; still=[]
for v,desc,cat in rows:
    desc=desc or ''
    code,nm=vendor_by_name(desc)
    if code:
        upd.append((v,'외주',code,f'품명업체 {nm}'))
    elif SANAE.search(v) or SANAE.search(desc):
        upd.append((v,'사내','','코드/품명 사내공정'))
    elif '외주' in desc:
        upd.append((v,'외주','','품명 외주(업체미상)'))
    else:
        still.append((v,desc[:30],cat))
for v,g,ven,why in upd:
    w.execute("UPDATE nx.sub_alias SET route_gubun=?, route_vendor=? WHERE variant=?", g, ven, v)
n.commit()
print(f"\n해소 UPDATE: {len(upd)}건")
for v,g,ven,why in upd: print(f"  {v:<22} → {g}({ven or '-'})  [{why}]")
print(f"\n★남은 진짜 미상: {len(still)}")
for v,d,cat in still: print(f"  {v:<22} [{cat}] {d}")
# 최종 분포
w.execute("SELECT route_gubun, COUNT(*) FROM nx.sub_alias GROUP BY route_gubun ORDER BY COUNT(*) DESC")
print("\n최종 route분포:", [tuple(x) for x in w.fetchall()])
n.close(); print("DONE")
