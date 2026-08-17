# -*- coding: utf-8 -*-
"""nx.bom_line ↔ CS 엣지 드리프트 정합: 잉여(nx-CS) 삭제 + 누락(CS-nx) 추가 → nx.bom_line=CS(용접봉제외) 100%.
가역: 실행 시 역로그(reverse_drift.json) 기록(삭제분·추가bom_id/seq). 스코프삭제(정확 parent+child)만, 대량삭제 아님.
--commit 없으면 DRY_RUN. 원가 게이트(r_cost_gate.py)로 전/후 검증 필수."""
import sys, os, json
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
DRY=('--commit' not in sys.argv)
def RO(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD};ApplicationIntent=ReadOnly')
def NX(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)
ro=RO().cursor(); nxc=NX(); n=nxc.cursor()
# 드리프트 재계산
ro.execute("SELECT ITEM_CODE,MAT_CODE FROM CS_M_ITEM_BOM WHERE FROM_APPLY_YMD<='991231' AND TO_APPLY_YMD>='260101' AND MAT_CODE NOT LIKE 'RAC%'")
CS=set(((r[0] or '').strip(),(r[1] or '').strip()) for r in ro.fetchall())
n.execute("SELECT h.item_code, bl.child_item FROM nx.bom_header h JOIN nx.bom_line bl ON bl.bom_id=h.bom_id WHERE bl.child_item NOT LIKE 'RAC%'")
NX_=set(((r[0] or '').strip(),(r[1] or '').strip()) for r in n.fetchall())
excess=sorted(NX_-CS)   # 삭제
missing=sorted(CS-NX_)  # 추가
print(f"잉여(삭제) {len(excess)}, 누락(추가) {len(missing)}, DRY={DRY}")
CSPAR=set(p for p,_ in CS)
# 누락 자식 중 nx.item 미등록 → 선등록(FK)
childs=set(ch for _,ch in missing)
if childs:
    phc=",".join("?"*len(childs)); cl=list(childs)
    n.execute(f"SELECT item_code FROM nx.item WHERE item_code IN ({phc})", *cl)
    have=set((r[0] or '').strip() for r in n.fetchall())
    need=[x for x in cl if x not in have]
else: need=[]
reverse={"deleted":[], "added":[], "item_added":need}
if not DRY:
    # nx.item 선등록
    for m in need:
        ro.execute("SELECT ISNULL(ITEM_DESC,?),ISNULL(ITEM_SPEC,''),ISNULL(MAKE_TYPE,''),ISNULL(ITEM_DIAM,0),ISNULL(ITEM_THICK,0),ISNULL(ITEM_LENGTH,0),ISNULL(METAL_GUBUN,''),ISNULL(IN_CUST_CODE,'') FROM PR_M_ITEM WHERE ITEM_CODE=?", m, m)
        pr=ro.fetchone()
        it='서브ASSY' if m in CSPAR else '부자재'
        n.execute("DELETE FROM nx.item WHERE item_code=? AND item_source='드리프트정합'", m)
        n.execute("""INSERT INTO nx.item(item_code,item_name,item_spec,item_type,unit,silver_flag,status,has_gagong,make_type,diam,thick,length,metal_gubun,in_cust,item_source)
            VALUES(?,?,?,?,N'EA',0,N'사용',0,?,?,?,?,?,?,N'드리프트정합')""",
            m,(pr[0] if pr else m),(pr[1] if pr else ''),it,(pr[2] if pr else ''),float(pr[3] or 0),float(pr[4] or 0),float(pr[5] or 0),(pr[6] if pr else ''),(pr[7] if pr else ''))
    # 잉여 삭제(정확 parent+child, 역로그)
    for p,ch in excess:
        n.execute("SELECT bl.bom_id,bl.seq,bl.qty FROM nx.bom_line bl JOIN nx.bom_header h ON h.bom_id=bl.bom_id WHERE h.item_code=? AND bl.child_item=?", p, ch)
        for r in n.fetchall(): reverse["deleted"].append({"parent":p,"child":ch,"bom_id":int(r[0]),"seq":int(r[1]),"qty":float(r[2] or 0)})
        n.execute("DELETE bl FROM nx.bom_line bl JOIN nx.bom_header h ON h.bom_id=bl.bom_id WHERE h.item_code=? AND bl.child_item=?", p, ch)
    # 누락 추가(CS 매핑, 기존 bom_header에 seq=max+1)
    for p,ch in missing:
        n.execute("SELECT bom_id FROM nx.bom_header WHERE item_code=?", p)
        hr=n.fetchone()
        if not hr:  # 부모 헤더도 없으면 생성
            n.execute("INSERT INTO nx.bom_header(item_code,version,apply_from,apply_to,status) OUTPUT INSERTED.bom_id VALUES(?,1,'2000-01-01',NULL,N'확정')", p)
            bomid=int(n.fetchone()[0])
        else: bomid=int(hr[0])
        n.execute("SELECT ISNULL(MAX(seq),0) FROM nx.bom_line WHERE bom_id=?", bomid); sq=int(n.fetchone()[0])+1
        ro.execute("""SELECT TOP 1 USE_QTY,ISNULL(PROC_GUBUN,''),ISNULL(GAGONG_PROC_CODE,''),S_WORK_CODE,ISNULL(WH_GAGONG_PROC_CODE,''),ISNULL(IN_GAGONG_PROC_CODE,''),
             ISNULL(CS_CALC_EXCEPT_FLAG,'0'),ISNULL(LME_EXCEPT_FLAG,'0'),ISNULL(SAGUB_FLAG,'0'),ISNULL(SET_EXCEPT_FLAG,'0'),ISNULL(KITTING_FLAG,'0'),ISNULL(VIR_ITEM_FLAG,'0'),ISNULL(CUST_CODE,''),ISNULL(FROM_APPLY_YMD,''),ISNULL(TO_APPLY_YMD,'')
           FROM CS_M_ITEM_BOM WHERE ITEM_CODE=? AND MAT_CODE=? AND FROM_APPLY_YMD<='991231' AND TO_APPLY_YMD>='260101'""", p, ch)
        cr=ro.fetchone()
        if not cr: continue
        (q,pg,gp,sw,wg,ig,cx,lx,sg,se,kt,vir,cust,fy,ty)=cr
        nt='서브ASSY' if ch in CSPAR else '키팅'
        n.execute("""INSERT INTO nx.bom_line(bom_id,seq,child_item,qty,node_type,cs_calc_except,lme_except,sagub_default,is_optional,from_ymd,to_ymd,except_flag,set_except,kitting,vir_item,proc_gubun,gagong_proc,s_work,wh_gagong,in_gagong,cust_code,remarks)
            VALUES(?,?,?,?,?,?,?,?,0,?,?,0,?,?,?,?,?,?,?,?,?,N'드리프트정합')""",
            bomid,sq,ch,float(q or 0),nt,1 if cx=='1' else 0,1 if lx=='1' else 0,1 if sg=='1' else 0,str(fy),str(ty),1 if se=='1' else 0,1 if kt=='1' else 0,1 if vir=='1' else 0,str(pg),str(gp),str(sw or ''),str(wg),str(ig),str(cust))
        reverse["added"].append({"parent":p,"child":ch,"bom_id":bomid,"seq":sq})
    nxc.commit()
    json.dump(reverse, open(os.path.join(os.path.dirname(__file__),'reverse_drift.json'),'w',encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f"COMMIT: 삭제 {len(reverse['deleted'])}, 추가 {len(reverse['added'])}, nx.item선등록 {len(need)}. 역로그 저장.")
else:
    print("  삭제예시:", excess[:5]); print("  추가예시:", missing[:5]); print("  nx.item선등록 필요:", need)
    nxc.rollback()
nxc.close()
