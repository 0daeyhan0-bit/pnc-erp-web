# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
for sp in ('SP_PU_CALC_ALL_STOCK','SP_PU_SET_MAT_STOCK','SP_PU_CHECK_STOCK'):
    print("\n"+"="*90)
    print(f"===== {sp} =====")
    print("="*90)
    df=db_client.run_query(f"SELECT m.definition FROM sys.sql_modules m JOIN sys.objects o ON o.object_id=m.object_id WHERE o.name='{sp}'")
    if df.empty: print("(없음)"); continue
    print(df.iloc[0,0])
