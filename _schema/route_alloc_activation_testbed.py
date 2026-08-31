# -*- coding: utf-8 -*-
"""★R02 활성소스 통일 검증 테스트베드 (2026-08-31).
문제: R02를 조달프로파일에서 택1 활성해도 생산계획 구조에 반영 안 됨.
근본: 구조게이트(_route_setup→plan_route_active)는 sourcing_route.current_flag=1을 읽는데,
      택1 라디오는 route_alloc.is_active만 켠다(current_flag 미변경) → 영영 미반영.
수정: _route_setup·_route_gate_incomplete의 활성소스를 route_alloc.is_active(route_no>1)로 통일
      (soyo.py·planrev.py 양쪽). plan_mat_source(배분축)은 이미 route_alloc.is_active를 봄 → 두 축 단일 스위치.

검증방식: autocommit=False 샌드박스(전부 rollback). 공유 nx.plan_route_active 미접촉 —
      _route_setup의 활성선정 SELECT를 세션 #temp에 복제(NEW/OLD)해 멤버십 비교.
      ★소스-drift 가드: soyo.py·planrev.py 실제 코드에 NEW 조인구문 존재 + OLD current_flag 게이트 부재 확인.
"""
import sys, os, io, datetime
sys.path.insert(0, r'd:/피앤씨인더스트리/100_AI_AGENT/Projects/New_ERP')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import db_client

REPO = r'd:/피앤씨인더스트리/100_AI_AGENT/Projects/_wt_order/PNC_ERP_Web/backend/routers'
GATE5 = """ISNULL(h.approve_flag,0)=1
  AND EXISTS(SELECT 1 FROM nx.route_edges re WHERE re.route_id=h.route_id)
  AND EXISTS(SELECT 1 FROM nx.sourcing_profile p WHERE p.route_id=h.route_id AND ISNULL(p.vendor_code,'')<>'')
  AND EXISTS(SELECT 1 FROM nx.sourcing_profile p WHERE p.route_id=h.route_id AND (p.buy_price IS NOT NULL OR p.sagub_price IS NOT NULL))
  AND EXISTS(SELECT 1 FROM nx.route_proc_gagong rp WHERE rp.route_id=h.route_id)"""
GATE4 = "\n  AND ".join(GATE5.split("\n  AND ")[:4])  # planrev(P4 게이트 없음) 버전

PASS=[]; FAIL=[]
def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — '+extra) if extra else ''}")

# ───────── 0. 소스-drift 가드 (실제 배포코드가 테스트 전제와 일치하는지) ─────────
print("=== 0. 소스-drift 가드 ===")
for fn in ("soyo.py", "planrev.py"):
    src = open(os.path.join(REPO, fn), encoding='utf-8').read()
    has_new = "JOIN nx.route_alloc ra ON ra.route_id=h.route_id AND ISNULL(ra.is_active,0)=1" in src
    # _route_setup 안에서 옛 current_flag 활성게이트가 사라졌는지(plan_route_active 선정부)
    no_old_setup = "WHERE ISNULL(h.current_flag,0)=1 AND ISNULL(h.route_no,1)>1\n          AND " not in src
    check(f"{fn}: NEW route_alloc.is_active 조인 존재", has_new)
    check(f"{fn}: OLD current_flag 활성게이트 제거", no_old_setup)

cn = db_client.get_connection(); cn.autocommit = False; cur = cn.cursor()
def ensure():
    cur.execute("""IF OBJECT_ID('nx.route_proc_gagong') IS NULL CREATE TABLE nx.route_proc_gagong(
        route_id INT, item_code varchar(20), proc_seq tinyint, work_code varchar(10), gagong_proc_code varchar(10),
        s_work_code smallint, mach_code varchar(10), work_qty decimal(18,5), std_size varchar(100), mix_gagong tinyint,
        gagong_proc_flag varchar(1), gagong_proc_seq tinyint, ready_st decimal(18,5), mach_ct decimal(18,5), inwon tinyint,
        human_st decimal(18,5), tot_st decimal(18,5), jp_proc_method varchar(1), lt_hr decimal(18,5), key_id int,
        upd_user varchar(30), upd_at datetime DEFAULT getdate(),
        CONSTRAINT pk_route_proc_gagong PRIMARY KEY(route_id, item_code, proc_seq))""")
    cur.execute("""IF OBJECT_ID('nx.route_edges','U') IS NULL CREATE TABLE nx.route_edges(
        route_id INT NOT NULL, item_code varchar(20) NOT NULL, mat_code varchar(20) NOT NULL,
        use_qty_pr FLOAT NOT NULL DEFAULT 1, CONSTRAINT ix_route_edges UNIQUE(route_id,item_code,mat_code))""")
    cur.execute("""IF OBJECT_ID('nx.route_alloc','U') IS NULL CREATE TABLE nx.route_alloc(
        item_code NVARCHAR(60) NOT NULL, route_id INT NOT NULL, apply_from DATE NULL, apply_to DATE NULL,
        is_active BIT DEFAULT 0, alloc_ratio FLOAT NULL, upd_dt datetime DEFAULT getdate(),
        CONSTRAINT PK_nx_route_alloc PRIMARY KEY(item_code, route_id))""")

def active_set(item, scheme):
    """scheme='new'|'old'|'new4'. plan_route_active 선정 SELECT를 #temp에 복제 → item 포함여부 반환."""
    cur.execute("IF OBJECT_ID('tempdb..#pra') IS NOT NULL DROP TABLE #pra")
    if scheme == 'old':
        sql = """SELECT DISTINCT UPPER(LTRIM(RTRIM(h.item_code))) assy, MIN(h.route_id) rid INTO #pra
            FROM nx.sourcing_route h
            WHERE ISNULL(h.current_flag,0)=1 AND ISNULL(h.route_no,1)>1 AND """ + GATE5 + """
            GROUP BY UPPER(LTRIM(RTRIM(h.item_code)))"""
    else:
        g = GATE4 if scheme == 'new4' else GATE5
        sql = """SELECT DISTINCT UPPER(LTRIM(RTRIM(h.item_code))) assy, MIN(h.route_id) rid INTO #pra
            FROM nx.sourcing_route h
            JOIN nx.route_alloc ra ON ra.route_id=h.route_id AND ISNULL(ra.is_active,0)=1
            WHERE ISNULL(h.route_no,1)>1 AND """ + g + """
            GROUP BY UPPER(LTRIM(RTRIM(h.item_code)))"""
    cur.execute(sql)
    cur.execute("SELECT COUNT(*), MIN(rid) FROM #pra WHERE assy=?", item.upper())
    r = cur.fetchone(); return int(r[0]), (r[1] if r and r[1] is not None else None)

try:
    ensure()
    # 실제 item(FK) + 실제 vendor(FK) 확보
    cur.execute("SELECT TOP 1 LTRIM(RTRIM(item_code)) FROM nx.item WHERE LTRIM(RTRIM(item_code))<>'' ORDER BY item_code")
    ITEM = cur.fetchone()[0].strip()
    cur.execute("SELECT TOP 1 LTRIM(RTRIM(partner_code)) FROM nx.partner WHERE LTRIM(RTRIM(partner_code))<>''")
    VEN = cur.fetchone()[0].strip()
    today = datetime.date.today().isoformat()   # 문자열 바인딩(구형 드라이버 date 파라미터 회피)
    print(f"\n테스트 대상 item={ITEM} vendor={VEN}")

    # ───────── 1. diff0 안전(활성 없음): NEW==OLD(둘 다 미포함) ─────────
    print("\n=== 1. diff0 안전 — 활성 R02 없음 ===")
    n0,_ = active_set(ITEM, 'new'); o0,_ = active_set(ITEM, 'old')
    check("활성 없을 때 NEW 미포함", n0 == 0)
    check("활성 없을 때 OLD 미포함", o0 == 0)
    check("활성 없을 때 NEW==OLD(현행 diff0)", n0 == o0)

    # ───────── 완전 세팅된 R02 시드(current_flag=0, route_alloc.is_active=1) ─────────
    cur.execute("""INSERT INTO nx.sourcing_route(item_code,route_no,route_name,gubun,current_flag,approve_flag,apply_from,ins_user)
        OUTPUT INSERTED.route_id VALUES(?,?,?,?,0,1,?,?)""", ITEM, 2, '테스트 R02', '매입', today, 'testbed')
    RID = int(cur.fetchone()[0])
    cur.execute("INSERT INTO nx.route_edges(route_id,item_code,mat_code,use_qty_pr) VALUES(?,?,?,1)", RID, ITEM, ITEM)
    cur.execute("""INSERT INTO nx.sourcing_profile(item_code,profile_name,supply_gubun,vendor_code,lme_flag,apply_from,is_active,is_internal,route_id,buy_price)
        VALUES(?,?,?,?,0,?,1,0,?,100)""", ITEM, 'tb', '매입', VEN, today, RID)
    cur.execute("INSERT INTO nx.route_proc_gagong(route_id,item_code,proc_seq) VALUES(?,?,1)", RID, ITEM)
    cur.execute("INSERT INTO nx.route_alloc(item_code,route_id,is_active,alloc_ratio) VALUES(?,?,1,100)", ITEM, RID)

    # ───────── 2. 완전세팅 R02 활성 → NEW 반영 / OLD 미반영(버그) ─────────
    print("\n=== 2. 완전 세팅 R02 활성(current_flag=0·route_alloc.is_active=1) ===")
    nc, nrid = active_set(ITEM, 'new'); oc,_ = active_set(ITEM, 'old')
    check("NEW: plan_route_active 진입(수정 후 반영됨)", nc == 1 and nrid == RID, f"cnt={nc} rid={nrid}")
    check("OLD: 미진입(current_flag=0이라 구식은 미반영=버그 재현)", oc == 0)

    # ───────── 3. 게이트 차단(NEW) — 조건 하나씩 제거 ─────────
    print("\n=== 3. 게이트 차단(NEW) ===")
    cur.execute("DELETE FROM nx.route_proc_gagong WHERE route_id=?", RID)
    check("생산정보(route_proc) 제거 → 미진입", active_set(ITEM,'new')[0] == 0)
    check("  (참고)planrev 4게이트는 생산정보 무관 → 진입 유지", active_set(ITEM,'new4')[0] == 1)
    cur.execute("INSERT INTO nx.route_proc_gagong(route_id,item_code,proc_seq) VALUES(?,?,1)", RID, ITEM)

    cur.execute("UPDATE nx.sourcing_profile SET vendor_code=NULL WHERE route_id=?", RID)  # NULL=FK안전·게이트차단
    check("업체 제거 → 미진입", active_set(ITEM,'new')[0] == 0)
    cur.execute("UPDATE nx.sourcing_profile SET vendor_code=? WHERE route_id=?", VEN, RID)

    cur.execute("UPDATE nx.sourcing_profile SET buy_price=NULL, sagub_price=NULL WHERE route_id=?", RID)
    check("단가 제거 → 미진입", active_set(ITEM,'new')[0] == 0)
    cur.execute("UPDATE nx.sourcing_profile SET buy_price=100 WHERE route_id=?", RID)

    cur.execute("DELETE FROM nx.route_edges WHERE route_id=?", RID)
    check("route_edges 제거 → 미진입", active_set(ITEM,'new')[0] == 0)
    cur.execute("INSERT INTO nx.route_edges(route_id,item_code,mat_code,use_qty_pr) VALUES(?,?,?,1)", RID, ITEM, ITEM)

    cur.execute("UPDATE nx.sourcing_route SET approve_flag=0 WHERE route_id=?", RID)
    check("미승인 → 미진입", active_set(ITEM,'new')[0] == 0)
    cur.execute("UPDATE nx.sourcing_route SET approve_flag=1 WHERE route_id=?", RID)

    # 복구 후 다시 진입 확인
    check("전 조건 복구 → 재진입", active_set(ITEM,'new')[0] == 1)

    # ───────── 4. 비활성(택1 해제) → 미진입 ─────────
    print("\n=== 4. 활성 해제(route_alloc.is_active=0) ===")
    cur.execute("UPDATE nx.route_alloc SET is_active=0 WHERE route_id=?", RID)
    check("is_active=0 → 미진입(비활성)", active_set(ITEM,'new')[0] == 0)
    cur.execute("UPDATE nx.route_alloc SET is_active=1 WHERE route_id=?", RID)

    # ───────── 5. 택1 배타성(같은 item 2 활성 → 1행·MIN) ─────────
    print("\n=== 5. 택1 배타성(방어) ===")
    cur.execute("""INSERT INTO nx.sourcing_route(item_code,route_no,route_name,gubun,current_flag,approve_flag,apply_from,ins_user)
        OUTPUT INSERTED.route_id VALUES(?,?,?,?,0,1,?,?)""", ITEM, 3, '테스트 R03', '매입', today, 'testbed')
    RID2 = int(cur.fetchone()[0])
    cur.execute("INSERT INTO nx.route_edges(route_id,item_code,mat_code,use_qty_pr) VALUES(?,?,?,1)", RID2, ITEM, ITEM)
    cur.execute("""INSERT INTO nx.sourcing_profile(item_code,profile_name,supply_gubun,vendor_code,lme_flag,apply_from,is_active,is_internal,route_id,buy_price)
        VALUES(?,?,?,?,0,?,1,0,?,100)""", ITEM, 'tb', '매입', VEN, today, RID2)
    cur.execute("INSERT INTO nx.route_proc_gagong(route_id,item_code,proc_seq) VALUES(?,?,1)", RID2, ITEM)
    cur.execute("INSERT INTO nx.route_alloc(item_code,route_id,is_active,alloc_ratio) VALUES(?,?,1,100)", ITEM, RID2)
    c2, rid2 = active_set(ITEM, 'new')
    check("2개 활성 → plan_route_active 정확히 1행(item당 유일)", c2 == 1, f"cnt={c2}")
    check("  선정=MIN(route_id)", rid2 == min(RID, RID2))

finally:
    cn.rollback(); cn.close()

print(f"\n{'='*48}\n결과: PASS {len(PASS)} / FAIL {len(FAIL)}")
if FAIL:
    print("실패:", FAIL); sys.exit(1)
print("전부 통과 (샌드박스 rollback·라이브 무접촉).")
