# -*- coding: utf-8 -*-
# LG리시빙관리(dw_sa_sale_110) → data.js (라이브,검증). 도번×일자 피벗용 셀 + 품목속성
import sys, io, json, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc, pandas as pd
def live_df(sql):
    cs=(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
    cn=pyodbc.connect(cs, readonly=True)
    try: return pd.read_sql(sql, cn)
    finally: cn.close()

FR,TO='260701','260718'
# 검증
v=live_df(f"SELECT COUNT(DISTINCT item_code) itemcnt, SUM(recv_qty) tq, SUM(recv_amt) ta FROM sa_t_lg_receiving_dtl WHERE receiving_ymd BETWEEN '{FR}' AND '{TO}'")
print("검증:", int(v['itemcnt'].iloc[0]),"품목  수량", round(v['tq'].iloc[0],2),"금액", int(v['ta'].iloc[0]), " (목표 493 / 합계 3,257,344,277)")
print("mkt 분포:")
print(live_df(f"SELECT isnull(mkt,'') mkt, COUNT(*) cnt FROM sa_t_lg_receiving_dtl WHERE receiving_ymd BETWEEN '{FR}' AND '{TO}' GROUP BY mkt").to_string(index=False))

# 셀: item×mkt×day
cells=live_df(f"""
SELECT a.item_code item, ISNULL(a.mkt,'') mkt, CAST(RIGHT(a.receiving_ymd,2) AS INT) d,
  SUM(a.recv_qty) q, SUM(a.recv_amt) amt
FROM sa_t_lg_receiving_dtl a
WHERE a.receiving_ymd BETWEEN '{FR}' AND '{TO}'
GROUP BY a.item_code, ISNULL(a.mkt,''), CAST(RIGHT(a.receiving_ymd,2) AS INT)""")
# 품목속성: 작업처 + 동소요량(정수)
items=live_df(f"""
SELECT m.item_code item,
  CASE WHEN m.work_code>'' THEN m.work_code ELSE m.in_cust_code END wcc,
  CASE WHEN m.work_code>'' THEN (SELECT work_desc FROM pr_m_work WHERE work_code=m.work_code)
       ELSE (SELECT cust_desc FROM cm_m_cust WHERE cust_code=m.in_cust_code) END wc,
  CAST(ROUND(dbo.f_get_weight(m.item_code,1),0) AS BIGINT) wt
FROM pr_m_item m
WHERE m.item_code IN (SELECT DISTINCT item_code FROM sa_t_lg_receiving_dtl WHERE receiving_ymd BETWEEN '{FR}' AND '{TO}')""")
print("cells:",len(cells),"items:",len(items))

path=r"d:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js"
raw=open(path,encoding="utf-8").read()
head=raw[:raw.index("const DB = ")+len("const DB = ")]
DB=json.loads(raw[raw.index("const DB = ")+len("const DB = "):raw.rindex(";")])
DB['lgRecvCells']=json.loads(cells.to_json(orient='records',force_ascii=False))
DB['lgRecvItems']=json.loads(items.to_json(orient='records',force_ascii=False))
DB['lgRecvYm']='2026-07'
open(path,"w",encoding="utf-8").write(head+json.dumps(DB,ensure_ascii=False,indent=0)+";\n")
print("data.js 패치완료 (lgRecvCells/lgRecvItems)")
