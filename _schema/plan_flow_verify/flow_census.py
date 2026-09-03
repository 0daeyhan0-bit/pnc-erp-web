# -*- coding: utf-8 -*-
"""레거시 vs 웹 — 계획 테이블 계보 실측 (읽기 전용)
   각 단계 테이블의 행수·수량·일자범위를 라이브/nx 양쪽에서 세어 나란히 놓는다.
   목적 = "어디서부터 갈라지는가"를 단계별로 특정.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.path.insert(0, r'c:\Users\박근민\Desktop\New_ERP')
import pyodbc, db_client
def C(db):
    return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
                          f'DATABASE={db};UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
live = C('PARTNER_ERP').cursor(); nx = C('PARTNER_ERP_TEST3').cursor()

F, T = '260902', '260907'      # 대사 기간

def stat(cur, label, tb, ycol, qcol, wocol='WORK_ORDER', extra=''):
    try:
        cur.execute(f"""SELECT COUNT(*) c, COUNT(DISTINCT {wocol}) wos,
                               SUM(CAST(ISNULL({qcol},0) AS float)) q,
                               MIN({ycol}) f, MAX({ycol}) t
                          FROM {tb} WITH(NOLOCK)
                         WHERE {ycol} BETWEEN '{F}' AND '{T}' {extra}""")
        r = cur.fetchone()
        print(f'   {label:38s} {r[0]:>8,}행 {r[1]:>7,}제번 {(r[2] or 0):>13,.0f}  {r[3]}~{r[4]}')
        return (r[0], r[1], float(r[2] or 0))
    except Exception as e:
        print(f'   {label:38s} ERR {str(e)[:95]}')
        return None

print('═' * 100)
print(f'계획 테이블 계보 실측  (기간 {F}~{T})')
print('═' * 100)

print('\n■ ① 업로드 원본')
stat(live, '라이브 PR_T_PLAN_DTL (PLAN_YMD)', 'PR_T_PLAN_DTL', 'PLAN_YMD', 'PLAN_QTY')
stat(live, '  └ ORG_PLAN_YMD 기준', 'PR_T_PLAN_DTL', 'ISNULL(NULLIF(ORG_PLAN_YMD,\'\'),PLAN_YMD)', 'PLAN_QTY')
stat(nx,   '웹 nx.plan_dtl (PLAN_YMD)', 'nx.plan_dtl', 'PLAN_YMD', 'PLAN_QTY')

print('\n■ ② H단계 = 당김 되돌린 원본 스냅샷')
stat(live, '라이브 SA_T_PLAN_DTL', 'SA_T_PLAN_DTL', 'PLAN_YMD', 'PLAN_QTY')
stat(nx,   '웹 nx.sale_plan', 'nx.sale_plan', 'plan_ymd', 'plan_qty', 'work_order')

print('\n■ ③ I단계 = 품목별(제번×완제품)')
stat(live, '라이브 PR_T_PLAN_ITEM_DTL (당김후)', 'PR_T_PLAN_ITEM_DTL', 'PLAN_YMD', 'PLAN_QTY')
stat(live, '  └ ORG_PLAN_YMD (원본)', 'PR_T_PLAN_ITEM_DTL', 'ISNULL(NULLIF(ORG_PLAN_YMD,\'\'),PLAN_YMD)', 'PLAN_QTY')
stat(live, '라이브 SA_T_PLAN_ITEM_DTL (040용)', 'SA_T_PLAN_ITEM_DTL', 'PLAN_YMD', 'PLAN_QTY')
stat(nx,   '웹 nx.plan_item_dtl (당김후)', 'nx.plan_item_dtl', 'PLAN_YMD', 'PLAN_QTY')
stat(nx,   '웹 nx.sale_plan_item (원본)', 'nx.sale_plan_item', 'PLAN_YMD', 'PLAN_QTY')
stat(nx,   '웹 뷰 v_plan_item_dtl_new (→580)', 'nx.v_plan_item_dtl_new', 'PLAN_YMD', 'PLAN_QTY')
stat(nx,   '웹 뷰 v_sale_plan_item_050 (→040)', 'nx.v_sale_plan_item_050', 'PLAN_YMD', 'PLAN_QTY')

print('\n■ ④ 파트별 (소요일 = PART_PLAN_YMD)')
stat(live, '라이브 PR_T_PLAN_PART_DTL', 'PR_T_PLAN_PART_DTL', 'PART_PLAN_YMD', 'PART_PLAN_QTY')
stat(live, '  └ proc_seq=1 만', 'PR_T_PLAN_PART_DTL', 'PART_PLAN_YMD', 'PART_PLAN_QTY', extra='AND PROC_SEQ=1')
stat(live, '라이브 PR_T_PLAN_PART_COPY', 'PR_T_PLAN_PART_COPY', 'PART_PLAN_YMD', 'PART_PLAN_QTY')
stat(nx,   '웹 nx.plan_part_dtl', 'nx.plan_part_dtl', 'part_plan_ymd', 'part_plan_qty', 'work_order')
stat(nx,   '  └ proc_seq=1 만', 'nx.plan_part_dtl', 'part_plan_ymd', 'part_plan_qty', 'work_order', 'AND proc_seq=1')
stat(nx,   '웹 뷰 v_plan_part_copy_new', 'nx.v_plan_part_copy_new', 'PART_PLAN_YMD', 'PART_PLAN_QTY')

print('\n■ ⑤ 자재소요')
stat(live, '라이브 PR_T_PLAN_PART_MAT', 'PR_T_PLAN_PART_MAT', 'PART_PLAN_YMD', 'PART_PLAN_QTY')
stat(nx,   '웹 nx.plan_part_mat', 'nx.plan_part_mat', 'part_plan_ymd', 'part_plan_qty', 'work_order')

print('\n■ ⑥ 예외생산(A/S)')
stat(live, '라이브 PR_T_PLAN_INPUT', 'PR_T_PLAN_INPUT', 'PLAN_YMD', 'PLAN_QTY')
stat(nx,   '웹 nx.prod_plan_input', 'nx.prod_plan_input', 'PLAN_YMD', 'PLAN_QTY')
stat(nx,   '웹 뷰 v_prod_plan_input_new', 'nx.v_prod_plan_input_new', 'PLAN_YMD', 'PLAN_QTY')

print('\n' + '═' * 100)
print('■ ★일자 컬럼별 분포 — 당김이 실제로 얼마나 움직이나')
print('═' * 100)
for nm, cur, tb, a, b in (
    ('라이브 PR_T_PLAN_DTL', live, 'PR_T_PLAN_DTL', 'PLAN_YMD', 'ORG_PLAN_YMD'),
    ('라이브 PR_T_PLAN_ITEM_DTL', live, 'PR_T_PLAN_ITEM_DTL', 'PLAN_YMD', 'ORG_PLAN_YMD'),
):
    try:
        cur.execute(f"""SELECT COUNT(*) c,
                               SUM(CASE WHEN ISNULL(NULLIF({b},''),{a})={a} THEN 1 ELSE 0 END) same_,
                               SUM(CASE WHEN ISNULL(NULLIF({b},''),{a})<>{a} THEN 1 ELSE 0 END) diff_
                          FROM {tb} WITH(NOLOCK) WHERE {a} BETWEEN '{F}' AND '{T}'""")
        r = cur.fetchone()
        p = (r[2]*100.0/r[0]) if r[0] else 0
        print(f'   {nm:34s} 전체 {r[0]:>7,} · 당김없음 {r[1]:>7,} · ★당김됨 {r[2]:>7,} ({p:.1f}%)')
    except Exception as e:
        print(f'   {nm:34s} ERR {str(e)[:90]}')

print('\n■ 웹 당김 보존 위치 nx.plan_line_pull')
try:
    nx.execute("""SELECT COUNT(*) c, COUNT(DISTINCT work_order) wos FROM nx.plan_line_pull WITH(NOLOCK)""")
    r = nx.fetchone(); print(f'   nx.plan_line_pull {r[0]:,}행 · {r[1]:,}제번')
    nx.execute("""SELECT TOP 3 * FROM nx.plan_line_pull WITH(NOLOCK)""")
    print('   컬럼: ' + ', '.join(d[0] for d in nx.description))
except Exception as e:
    print('   ERR', str(e)[:120])
