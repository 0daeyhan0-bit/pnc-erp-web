# -*- coding: utf-8 -*-
"""nx 마스터 갭 인벤토리: 전 라우터가 읽는 라이브 PARTNER_ERP 테이블 추출 + nx 대응 매핑.
출력: 라이브테이블 → 사용 라우터·횟수 + nx 후보. durable NX_MASTER_GAP.md 생성용."""
import sys, io, os, re, glob
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROUTERS=r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\PNC_ERP_Web\backend\routers'
# 라이브 테이블 패턴: 대문자_언더스코어, 알려진 접두(PR/CS/CM/PU/SA/FI/QA/GG/HR/SY/BA), PARTNER_ERP.dbo.X 포함
LIVE_RE=re.compile(r'\b((?:PR|CS|CM|PU|SA|FI|QA|GG|HR|SY|BA|MA|MM|SD|CO)_[A-Z]_?[A-Z0-9_]+)\b')
DBO_RE=re.compile(r'PARTNER_ERP\.dbo\.([A-Za-z0-9_]+)', re.I)
usage={}  # table -> {file: count}
for fp in glob.glob(os.path.join(ROUTERS,'*.py')):
    fn=os.path.basename(fp)
    txt=open(fp,encoding='utf-8').read()
    for m in LIVE_RE.findall(txt):
        usage.setdefault(m,{}).setdefault(fn,0); usage[m][fn]+=1
    for m in DBO_RE.findall(txt):
        t=m.upper()
        if not t.startswith('NX'):
            usage.setdefault(t,{}).setdefault(fn,0); usage[t][fn]+=1
# nx 테이블 목록(대응 후보 탐색용)
n=pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}').cursor()
n.execute("SELECT name FROM sys.tables WHERE schema_id=SCHEMA_ID('nx') AND name NOT LIKE '%bak%' AND name NOT LIKE '%_tmp'")
NXT=[r[0] for r in n.fetchall()]
def nx_cand(lv):
    # 라이브명 토큰 → nx 이름 키워드 매칭
    key=lv.lower().replace('pr_m_','').replace('pr_t_','').replace('cs_m_','').replace('cm_m_','').replace('_',' ')
    toks=[t for t in key.split() if len(t)>2]
    c=[t for t in NXT if any(tok in t.lower() for tok in toks)]
    return c[:4]
rows=sorted(usage.items(), key=lambda kv:-sum(kv[1].values()))
print(f"라이브 테이블 참조 {len(rows)}종 (사용많은순)\n")
print(f"{'라이브테이블':<30}{'총':>4}  {'라우터':<28} nx후보")
for t,files in rows:
    tot=sum(files.values()); fl=",".join(sorted(files))[:26]
    print(f"  {t:<30}{tot:>4}  {fl:<28} {nx_cand(t)}")
print("\nDONE")
