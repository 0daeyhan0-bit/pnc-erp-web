# -*- coding: utf-8 -*-
"""세트제외 판별조건 교차검증 — 전 업체의 세트제외 자재를 훑는다.
   가설: 상위도번 part_plan_ymd(proc_seq=1) > 조회기준일  →  자재가 자기행
   미래정밀은 MJU66478801 한 건뿐이라 다른 업체 사례가 필요하다."""
import sys, io, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.path.insert(0, r'c:\Users\박근민\Desktop\New_ERP')
import pyodbc, db_client
nx = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
                    f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}').cursor()
BASE, TO = '260902', '260911'

def q(t, sql, *a):
    print(f'\n-- {t}')
    try:
        nx.execute(sql, *a)
        cols = [d[0] for d in nx.description]; rs = nx.fetchall()
        if not rs: print('   (none)'); return []
        print('   ' + ' | '.join(cols))
        for r in rs[:24]: print('   ' + ' | '.join('' if v is None else str(v) for v in r))
        if len(rs) > 24: print(f'   ... {len(rs)}행')
        return rs
    except Exception as e:
        print('   ERR', str(e)[:220]); return []

print('■ 전 업체 — 세트제외 자재별 소요 현황')
q('세트제외 자재 × 업체 (기간 내)', f"""
    SELECT TOP 20 RTRIM(m.mat_code) mat, RTRIM(ISNULL(m.mat_work_center_code,'')) cust,
           COUNT(DISTINCT m.work_order) wos, SUM(CAST(m.part_plan_qty AS float)) q
      FROM nx.plan_part_mat m WITH(NOLOCK)
     WHERE m.part_plan_ymd BETWEEN '{BASE}' AND '{TO}'
       AND RTRIM(ISNULL(m.mat_work_center_code,''))<>''
       AND EXISTS(SELECT 1 FROM nx.bom_line b WITH(NOLOCK)
                   WHERE RTRIM(b.child_item)=RTRIM(m.mat_code)
                     AND RTRIM(ISNULL(b.set_except,''))='1')
     GROUP BY RTRIM(m.mat_code), RTRIM(ISNULL(m.mat_work_center_code,''))
     ORDER BY 4 DESC""")

print('\n■ ★가설 적용 — 각 세트제외 자재에서 "자기행이 될 제번" 이 몇 건인가')
q('자재×업체별 자기행 후보 수', f"""
    SELECT RTRIM(m.mat_code) mat, RTRIM(ISNULL(m.mat_work_center_code,'')) cust,
           COUNT(*) 전체,
           SUM(CASE WHEN up.ppy > '{BASE}' THEN 1 ELSE 0 END) 자기행후보,
           SUM(CASE WHEN up.ppy > '{BASE}' THEN CAST(m.part_plan_qty AS float) ELSE 0 END) 자기행수량,
           SUM(CASE WHEN up.ppy IS NULL THEN 1 ELSE 0 END) 상위없음
      FROM nx.plan_part_mat m WITH(NOLOCK)
      OUTER APPLY (SELECT MIN(d.part_plan_ymd) ppy FROM nx.plan_part_dtl d WITH(NOLOCK)
                    WHERE d.work_order=m.work_order
                      AND RTRIM(d.item_code)=RTRIM(m.upper_item_code)
                      AND d.proc_seq=1) up
     WHERE m.part_plan_ymd <= '{BASE}'
       AND RTRIM(ISNULL(m.mat_work_center_code,''))<>''
       AND ISNULL(m.bom_level,0)>0
       AND EXISTS(SELECT 1 FROM nx.bom_line b WITH(NOLOCK)
                   WHERE RTRIM(b.child_item)=RTRIM(m.mat_code)
                     AND RTRIM(ISNULL(b.set_except,''))='1')
     GROUP BY RTRIM(m.mat_code), RTRIM(ISNULL(m.mat_work_center_code,''))
     ORDER BY 5 DESC""")

print('\n■ ★가설을 세트제외가 "아닌" 자재에도 적용하면? (오탐 확인)')
q('일반 자재 중 상위 ppy>기준일 인 건수 (많으면 조건이 세트제외 특유가 아님)', f"""
    SELECT COUNT(*) 전체_일반자재행,
           SUM(CASE WHEN up.ppy > '{BASE}' THEN 1 ELSE 0 END) 상위미래,
           COUNT(DISTINCT CASE WHEN up.ppy > '{BASE}' THEN RTRIM(m.mat_code) END) 해당자재수
      FROM nx.plan_part_mat m WITH(NOLOCK)
      OUTER APPLY (SELECT MIN(d.part_plan_ymd) ppy FROM nx.plan_part_dtl d WITH(NOLOCK)
                    WHERE d.work_order=m.work_order
                      AND RTRIM(d.item_code)=RTRIM(m.upper_item_code)
                      AND d.proc_seq=1) up
     WHERE m.part_plan_ymd <= '{BASE}'
       AND RTRIM(ISNULL(m.mat_work_center_code,''))='2096'
       AND ISNULL(m.bom_level,0)>0
       AND NOT EXISTS(SELECT 1 FROM nx.bom_line b WITH(NOLOCK)
                       WHERE RTRIM(b.child_item)=RTRIM(m.mat_code)
                         AND RTRIM(ISNULL(b.set_except,''))='1')""")

print('\n   ※상위미래가 일반자재에도 많다면 → 이 조건만으로는 세트제외를 못 가른다')
print('     (세트제외 플래그 AND 상위미래) 두 조건을 모두 걸어야 한다는 뜻')
