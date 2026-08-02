# -*- coding: utf-8 -*-
# 460 재구성: 유니버스=pr_t_mat_stock_wh(part,mat) 기준정보, 값=수불장(전월이월2502+당월이동) 재구성
import sys, io, json, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import pandas as pd, db_client, pyodbc
def live(sql):
    cs=(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
    cn=pyodbc.connect(cs, readonly=True)
    try: return pd.read_sql(sql, cn)
    finally: cn.close()
INSP="NOT(ISNULL(a.insp_flag,'N') IN ('S','F') AND ISNULL(a.insp_proc_flag,'0')<>'1')"
CUST="ISNULL((SELECT cust_desc FROM cm_m_cust m WHERE m.cust_code=a.cust_code),'')"
FR="'260701'"; BFT="'260701'"
CUR=f"""
 SELECT a.TO_GAGONG_PROC_CODE part, UPPER(a.mat_code) mat, a.maint_ymd ymd, a.maint_qty*-1 inq,CAST(0 AS decimal(18,4)) outq,CAST(0 AS decimal(18,4)) etc,'생산창고입고' div, {CUST} tag
   FROM PU_T_STOCK_MAINT a WHERE a.maint_ymd>={FR} AND a.maint_tag='B' AND ISNULL(a.out_wh_gubun,'1')='1' AND a.maint_qty<>0 AND {INSP} AND a.TO_GAGONG_PROC_CODE>''
 UNION ALL SELECT a.gagong_proc_code, UPPER(a.mat_code), a.cut_ymd, a.cut_qty,0,0,'가공생산입고','제조1팀' FROM pu_t_cut_dtl a WHERE a.cut_ymd>={FR} AND a.cut_qty<>0 AND a.gagong_proc_code>''
 UNION ALL SELECT a.TO_GAGONG_PROC_CODE, UPPER(a.mat_code), a.maint_ymd, 0, a.maint_qty*-1,0,'자재창고반품',{CUST} FROM PU_T_STOCK_MAINT a WHERE a.maint_ymd>={FR} AND a.maint_tag='T' AND ISNULL(a.out_wh_gubun,'3')='3' AND a.maint_qty<>0 AND a.TO_GAGONG_PROC_CODE>''
 UNION ALL SELECT a.TO_GAGONG_PROC_CODE, UPPER(a.mat_code), a.maint_ymd, 0, a.maint_qty,0,'가공부품이동',{CUST} FROM PU_T_STOCK_MAINT a WHERE a.maint_ymd>={FR} AND a.maint_tag='C' AND a.maint_qty<>0 AND a.TO_GAGONG_PROC_CODE>''
 UNION ALL SELECT a.STOCK_PART_CODE, UPPER(a.item_code), a.prod_ymd, a.prod_qty,0,0,'SUB생산실적','' FROM pr_t_prod_dtl a WHERE a.prod_ymd>={FR} AND a.STOCK_PART_CODE>'' AND NOT EXISTS(SELECT 1 FROM sa_t_stock_maint s WHERE s.maint_ymd=a.prod_ymd AND s.item_code=a.item_code AND s.in_part_code=a.stock_part_code)
 UNION ALL SELECT a.IN_PART_CODE, UPPER(a.item_code), a.maint_ymd, a.maint_qty,0,0,'생산실적',{CUST} FROM sa_t_stock_maint a WHERE a.maint_ymd>={FR} AND a.IN_PART_CODE>''
 UNION ALL SELECT a.part_code, UPPER(a.mat_code), a.maint_ymd, a.maint_qty,0,0,'기초재고',{CUST} FROM PR_T_STOCK_MAINT_MAT a WHERE a.maint_ymd>={FR} AND a.part_code>'' AND a.maint_tag='3' AND a.maint_qty<>0
 UNION ALL SELECT a.part_code, UPPER(a.mat_code), a.maint_ymd, 0,0,a.maint_qty,'재고조정',{CUST} FROM PR_T_STOCK_MAINT_MAT a WHERE a.maint_ymd>={FR} AND a.part_code>'' AND a.maint_tag IN ('2','1') AND a.maint_qty<>0
 UNION ALL SELECT a.part_code, UPPER(a.mat_code), a.maint_ymd, 0, a.maint_qty*-1,0,'생산사용',{CUST} FROM PR_T_STOCK_MAINT_MAT a WHERE a.maint_ymd>={FR} AND a.part_code>'' AND a.maint_tag='4' AND a.maint_qty<>0
"""
BF=f"""
 SELECT a.gagong_proc_code part, UPPER(a.mat_code) mat, a.stock_qty sq FROM PR_T_MONTH_STOCK_WH a WHERE a.stock_yymm='2502'
 UNION ALL SELECT a.TO_GAGONG_PROC_CODE, UPPER(a.mat_code), a.maint_qty*-1 FROM PU_T_STOCK_MAINT a WHERE a.maint_ymd>'250299' AND a.maint_ymd<{BFT} AND a.maint_tag='B' AND ISNULL(a.out_wh_gubun,'1')='1' AND {INSP} AND a.TO_GAGONG_PROC_CODE>''
 UNION ALL SELECT a.STOCK_PART_CODE, UPPER(a.item_code), a.prod_qty FROM pr_t_prod_dtl a WHERE a.prod_ymd>'250299' AND a.prod_ymd<{BFT} AND a.STOCK_PART_CODE>'' AND NOT EXISTS(SELECT 1 FROM sa_t_stock_maint s WHERE s.maint_ymd=a.prod_ymd AND s.item_code=a.item_code AND s.in_part_code=a.stock_part_code)
 UNION ALL SELECT a.IN_PART_CODE, UPPER(a.item_code), a.MAINT_QTY FROM sa_t_stock_maint a WHERE a.maint_ymd>'250299' AND a.maint_ymd<{BFT} AND a.IN_PART_CODE>''
 UNION ALL SELECT a.gagong_proc_code, UPPER(a.mat_code), a.cut_qty FROM pu_t_cut_dtl a WHERE a.cut_ymd>'250299' AND a.cut_ymd<{BFT} AND a.gagong_proc_code>'' AND a.cut_qty<>0
 UNION ALL SELECT a.PART_CODE, UPPER(a.MAT_CODE), a.MAINT_QTY FROM PR_T_STOCK_MAINT_MAT a WHERE a.MAINT_YMD>'250299' AND a.MAINT_YMD<{BFT} AND a.PART_CODE>'' AND a.MAINT_TAG IN ('3','2','1')
 UNION ALL SELECT a.PART_CODE, UPPER(a.MAT_CODE), a.MAINT_QTY FROM PR_T_STOCK_MAINT_MAT a WHERE a.MAINT_YMD>'250299' AND a.MAINT_YMD<{BFT} AND a.PART_CODE>'' AND a.MAINT_TAG='4'
 UNION ALL SELECT a.TO_GAGONG_PROC_CODE, UPPER(a.mat_code), a.MAINT_QTY FROM PU_T_STOCK_MAINT a WHERE a.MAINT_YMD>'250299' AND a.MAINT_YMD<{BFT} AND a.maint_tag='T' AND a.TO_GAGONG_PROC_CODE>''
 UNION ALL SELECT a.TO_GAGONG_PROC_CODE, UPPER(a.mat_code), a.MAINT_QTY*-1 FROM PU_T_STOCK_MAINT a WHERE a.MAINT_YMD>'250299' AND a.MAINT_YMD<{BFT} AND a.maint_tag='C' AND a.TO_GAGONG_PROC_CODE>''
"""
# ★유니버스 = pr_t_mat_stock_wh (생산파트재고 기준정보)
uni=live("SELECT part_code part, UPPER(mat_code) mat, SUM(stock_qty) snap FROM pr_t_mat_stock_wh GROUP BY part_code, UPPER(mat_code)")
bf=live(f"SELECT part, mat, SUM(sq) bf FROM ({BF}) b GROUP BY part, mat")
lines=live(f"SELECT part, mat, ymd, inq, outq, etc, div, tag FROM ({CUR}) x ORDER BY part, mat, ymd")
item=live("SELECT UPPER(item_code) mat, item_desc, item_spec, item_sgroup FROM cm_m_item")
raw0=open(r"d:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js",encoding="utf-8").read()
DB0=json.loads(raw0[raw0.index("const DB = ")+len("const DB = "):raw0.rindex(";")])
sgm={str(k).strip():str(v).strip() for k,v in (DB0.get('sgroupNames') or {}).items()}
net=lines.assign(v=lines.inq-lines.outq+lines.etc).groupby(['part','mat'])['v'].sum().reset_index()
left=uni.merge(bf,on=['part','mat'],how='left').merge(net,on=['part','mat'],how='left').fillna({'bf':0,'v':0})
left['stock']=left['bf']+left['v']
# 검증
def g(p,m):
    r=left[(left.part==p)&(left.mat==m)]; return None if r.empty else (round(float(r.stock.iloc[0]),1),round(float(r.bf.iloc[0]),1),round(float(r.snap.iloc[0]),1))
print("검증 S6/4930A20053B (라이브 우측 3,130):", g('S6','4930A20053B'))
print("검증 S10/MJU66929204 (라이브 600):", g('S10','MJU66929204'))
print("검증 S5/AJR76562819-STS (라이브 0):", g('S5','AJR76562819-STS'), " S5-2:", g('S5-2','AJR76562819-STS'))
print("유령 확인 bare AJR76562819 (없어야함):", g('IS0001','AJR76562819'), left[left.mat=='AJR76562819'][['part','mat','stock']].to_string(index=False))
# 기록
left=left.merge(item.drop_duplicates('mat'),on='mat',how='left').fillna({'item_desc':'','item_spec':'','item_sgroup':''})
left=left[left.stock.abs()>0.0001].copy()
left['sgn']=left['item_sgroup'].map(lambda x: sgm.get(str(x).strip(),'' if str(x).strip() in('','nan') else str(x).strip()))
left=left.sort_values(['part','item_desc','mat'])
prodStock=[[r.part,r.mat,r.item_desc or '',r.item_spec or '',r.sgn or '',round(float(r.stock),3),round(float(r.bf),3)] for r in left.itertuples()]
keys=set(r.part+'||'+r.mat for r in left.itertuples())   # 유니버스로 moves 제한
mv={}
for r in lines.itertuples():
    k=r.part+'||'+r.mat
    if k in keys: mv.setdefault(k,[]).append([r.ymd, round(float(r.inq),3), round(float(r.outq),3), round(float(r.etc),3), r.div, (r.tag or '').strip()])
pn=live("SELECT gagong_proc_code code, gagong_proc_desc nm FROM PR_M_PROC_GAGONG")
partNames={str(r.code).strip():str(r.nm).strip() for r in pn.itertuples()}
DB0['prodStock']=prodStock; DB0['prodMoves']=mv; DB0['prodPartNames']=partNames
head=raw0[:raw0.index("const DB = ")+len("const DB = ")]
open(r"d:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js","w",encoding="utf-8").write(head+json.dumps(DB0,ensure_ascii=False,indent=0)+";\n")
print("data.js 기록 — prodStock", len(prodStock),"품목, moves", len(mv),", 재고합", round(sum(r[5] for r in prodStock),1))
