# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
print("PR_M_PROC_GAGONG 컬럼:")
print(", ".join(db_client.run_query("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='PR_M_PROC_GAGONG' ORDER BY ORDINAL_POSITION")['COLUMN_NAME'].tolist()))
print("\n전체 내용 (코드→이름):")
print(db_client.run_query("SELECT * FROM PR_M_PROC_GAGONG ORDER BY GAGONG_PROC_CODE").to_string(index=False))
