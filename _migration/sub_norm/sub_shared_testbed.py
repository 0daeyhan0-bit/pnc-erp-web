# -*- coding: utf-8 -*-
"""SUB 공용/강제재사용 테스트베드 (무커밋 롤백·오염0, 워크트리 대상).
실제 엔드포인트 핸들러(sourcing_sub_create·route_approve·bom_addline·sub_dedup)를 커밋/close 무력화 프록시로 호출.
검증: ①다른 흐름(route)에서 동일 SUB 편성 → 공용 대체(강제재사용) ②제작처(사내/외주) 다르면 별개 SUB
     ③사용자가 2번째 제품 BOM에 SUB 넣으면 공용 변환(is_shared) ④공용확인 API(sub_dedup) 매치.
전 롤백(라이브 무접촉). 실행: python sub_shared_testbed.py"""
import sys, io, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'PNC_ERP_Web', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'New_ERP'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import common
import routers.sourcing as S
import routers.bom as B

real_cn = common._nx_tx()

class Tx:
    def __init__(self, cn): object.__setattr__(self, '_cn', cn)
    def cursor(self): return object.__getattribute__(self, '_cn').cursor()
    def commit(self): pass
    def rollback(self): pass
    def close(self): pass
    def __getattr__(self, n): return getattr(object.__getattribute__(self, '_cn'), n)

proxy = Tx(real_cn)
S._nx_tx = lambda: proxy; S._nx = lambda: proxy
B._nx = lambda: proxy; B._nx_tx = lambda: proxy
B._reset_cost_engine = lambda: None   # 캐시 리셋 무력화(테스트 격리)
cur = real_cn.cursor()
S._ensure_route_tbl(cur)

PASS = []; FAIL = []
def chk(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  [OK] " if cond else "  [FAIL] ") + name + ("" if cond else " :: " + detail))

# ── ASSY 자동선택: BOM 보유 + 비RAC 직속부품 >=3 ──
cur.execute("""SELECT TOP 1 h.item_code FROM nx.bom_header h
    JOIN nx.bom_line l ON l.bom_id=h.bom_id AND l.child_item NOT LIKE 'RAC%'
    GROUP BY h.item_code HAVING COUNT(*)>=3 ORDER BY h.item_code""")
IT = (cur.fetchone()[0] or '').strip()
print("테스트 ASSY =", IT)

def new_route(gubun_seed='자체'):
    cur.execute("SELECT ISNULL(MAX(route_no),1)+21 FROM nx.sourcing_route WHERE item_code=?", IT); rno = int(cur.fetchone()[0])
    cur.execute("INSERT INTO nx.sourcing_route(item_code,route_no,route_name,current_flag,approve_flag,ins_user) OUTPUT INSERTED.route_id VALUES(?,?,'공용테스트',0,0,'검증')", IT, rno)
    rid = int(cur.fetchone()[0])
    S._insert_current_tree(cur, rid, IT, '260630')
    return rid

def flat_parts(rid):
    cur.execute("SELECT line_id, LTRIM(RTRIM(ISNULL(child_item,''))), ISNULL(qty,1) FROM nx.sourcing_route_line WHERE route_id=? AND node_kind<>'SUB' AND parent_line IS NULL AND child_item NOT LIKE 'RAC%' ORDER BY line_id", rid)
    return [(int(r[0]), str(r[1]).strip(), float(r[2] or 1)) for r in cur.fetchall()]

def compose_sub(rid, base, gubun):
    fp = flat_parts(rid)[:3]
    picks = [x[0] for x in fp]
    r = S.sourcing_sub_create({"route_id": rid, "line_ids": picks, "base_child": base, "gubun": gubun, "name": base})
    return r.get("sub_item"), [{"item": x[1], "qty": x[2]} for x in fp]   # kids = [{item,qty}] (실제 qty)

def approve(rid):
    return S.sourcing_route_approve({"route_id": rid, "approve": 1, "user": "검증"})

def my_code(approve_res, my_subcode):
    """approve 결과에서 내가 만든 SUB(old==my_subcode)의 최종 코드+is_new. (기존 트리 SUB 혼입 배제)"""
    for m in approve_res.get("minted", []):
        if m.get("old") == my_subcode:
            return m.get("new"), bool(m.get("is_new"))
    return None, None

def sig_code(kids, own_mk):
    return B.sub_dedup({"children": kids, "weld": [], "make_type": own_mk})

# ── T1: 다른 흐름(route)에서 동일 SUB 편성 → 공용 대체(강제재사용) ──
print("\n=== T1: 다른 route에서 동일 SUB → 강제재사용(공용 대체) ===")
r1 = new_route(); c1, kids1 = compose_sub(r1, "ZZTESTSUB1", "자체")
code1, isnew1 = my_code(approve(r1), c1)
chk("T1 route1 SUB mint됨", bool(code1), str(c1))
chk("T1 route1 신규발급(is_new)", isnew1 is True, f"isnew={isnew1}")

r2 = new_route(); c2, kids2 = compose_sub(r2, "ZZTESTSUB2", "자체")   # 다른 base코드지만 동일 구성+제작처
code2, isnew2 = my_code(approve(r2), c2)
chk("T1 route2 동일구성 = route1 코드로 강제재사용", code2 == code1, f"route2={code2} vs route1={code1} kids1={kids1} kids2={kids2}")
chk("T1 route2 재사용(is_new=False)", isnew2 is False, f"isnew={isnew2}")

# ── T2: 제작처 다르면(외주) 별개 SUB ──
print("\n=== T2: 제작처(외주) 다르면 별개 SUB ===")
r3 = new_route(); c3, kids3 = compose_sub(r3, "ZZTESTSUB3", "외주")
code3, isnew3 = my_code(approve(r3), c3)
chk("T2 외주 = route1(자체)과 다른 코드", bool(code3) and code3 != code1, f"외주={code3} vs 자체={code1}")

# ── T3: 사용자가 2번째 제품 BOM에 SUB 넣으면 공용 변환 ──
print("\n=== T3: 2번째 제품 BOM에 SUB addline → 공용 변환(is_shared) ===")
# is_shared=0(비공용) 등록 SUB 하나 + 그와 다른 제품(부모) 선택
cur.execute("""SELECT TOP 1 m.raw_item, r.sub_code FROM nx.sub_registry r JOIN nx.sub_code_map m ON m.sub_code=r.sub_code
    WHERE ISNULL(r.is_shared,0)=0 AND EXISTS(SELECT 1 FROM nx.bom_line bl WHERE bl.child_item=m.raw_item)
    ORDER BY r.sub_code""")
_row = cur.fetchone()
sub_raw = (_row[0] or '').strip(); sub_code = (_row[1] or '').strip()
# 이 SUB를 현재 안 쓰는 다른 제품(부모) 선택
cur.execute("""SELECT TOP 1 item_code FROM nx.bom_header h WHERE item_code<>? AND EXISTS(SELECT 1 FROM nx.bom_line bl WHERE bl.bom_id=h.bom_id)
    AND NOT EXISTS(SELECT 1 FROM nx.bom_line bl2 WHERE bl2.bom_id=h.bom_id AND bl2.child_item=?) ORDER BY item_code""", sub_raw, sub_raw)
other_prod = (cur.fetchone()[0] or '').strip()
cur.execute("SELECT ISNULL(is_shared,0),ISNULL(ref_count,0) FROM nx.sub_registry WHERE sub_code=?", sub_code)
b4 = cur.fetchone(); before_shared = bool(b4[0]); before_ref = int(b4[1])
print(f"  대상 SUB raw={sub_raw} code={sub_code} (before is_shared={before_shared} ref={before_ref}) → 넣을 제품={other_prod}")
res = B.bom_addline({"parent": other_prod, "child": sub_raw, "qty": 1})
si = res.get("shared_info") or {}
chk("T3 addline 성공", res.get("ok"), str(res.get("errors")))
chk("T3 공용확인 반환됨", bool(si), str(res))
chk("T3 공용 변환(is_shared True·ref 증가)", si.get("is_shared") and si.get("ref_count", 0) > before_ref, f"before ref={before_ref} → after {si.get('ref_count')} shared={si.get('is_shared')}")

# ── T4: 공용확인 API(sub_dedup) 매치 ──
print("\n=== T4: 공용확인 API(sub_dedup) — 동일 구성+제작처 매치 ===")
d1 = sig_code(kids1, "1")   # route1 SUB 구성+자체(make_type 1)
chk("T4 dedup 기존 SUB 매치", d1.get("exists") and d1.get("sub_code") == code1, str(d1))
d2 = sig_code(kids1, "2")   # 같은 구성·제작처만 외주 → route1과 다른 SUB(=T2의 외주와 동일)
chk("T4 제작처 외주 = route1과 다른 매치", d2.get("sub_code") != code1, str(d2))

# ── 정리: 전 롤백 ──
S._nx_tx = common._nx_tx; S._nx = common._nx
real_cn.rollback(); real_cn.close()
print("\n=== 결과 ===")
print(f"PASS {len(PASS)} · FAIL {len(FAIL)}")
if FAIL: print("실패:", FAIL)
print("✓전 롤백(테스트 route·편집·mint 모두 제거·라이브 무접촉)")
