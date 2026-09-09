# -*- coding: utf-8 -*-
"""컷오버 후 복구 — r_bulk_copy 가 덮어쓴 뒤 웹 산출물을 되돌린다.

   백업 시각 260909_1315 · protect_web_outputs_260909.py 가 생성.
   r_bulk_copy 실행 **직후** 돌린다(순서 중요 — 먼저 돌리면 다시 덮인다).
"""
import sys, os, io
BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

APPLY = "--apply" in sys.argv
S = "PARTNER_ERP_TEST3.nx"
nx = _nx(); nx.autocommit = False
cur = nx.cursor()
print("컷오버 후 웹 산출물 복구 — 모드:", "★반영" if APPLY else "조회만")
PAIRS = [
    ("PU_T_MONTH_STOCK_WH", "bk_webout_pu_t_month_stock_wh_260909_1315", ['STOCK_YYMM', 'CUST_CODE', 'GAGONG_PROC_CODE', 'MAT_CODE']),   # 3,692행
    ("CS_M_PROC", "bk_webout_cs_m_proc_260909_1315", ['PROC_CODE']),   # 21행
]
for t, bk, keys in PAIRS:
    cur.execute("SELECT COUNT(*) FROM {S}.[{b}]".format(S=S, b=bk))
    nb = cur.fetchone()[0]
    on = " AND ".join("RTRIM(ISNULL(CAST(t.[{c}] AS varchar(60)),''))="
                      "RTRIM(ISNULL(CAST(b.[{c}] AS varchar(60)),''))".format(c=c) for c in keys)
    cur.execute("""SELECT COUNT(*) FROM {S}.[{b}] b
                    WHERE NOT EXISTS(SELECT 1 FROM {S}.[{t}] t WHERE {on})""".format(S=S, b=bk, t=t, on=on))
    miss = cur.fetchone()[0]
    print("  {:<26s} 백업 {:,}행 · 원표에 없는 것 {:,}행".format(t, nb, miss))
    if not APPLY or not miss: continue
    cur.execute("""INSERT INTO {S}.[{t}] SELECT b.* FROM {S}.[{b}] b
                    WHERE NOT EXISTS(SELECT 1 FROM {S}.[{t}] t WHERE {on})""".format(S=S, b=bk, t=t, on=on))
    print("     ✔ 복구 {:,}행".format(cur.rowcount))
if APPLY:
    nx.commit()
    print("✅ 커밋")
else:
    nx.rollback()
nx.close()