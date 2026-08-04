# -*- coding: utf-8 -*-
"""양산중_조치필요 145개 트리아지 — LG 용접봉 유무를 '가정 신호'로만 사용(소요량엔 미사용). 읽기전용·정본 불변.
대상: 원천갭(CS_T_ITEM_WELD 부재) + 최근24개월 생산실적有.
triage: LG에 용접봉 있음→'정비대상(용접가능성高)' / 없음→'확인후 부자재·제외후보(용접없을수도)'.
용접봉 소요량은 우리 산식(관경별횟수×표준소요량×1.5)만 — LG 소요량 사용 안 함."""
import sys, io, re, csv
sys.path.insert(0, r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc
from collections import defaultdict
def L(): return pyodbc.connect(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}", autocommit=True)
def N(): return pyodbc.connect(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}", autocommit=True)
lv = L().cursor(); nx = N().cursor()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
CUT = '240801'
def basew(x): return re.sub(r'(-\d+)+$', '', x)
def basep(x): return re.sub(r'(-(?:SUB\d*|S\d+|은납\d*|J\d+|\d+))+$', '', x)

lv.execute("SELECT DISTINCT ITEM_CODE FROM PR_T_PROD_DTL WHERE PROD_YMD>=? AND ISNULL(PROD_QTY,0)<>0", CUT)
PROD24 = set(str(r[0]).strip() for r in lv.fetchall())
lv.execute("SELECT ITEM_CODE, MAX(PROD_YMD) FROM PR_T_PROD_DTL GROUP BY ITEM_CODE")
LASTPROD = {str(r[0]).strip(): str(r[1]).strip() for r in lv.fetchall()}
lv.execute("SELECT DISTINCT P_ITEM_CODE FROM CS_T_ITEM_WELD"); HASWELD = set(str(r[0]).strip() for r in lv.fetchall())
nx.execute("SELECT item_code, ISNULL(item_name,'') FROM nx.item"); NAME = {str(r[0]).strip(): str(r[1]).strip() for r in nx.fetchall()}
# LG BOM 용접봉(base 매칭)
nx.execute("SELECT parent_code,child_code FROM nx.lg_bom WHERE child_code LIKE 'RAC%'")
LGset = set()
for r in nx.fetchall():
    p = str(r[0]).strip(); w = str(r[1]).strip()
    LGset.add((p, basew(w))); LGset.add((basep(p), basew(w)))
# routing 용접ST(51/28) per (parent,weld)
nx.execute("SELECT p_item,item_code,SUM(work_qty) FROM nx.routing WHERE item_code LIKE 'RAC%' AND proc_code IN ('51','28') AND work_qty>0 GROUP BY p_item,item_code")
RST = {(str(r[0]).strip(), str(r[1]).strip()): float(r[2]) for r in nx.fetchall()}
def ymd(y): return f"20{y[:2]}-{y[2:4]}-{y[4:6]}" if len(y) == 6 else (y or '없음')

# 대상: 원천갭 + 최근24M 생산有
nx.execute("SELECT parent_item,weld_item,ISNULL(use_qty,0) FROM nx.proc_weld WHERE ISNULL(meta_ok,0)=0 AND use_qty>0")
rows = []
for r in nx.fetchall():
    p = str(r[0]).strip(); w = str(r[1]).strip(); use = float(r[2])
    if p in HASWELD: continue          # 원천 있음 제외
    if p not in PROD24: continue       # 비양산 제외 → 양산중만
    inlg = (p, basew(w)) in LGset or (basep(p), basew(w)) in LGset
    rst = RST.get((p, w), 0.0)
    if inlg:
        triage = "정비대상(LG용접봉有·용접가능성高)"
        chk = "관경별 용접횟수 입력 필요 — 실제 몇파이 몇점? (routingST 참고)"
    else:
        triage = "확인후 부자재·제외후보(LG용접봉無)"
        chk = ("routing 용접ST 있음 → 용접 실재 가능, 관경확인" if rst > 0
               else "routing 용접ST도 없음 → 용접공정 없을수도, 부자재/제외 확인")
    rows.append({"item": p, "item_name": NAME.get(p, ''), "use_qty": round(use, 6),
                 "routing_weldST": rst, "in_lg_bom": int(inlg),
                 "last_prod_date": ymd(LASTPROD.get(p, '')), "triage": triage, "checkpoint": chk})

for path in [r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\PNC_ERP_Web\_schema\active_needfix_145.csv",
             r"C:\Users\admin\AppData\Local\Temp\claude\d-----------100-AI-AGENT\02b63e35-1303-4eb0-8eb4-29df63d29c62\scratchpad\active_needfix_145.csv"]:
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["item","item_name","use_qty","routing_weldST","in_lg_bom","last_prod_date","triage","checkpoint"])
        w.writeheader()
        for r in sorted(rows, key=lambda x: (-x["in_lg_bom"], x["item"])): w.writerow(r)

g_yes = [r for r in rows if r["in_lg_bom"]]
g_no = [r for r in rows if not r["in_lg_bom"]]
print(f"양산중_조치필요 {len(rows)}행 트리아지:")
print(f"  ① 정비대상(LG용접봉 有): {len(g_yes)}  ({round(100*len(g_yes)/len(rows),1)}%)")
print(f"  ② 확인후 부자재/제외후보(LG용접봉 無): {len(g_no)}  (그중 routingST有 {sum(1 for r in g_no if r['routing_weldST']>0)} / ST無 {sum(1 for r in g_no if r['routing_weldST']==0)})")
big = g_yes if len(g_yes) >= len(g_no) else g_no
print(f"\n=== 최다그룹 대표 (품번·품명·use·routingST·LG·최근생산) 12건 ===")
for r in big[:12]:
    print(f"  {r['item']} | {r['item_name'][:24]} | use={r['use_qty']} ST={r['routing_weldST']} LG={r['in_lg_bom']} 생산={r['last_prod_date']}")
print(f"\n=== 소그룹 대표 12건 ===")
small = g_no if big is g_yes else g_yes
for r in small[:12]:
    print(f"  {r['item']} | {r['item_name'][:24]} | use={r['use_qty']} ST={r['routing_weldST']} LG={r['in_lg_bom']} 생산={r['last_prod_date']}")
print("\nCSV: _schema/active_needfix_145.csv (+scratchpad)")
