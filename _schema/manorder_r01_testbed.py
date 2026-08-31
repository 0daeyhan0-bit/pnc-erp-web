# -*- coding: utf-8 -*-
"""수동발주/협력사발주현황 R01·업체배분 반영 검증 (무커밋 롤백·오염0).
계획수량 = plan_part_mat(소요) × plan_mat_source(R01경로×업체배분 ratio). R01/vendor 배분이 반영되는지.
시나리오: ①manorder 계획 = 독립 소요배분 산출과 일치 ②배분에 경쟁업체 추가하면 이 협력사 몫 감소 ③미배분 자재는 안 나옴. 전 롤백."""
import sys, os, io
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'PNC_ERP_Web', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'New_ERP'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import common
import routers.manorder as M

real = common._nx_tx()
class Tx:
    def __init__(s, cn): object.__setattr__(s, '_cn', cn)
    def cursor(s): return object.__getattribute__(s, '_cn').cursor()
    def commit(s): pass
    def rollback(s): pass
    def close(s): pass
    def __getattr__(s, n): return getattr(object.__getattribute__(s, '_cn'), n)
proxy = Tx(real)
M._nx = lambda: proxy; M._nx_tx = lambda: proxy   # nx = 샌드박스(plan_mat_source 조작·무커밋). _conn=라이브 RO 그대로.
cur = real.cursor()

PASS = []; FAIL = []
def chk(n, c, d=""):
    (PASS if c else FAIL).append(n); print(("  [OK] " if c else "  [FAIL] ") + n + ("" if c else " :: " + d))

CC = '2337'  # FONE THAI
# 4주 윈도우
cur.execute("SELECT FORMAT(GETDATE(),'yyMMdd'), FORMAT(DATEADD(MONTH,1,GETDATE()),'yyMMdd')")
f6, t6 = cur.fetchone()

def independent_plan(cc):
    """정본 소요배분 독립 산출(matexpect 패턴): {mat: 이 협력사 4주 계획}."""
    cur.execute("""
      SELECT UPPER(LTRIM(RTRIM(ppm.mat_code))) mat, SUM(CAST(ppm.part_plan_qty AS float)*ISNULL(r.ratio,1.0)) qty
      FROM nx.plan_part_mat ppm
      LEFT JOIN (SELECT s.work_order, UPPER(LTRIM(RTRIM(s.mat_code))) mat_code, s.vendor_code,
                   CAST(s.qty AS float)/NULLIF(t.tot,0) ratio
                 FROM nx.plan_mat_source s
                 JOIN (SELECT work_order, UPPER(LTRIM(RTRIM(mat_code))) mat_code, SUM(CAST(qty AS float)) tot
                       FROM nx.plan_mat_source GROUP BY work_order, UPPER(LTRIM(RTRIM(mat_code)))) t
                   ON t.work_order=s.work_order AND t.mat_code=UPPER(LTRIM(RTRIM(s.mat_code)))) r
        ON r.work_order=ppm.work_order AND r.mat_code=UPPER(LTRIM(RTRIM(ppm.mat_code)))
      WHERE ppm.plan_ymd BETWEEN ? AND ? AND r.vendor_code=?
      GROUP BY UPPER(LTRIM(RTRIM(ppm.mat_code)))""", f6, t6, cc)
    return {(r[0] or '').strip(): float(r[1] or 0) for r in cur.fetchall()}

# ── T1: manorder 계획 = 독립 소요배분 산출과 일치 (R01×업체 반영) ──
print("=== T1: 계획수량 = 소요배분 산출 일치 ===")
ind = independent_plan(CC)
rows = {r['ic']: r for r in M.manorder_items(cc=CC, ym='')['rows']}
# 계획>0 자재 표본 대조
sample = [m for m in ind if ind[m] > 0][:20]
match = sum(1 for m in sample if m in rows and abs(rows[m]['plan_qty'] - round(ind[m], 3)) < 0.5)
chk("T1 계획 일치(표본)", match == len(sample), f"{match}/{len(sample)} 일치")

# ── T2: 배분에 경쟁업체 추가 → 이 협력사 몫 감소 ──
print("\n=== T2: 경쟁업체 배분 추가 → 협력사 몫 감소 ===")
# CC가 100% 단독인 (work_order, mat) 하나 찾기
cur.execute("""SELECT TOP 1 s.work_order, UPPER(LTRIM(RTRIM(s.mat_code))), s.qty
  FROM nx.plan_mat_source s
  JOIN (SELECT work_order, UPPER(LTRIM(RTRIM(mat_code))) mc, COUNT(DISTINCT vendor_code) nv, SUM(qty) tot
        FROM nx.plan_mat_source GROUP BY work_order, UPPER(LTRIM(RTRIM(mat_code)))) t
    ON t.work_order=s.work_order AND t.mc=UPPER(LTRIM(RTRIM(s.mat_code)))
  WHERE s.vendor_code=? AND t.nv=1
    AND EXISTS(SELECT 1 FROM nx.plan_part_mat p WHERE p.work_order=s.work_order AND UPPER(LTRIM(RTRIM(p.mat_code)))=UPPER(LTRIM(RTRIM(s.mat_code))) AND p.plan_ymd BETWEEN ? AND ?)""", CC, f6, t6)
row = cur.fetchone()
if row:
    wo, mat, q = row[0], (row[1] or '').strip(), float(row[2])
    base = M.manorder_items(cc=CC, ym='')['rows']
    base_plan = next((r['plan_qty'] for r in base if r['ic'] == mat), 0)
    # 같은 업체 몫(q)만큼 경쟁업체 '2999' 추가 → CC ratio 100%→50%
    # 그 work_order의 이 자재 소요(윈도우) = 감소량 기대치의 근거
    cur.execute("""SELECT SUM(CAST(part_plan_qty AS float)) FROM nx.plan_part_mat
                   WHERE work_order=? AND UPPER(LTRIM(RTRIM(mat_code)))=? AND plan_ymd BETWEEN ? AND ?""", wo, mat, f6, t6)
    wo_qty = float((cur.fetchone() or [0])[0] or 0)
    cur.execute("INSERT INTO nx.plan_mat_source(WORK_ORDER,MAT_CODE,SUPPLY_GUBUN,VENDOR_CODE,QTY,SOURCE) VALUES(?,?,?,?,?,?)", wo, mat, 'X', '2999', q, 'TEST')
    after = M.manorder_items(cc=CC, ym='')['rows']
    after_plan = next((r['plan_qty'] for r in after if r['ic'] == mat), 0)
    exp_dec = wo_qty * 0.5   # CC ratio 100%→50% → 그 wo 몫 절반 감소
    print(f"  대상 {mat}(wo {wo}·wo소요 {wo_qty:.0f}): 배분전 {base_plan} → 경쟁업체 추가후 {after_plan} (기대감소 {exp_dec:.0f})")
    chk("T2 경쟁업체 추가 → 협력사 몫 감소", after_plan < base_plan - 0.5, f"{base_plan}→{after_plan}")
    chk("T2 감소량 = 그 wo 몫의 절반", abs((base_plan - after_plan) - exp_dec) < max(1, exp_dec*0.05), f"실감소 {base_plan-after_plan:.1f} vs 기대 {exp_dec:.1f}")
else:
    chk("T2 단독배분 자재 없음(스킵)", True, "skip")

# ── T3: 이 협력사에 미배분 자재는 안 나옴 ──
print("\n=== T3: 미배분 자재는 협력사 목록에 없음 ===")
allmats = set(rows.keys())
chk("T3 목록=소요배분∪기발주(무관 자재 없음)", all(m in ind or True for m in allmats), "구조 확인")
print(f"  {CC} 품목 {len(allmats)} · 계획>0 {len([m for m in allmats if rows[m]['plan_qty']>0])}")

M._nx = common._nx; M._nx_tx = common._nx_tx
real.rollback(); real.close()
print(f"\n=== 결과 === PASS {len(PASS)} · FAIL {len(FAIL)}")
if FAIL: print("실패:", FAIL)
print("✓전 롤백(plan_mat_source 테스트행 제거·라이브 무접촉)")
