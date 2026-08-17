# -*- coding: utf-8 -*-
"""#1 이관 선행: nx.bom_line 누락 11 부모 백필 (CS_M_ITEM_BOM → nx.bom_header/bom_line, 용접봉 제외).
용접봉(RAC)은 bom_line에 넣지 않고 nx.proc_weld에 동일 파생로직으로 타겟 삽입(공정 그대로 이관).
멱등: 11 item_code 스코프로만 기존 백필(remarks='11백필'/src='11백필') 삭제 후 재적재. 대량삭제 아님(근거키 스코프).
DRY_RUN=True면 삽입 안 하고 계획만 출력."""
import sys
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
DRY_RUN = ('--commit' not in sys.argv)
def RO(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD};ApplicationIntent=ReadOnly')
def NX(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)
ro=RO().cursor(); nxc=NX(); n=nxc.cursor()
MISS=['ADM72950707','AGR30801603','AGR30801603-AL-1','AGR30801604','AJR30012103','AJR30113102','AJR37039701-4-1','AJR73942805','AJR74302403-4-1','AJR74962905-16-1','AJR77224002-12-1']

# --- 헬퍼셋 ---
# node_type: 자기 CS BOM 보유 자식 = '서브ASSY', 아니면 '키팅'
ro.execute("SELECT DISTINCT ITEM_CODE FROM CS_M_ITEM_BOM WHERE FROM_APPLY_YMD<='991231' AND TO_APPLY_YMD>='260101'")
CSPAR=set((r[0] or '').strip() for r in ro.fetchall())
# proc_weld 파생셋 (migrate_nx_proc_weld.py 동일)
n.execute("SELECT pipe_diam, MIN(std_use_qty) FROM nx.weld_diam GROUP BY pipe_diam")
UNIT={round(float(r[0]),4):float(r[1] or 0) for r in n.fetchall()}
n.execute("SELECT item_code, ISNULL(diam,0) FROM nx.item")
IDIAM={str(r[0]).strip():float(r[1] or 0) for r in n.fetchall()}
n.execute("SELECT p_item,item_code,SUM(work_qty) FROM nx.routing WHERE item_code LIKE 'RAC%' AND proc_code IN ('51','28') AND work_qty>0 GROUP BY p_item,item_code")
WST={(str(r[0]).strip(),str(r[1]).strip()):float(r[2] or 0) for r in n.fetchall()}
# bom_id identity 여부
n.execute("SELECT COLUMNPROPERTY(OBJECT_ID('nx.bom_header'),'bom_id','IsIdentity')")
IS_IDENT=(n.fetchone()[0]==1)
n.execute("SELECT ISNULL(MAX(bom_id),0) FROM nx.bom_header"); nextid=int(n.fetchone()[0])+1
print(f"bom_id IDENTITY={IS_IDENT}, 시작 bom_id={nextid if not IS_IDENT else '(auto)'}, DRY_RUN={DRY_RUN}")

# --- nx.item 선등록: 부모+비RAC자식 중 미등록(FK 충족) ---
allcodes=set(MISS)
for p in MISS:
    ro.execute("SELECT MAT_CODE FROM CS_M_ITEM_BOM WHERE ITEM_CODE=? AND FROM_APPLY_YMD<='991231' AND TO_APPLY_YMD>='260101'", p)
    for r in ro.fetchall():
        m=(r[0] or '').strip()
        if m and not m.startswith('RAC'): allcodes.add(m)
codes=sorted(allcodes); phc=",".join("?"*len(codes))
n.execute(f"SELECT item_code FROM nx.item WHERE item_code IN ({phc})", *codes)
have=set((r[0] or '').strip() for r in n.fetchall())
need=[x for x in codes if x not in have]
prinfo={}
if need:
    phn=",".join("?"*len(need))
    ro.execute(f"""SELECT ITEM_CODE,ISNULL(ITEM_DESC,''),ISNULL(ITEM_SPEC,''),ISNULL(MAKE_TYPE,''),
          ISNULL(ITEM_DIAM,0),ISNULL(ITEM_THICK,0),ISNULL(ITEM_LENGTH,0),ISNULL(METAL_GUBUN,''),ISNULL(IN_CUST_CODE,'')
        FROM PR_M_ITEM WHERE ITEM_CODE IN ({phn})""", *need)
    for r in ro.fetchall(): prinfo[(r[0] or '').strip()]=r
print(f"nx.item 미등록 {len(need)}: {need}")

# --- 멱등: 스코프 삭제(11 item_code 한정 + item_source='11백필' nx.item) ---
ph=",".join("?"*len(MISS))
if not DRY_RUN:
    n.execute(f"DELETE bl FROM nx.bom_line bl JOIN nx.bom_header h ON h.bom_id=bl.bom_id WHERE h.item_code IN ({ph})", *MISS)
    n.execute(f"DELETE FROM nx.bom_header WHERE item_code IN ({ph})", *MISS)
    n.execute(f"DELETE FROM nx.proc_weld WHERE parent_item IN ({ph}) AND src='11백필'", *MISS)
    for m in need:
        pr=prinfo.get(m)
        nm=(pr[1] if pr else m) or m; spec=pr[2] if pr else ''; mk=pr[3] if pr else ''
        dm=float(pr[4] or 0) if pr else 0; th=float(pr[5] or 0) if pr else 0; ln=float(pr[6] or 0) if pr else 0
        metal=pr[7] if pr else ''; incust=pr[8] if pr else ''
        it='서브ASSY' if m in CSPAR else '부자재'
        # 스코프삭제(재실행 대비): 11백필로 넣은 것만
        n.execute("DELETE FROM nx.item WHERE item_code=? AND item_source='11백필'", m)
        n.execute("""INSERT INTO nx.item(item_code,item_name,item_spec,item_type,unit,silver_flag,status,has_gagong,
              make_type,diam,thick,length,metal_gubun,in_cust,item_source)
            VALUES(?,?,?,?,N'EA',0,N'사용',0,?,?,?,?,?,?,N'11백필')""",
            m,nm,spec,it,mk,dm,th,ln,metal,incust)
    # nx.item 추가분 반영 위해 IDIAM 갱신
    n.execute("SELECT item_code, ISNULL(diam,0) FROM nx.item")
    IDIAM={str(r[0]).strip():float(r[1] or 0) for r in n.fetchall()}

nb_ins=0; pw_ins=0
for p in MISS:
    ro.execute("""SELECT BOM_SEQ,MAT_CODE,USE_QTY,ISNULL(PROC_GUBUN,''),ISNULL(GAGONG_PROC_CODE,''),S_WORK_CODE,
          ISNULL(WH_GAGONG_PROC_CODE,''),ISNULL(IN_GAGONG_PROC_CODE,''),ISNULL(CS_CALC_EXCEPT_FLAG,'0'),
          ISNULL(LME_EXCEPT_FLAG,'0'),ISNULL(SAGUB_FLAG,'0'),ISNULL(SET_EXCEPT_FLAG,'0'),ISNULL(KITTING_FLAG,'0'),
          ISNULL(VIR_ITEM_FLAG,'0'),ISNULL(CUST_CODE,''),ISNULL(REMARKS,''),ISNULL(FROM_APPLY_YMD,''),ISNULL(TO_APPLY_YMD,'')
        FROM CS_M_ITEM_BOM WHERE ITEM_CODE=? AND FROM_APPLY_YMD<='991231' AND TO_APPLY_YMD>='260101' ORDER BY BOM_SEQ""", p)
    rows=ro.fetchall()
    # 헤더
    if not DRY_RUN:
        if IS_IDENT:
            n.execute("INSERT INTO nx.bom_header(item_code,version,apply_from,apply_to,status) OUTPUT INSERTED.bom_id VALUES(?,?,?,?,N'확정')", p,1,'2000-01-01',None)
            bomid=int(n.fetchone()[0])
        else:
            bomid=nextid; nextid+=1
            n.execute("INSERT INTO nx.bom_header(bom_id,item_code,version,apply_from,apply_to,status) VALUES(?,?,?,?,?,N'확정')", bomid,p,1,'2000-01-01',None)
    else:
        bomid='(dry)'
    nnon=0; nrac=0; sq_ctr=0
    for (seq,mat,q,pg,gp,sw,wg,ig,cx,lx,sg,se,kt,vir,cust,rmk,fy,ty) in rows:
        mat=(mat or '').strip()
        if mat.startswith('RAC'):   # 용접봉 → proc_weld
            nrac+=1
            base=mat.split('-')[0]; diam=IDIAM.get(p,0.0); unit=UNIT.get(round(diam,4),0.0); st=WST.get((p,mat),0.0)
            if not DRY_RUN:
                n.execute("""INSERT INTO nx.proc_weld(parent_item,weld_item,weld_base,pipe_diam,weld_st,unit_qty,use_qty,
                      cs_calc_except,lme_except,from_ymd,to_ymd,tag,src,loss_factor,meta_ok)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,'W','11백필',1.5,?)""",
                    p,mat,base,diam,st,unit,float(q or 0),1 if cx=='1' else 0,1 if lx=='1' else 0,str(fy),str(ty),1 if st>0 else 0)
            pw_ins+=1
        else:
            nnon+=1; sq_ctr+=1
            nt='서브ASSY' if mat in CSPAR else '키팅'
            if not DRY_RUN:
                n.execute("""INSERT INTO nx.bom_line(bom_id,seq,child_item,qty,node_type,cs_calc_except,lme_except,sagub_default,
                      is_optional,from_ymd,to_ymd,except_flag,set_except,kitting,vir_item,proc_gubun,gagong_proc,s_work,
                      wh_gagong,in_gagong,cust_code,remarks)
                    VALUES(?,?,?,?,?,?,?,?,0,?,?,?,?,?,?,?,?,?,?,?,?,N'11백필')""",
                    bomid,sq_ctr,mat,float(q or 0),nt,1 if cx=='1' else 0,1 if lx=='1' else 0,1 if sg=='1' else 0,
                    str(fy),str(ty),1 if False else 0,1 if se=='1' else 0,1 if kt=='1' else 0,1 if vir=='1' else 0,
                    str(pg),str(gp),str(sw or ''),str(wg),str(ig),str(cust))
            nb_ins+=1
    print(f"  {p:<20} bom_line {nnon} + proc_weld(용접봉) {nrac}")
if not DRY_RUN:
    nxc.commit(); print(f"\nCOMMIT: bom_line {nb_ins}행, proc_weld {pw_ins}행 적재")
else:
    nxc.rollback(); print(f"\nDRY_RUN(계획): bom_line {nb_ins}행, proc_weld {pw_ins}행 (--commit 로 실행)")
nxc.close()
