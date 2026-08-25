# -*- coding: utf-8 -*-
"""SUB 편집 워크플로우 시나리오 검증 하네스 (S1·S2·S4·S5·S6·S7·S10).
실제 엔드포인트 핸들러를 커밋/롤백/close 무력화 프록시로 호출 → 불변식 assert → 전 롤백(라이브 무접촉)."""
import sys, io
sys.path.insert(0, r"d:/피앤씨인더스트리/100_AI_AGENT/Projects/NEW_ERP_1/PNC_ERP_Web/backend")
sys.path.insert(0, r"d:/피앤씨인더스트리/100_AI_AGENT/Projects/New_ERP")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import importlib
import common
import routers.sourcing as S
importlib.reload(S)

IT = 'AJR30087002'; YMD = '260630'
real_cn = common._nx_tx()

class Tx:
    def __init__(self, cn): object.__setattr__(self, '_cn', cn)
    def cursor(self): return object.__getattribute__(self, '_cn').cursor()
    def commit(self): pass
    def rollback(self): pass
    def close(self): pass
    def __getattr__(self, n): return getattr(object.__getattribute__(self, '_cn'), n)

proxy = Tx(real_cn)
S._nx_tx = lambda: proxy
S._nx = lambda: proxy
cur = real_cn.cursor()
S._ensure_route_tbl(cur)

PASS = []; FAIL = []
def chk(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  [OK] " if cond else "  [FAIL] ") + name + ("" if cond else " :: " + detail))

def parts_of(rid):
    cur.execute("SELECT line_id,UPPER(LTRIM(RTRIM(ISNULL(child_item,'')))),node_kind,parent_line,ISNULL(staged,0) FROM nx.sourcing_route_line WHERE route_id=?", rid)
    return cur.fetchall()
def partset(rid):
    return set(r[1] for r in parts_of(rid) if r[2] != 'SUB' and r[1] and not r[1].startswith('RAC'))
def base_set():
    return set(str(l['child_item']).strip().upper() for l in S._base_flat_lines(IT, YMD) if not str(l['child_item']).strip().upper().startswith('RAC'))
def finalize_flags(rid):
    r = S.sourcing_route_finalize({"route_id": rid, "item_code": IT, "ymd": YMD, "commit": 0})
    return r

BASE = base_set()
print("BASE 부품수 =", len(BASE))

# ── 테스트 route 생성 + 현행복사 seed (S1) ──
cur.execute("SELECT ISNULL(MAX(route_no),1)+11 FROM nx.sourcing_route WHERE item_code=?", IT); rno = int(cur.fetchone()[0])
cur.execute("INSERT INTO nx.sourcing_route(item_code,route_no,route_name,current_flag,approve_flag,ins_user) OUTPUT INSERTED.route_id VALUES(?,?,'하네스',0,0,'검증')", IT, rno)
RID = int(cur.fetchone()[0])
nseed = S._insert_current_tree(cur, RID, IT, YMD)
# ASSY 조립공정 프리시드 (복사 핸들러와 동일 — 공수합 BASE 위해 필요)
node_asm = S._panel_node_asm(IT, YMD)
for _node, _procs in (node_asm or {}).items():
    for pc_code, wq in (_procs or {}).items():
        if wq and float(wq) != 0:
            cur.execute("""INSERT INTO nx.sourcing_route_proc(route_id,node_item,proc_code,work_qty,prod_uph,calc_gubun)
                VALUES(?,?,?,?,0,'')""", RID, str(_node).strip()[:60], str(pc_code).strip()[:10], float(wq))

print("\n=== S1: 현행복사 seed = BASE ===")
ps = partset(RID)
chk("S1 부품수=BASE", ps == BASE, f"route{len(ps)} vs base{len(BASE)} diff={sorted(ps ^ BASE)[:5]}")
f = finalize_flags(RID)
chk("S1 finalize part_ok", f.get("part_ok"), str(f.get("missing")) + "/" + str(f.get("extra")))
chk("S1 finalize gongsu_ok", f.get("gongsu_ok"), f"cand {f.get('cand_gongsu')} vs base {f.get('base_gongsu')}")
chk("S1 finalize staged_ok", f.get("staged_ok"), str(f.get("staged")))

print("\n=== S2: SUB 묶기 (부품 3개 → 새 SUB) ===")
flat = [r for r in parts_of(RID) if r[2] != 'SUB' and r[3] is None and not r[1].startswith('RAC')]
pick = [r[0] for r in flat[:3]]
r2 = S.sourcing_sub_create({"route_id": RID, "line_ids": pick})
subs = [r for r in parts_of(RID) if r[2] == 'SUB']
chk("S2 SUB 생성됨", len(subs) >= 1, f"subs={len(subs)}")
sub_lid = subs[0][0]
moved = [r for r in parts_of(RID) if r[0] in pick]
chk("S2 선택부품 parent_line=SUB", all(r[3] == sub_lid for r in moved), str([(r[0], r[3]) for r in moved]))
chk("S2 선택부품 staged=0", all(r[4] == 0 for r in moved), str([(r[0], r[4]) for r in moved]))
chk("S2 부품수 불변=BASE", partset(RID) == BASE, f"diff={sorted(partset(RID) ^ BASE)[:5]}")
f = finalize_flags(RID)
chk("S2 공수합 보존", f.get("gongsu_ok"), f"{f.get('cand_gongsu')} vs {f.get('base_gongsu')}")

print("\n=== S4: SUB간/평면 이동 (부품 1개 → ASSY 평면) ===")
mv = pick[0]
S.sourcing_part_assign({"route_id": RID, "line_ids": [mv], "sub_line": 0})
row = [r for r in parts_of(RID) if r[0] == mv][0]
chk("S4 parent_line=NULL(평면)", row[3] is None, f"parent={row[3]}")
chk("S4 부품수 불변=BASE", partset(RID) == BASE)
chk("S4 공수합 보존", finalize_flags(RID).get("gongsu_ok"))

print("\n=== S5: SUB 해체 ===")
S.sourcing_sub_dissolve({"route_id": RID, "sub_line": sub_lid})
subs2 = [r for r in parts_of(RID) if r[2] == 'SUB' and r[0] == sub_lid]
chk("S5 SUB행 삭제", len(subs2) == 0)
returned = [r for r in parts_of(RID) if r[0] in pick]
chk("S5 하위부품 평면복귀(parent=NULL)", all(r[3] is None for r in returned), str([(r[0], r[3]) for r in returned]))
chk("S5 부품수 불변=BASE", partset(RID) == BASE)
chk("S5 공수합 보존", finalize_flags(RID).get("gongsu_ok"))

print("\n=== S6: 보관함(staged) → finalize 차단 → 재배치 ===")
p6 = pick[0]
S.sourcing_part_assign({"route_id": RID, "line_ids": [p6], "to_pool": 1})
row6 = [r for r in parts_of(RID) if r[0] == p6][0]
chk("S6 staged=1(보관)", row6[4] == 1, f"staged={row6[4]}")
f6 = finalize_flags(RID)
chk("S6 finalize staged_ok=False(차단)", not f6.get("staged_ok"), str(f6.get("staged")))
S.sourcing_part_assign({"route_id": RID, "line_ids": [p6], "sub_line": 0})
row6b = [r for r in parts_of(RID) if r[0] == p6][0]
chk("S6 재배치 staged=0", row6b[4] == 0)
chk("S6 재배치후 staged_ok=True", finalize_flags(RID).get("staged_ok"))

print("\n=== S7: 저장 게이트(무편집상태 통과) ===")
f7 = finalize_flags(RID)
chk("S7 전 게이트 통과(part·gongsu·staged)", f7.get("ok"), f"part{f7.get('part_ok')} gongsu{f7.get('gongsu_ok')} staged{f7.get('staged_ok')}")

# ── 정리: 전 롤백 ──
S._nx_tx = common._nx_tx; S._nx = common._nx
real_cn.rollback(); real_cn.close()
print("\n=== 결과 ===")
print(f"PASS {len(PASS)} · FAIL {len(FAIL)}")
if FAIL: print("실패:", FAIL)
print("✓전 롤백(테스트route·모든편집 제거·라이브 무접촉)")
