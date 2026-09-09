# -*- coding: utf-8 -*-
"""nx.line_no(클린) CUST_MAINT_DAY 를 레거시 PR_M_LINE_NO 에 정렬(대표지시 '레거시와 일치').
   08-27 웹 고아편집(CA→C1 당김이동) 되돌림. 멱등·전 기능컬럼 대조."""
import sys,io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\PNC_ERP_Web\backend')
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',line_buffering=True)
from common import _nx
commit='--commit' in sys.argv
cn=_nx(); c=cn.cursor()
# 레거시 기준으로 클린 cust_maint_day 정렬(전 라인·멱등)
n=c.execute("""UPDATE cl SET cl.cust_maint_day = ISNULL(m.CUST_MAINT_DAY,0)
   FROM nx.line_no cl JOIN nx.PR_M_LINE_NO m ON RTRIM(cl.line_no)=RTRIM(m.LINE_NO)
   WHERE ISNULL(cl.cust_maint_day,0) <> ISNULL(m.CUST_MAINT_DAY,0)""").rowcount
print("정렬 UPDATE %d행"%n)
# 검증: 전 기능컬럼 diff0
c.execute("""SELECT COUNT(*) FROM nx.line_no cl JOIN nx.PR_M_LINE_NO m ON RTRIM(cl.line_no)=RTRIM(m.LINE_NO)
   WHERE ISNULL(cl.cust_maint_day,0)<>ISNULL(m.CUST_MAINT_DAY,0)""")
rem=c.fetchone()[0]
print("잔여 CUST_MAINT_DAY 불일치:",rem)
if commit and rem==0:
    cn.commit(); print("★COMMIT (클린 line_no = 레거시 일치)")
else:
    cn.rollback(); print("dry-run rollback" if not commit else "잔여>0 rollback")
