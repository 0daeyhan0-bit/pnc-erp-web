# -*- coding: utf-8 -*-
"""원가 diff0(SUB변형 BOM 구조차): nx.bom_line이 CS_M_ITEM_BOM 대비 누락한 엣지 추가.
SP(실원가 오라클)는 CS를 전개 → CS엣지가 nx에 없으면 그 자식 재료비 누락(예 AJR37039706-은납→AJR37039701-4-1 −4372).
대상=부모가 nx.bom_header에 있고, except<>1, 비RAC(용접봉=proc_weld 별도), 자식이 nx.item에 존재. **추가만**(제거/치환 없음=과거 강제정합 롤백 회피).
방식: 부모의 기존 sibling bom_line 행 defaults 복사 → child_item·qty·seq만 교체(스키마 안전). 백업 nx.bom_line_bak_edgeadd. --commit 없으면 계획만."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
DRY = ('--commit' not in sys.argv)
ro=pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD};ApplicationIntent=ReadOnly').cursor()
n=pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c=n.cursor()
hdr={str(r[0]).strip():int(r[1]) for r in c.execute("""SELECT bh.item_code,bh.bom_id FROM nx.bom_header bh
   JOIN (SELECT item_code,MAX(ISNULL(version,1)) mv FROM nx.bom_header GROUP BY item_code) m
     ON m.item_code=bh.item_code AND ISNULL(bh.version,1)=m.mv""").fetchall()}
nxedges=set((str(r[0]).strip(),str(r[1]).strip()) for r in c.execute("SELECT h.item_code,b.child_item FROM nx.bom_header h JOIN nx.bom_line b ON b.bom_id=h.bom_id").fetchall())
nxitem=set(str(r[0]).strip() for r in c.execute("SELECT item_code FROM nx.item").fetchall())
missing=[]
for r in ro.execute("SELECT LTRIM(RTRIM(ITEM_CODE)),LTRIM(RTRIM(MAT_CODE)),USE_QTY FROM CS_M_ITEM_BOM WHERE ISNULL(CS_CALC_EXCEPT_FLAG,'0')<>'1'").fetchall():
    p,ch,q=str(r[0]).strip(),str(r[1]).strip(),float(r[2] or 0)
    # ★제외: 자식=부모의 base코드(parent=child+'-…') → nx가 의도적 평탄화한 구조라 추가시 이중계상(AJR74482401-1→AJR74482401 = +28538 회귀 확인). skip.
    if p in hdr and (p,ch) not in nxedges and not ch.startswith('RAC') and ch in nxitem and not (p.startswith(ch+'-')):
        missing.append((p,ch,q))
print(f"누락엣지 추가대상: {len(missing)}건 (부모 {len(set(m[0] for m in missing))}개)")
for m in missing: print(f"  {m[0]:<20} → {m[1]:<18} q={m[2]}")
if DRY: print("DRY (--commit 로 적용)"); n.close(); sys.exit()
# 백업(원본 보존 — 이미 있으면 유지, 재실행 시 덮어쓰지 않음)
if c.execute("SELECT OBJECT_ID('nx.bom_line_bak_edgeadd','U')").fetchone()[0] is None:
    c.execute("SELECT * INTO nx.bom_line_bak_edgeadd FROM nx.bom_line")
    print("백업 생성 nx.bom_line_bak_edgeadd:", c.execute("SELECT COUNT(*) FROM nx.bom_line_bak_edgeadd").fetchone()[0])
else:
    print("백업 유지(기존 nx.bom_line_bak_edgeadd):", c.execute("SELECT COUNT(*) FROM nx.bom_line_bak_edgeadd").fetchone()[0])
cols=[r[0] for r in c.execute("SELECT name FROM sys.columns WHERE object_id=OBJECT_ID('nx.bom_line') ORDER BY column_id").fetchall()]
added=0
for p,ch,q in missing:
    bid=hdr[p]
    # 부모 sibling 한 행(defaults 복사원)
    sib=c.execute(f"SELECT TOP 1 {','.join(cols)} FROM nx.bom_line WHERE bom_id=? ORDER BY seq", bid).fetchone()
    nextseq=c.execute("SELECT ISNULL(MAX(seq),0)+1 FROM nx.bom_line WHERE bom_id=?", bid).fetchone()[0]
    if sib:
        row=dict(zip(cols,sib))
    else:   # 빈 부모(bom_line 0행): generic 안전기본값. NOT NULL=bit 0·node_type '키팅'(표준).
        row={k:None for k in cols}
        for b in ('cs_calc_except','lme_except','sagub_default','is_optional','except_flag','set_except','kitting','vir_item'): row[b]=0
        row['node_type']='키팅'
    row['bom_id']=bid; row['seq']=nextseq; row['child_item']=ch; row['qty']=q
    row['cs_calc_except']=0; row['except_flag']=0
    row['remarks']=(str(row.get('remarks') or '')+' [edgeadd 2026-08-13 CS정합]')[:200]
    ins=[c2 for c2 in cols]
    c.execute(f"INSERT INTO nx.bom_line ({','.join(ins)}) VALUES ({','.join('?'*len(ins))})", *[row[c2] for c2 in ins])
    added+=1
print(f"추가 완료 {added}건. 되돌리기: nx.bom_line_bak_edgeadd 복원(DELETE nx.bom_line; INSERT SELECT).")
n.close()
