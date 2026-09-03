# -*- coding: utf-8 -*-
"""★nx 미러가 라이브보다 얼마나 낡았나 — 화면 토글 'nx' 를 레거시로 알고 쓰면 오판한다.
   실측: nx.PR_T_PLAN_PART_COPY 가 라이브보다 -2,448 뒤처짐(420 기준)."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.path.insert(0, r'c:\Users\박근민\Desktop\New_ERP')
import pyodbc, db_client
nx = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
                    f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}').cursor()
F, T = '260902', '260907'

PAIRS = [
    ('PR_T_PLAN_DTL',        'PLAN_YMD',      'PLAN_QTY'),
    ('PR_T_PLAN_ITEM_DTL',   'PLAN_YMD',      'PLAN_QTY'),
    ('SA_T_PLAN_DTL',        'PLAN_YMD',      'PLAN_QTY'),
    ('SA_T_PLAN_ITEM_DTL',   'PLAN_YMD',      'PLAN_QTY'),
    ('PR_T_PLAN_PART_DTL',   'PART_PLAN_YMD', 'PART_PLAN_QTY'),
    ('PR_T_PLAN_PART_COPY',  'PART_PLAN_YMD', 'PART_PLAN_QTY'),
    ('PR_T_PLAN_PART_MAT',   'PART_PLAN_YMD', 'PART_PLAN_QTY'),
    ('PR_T_PLAN_INPUT',      'PLAN_YMD',      'PLAN_QTY'),
]
print('■ nx 미러 vs 라이브 — 계획 테이블 신선도')
print(f'   {"테이블":30s} {"라이브":>12s} {"nx미러":>12s} {"차":>12s}  판정')
for tb, yc, qc in PAIRS:
    try:
        nx.execute(f"""SELECT
            (SELECT SUM(CAST(ISNULL({qc},0) AS float)) FROM PARTNER_ERP.dbo.{tb} WITH(NOLOCK)
              WHERE {yc} BETWEEN '{F}' AND '{T}'),
            (SELECT SUM(CAST(ISNULL({qc},0) AS float)) FROM nx.{tb} WITH(NOLOCK)
              WHERE {yc} BETWEEN '{F}' AND '{T}')""")
        r = nx.fetchone()
        a, b = float(r[0] or 0), float(r[1] or 0)
        m = '✅동일' if abs(a-b) < 0.5 else f'❌{(b-a)/a*100 if a else 0:+.1f}%'
        print(f'   {tb:30s} {a:>12,.0f} {b:>12,.0f} {b-a:>+12,.0f}  {m}')
    except Exception as e:
        print(f'   {tb:30s} ERR {str(e)[:70]}')

print('\n■ 미러 갱신 시각 (INSERT_DATETIME 최댓값)')
for tb in ('PR_T_PLAN_PART_COPY', 'PR_T_PLAN_PART_DTL', 'PR_T_PLAN_ITEM_DTL', 'PR_T_PLAN_DTL'):
    for db in ('PARTNER_ERP.dbo', 'nx'):
        try:
            nx.execute(f"SELECT MAX(INSERT_DATETIME) FROM {db}.{tb} WITH(NOLOCK)")
            print(f'   {db+"."+tb:44s} {nx.fetchone()[0]}')
        except Exception as e:
            print(f'   {db+"."+tb:44s} ERR {str(e)[:60]}')

print('\n■ ★화면 src 토글이 미러를 가리키는 곳 (낡은 값 노출 위험)')
print('   420 gagong_prog420nx  plansrc=nx  → nx.PR_T_PLAN_PART_COPY   ← 실측 -2,448 낡음')
print('   410 plan_part410      src=nx      → ?')
print('   키팅 kitting_grid      src=nx      → ?')
print('   040 sale040_grid      src=nx      → ?')
