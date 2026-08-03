# -*- coding: utf-8 -*-
"""proc_weld 원천데이터 갭(CS_T_ITEM_WELD 부재) 부모를 '작업 형태'별로 분해 — 읽기전용, 임의확정 금지.
대상: proc_weld(meta_ok=0, use_qty>0) 中 부모가 레거시 CS_T_ITEM_WELD.P_ITEM_CODE에 EXACT 없음.
형태:
 (a) 은납/BCUP 계열만  (b) 체결/포장 only  (c) 수동입력 bom_line  (d) 노후/폐번·비활성
 (e) SUB/변형 접미사(정규화하면 item_weld 있음 — 이 변형만 없음)  (f) 기타(비용접 소모품 오분류 등)
산출: _schema/procweld_nosource.csv (+scratchpad 사본). use_qty/ diff0 불변(RO)."""
import sys, io, re, csv
sys.path.insert(0, r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc
from collections import defaultdict
def L():  return pyodbc.connect(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}", autocommit=True)
def N():  return pyodbc.connect(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}", autocommit=True)
nx = N().cursor(); lv = L().cursor()

# RAC 용접봉 코드 분류(품명 기반 실측)
WELD_ROD = {"RAC30823003"}                                   # WELDING WIRE(용접)
NONWELD  = {"RAC31704701", "RAC31704702", "RAC36134101"}     # Silicon/진공구리스(비용접 소모품 오분류)
def rodcat(w):
    if w in NONWELD: return "비용접소모품"
    if w in WELD_ROD: return "용접"
    return "은납/BCUP"                                        # 나머지 RAC=은납·BCUP 계열(brazing)

# 레거시 CS_T_ITEM_WELD 원천(EXACT P_ITEM) + nx.item_weld 부모집합
lv.execute("SELECT DISTINCT P_ITEM_CODE FROM CS_T_ITEM_WELD")
LEG = set(str(r[0]).strip() for r in lv.fetchall())
nx.execute("SELECT DISTINCT item_code FROM nx.item_weld")
IWP = set(str(r[0]).strip() for r in nx.fetchall())
# sub_variant_map 정규화
nx.execute("SELECT variant_item,base_item,common_sub FROM nx.sub_variant_map")
V2B = {str(r[0]).strip(): (str(r[1]).strip(), str(r[2]).strip()) for r in nx.fetchall()}
def norms(p):
    out = [p]
    if p in V2B:
        b, cs = V2B[p]
        if b: out.append(b)
        if cs: out.append(cs)
    s = re.sub(r'(-\d+)+$', '', p)
    if s != p: out.append(s)
    s2 = re.sub(r'(-(?:SUB\d*|S\d+|은납|J\d+|\d+))+$', '', p)
    if s2 != p: out.append(s2)
    return out
def norm_in_iw(p):
    return any(np in IWP for np in norms(p))
def has_suffix(p):
    return bool(re.search(r'-(?:SUB\d*|S\d+|은납|J\d+|\d+)', p))

# 부모별 routing 조립공정군(carrier p_item=부모)
nx.execute("""SELECT p_item, proc_code FROM nx.routing WHERE item_code LIKE 'RAC%' AND ISNULL(work_qty,0)>0 AND ISNULL(TRY_CONVERT(int,proc_code),99)<90""")
RGRP = defaultdict(set)
_WELD = {"51", "28"}; _FAST = {"55","52","69","70","71","72","73","74","75","76","77","78","79","80","81","82","68","23","24","25"}; _PACK = {"61","83"}
for r in nx.fetchall():
    p = str(r[0]).strip(); pc = str(r[1]).strip()
    g = "용접" if pc in _WELD else ("체결" if pc in _FAST else ("포장" if pc in _PACK else "가공"))
    RGRP[p].add(g)

# 품명(nx.item) + 상태·생산구분(PR_M_ITEM 라이브)
nx.execute("SELECT item_code, ISNULL(item_name,'') FROM nx.item")
NAME = {str(r[0]).strip(): str(r[1]).strip() for r in nx.fetchall()}
lv.execute("SELECT ITEM_CODE, ISNULL(ITEM_STATUS,''), ISNULL(COST_GUBUN,'') FROM PR_M_ITEM")
STAT = {}; CG = {}
for r in lv.fetchall():
    STAT[str(r[0]).strip()] = str(r[1]).strip(); CG[str(r[0]).strip()] = str(r[1] and str(r[2]).strip() or "")
ACTIVE = {"1"}   # 1=양산/정상, 그외(2·3·4·5·9·'')=개발/폐번/비활성 후보

# 대상 rows
nx.execute("SELECT parent_item,weld_item,ISNULL(use_qty,0) FROM nx.proc_weld WHERE ISNULL(meta_ok,0)=0 AND use_qty>0")
rows = [(str(r[0]).strip(), str(r[1]).strip(), float(r[2])) for r in nx.fetchall()]
# 라우팅ST(51/28)
nx.execute("SELECT p_item,item_code,SUM(work_qty) FROM nx.routing WHERE item_code LIKE 'RAC%' AND proc_code IN ('51','28') AND work_qty>0 GROUP BY p_item,item_code")
RST = {(str(r[0]).strip(), str(r[1]).strip()): float(r[2]) for r in nx.fetchall()}

def classify(p, w, use):
    cat = rodcat(w); grp = RGRP.get(p, set()); st = STAT.get(p, ""); nm = NAME.get(p, "")
    rst = RST.get((p, w), 0.0)
    if p in LEG:
        return None  # 원천 있음(다른 문제) — 대상 아님
    # 형태 판정(우선순위)
    if cat == "비용접소모품":
        return "f", f"비용접 소모품({NAME.get(w,'')})이 용접봉으로 BOM 등록됨 — 용접 원천 대상 아님"
    if norm_in_iw(p):
        return "e", f"변형 접미사 — 정규화 부모({[x for x in norms(p) if x in IWP][:1]})는 item_weld 있음, 이 변형만 없음"
    if st and st not in ACTIVE:
        return "d", f"품목상태={st}(비양산/폐번·개발 추정) — item_weld 미정비"
    if grp and "용접" not in grp and ("체결" in grp or "포장" in grp):
        return "b", f"routing 조립공정={sorted(grp)} (용접/은납 공정 없음) — 용접봉 소요 수동"
    if cat == "은납/BCUP":
        return "a", f"용접봉={NAME.get(w,'')}(은납/BCUP), item_weld 관경행 부재 (routing={sorted(grp) or '없음'})"
    return "c", f"item_weld 전무·정규화도 없음(수동 bom_line 추정, routing={sorted(grp) or '없음'})"

out = []
for p, w, use in rows:
    r = classify(p, w, use)
    if r is None: continue
    form, note = r
    out.append({"parent_item": p, "weld_item": w, "item_name": NAME.get(p, ""),
                "use_qty": round(use, 6), "routing_st": RST.get((p, w), 0.0),
                "form": form, "note": note})

# CSV 저장
for path in [r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\PNC_ERP_Web\_schema\procweld_nosource.csv",
             r"C:\Users\admin\AppData\Local\Temp\claude\d-----------100-AI-AGENT\02b63e35-1303-4eb0-8eb4-29df63d29c62\scratchpad\procweld_nosource.csv"]:
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["parent_item","weld_item","item_name","use_qty","routing_st","form","note"])
        w.writeheader()
        for row in sorted(out, key=lambda x: (x["form"], x["parent_item"])): w.writerow(row)

FN = {"a":"은납/BCUP 계열만","b":"체결/포장 only","c":"수동입력 bom_line","d":"노후/폐번·비활성","e":"SUB/변형 접미사","f":"기타(비용접 소모품 등)"}
cnt = defaultdict(int); parents = defaultdict(set)
for row in out: cnt[row["form"]] += 1; parents[row["form"]].add(row["parent_item"])
print(f"대상(원천 부재) rows={len(out)} · 부모={len(set(x['parent_item'] for x in out))}")
print("=== 형태별 건수 ===")
for f in ["a","b","c","d","e","f"]:
    print(f"  ({f}) {FN[f]}: {cnt[f]}행 / {len(parents[f])}부모")
print("\n=== 형태별 대표(품번·품명·소요량·routingST) 최대 12건 ===")
for f in ["a","b","c","d","e","f"]:
    reps = [x for x in out if x["form"] == f][:12]
    print(f"\n■ ({f}) {FN[f]} — {cnt[f]}행")
    for x in reps:
        print(f"   {x['parent_item']} | {x['item_name'][:26]} | use={x['use_qty']} ST={x['routing_st']} | {x['weld_item']}")
