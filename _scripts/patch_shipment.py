# -*- coding: utf-8 -*-
# 출하실적현황(dw_sa_list_010) 라인데이터 → data.js (라이브, 검증). 최적화: PR_T_PLAN_INPUT OUTER APPLY TOP1
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

Q = """
SELECT a.SALE_YMD ymd, a.WORK_ORDER wo, a.SPLIT_WORK_ORDER swo, a.ITEM_CODE item,
  a.SALE_QTY qty, a.SALE_COST cost, a.SALE_AMT amt,
  ISNULL((SELECT TOP 1 item_cost FROM pr_m_item_cost WHERE item_code=a.item_code AND cost_apply_ymd<=a.sale_ymd AND cost_tag='S' AND cust_code IN ('1010','1020') ORDER BY cost_apply_ymd DESC),0) mcost,
  a.SALE_USER_ID usr, a.SALE_HMS hms,
  CASE WHEN m.work_code>'' THEN (SELECT work_desc FROM pr_m_work WHERE work_code=m.work_code)
       ELSE (SELECT cust_desc FROM cm_m_cust WHERE cust_code=m.in_cust_code) END wc,
  pi.REMARKS remarks
FROM sa_t_sale_dtl a JOIN pr_m_item m ON a.item_code=m.item_code
 OUTER APPLY (SELECT TOP 1 REMARKS FROM PR_T_PLAN_INPUT WHERE WORK_ORDER=a.WORK_ORDER) pi
WHERE a.sale_ymd BETWEEN '260701' AND '260718'
"""
df=live_df(Q)
print("출하실적:", len(df),"건 수량", round(df.qty.sum(),2), "금액", int(df.amt.sum()), " (목표 4,150 / 142,802 / 3,190,024,152)")

path=r"d:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js"
raw=open(path,encoding="utf-8").read()
head=raw[:raw.index("const DB = ")+len("const DB = ")]
DB=json.loads(raw[raw.index("const DB = ")+len("const DB = "):raw.rindex(";")])
DB['shipment']=json.loads(df.to_json(orient='records',force_ascii=False))
open(path,"w",encoding="utf-8").write(head+json.dumps(DB,ensure_ascii=False,indent=0)+";\n")
print("data.js 패치완료 (shipment)")
