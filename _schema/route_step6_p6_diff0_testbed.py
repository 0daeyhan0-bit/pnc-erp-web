# -*- coding: utf-8 -*-
"""P6 diff0 게이트(protect-plan 최고위험): STEP6 공정 route-aware 오버레이가
활성 route 없을 때 현행과 완전 동일(identity)함을 증명 + 합성 route 오버라이드 동작 확인.
입력=현재 nx.plan_part_temp(무변경). OLD/NEW plan_part_gagong를 #temp로 빌드·EXCEPT 비교. T2만 롤백tx."""
import sys, os, io
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'New_ERP'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import db_client

PASS = []; FAIL = []
def chk(n, c, d=""):
    (PASS if c else FAIL).append(n); print(("  [OK] " if c else "  [FAIL] ") + n + ("" if c else " :: " + d))

# 공정 SELECT 리스트(OLD/NEW 공통) — plan_part_gagong 컬럼
SEL = """a.assy_item_code,a.level_no,a.item_code,a.mat_code,a.p_item_code,a.vir_item_flag,b.proc_seq,g.gc_gubun,a.cum_use_qty,s.gagong_proc_code,b.gagong_proc_seq,b.s_work_code,ISNULL(b.lt_hr,0) lt_hr"""
WH = "WHERE a.vir_item_flag='0' AND ISNULL(a.in_cust_code,'') IN ('','2228')"
JOIN_SG = "JOIN nx.PR_M_WORK_SINGLE s ON b.s_work_code=s.s_work_code JOIN nx.PR_M_PROC_GAGONG g ON s.gagong_proc_code=g.gagong_proc_code"

OLD = f"""SELECT {SEL} INTO #old_g FROM nx.plan_part_temp a
    JOIN nx.PR_M_ITEM_PROC_GAGONG b ON a.mat_code=b.item_code {JOIN_SG} {WH}"""

def NEW(tgt):
    return f"""SELECT {SEL} INTO {tgt} FROM nx.plan_part_temp a
    LEFT JOIN nx.plan_route_active pra ON pra.assy_item_code=a.assy_item_code
    JOIN (
        SELECT item_code, CAST(0 AS INT) route_id, proc_seq, s_work_code, gagong_proc_seq, lt_hr FROM nx.PR_M_ITEM_PROC_GAGONG
        UNION ALL
        SELECT item_code, route_id, proc_seq, s_work_code, gagong_proc_seq, lt_hr FROM nx.route_proc_gagong
    ) b ON a.mat_code=b.item_code
       AND b.route_id = CASE WHEN pra.route_id IS NOT NULL
             AND EXISTS(SELECT 1 FROM nx.route_proc_gagong x WHERE x.route_id=pra.route_id AND x.item_code=a.mat_code)
           THEN pra.route_id ELSE 0 END
    {JOIN_SG} {WH}"""

cn = db_client.get_connection(); cn.autocommit = False; cur = cn.cursor()
try:
    # route_proc_gagong 없으면 생성(멱등)
    cur.execute("""IF OBJECT_ID('nx.route_proc_gagong') IS NULL CREATE TABLE nx.route_proc_gagong(
        route_id INT, item_code varchar(20), proc_seq tinyint, work_code varchar(10), gagong_proc_code varchar(10),
        s_work_code smallint, mach_code varchar(10), work_qty decimal(18,5), std_size varchar(100), mix_gagong tinyint,
        gagong_proc_flag varchar(1), gagong_proc_seq tinyint, ready_st decimal(18,5), mach_ct decimal(18,5), inwon tinyint,
        human_st decimal(18,5), tot_st decimal(18,5), jp_proc_method varchar(1), lt_hr decimal(18,5), key_id int,
        upd_user varchar(30), upd_at datetime DEFAULT getdate(),
        CONSTRAINT pk_route_proc_gagong PRIMARY KEY(route_id, item_code, proc_seq))""")

    # ═══ T1: identity (plan_route_active 비어있음 = 활성 R02 없음) ═══
    cur.execute("SELECT COUNT(*) FROM nx.plan_route_active"); pra_n = cur.fetchone()[0]
    print(f"plan_route_active {pra_n}행 (0=활성R02없음)")
    cur.execute("IF OBJECT_ID('tempdb..#old_g') IS NOT NULL DROP TABLE #old_g")
    cur.execute(OLD)
    cur.execute("IF OBJECT_ID('tempdb..#new_g') IS NOT NULL DROP TABLE #new_g")
    cur.execute(NEW("#new_g"))
    cur.execute("SELECT (SELECT COUNT(*) FROM #old_g),(SELECT COUNT(*) FROM #new_g)")
    on, nn = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM (SELECT * FROM #old_g EXCEPT SELECT * FROM #new_g) x"); only_old = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM (SELECT * FROM #new_g EXCEPT SELECT * FROM #old_g) x"); only_new = cur.fetchone()[0]
    print(f"OLD {on}행 · NEW {nn}행 · OLD만 {only_old} · NEW만 {only_new}")
    chk("T1 identity: 행수 동일", on == nn, f"{on} vs {nn}")
    chk("T1b identity: OLD⊖NEW=0 (완전동일)", only_old == 0 and only_new == 0, f"old만{only_old}·new만{only_new}")

    # ═══ T2: 합성 route 오버라이드 동작 (롤백tx) ═══
    # plan_part_temp에서 부품(mat_code)이 PR_M_ITEM_PROC_GAGONG에 있고 해당 assy 하나 선택
    cur.execute("""SELECT TOP 1 a.assy_item_code, a.mat_code
        FROM nx.plan_part_temp a
        WHERE a.vir_item_flag='0' AND ISNULL(a.in_cust_code,'') IN ('','2228')
          AND EXISTS(SELECT 1 FROM nx.PR_M_ITEM_PROC_GAGONG b WHERE b.item_code=a.mat_code)
        ORDER BY a.assy_item_code, a.mat_code""")
    ASSY, PART = [str(x).strip() for x in cur.fetchone()]
    print(f"T2 대상 ASSY={ASSY} PART={PART}")
    # 그 부품의 현행 공정(OLD)
    cur.execute("SELECT proc_seq,s_work_code FROM nx.PR_M_ITEM_PROC_GAGONG WHERE item_code=? ORDER BY proc_seq", PART)
    base_proc = cur.fetchall()
    RID = 990088
    # 합성 활성 route + 그 부품 route 생산정보(현행과 다른 s_work_code로 구분)
    # s_work_code는 PR_M_WORK_SINGLE에 존재해야 JOIN 성립 → 현행과 다른 유효 s_work 하나 선택
    # ★유효 s_work = PR_M_WORK_SINGLE→PR_M_PROC_GAGONG 조인 성립(공정 JOIN 체인 통과)해야 gagong 행 생존
    cur.execute("""SELECT TOP 1 s.s_work_code FROM nx.PR_M_WORK_SINGLE s
        JOIN nx.PR_M_PROC_GAGONG g ON s.gagong_proc_code=g.gagong_proc_code
        WHERE s.s_work_code NOT IN (SELECT ISNULL(s_work_code,0) FROM nx.PR_M_ITEM_PROC_GAGONG WHERE item_code=?)
        ORDER BY s.s_work_code""", PART)
    alt_sw = int(cur.fetchone()[0])
    cur.execute("DELETE FROM nx.route_proc_gagong WHERE route_id=?", RID)
    cur.execute("INSERT INTO nx.route_proc_gagong(route_id,item_code,proc_seq,s_work_code,gagong_proc_seq,lt_hr) VALUES(?,?,1,?,1,9)", RID, PART, alt_sw)
    cur.execute("INSERT INTO nx.plan_route_active(assy_item_code,route_id) VALUES(?,?)", ASSY, RID)

    cur.execute("IF OBJECT_ID('tempdb..#new_g2') IS NOT NULL DROP TABLE #new_g2")
    cur.execute(NEW("#new_g2"))
    # 그 (ASSY,PART)의 NEW 공정 = route 버전(s_work=alt_sw·1행)이어야
    cur.execute("SELECT s_work_code, proc_seq FROM #new_g2 WHERE assy_item_code=? AND mat_code=? ORDER BY proc_seq", ASSY, PART)
    ov = cur.fetchall()
    chk("T2 오버라이드: 대상 부품 공정=route버전(alt s_work·1행)",
        len(ov) == 1 and int(ov[0][0]) == alt_sw, f"got={[(int(x[0]),int(x[1])) for x in ov]} expect s_work={alt_sw}")
    # 다른 ASSY(같은 부품이라도 활성route 없는)나 다른 부품은 현행 유지 = 오버라이드 국소성
    cur.execute("""SELECT COUNT(*) FROM (
        SELECT * FROM #new_g2 WHERE NOT(assy_item_code=? AND mat_code=?)
        EXCEPT SELECT * FROM #old_g WHERE NOT(assy_item_code=? AND mat_code=?)) x""", ASSY, PART, ASSY, PART)
    leak = cur.fetchone()[0]
    chk("T2b 국소성: 대상 외 전부 현행과 동일(누수0)", leak == 0, f"누수 {leak}행")

finally:
    cn.rollback(); cn.close()   # ★T2 합성 route·오버라이드 전부 롤백(오염0)

print(f"\n=== 결과 === PASS {len(PASS)} · FAIL {len(FAIL)}")
if FAIL: print("실패:", FAIL)
print("✓입력 nx.plan_part_temp 무변경·#temp 비교·T2 롤백(오염0)")
