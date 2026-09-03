# -*- coding: utf-8 -*-
"""⑤420 +2,448 / ⑨040 -66 의 원인 규명 (읽기 전용)"""
import sys, io, os, collections, traceback
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
B = r'c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend'
sys.path.insert(0, B); sys.path.insert(0, os.path.join(B, 'routers'))
sys.path.insert(0, r'c:\Users\박근민\Desktop\New_ERP')
os.chdir(B)
import pyodbc, db_client
def C(db):
    return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
                          f'DATABASE={db};UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
live = C('PARTNER_ERP').cursor(); nx = C('PARTNER_ERP_TEST3').cursor()

def hdr(t): print('\n' + '═' * 96); print(t); print('═' * 96)
def q(cur, t, sql, *a):
    print(f'\n-- {t}')
    try:
        cur.execute(sql, *a)
        cols = [d[0] for d in cur.description]; rs = cur.fetchall()
        if not rs: print('   (none)'); return
        print('   ' + ' | '.join(cols))
        for r in rs[:16]: print('   ' + ' | '.join('' if v is None else str(v) for v in r))
        if len(rs) > 16: print(f'   ... {len(rs)}행')
    except Exception as e: print('   ERR', str(e)[:200])

hdr('⑨ 040 — 제번 6J3M0012 : 레거시 72 / 웹 63 (도번 7개 전부 -9)')
q(live, '라이브 SA_T_PLAN_ITEM_DTL', """
    SELECT WORK_ORDER, SPLIT_WORK_ORDER, C_ITEM_CODE, PLAN_YMD, PLAN_QTY, LOT_QTY, USE_QTY
      FROM SA_T_PLAN_ITEM_DTL WITH(NOLOCK) WHERE WORK_ORDER='6J3M0012' ORDER BY 3""")
q(nx, '웹 nx.sale_plan_item', """
    SELECT WORK_ORDER, SPLIT_WORK_ORDER, C_ITEM_CODE, PLAN_YMD, PLAN_QTY, LOT_QTY, USE_QTY
      FROM nx.sale_plan_item WITH(NOLOCK) WHERE WORK_ORDER='6J3M0012' ORDER BY 3""")
q(live, '라이브 SA_T_PLAN_DTL (원본)', """
    SELECT WORK_ORDER, SPLIT_WORK_ORDER, MODEL_NO, PLAN_YMD, LOT_QTY, PLAN_QTY
      FROM SA_T_PLAN_DTL WITH(NOLOCK) WHERE WORK_ORDER='6J3M0012'""")
q(nx, '웹 nx.sale_plan', """
    SELECT work_order, split_work_order, model_no, plan_ymd, lot_qty, plan_qty
      FROM nx.sale_plan WITH(NOLOCK) WHERE work_order='6J3M0012'""")
q(nx, '웹 nx.plan_dtl (업로드 원본)', """
    SELECT WORK_ORDER, MODEL_NO, PLAN_YMD, LOT_QTY, PLAN_QTY, REMAIN_QTY, TOTAL_QTY
      FROM nx.plan_dtl WITH(NOLOCK) WHERE WORK_ORDER='6J3M0012'""")
q(live, '라이브 PR_T_PLAN_DTL (업로드 원본)', """
    SELECT WORK_ORDER, MODEL_NO, PLAN_YMD, ORG_PLAN_YMD, LOT_QTY, PLAN_QTY, REMAIN_QTY, TOTAL_QTY
      FROM PR_T_PLAN_DTL WITH(NOLOCK) WHERE WORK_ORDER='6J3M0012'""")

hdr('⑨ 040 — 레거시에만 있는 2건 (A/S 제번)')
for w in ('WO1094982GR', 'WO1095018ZZ'):
    q(live, f'라이브 PR_T_PLAN_INPUT {w}', """
        SELECT WORK_ORDER, ITEM_CODE, PLAN_YMD, PLAN_QTY, LINE_NO, PROD_TAG
          FROM PR_T_PLAN_INPUT WITH(NOLOCK) WHERE WORK_ORDER=?""", w)
    q(nx, f'웹 nx.prod_plan_input {w}', """
        SELECT WORK_ORDER, ITEM_CODE, PLAN_YMD, PLAN_QTY, LINE_NO
          FROM nx.prod_plan_input WITH(NOLOCK) WHERE WORK_ORDER=?""", w)

hdr('⑤ 420 — AJR30123401 : nx=19 / new=245 (+226)')
q(nx, '웹 nx.plan_part_dtl', """
    SELECT work_order, item_code, part_plan_ymd, plan_ymd, proc_seq, gc_gubun,
           CAST(part_plan_qty AS float) q, RTRIM(ISNULL(gagong_proc_code,'')) gpc
      FROM nx.plan_part_dtl WITH(NOLOCK)
     WHERE RTRIM(assy_item_code)='AJR30123401' AND part_plan_ymd BETWEEN '260902' AND '260907'
     ORDER BY 3,1""")
q(live, '라이브 PR_T_PLAN_PART_COPY', """
    SELECT WORK_ORDER, ITEM_CODE, PART_PLAN_YMD, PLAN_YMD, PROC_SEQ, GC_GUBUN,
           CAST(PART_PLAN_QTY AS float) q, RTRIM(ISNULL(GAGONG_PROC_CODE,'')) gpc
      FROM PR_T_PLAN_PART_COPY WITH(NOLOCK)
     WHERE RTRIM(ASSY_ITEM_CODE)='AJR30123401' AND PART_PLAN_YMD BETWEEN '260902' AND '260907'
     ORDER BY 3,1""")

hdr('⑤ 420 — 웹에만 있는 조합 5211A10305E (자기 자신이 아닌 도번들)')
q(nx, '웹 plan_part_dtl 5211A10305E', """
    SELECT work_order, assy_item_code, item_code, part_plan_ymd, proc_seq, gc_gubun,
           CAST(part_plan_qty AS float) q
      FROM nx.plan_part_dtl WITH(NOLOCK)
     WHERE RTRIM(assy_item_code)='5211A10305E' AND part_plan_ymd BETWEEN '260902' AND '260907'""")
q(live, '라이브 PART_COPY 5211A10305E', """
    SELECT WORK_ORDER, ASSY_ITEM_CODE, ITEM_CODE, PART_PLAN_YMD, PROC_SEQ, GC_GUBUN,
           CAST(PART_PLAN_QTY AS float) q
      FROM PR_T_PLAN_PART_COPY WITH(NOLOCK)
     WHERE RTRIM(ASSY_ITEM_CODE)='5211A10305E' AND PART_PLAN_YMD BETWEEN '260902' AND '260907'""")
