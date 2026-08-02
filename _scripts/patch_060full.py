# -*- coding: utf-8 -*-
# 자재재고입출고현황(060) → data.js. 전 품목 상세라인 + 전월이월(bf). 좌=집계, 우=이력(누적재고 JS계산)
import sys, io, json, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc, pandas as pd
def live(sql):
    cs=(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
    cn=pyodbc.connect(cs, readonly=True)
    try: return pd.read_sql(sql, cn)
    finally: cn.close()
INSP="NOT(ISNULL(a.insp_flag,'N') IN ('S','F') AND ISNULL(a.insp_proc_flag,'0')<>'1')"
W="ISNULL(a.wh_cust_code,'Z99990')='Z99990' AND ISNULL(a.gagong_proc_code,'')='IS0001'"
CUST="ISNULL((SELECT cust_desc FROM cm_m_cust m WHERE m.cust_code=a.cust_code),'')"
# 당월 상세 라인 (mat, ymd, inq, outq, etc, mv, div, cust, wo)
LINES=f"""
 SELECT UPPER(a.mat_code) mat, a.maint_ymd ymd, a.maint_qty inq,CAST(0 AS decimal(18,4)) outq,CAST(0 AS decimal(18,4)) etc,CAST(0 AS decimal(18,4)) mv,
   CASE a.maint_tag WHEN '3' THEN '기초재고' WHEN '9' THEN '자재창고입고' WHEN 'C' THEN IIF(a.maint_qty>0,'가공이동입고','가공이동취소') WHEN 'G' THEN '축관입고' WHEN 'H' THEN '가공입고' WHEN 'S' THEN '세트입고' WHEN 'P' THEN '생산'+IIF(a.maint_qty<0,'취소','') WHEN 'R' THEN '반품' ELSE '' END div, {CUST} cust, a.work_order wo
  FROM pu_t_stock_maint a WHERE a.maint_ymd>='260701' AND a.maint_tag IN ('3','9','C','G','H','S','P','R') AND a.maint_qty<>0 AND {INSP} AND {W}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_ymd, a.maint_qty,0,0,0,'도입-구매',{CUST},a.work_order FROM pu_t_stock_maint_c a WHERE a.maint_ymd>='260701' AND a.maint_qty<>0 AND a.wh_cust_code='Z99990' AND a.part_code='IS0001' AND a.division='P'
 UNION ALL SELECT UPPER(a.mat_code), a.maint_ymd, a.maint_qty*-1,0,0,0,'생산창고반품',{CUST},a.work_order FROM pu_t_stock_maint a WHERE a.maint_ymd>='260701' AND a.maint_tag IN ('T') AND a.maint_qty<>0 AND {INSP} AND {W}
 UNION ALL SELECT UPPER(a.mat_code), a.cut_ymd, a.cut_qty,0,0,0,'자재창고입고','작업처 : 제조1팀',NULL FROM pu_t_cut_dtl a WHERE a.cut_ymd>='260701' AND a.cut_qty<>0 AND a.cut_ymd>='180528' AND {W}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_ymd, 0,0,a.maint_qty,0,'재고조정',{CUST},a.work_order FROM pu_t_stock_maint a WHERE a.maint_ymd>='260701' AND a.maint_tag='2' AND a.maint_qty<>0 AND {W}
 UNION ALL SELECT UPPER(a.item_code), a.move_ymd, 0,0,0, CASE WHEN a.to_cust_code='Z99990' AND a.to_gagong_proc_code='IS0001' THEN a.move_qty ELSE 0 END,'창고재고입고',ISNULL((SELECT cust_desc FROM cm_m_cust m WHERE m.cust_code=CASE WHEN a.to_cust_code='Z99990' THEN a.fr_cust_code ELSE a.to_cust_code END),''),'' FROM PU_T_STOCK_MOVE a WHERE a.move_ymd>='260701' AND a.move_qty<>0 AND a.to_cust_code='Z99990' AND a.to_gagong_proc_code='IS0001'
 UNION ALL SELECT UPPER(a.item_code), a.move_ymd, 0,0,0, CASE WHEN a.fr_cust_code='Z99990' AND a.fr_gagong_proc_code='IS0001' THEN a.move_qty*-1 ELSE 0 END,'창고재고출고',ISNULL((SELECT cust_desc FROM cm_m_cust m WHERE m.cust_code=CASE WHEN a.to_cust_code='Z99990' THEN a.fr_cust_code ELSE a.to_cust_code END),''),'' FROM PU_T_STOCK_MOVE a WHERE a.move_ymd>='260701' AND a.move_qty<>0 AND a.fr_cust_code='Z99990' AND a.fr_gagong_proc_code='IS0001'
 UNION ALL SELECT UPPER(a.mat_code), a.maint_ymd, 0, a.maint_qty*-1,0,0,
   CASE a.maint_tag WHEN '1' THEN '불량' WHEN '4' THEN '생산사용'+IIF(a.maint_qty>0,'취소','') WHEN '5' THEN '협력업체판매' WHEN '6' THEN '일반간판출하' WHEN '8' THEN '라인무상공급' WHEN 'A' THEN '개발불출' WHEN 'B' THEN IIF(a.out_wh_gubun='1','생산창고출고','영업창고출고') WHEN 'J' THEN '출하'+IIF(a.maint_qty>0,'취소','') ELSE '' END,
   ISNULL((SELECT cust_desc FROM cm_m_cust m WHERE m.cust_code=a.cust_code AND a.cust_code<>'Z99990'),''), a.work_order
  FROM pu_t_stock_maint a WHERE a.maint_ymd>='260701' AND a.maint_tag IN ('1','4','5','6','8','A','B','J') AND a.maint_qty<>0 AND {W}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_ymd, 0, a.maint_qty,0,0,'도입-판매',{CUST},a.work_order FROM pu_t_stock_maint_c a WHERE a.maint_ymd>='260701' AND a.maint_qty<>0 AND a.wh_cust_code='Z99990' AND a.part_code='IS0001' AND a.division='Q'
"""
# 전월이월 bf per mat
BF=f"""
 SELECT UPPER(a.mat_code) mat, a.stock_qty sq FROM pu_t_month_stock_wh a WHERE a.stock_yymm='2606' AND a.cust_code='Z99990' AND ISNULL(a.gagong_proc_code,'')='IS0001'
 UNION ALL SELECT UPPER(a.mat_code), a.maint_qty FROM pu_t_stock_maint a WHERE a.maint_ymd>'260699' AND a.maint_ymd<'260701' AND a.maint_tag IN ('3','9','C','G','H','S','P','R') AND {INSP} AND {W}
 UNION ALL SELECT UPPER(a.mat_code), IIF(a.division='Q',-a.maint_qty,a.maint_qty) FROM pu_t_stock_maint_c a WHERE a.maint_ymd>'260699' AND a.maint_ymd<'260701' AND a.wh_cust_code='Z99990' AND a.part_code='IS0001'
 UNION ALL SELECT UPPER(a.mat_code), a.maint_qty*-1 FROM pu_t_stock_maint a WHERE a.maint_ymd>'260699' AND a.maint_ymd<'260701' AND a.maint_tag IN ('T') AND {INSP} AND {W}
 UNION ALL SELECT UPPER(a.mat_code), a.cut_qty FROM pu_t_cut_dtl a WHERE a.cut_ymd>'260699' AND a.cut_ymd<'260701' AND a.cut_ymd>='180528' AND {W}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_qty FROM pu_t_stock_maint a WHERE a.maint_ymd>'260699' AND a.maint_ymd<'260701' AND a.maint_tag='2' AND {W}
 UNION ALL SELECT UPPER(a.item_code), (CASE WHEN a.fr_cust_code='Z99990' AND a.fr_gagong_proc_code='IS0001' THEN a.move_qty*-1 ELSE 0 END)+(CASE WHEN a.to_cust_code='Z99990' AND a.to_gagong_proc_code='IS0001' THEN a.move_qty ELSE 0 END) FROM PU_T_STOCK_MOVE a WHERE a.move_ymd>'260699' AND a.move_ymd<'260701' AND ('Z99990' IN (a.fr_cust_code,a.to_cust_code)) AND ('IS0001' IN (a.fr_gagong_proc_code,a.to_gagong_proc_code))
 UNION ALL SELECT UPPER(a.mat_code), a.maint_qty FROM pu_t_stock_maint a WHERE a.maint_ymd>'260699' AND a.maint_ymd<'260701' AND a.maint_tag IN ('1','4','5','6','8','A','B','J') AND {W}
"""
lines=live(f"SELECT mat, ymd, inq, outq, etc, mv, div, cust, ISNULL(wo,'') wo FROM ({LINES}) x")
bf=live(f"SELECT mat, SUM(sq) bf FROM ({BF}) b GROUP BY mat")
# 좌측: PU_T_MAT_STOCK_WH 목록 기준 + 재고=bf+net
print("lines:",len(lines)," bf mats:",len(bf))
# 좌측 재고 = bf + Σ(inq-outq+etc+mv), 검증
net=lines.assign(v=lines.inq-lines.outq+lines.etc+lines.mv).groupby('mat')['v'].sum().reset_index()
m=bf.merge(net,on='mat',how='outer').fillna(0)
m['stock']=m['bf']+m['v']
print("좌측 검증(집계): 품목",len(m),"재고합",round(m['stock'].sum(),2)," (목표 7,651 / 299,913.0076)")

# 품목명
mats=list(m['mat'].unique())
nm={}
CH=200
for i in range(0,len(mats),CH):
    inlist=",".join("'"+x.replace("'","''")+"'" for x in mats[i:i+CH])
    for r in live(f"SELECT item_code c, item_desc d FROM pr_m_item WHERE item_code IN ({inlist})").itertuples():
        nm[r.c]=r.d
# 최종입고일 = 입고(inq>0) 최대 ymd
li=lines[lines.inq>0].groupby('mat')['ymd'].max().to_dict()

path=r"d:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js"
raw=open(path,encoding="utf-8").read()
head=raw[:raw.index("const DB = ")+len("const DB = ")]
DB=json.loads(raw[raw.index("const DB = ")+len("const DB = "):raw.rindex(";")])
DB['matMoves060']=json.loads(lines.rename(columns={'inq':'i','outq':'o','etc':'e','mv':'mv'})[['mat','ymd','i','o','e','mv','div','cust','wo']].to_json(orient='records',force_ascii=False))
DB['matStock060']=[{'mat':r['mat'],'nm':nm.get(r['mat'],''),'stock':round(r['stock'],4),'bf':round(r['bf'],4),'lastin':li.get(r['mat'],'')} for _,r in m.sort_values('mat').iterrows()]
open(path,"w",encoding="utf-8").write(head+json.dumps(DB,ensure_ascii=False,indent=0)+";\n")
print("data.js 패치완료: matStock060",len(DB['matStock060']),"/ matMoves060",len(DB['matMoves060']))
