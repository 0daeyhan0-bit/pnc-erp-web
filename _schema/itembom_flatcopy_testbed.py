# -*- coding: utf-8 -*-
"""P1 검증: 복사→평면(leaf) 신규등록. flatget이 SUB 없이 완전 leaf + 마스터 pre-fill + 자식 전 필드 반환.
읽기전용(bom_flatget·bom_get 호출·쓰기 없음)."""
import sys, os, io
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'PNC_ERP_Web', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'New_ERP'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import routers.bom as B

PASS = []; FAIL = []
def chk(n, c, d=""):
    (PASS if c else FAIL).append(n); print(("  [OK] " if c else "  [FAIL] ") + n + ("" if c else " :: " + d))

SRC = 'AJR73364008'
print(f"=== P1: {SRC} 복사→평면 신규등록 검증 ===")

# 1) flatget = 평면 leaf
fg = B.bom_flatget(item=SRC)
leaves = fg['lines']
print(f"  flatget leaf {len(leaves)} · top(lgroup={fg['lgroup']} sgroup={fg['sgroup']} make_type={fg['make_type']})")
chk("T1 leaf 존재", len(leaves) > 0, "0")
chk("T1 top 마스터 pre-fill(lgroup·sgroup·make_type)", bool(fg['lgroup'] and fg['sgroup'] and fg['make_type']), f"{fg['lgroup']}/{fg['sgroup']}/{fg['make_type']}")

# 2) SUB 없음(완전 leaf) — bom_line 직하위엔 SUB 있으나 flat엔 없어야
codes = [str(l['child_item']) for l in leaves]
sub_like = [c for c in codes if ('-S' in c.upper()) or c.upper().startswith(SRC.upper())]
chk("T2 평면=SUB 없음(자기품번 파생/-S 없음)", len(sub_like) == 0, f"SUB흔적 {sub_like}")

# 3) bom_line 직하위(편집 기존)엔 SUB 포함 = 대비 증명
bg = B.bom_get(item=SRC)
bg_codes = [str(l['child_item']) for l in bg['lines']]
bg_sub = [c for c in bg_codes if ('-S' in c.upper()) or c.upper().startswith(SRC.upper())]
print(f"  (대비) bom_line 직하위 {len(bg_codes)} · 그중 SUB {bg_sub}")
chk("T3 bom_line엔 SUB 존재(평면이 실제로 펼침 증명)", len(bg_sub) > 0, "SUB 없음=대비 불가")

# 4) 각 leaf = 신규 BOM 라인 필드 완비(child_item·item_name·qty·마스터)
need = ('child_item', 'item_name', 'qty', 'unit', 'metal_gubun', 'diam', 'thick', 'sgroup', 'lgroup', 'make_type', 'cost_gubun', 'status')
allok = all(all(k in l for k in need) for l in leaves)
chk("T4 leaf 전 필드(마스터 포함) 완비", allok, "필드 누락")
# 품명 존재(빈 자식 없이)
named = sum(1 for l in leaves if str(l.get('item_name') or '').strip())
chk("T4 leaf 품명 존재", named == len(leaves), f"{named}/{len(leaves)}")

# 5) qty 숫자(JSON-safe)
chk("T5 qty 숫자형", all(isinstance(l['qty'], (int, float)) for l in leaves), "비숫자")

print(f"\n=== 결과 === PASS {len(PASS)} · FAIL {len(FAIL)}")
if FAIL: print("실패:", FAIL)
print("✓읽기전용(쓰기 없음)")
