# -*- coding: utf-8 -*-
"""R01 생산공정 클린(nx.prodinfo_proc) 완성 seed: 미러 PR_M_ITEM_PROC_GAGONG에 있고
   prodinfo_proc엔 없는 품목만 보충(멱등). 웹편집분(이미 있는 품목)은 절대 건드리지 않음.
   ITEM_PROC_GAGONG_CLEAN_260909.md §4-1. --commit 없으면 dry-run."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\PNC_ERP_Web\backend')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
from common import _nx
commit = '--commit' in sys.argv
cn=_nx(); c=cn.cursor()
def n(q):
    c.execute(q); return c.fetchone()[0]
before_rows=n("SELECT COUNT(*) FROM nx.prodinfo_proc")
before_items=n("SELECT COUNT(DISTINCT UPPER(LTRIM(RTRIM(item_code)))) FROM nx.prodinfo_proc")
need=n("""SELECT COUNT(*) FROM (SELECT DISTINCT UPPER(LTRIM(RTRIM(ITEM_CODE))) ic FROM nx.PR_M_ITEM_PROC_GAGONG
         EXCEPT SELECT DISTINCT UPPER(LTRIM(RTRIM(item_code))) FROM nx.prodinfo_proc) t""")
print("seed 전: prodinfo_proc 행 %d·품목 %d / 보충대상 품목 %d" % (before_rows,before_items,need))
c.execute("""INSERT INTO nx.prodinfo_proc
    (item_code,proc_seq,work_code,gagong_proc_code,s_work_code,mach_code,work_qty,std_size,mix_gagong,
     gagong_proc_flag,gagong_proc_seq,ready_st,mach_ct,inwon,human_st,tot_st,jp_proc_method,lt_hr,key_id,upd_user,upd_at)
  SELECT m.ITEM_CODE,m.PROC_SEQ,m.WORK_CODE,m.GAGONG_PROC_CODE,m.S_WORK_CODE,m.MACH_CODE,m.WORK_QTY,m.STD_SIZE,m.MIX_GAGONG,
         m.GAGONG_PROC_FLAG,m.GAGONG_PROC_SEQ,m.READY_ST,m.MACH_CT,m.INWON,m.HUMAN_ST,m.TOT_ST,m.JP_PROC_METHOD,m.LT_HR,m.KEY_ID,'seed_r01',getdate()
    FROM nx.PR_M_ITEM_PROC_GAGONG m
   WHERE UPPER(LTRIM(RTRIM(m.ITEM_CODE))) NOT IN (SELECT UPPER(LTRIM(RTRIM(item_code))) FROM nx.prodinfo_proc)""")
ins=c.rowcount
after_rows=n("SELECT COUNT(*) FROM nx.prodinfo_proc")
after_items=n("SELECT COUNT(DISTINCT UPPER(LTRIM(RTRIM(item_code)))) FROM nx.prodinfo_proc")
# 검증: prodinfo_proc ⊇ 미러 (미러 품목 전부 포함)
still_missing=n("""SELECT COUNT(*) FROM (SELECT DISTINCT UPPER(LTRIM(RTRIM(ITEM_CODE))) ic FROM nx.PR_M_ITEM_PROC_GAGONG
         EXCEPT SELECT DISTINCT UPPER(LTRIM(RTRIM(item_code))) FROM nx.prodinfo_proc) t""")
print("INSERT %d행 → prodinfo_proc 행 %d·품목 %d · 미러대비 잔여미포함 품목 %d" % (ins,after_rows,after_items,still_missing))
if commit and still_missing==0:
    cn.commit(); print("★ COMMIT (prodinfo_proc ⊇ 미러 확인)")
else:
    cn.rollback(); print("dry-run rollback" if not commit else "★잔여미포함>0 → rollback(중단)")
