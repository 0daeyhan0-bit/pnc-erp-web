# -*- coding: utf-8 -*-
"""A/S 이중계상 확증 (EXISTS → LEFT JOIN 으로 교체)"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.path.insert(0, r'c:\Users\박근민\Desktop\New_ERP')
import pyodbc, db_client
def C(db):
    return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
                          f'DATABASE={db};UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
live = C('PARTNER_ERP').cursor(); nx = C('PARTNER_ERP_TEST3').cursor()
F, T = '260902', '260907'

def q(cur, t, sql):
    print(f'\n-- {t}')
    try:
        cur.execute(sql)
        cols = [d[0] for d in cur.description]; rs = cur.fetchall()
        if not rs: print('   (none)'); return
        print('   ' + ' | '.join(cols))
        for r in rs[:16]: print('   ' + ' | '.join('' if v is None else str(v) for v in r))
    except Exception as e: print('   ERR', str(e)[:200])

print('■ ★A/S 제번이 STEP5(plan_item_dtl) 안에 들어있나')
q(nx, '웹 — A/S 제번 중 plan_item_dtl 에도 있는 것', f"""
    SELECT COUNT(*) AS제번수, SUM(CASE WHEN d.WORK_ORDER IS NOT NULL THEN 1 ELSE 0 END) STEP5에도있음
      FROM (SELECT DISTINCT WORK_ORDER FROM nx.prod_plan_input WITH(NOLOCK)
             WHERE PLAN_YMD BETWEEN '{F}' AND '{T}') p
      LEFT JOIN (SELECT DISTINCT WORK_ORDER FROM nx.plan_item_dtl WITH(NOLOCK)
                  WHERE PLAN_YMD BETWEEN '{F}' AND '{T}') d ON d.WORK_ORDER=p.WORK_ORDER""")

q(live, '라이브 — A/S 제번 중 PR_T_PLAN_ITEM_DTL 에도 있는 것 (0이어야 정상)', f"""
    SELECT COUNT(*) AS제번수, SUM(CASE WHEN d.WORK_ORDER IS NOT NULL THEN 1 ELSE 0 END) ITEMDTL에도있음
      FROM (SELECT DISTINCT WORK_ORDER FROM PR_T_PLAN_INPUT WITH(NOLOCK)
             WHERE PLAN_YMD BETWEEN '{F}' AND '{T}') p
      LEFT JOIN (SELECT DISTINCT WORK_ORDER FROM PR_T_PLAN_ITEM_DTL WITH(NOLOCK)
                  WHERE PLAN_YMD BETWEEN '{F}' AND '{T}') d ON d.WORK_ORDER=p.WORK_ORDER""")

q(nx, '★040 정본 sale_plan_item 에도 A/S 가 섞였나', f"""
    SELECT COUNT(*) AS제번수, SUM(CASE WHEN s.WORK_ORDER IS NOT NULL THEN 1 ELSE 0 END) sale_plan_item에도
      FROM (SELECT DISTINCT WORK_ORDER FROM nx.prod_plan_input WITH(NOLOCK)
             WHERE PLAN_YMD BETWEEN '{F}' AND '{T}') p
      LEFT JOIN (SELECT DISTINCT WORK_ORDER FROM nx.sale_plan_item WITH(NOLOCK)
                  WHERE PLAN_YMD BETWEEN '{F}' AND '{T}') s ON s.WORK_ORDER=p.WORK_ORDER""")

q(live, '라이브 SA_T_PLAN_ITEM_DTL 에 A/S (040 정답지, 0이어야)', f"""
    SELECT COUNT(*) AS제번수, SUM(CASE WHEN s.WORK_ORDER IS NOT NULL THEN 1 ELSE 0 END) SA에도
      FROM (SELECT DISTINCT WORK_ORDER FROM PR_T_PLAN_INPUT WITH(NOLOCK)
             WHERE PLAN_YMD BETWEEN '{F}' AND '{T}') p
      LEFT JOIN (SELECT DISTINCT WORK_ORDER FROM SA_T_PLAN_ITEM_DTL WITH(NOLOCK)
                  WHERE PLAN_YMD BETWEEN '{F}' AND '{T}') s ON s.WORK_ORDER=p.WORK_ORDER""")

print('\n■ ★그럼 580 결과에 A/S 가 두 번 들어가나 — 실제 SP 결과로 확인')
q(nx, '웹 plan_item_dtl 에서 A/S 패턴(WO%) 행 집계', f"""
    SELECT COUNT(*) c, COUNT(DISTINCT WORK_ORDER) wos, SUM(CAST(PLAN_QTY AS float)) q
      FROM nx.plan_item_dtl WITH(NOLOCK)
     WHERE PLAN_YMD BETWEEN '{F}' AND '{T}' AND WORK_ORDER LIKE 'WO%'""")
q(live, '라이브 PR_T_PLAN_ITEM_DTL 의 WO% 행 (없어야)', f"""
    SELECT COUNT(*) c, COUNT(DISTINCT WORK_ORDER) wos, SUM(CAST(PLAN_QTY AS float)) q
      FROM PR_T_PLAN_ITEM_DTL WITH(NOLOCK)
     WHERE PLAN_YMD BETWEEN '{F}' AND '{T}' AND WORK_ORDER LIKE 'WO%'""")

print('\n■ 웹 STEP5 가 A/S 를 넣는 이유 = planrev STEP5-AS 갈래')
q(nx, 'nx.plan_item_dtl 의 A/S vs prod_plan_input 수량 대조', f"""
    SELECT (SELECT SUM(CAST(PLAN_QTY AS float)) FROM nx.plan_item_dtl WITH(NOLOCK)
             WHERE PLAN_YMD BETWEEN '{F}' AND '{T}' AND WORK_ORDER LIKE 'WO%') STEP5_AS,
           (SELECT SUM(CAST(PLAN_QTY AS float)) FROM nx.prod_plan_input WITH(NOLOCK)
             WHERE PLAN_YMD BETWEEN '{F}' AND '{T}') prod_plan_input""")
