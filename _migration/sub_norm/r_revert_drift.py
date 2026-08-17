# -*- coding: utf-8 -*-
"""드리프트 정합 되돌리기 — SP게이트에서 정합이 레거시 원가 훼손 확인(22/27 멀어짐) → 원상복구.
①추가31 삭제(remarks='드리프트정합', bom_id+child 스코프) ②삭제25 재삽입(reverse_drift.json child+qty, cs_calc_except=0, PR있으면 PR값).
검증타깃=gate_before.json(정합전 엔진 silwon). --commit 없으면 DRY."""
import sys, os, json
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
DRY=('--commit' not in sys.argv)
def RO(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD};ApplicationIntent=ReadOnly')
def NX(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)
HERE=os.path.dirname(__file__)
rev=json.load(open(os.path.join(HERE,'reverse_drift.json'),encoding='utf-8'))
ro=RO().cursor(); nxc=NX(); n=nxc.cursor()
CSPAR=set()
ro.execute("SELECT DISTINCT ITEM_CODE FROM CS_M_ITEM_BOM WHERE FROM_APPLY_YMD<='991231' AND TO_APPLY_YMD>='260101'")
for r in ro.fetchall(): CSPAR.add((r[0] or '').strip())
ro.execute("SELECT DISTINCT ITEM_CODE FROM PR_M_ITEM_BOM"); PRPAR=set((r[0] or '').strip() for r in ro.fetchall())
def pr_row(p,ch):
    ro.execute("""SELECT TOP 1 USE_QTY,ISNULL(PROC_GUBUN,''),ISNULL(GAGONG_PROC_CODE,''),S_WORK_CODE,ISNULL(WH_GAGONG_PROC_CODE,''),ISNULL(IN_GAGONG_PROC_CODE,''),
         ISNULL(CS_CALC_EXCEPT_FLAG,'0'),ISNULL(LME_EXCEPT_FLAG,'0'),ISNULL(SAGUB_FLAG,'0'),ISNULL(SET_EXCEPT_FLAG,'0'),ISNULL(KITTING_FLAG,'0'),ISNULL(VIR_ITEM_FLAG,'0'),ISNULL(CUST_CODE,''),ISNULL(FROM_APPLY_YMD,''),ISNULL(TO_APPLY_YMD,'')
       FROM PR_M_ITEM_BOM WHERE ITEM_CODE=? AND MAT_CODE=?""", p, ch)
    return ro.fetchone()
ndel=nins=0
if not DRY:
    # ① 추가31 삭제
    for a in rev['added']:
        n.execute("DELETE FROM nx.bom_line WHERE bom_id=? AND child_item=? AND remarks=N'드리프트정합'", a['bom_id'], a['child'])
        ndel+=1
    # 정합때 선등록된 nx.item(있으면) 제거
    for m in rev.get('item_added',[]):
        n.execute("DELETE FROM nx.item WHERE item_code=? AND item_source=N'드리프트정합'", m)
    # ② 삭제25 재삽입(원 bom_id/seq/qty, PR있으면 PR 컬럼, 없으면 cs_calc_except=0 기본)
    for d in rev['deleted']:
        p,ch,bomid,seq,qty=d['parent'],d['child'],d['bom_id'],d['seq'],d['qty']
        pr=pr_row(p,ch)
        nt='서브ASSY' if (ch in CSPAR or ch in PRPAR) else '키팅'
        if pr:
            (q,pg,gp,sw,wg,ig,cx,lx,sg,se,kt,vir,cust,fy,ty)=pr
            vals=(bomid,seq,ch,float(q or qty or 0),nt,1 if cx=='1' else 0,1 if lx=='1' else 0,1 if sg=='1' else 0,str(fy),str(ty),1 if se=='1' else 0,1 if kt=='1' else 0,1 if vir=='1' else 0,str(pg),str(gp),str(sw or ''),str(wg),str(ig),str(cust))
        else:
            vals=(bomid,seq,ch,float(qty or 0),nt,0,0,0,'','',0,0,0,'','','','','','')
        n.execute("""INSERT INTO nx.bom_line(bom_id,seq,child_item,qty,node_type,cs_calc_except,lme_except,sagub_default,is_optional,from_ymd,to_ymd,except_flag,set_except,kitting,vir_item,proc_gubun,gagong_proc,s_work,wh_gagong,in_gagong,cust_code,remarks)
            VALUES(?,?,?,?,?,?,?,?,0,?,?,0,?,?,?,?,?,?,?,?,?,N'드리프트복원')""", *vals)
        nins+=1
    nxc.commit()
    print(f"REVERT COMMIT: 추가분삭제 {ndel}, 삭제분복원 {nins}")
else:
    print(f"DRY: 삭제할 추가 {len(rev['added'])}, 복원할 삭제 {len(rev['deleted'])} (PR보유 {sum(1 for d in rev['deleted'] if pr_row(d['parent'],d['child']))})")
    nxc.rollback()
nxc.close()
