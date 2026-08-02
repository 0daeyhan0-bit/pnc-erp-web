# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
print(db_client.run_query("SELECT DETAIL_CODE cd, DETAIL_DESC nm FROM CM_M_MASTER_DETAIL WHERE KIND_CODE='PR011' ORDER BY DETAIL_CODE").to_string(index=False))
