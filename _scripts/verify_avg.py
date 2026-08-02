# -*- coding: utf-8 -*-
# 평균법 검증: 라이브 일수불(260717) 저장값에서 단가 일관성 확인
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc, pandas as pd
def live(sql):
    cs=(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};"
        f"DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
    cn=pyodbc.connect(cs, readonly=True)
    try: return pd.read_sql(sql, cn)
    finally: cn.close()

print("== DAILY 테이블 전체 컬럼 ==")
print(", ".join(live("SELECT TOP 1 * FROM PU_T_MONTH_STOCK_WH_DAILY WHERE cust_code='Z99990' AND STOCK_YMD='260717'").columns.tolist()))

print("\n== 샘플 10품목: 저장 수량/금액 및 내재단가 ==")
df=live("""
SELECT TOP 12 mat_code,
  basic_qty, basic_amt, input_qty, input_amt, output_qty, output_amt, trans_qty, trans_amt, stock_qty, stock_amt
FROM PU_T_MONTH_STOCK_WH_DAILY
WHERE cust_code='Z99990' AND STOCK_YMD='260717' AND input_qty>0 AND output_qty>0 AND stock_qty>0
ORDER BY input_amt DESC
""")
def upr(a,q):
    try: return round(a/q,2) if q else None
    except: return None
rows=[]
for _,r in df.iterrows():
    b_u=upr(r.basic_amt,r.basic_qty); i_u=upr(r.input_amt,r.input_qty)
    o_u=upr(r.output_amt,r.output_qty); s_u=upr(r.stock_amt,r.stock_qty)
    # 총평균 예상단가 = (기초금액+입고금액)/(기초수량+입고수량)
    tot_q=(r.basic_qty or 0)+(r.input_qty or 0); tot_a=(r.basic_amt or 0)+(r.input_amt or 0)
    avg_u=round(tot_a/tot_q,2) if tot_q else None
    rows.append([r.mat_code, b_u, i_u, o_u, s_u, avg_u,
                 '출고=평균?' if (o_u and avg_u and abs(o_u-avg_u)<max(1,avg_u*0.01)) else 'X'])
print(pd.DataFrame(rows, columns=['품목','기초단가','입고단가','출고단가','재고단가','총평균단가','출고vs평균']).to_string(index=False))
