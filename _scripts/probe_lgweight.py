# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc, pandas as pd
def live(sql):
    cs=(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
    cn=pyodbc.connect(cs, readonly=True)
    try: return pd.read_sql(sql, cn)
    finally: cn.close()

# 1) mkt 내수/수출 확인: 각 mkt 합계
print("== mkt별 합계(금액) — 목표: 수출 1,475,785,859 / 내수 1,781,558,418 ==")
print(live("SELECT isnull(mkt,'') mkt, COUNT(DISTINCT item_code) items, SUM(recv_amt) amt FROM sa_t_lg_receiving_dtl WHERE receiving_ymd BETWEEN '260701' AND '260718' GROUP BY mkt").to_string(index=False))

# 2) f_get_weight 직접 테스트 (ERP 5211A10305E 동소요량=291,354.168)
print("\n== f_get_weight 테스트 ==")
for it in ('5211A10305E','5211A20459J','ADM72950717'):
    try:
        df=live(f"SELECT dbo.f_get_weight('{it}',1) w1, dbo.f_get_weight('{it}',0) w0")
        print(f"{it}: w(,1)={df['w1'].iloc[0]}  w(,0)={df['w0'].iloc[0]}")
    except Exception as e: print(it,"ERR",str(e)[:120])

# 3) 동소요량이 weight×수량인지: 5211A10305E 내수 recv_qty 총합
print("\n== 5211A10305E recv_qty 총합 & weight×qty 확인 ==")
print(live("SELECT SUM(recv_qty) qty FROM sa_t_lg_receiving_dtl WHERE item_code='5211A10305E' AND receiving_ymd BETWEEN '260701' AND '260718'").to_string(index=False))

# 4) 전체 동소요량 합계(dw 방식: 품목별 f_get_weight(item,1) 합) — 목표 1,917,070
print("\n== 품목별 f_get_weight(item,1) 합계 (전체 493품목) ==")
print(live("""SELECT SUM(dbo.f_get_weight(item_code,1)) totw FROM
 (SELECT DISTINCT item_code FROM sa_t_lg_receiving_dtl WHERE receiving_ymd BETWEEN '260701' AND '260718') x""").to_string(index=False))
