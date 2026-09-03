# -*- coding: utf-8 -*-
"""plan_ymd=260904 만 자기행 — 왜인가?
   가설A: 상위도번(AJR77224xxx)의 파트별계획이 조회기간(0902~0911) 안에 없다
          → 상위 행이 화면에 못 서니 자재가 자기 이름으로 선다
   가설B: 상위도번의 part_plan_ymd 가 기간 밖
   가설C: plan_ymd 자체가 조건"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.path.insert(0, r'c:\Users\박근민\Desktop\New_ERP')
import pyodbc, db_client
nx = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
                    f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}').cursor()
LEG13 = ['6J0M01AP','6J0M01B4','6J1M07MS','6J1M096V','6J1M09BM','6J1M09EA','6J1M09GT',
         '6J1M0A70','6J1M0A71','6J1M0A73','6JMGM00A','6JMGM00E','6JMGM01D']
LEGSET = "'" + "','".join(LEG13) + "'"

def q(t, sql):
    print(f'\n-- {t}')
    try:
        nx.execute(sql)
        cols = [d[0] for d in nx.description]; rs = nx.fetchall()
        if not rs: print('   (none)'); return
        print('   ' + ' | '.join(cols))
        for r in rs[:26]: print('   ' + ' | '.join('' if v is None else str(v) for v in r))
        if len(rs) > 26: print(f'   ... {len(rs)}행')
    except Exception as e: print('   ERR', str(e)[:200])

q('★상위도번의 파트별계획 part_plan_ymd (기간 0902~0911 안에 있나)', f"""
    SELECT m.work_order,
           CASE WHEN m.work_order IN ({LEGSET}) THEN '★자기행' ELSE '미표시' END leg,
           RTRIM(m.upper_item_code) up, m.plan_ymd mat_planymd,
           (SELECT MIN(d.part_plan_ymd) FROM nx.plan_part_dtl d WITH(NOLOCK)
             WHERE d.work_order=m.work_order AND RTRIM(d.item_code)=RTRIM(m.upper_item_code)) up_ppy_min,
           (SELECT MAX(d.part_plan_ymd) FROM nx.plan_part_dtl d WITH(NOLOCK)
             WHERE d.work_order=m.work_order AND RTRIM(d.item_code)=RTRIM(m.upper_item_code)) up_ppy_max,
           (SELECT MIN(d.plan_ymd) FROM nx.plan_part_dtl d WITH(NOLOCK)
             WHERE d.work_order=m.work_order AND RTRIM(d.item_code)=RTRIM(m.upper_item_code)) up_py,
           (SELECT MIN(d.proc_seq) FROM nx.plan_part_dtl d WITH(NOLOCK)
             WHERE d.work_order=m.work_order AND RTRIM(d.item_code)=RTRIM(m.upper_item_code)) up_seq
      FROM nx.plan_part_mat m WITH(NOLOCK)
     WHERE RTRIM(m.mat_code)='MJU66478801'
       AND RTRIM(ISNULL(m.mat_work_center_code,''))='2096'
       AND m.part_plan_ymd<='260902' AND ISNULL(m.bom_level,0)>0
     ORDER BY 2,1""")

q('★그 (제번,상위) 조합이 130 ①갈래(proc_seq=1 + 기간)에 잡히나', f"""
    SELECT m.work_order,
           CASE WHEN m.work_order IN ({LEGSET}) THEN '★자기행' ELSE '미표시' END leg,
           RTRIM(m.upper_item_code) up,
           (SELECT COUNT(*) FROM nx.plan_part_dtl d WITH(NOLOCK)
             WHERE d.work_order=m.work_order AND RTRIM(d.item_code)=RTRIM(m.upper_item_code)
               AND d.proc_seq=1 AND d.part_plan_ymd<='260911') 갈래1_잡힘,
           (SELECT COUNT(*) FROM nx.plan_part_dtl d WITH(NOLOCK)
             WHERE d.work_order=m.work_order AND RTRIM(d.item_code)=RTRIM(m.upper_item_code)
               AND d.proc_seq=1) 갈래1_기간무관
      FROM nx.plan_part_mat m WITH(NOLOCK)
     WHERE RTRIM(m.mat_code)='MJU66478801'
       AND RTRIM(ISNULL(m.mat_work_center_code,''))='2096'
       AND m.part_plan_ymd<='260902' AND ISNULL(m.bom_level,0)>0
     ORDER BY 2,1""")

q('★상위도번이 그 제번에서 2096 소요를 갖나 (=협력사 행으로 설 자격)', f"""
    SELECT m.work_order,
           CASE WHEN m.work_order IN ({LEGSET}) THEN '★자기행' ELSE '미표시' END leg,
           RTRIM(m.upper_item_code) up,
           (SELECT COUNT(*) FROM nx.plan_part_mat z WITH(NOLOCK)
             WHERE z.work_order=m.work_order
               AND ISNULL(NULLIF(z.assy_item_code,''),z.item_code)=RTRIM(m.upper_item_code)
               AND RTRIM(ISNULL(z.mat_work_center_code,''))='2096') 상위_2096소요,
           (SELECT COUNT(*) FROM nx.plan_part_mat z WITH(NOLOCK)
             WHERE z.work_order=m.work_order
               AND RTRIM(z.item_code)=RTRIM(m.upper_item_code)) 상위_item소요
      FROM nx.plan_part_mat m WITH(NOLOCK)
     WHERE RTRIM(m.mat_code)='MJU66478801'
       AND RTRIM(ISNULL(m.mat_work_center_code,''))='2096'
       AND m.part_plan_ymd<='260902' AND ISNULL(m.bom_level,0)>0
     ORDER BY 2,1""")
