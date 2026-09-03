# -*- coding: utf-8 -*-
"""⑤420 +2,448 — 두 계획원천을 420 SQL 그대로 돌려 비교
   PLAN_T:  new = nx.v_plan_part_copy_new
            nx  = nx.PR_T_PLAN_PART_COPY   (레거시 미러)
   ★파트별 원천(plan_part_dtl vs 라이브 PART_COPY)은 이미 동일 확인됨.
     그러면 nx.PR_T_PLAN_PART_COPY(미러) 가 라이브와 다른가? 를 먼저 본다."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.path.insert(0, r'c:\Users\박근민\Desktop\New_ERP')
import pyodbc, db_client
def C(db):
    return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
                          f'DATABASE={db};UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
live = C('PARTNER_ERP').cursor(); nx = C('PARTNER_ERP_TEST3').cursor()
F, T, WC = '260902', '260907', 'P2'

def q(cur, t, sql):
    print(f'\n-- {t}')
    try:
        cur.execute(sql)
        cols = [d[0] for d in cur.description]; rs = cur.fetchall()
        if not rs: print('   (none)'); return
        print('   ' + ' | '.join(cols))
        for r in rs[:20]: print('   ' + ' | '.join('' if v is None else str(v) for v in r))
        if len(rs) > 20: print(f'   ... {len(rs)}행')
    except Exception as e: print('   ERR', str(e)[:200])

BASE = f"""WHERE a.GC_GUBUN='Q' AND a.WORK_CODE='{WC}' AND a.PART_PLAN_YMD<='{T}'
             AND a.PART_PLAN_YMD>='{F}'"""

print('■ 420 base 집계 — 세 소스')
for nm, cur, tb in (('라이브 PART_COPY', live, 'PR_T_PLAN_PART_COPY'),
                    ('nx 미러 PART_COPY', nx, 'nx.PR_T_PLAN_PART_COPY'),
                    ('웹 뷰 v_plan_part_copy_new', nx, 'nx.v_plan_part_copy_new')):
    try:
        cur.execute(f"""SELECT COUNT(*) rows_,
                               COUNT(DISTINCT a.ASSY_ITEM_CODE+'|'+ISNULL(a.UPPER_ITEM_CODE,'')+'|'+a.ITEM_CODE) grains,
                               SUM(CAST(a.PART_PLAN_QTY AS float)) q
                          FROM {tb} a WITH(NOLOCK) {BASE}""")
        r = cur.fetchone()
        print(f'   {nm:32s} {r[0]:>7,}행 {r[1]:>7,}그레인 {(r[2] or 0):>12,.0f}')
    except Exception as e:
        print(f'   {nm:32s} ERR {str(e)[:100]}')

print('\n■ ★nx 미러가 라이브와 같은가 (420 이 nx 소스로 읽는 것)')
q(nx, '미러 vs 라이브 — 그레인별 차이 TOP', f"""
    SELECT TOP 15 ISNULL(m.assy,l.assy) assy, ISNULL(m.item,l.item) item,
           ISNULL(l.q,0) 라이브, ISNULL(m.q,0) 미러, ISNULL(m.q,0)-ISNULL(l.q,0) 차
      FROM (SELECT a.ASSY_ITEM_CODE assy, a.ITEM_CODE item, SUM(CAST(a.PART_PLAN_QTY AS float)) q
              FROM nx.PR_T_PLAN_PART_COPY a WITH(NOLOCK) {BASE}
             GROUP BY a.ASSY_ITEM_CODE, a.ITEM_CODE) m
      FULL JOIN (SELECT a.ASSY_ITEM_CODE assy, a.ITEM_CODE item, SUM(CAST(a.PART_PLAN_QTY AS float)) q
                   FROM PARTNER_ERP.dbo.PR_T_PLAN_PART_COPY a WITH(NOLOCK) {BASE}
                  GROUP BY a.ASSY_ITEM_CODE, a.ITEM_CODE) l
        ON l.assy=m.assy AND l.item=m.item
     WHERE ISNULL(m.q,0)<>ISNULL(l.q,0) ORDER BY ABS(ISNULL(m.q,0)-ISNULL(l.q,0)) DESC""")

print('\n■ ★웹뷰 vs nx미러 — 그레인별 차이 TOP (420 화면차 +2,448 의 정체)')
q(nx, '웹뷰 vs 미러', f"""
    SELECT TOP 15 ISNULL(v.assy,m.assy) assy, ISNULL(v.item,m.item) item,
           ISNULL(m.q,0) 미러, ISNULL(v.q,0) 웹뷰, ISNULL(v.q,0)-ISNULL(m.q,0) 차
      FROM (SELECT a.ASSY_ITEM_CODE assy, a.ITEM_CODE item, SUM(CAST(a.PART_PLAN_QTY AS float)) q
              FROM nx.v_plan_part_copy_new a WITH(NOLOCK) {BASE}
             GROUP BY a.ASSY_ITEM_CODE, a.ITEM_CODE) v
      FULL JOIN (SELECT a.ASSY_ITEM_CODE assy, a.ITEM_CODE item, SUM(CAST(a.PART_PLAN_QTY AS float)) q
                   FROM nx.PR_T_PLAN_PART_COPY a WITH(NOLOCK) {BASE}
                  GROUP BY a.ASSY_ITEM_CODE, a.ITEM_CODE) m
        ON m.assy=v.assy AND m.item=v.item
     WHERE ISNULL(v.q,0)<>ISNULL(m.q,0) ORDER BY ABS(ISNULL(v.q,0)-ISNULL(m.q,0)) DESC""")

print('\n■ AJR30123401 상세 (nx=19 / new=245)')
for nm, cur, tb in (('라이브', live, 'PR_T_PLAN_PART_COPY'),
                    ('nx미러', nx, 'nx.PR_T_PLAN_PART_COPY'),
                    ('웹뷰', nx, 'nx.v_plan_part_copy_new')):
    q(cur, f'{nm} AJR30123401 × MJU67039503', f"""
        SELECT a.WORK_ORDER, a.PART_PLAN_YMD, a.GC_GUBUN, a.WORK_CODE, a.PROC_SEQ,
               ISNULL(a.UPPER_ITEM_CODE,'') upper, CAST(a.PART_PLAN_QTY AS float) q
          FROM {tb} a WITH(NOLOCK)
         WHERE a.ASSY_ITEM_CODE='AJR30123401' AND a.ITEM_CODE='MJU67039503'
           AND a.PART_PLAN_YMD BETWEEN '{F}' AND '{T}'
         ORDER BY 2,1""")
