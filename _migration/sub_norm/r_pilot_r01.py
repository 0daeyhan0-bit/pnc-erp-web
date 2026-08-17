# -*- coding: utf-8 -*-
# ★Phase R2 파일럿: 다양 10건 R01 route 빌드(자도번→정규SUB·DISSOLVED해체·다단계) + 이슈로그 + 구조검증
import sys, hashlib
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
from collections import defaultdict
def RO(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD};ApplicationIntent=ReadOnly')
def NX(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)
c=RO().cursor(); nx=NX(); w=nx.cursor()

# sub_alias 로드
w.execute("SELECT variant, canonical, category, route_gubun, route_vendor FROM nx.sub_alias")
ALIAS={r[0]:dict(canon=r[1],cat=r[2],g=r[3],ven=r[4]) for r in w.fetchall()}
# 활성 BOM (PR) edges
c.execute("SELECT ITEM_CODE, MAT_CODE, USE_QTY FROM PR_M_ITEM_BOM WHERE ISNULL(EXCEPT_FLAG,'0')<>'1' AND MAT_CODE IS NOT NULL")
EDGES=defaultdict(list)
for r in c.fetchall():
    EDGES[(r[0] or '').strip()].append(((r[1] or '').strip(), float(r[2] or 1)))
c.execute("SELECT ITEM_CODE, ITEM_DESC FROM PR_M_ITEM")
NAME={(r[0] or '').strip():(r[1] or '') for r in c.fetchall()}

# 다양 10건 선별: sub_alias category 조합
FR,TO='250101','260731'
c.execute(f"SELECT DISTINCT ITEM_CODE FROM SA_T_SALE_DTL WHERE SALE_YMD BETWEEN ? AND ?", FR,TO)
shipped=set(r[0].strip() for r in c.fetchall() if r[0])
# 각 제품의 하위 변형 category 집계(직계+2단)
def variant_cats(p, depth=0, seen=None):
    if seen is None: seen=set()
    if p in seen or depth>6: return []
    seen.add(p); out=[]
    for ch,_ in EDGES.get(p,[]):
        a=ALIAS.get(ch)
        if a: out.append(a['cat'])
        out+=variant_cats(ch, depth+1, seen)
    return out
picks=[]
manual=['AJR75563402','AJR30012101','AJR30073601','AJR30089601','AJR77263008']  # 깊음·다SUB·태국·미래·DISSOLVED포함
for m in manual:
    if m in shipped: picks.append(m)
# 공용/리프/평면/MJU 자동보강
for p in sorted(shipped):
    if len(picks)>=10: break
    if p in picks: continue
    cats=variant_cats(p)
    if not cats and p.startswith('AJR') and EDGES.get(p) and len(picks)<7:  # 평면(변형없음)
        picks.append(p)
for p in sorted(shipped):
    if len(picks)>=10: break
    if p in picks: continue
    cats=set(variant_cats(p))
    if 'SUB_SHARED' in cats or 'DISSOLVED' in cats: picks.append(p)
picks=picks[:10]
print("파일럿 10건:", picks, "\n")

def is_weld(ch):  # ★용접봉/은납재만 = 공정종속(BOM 제외). 용접링은 사급부품이라 BOM 유지!
    if '용접링' in ch or '용접링' in NAME.get(ch,''): return False   # 용접링=사급부품 유지
    if ch.startswith(('RAC','BCUP','3H008')): return True
    nm=NAME.get(ch,'')
    if 'Solder' in nm or '용접봉' in nm: return True
    if '은납' in nm and not EDGES.get(ch): return True   # ★은납재(리프)만 제외 — 은납 SUB조립품은 유지
    return False
def is_realpum_node(ch):  # 실품번 sub(자도번 아님·자체 BOM 보유) = 노드(멈춤)
    return ('-' not in ch) and bool(EDGES.get(ch))
ISSUES=[]
def build(item):
    # R01 헤더(멱등: 기존 PILOT 삭제)
    w.execute("SELECT route_id FROM nx.sourcing_route WHERE item_code=? AND note='PILOT_R01'", item)
    for r in w.fetchall(): w.execute("DELETE FROM nx.sourcing_route_line WHERE route_id=?", r[0]); w.execute("DELETE FROM nx.sourcing_route WHERE route_id=?", r[0])
    w.execute("""INSERT INTO nx.sourcing_route(item_code,route_no,route_name,vendor_code,gubun,current_flag,approve_flag,apply_from,note,ins_user)
                 OUTPUT INSERTED.route_id VALUES(?,?,?,?,?,?,?,?,?,?)""",
              item,1,f"{item}_R01","","자체",1,1,'2026-08-12','PILOT_R01','R2pilot')
    rid=w.fetchone()[0]
    seq=[0]; leafset=set()
    def emit(parent_item, parent_line, seen, depth):
        if parent_item in seen or depth>8:
            ISSUES.append((item,'재귀중단/순환',parent_item)); return
        seen=seen|{parent_item}
        for ch,qty in EDGES.get(parent_item,[]):
            if is_weld(ch):  # 용접봉/은납재=공정종속 제외 (용접링은 유지)
                continue
            a=ALIAS.get(ch)
            seq[0]+=1; s=seq[0]
            if a and a['cat']=='DISSOLVED':
                ISSUES.append((item,'DISSOLVED 해체→하위단품',ch))
                emit(ch, parent_line, seen, depth+1)   # 하위를 이 레벨로
            elif a and a['cat'] in ('SUB','SUB_SHARED'):
                canon=a['canon']
                w.execute("""INSERT INTO nx.sourcing_route_line(route_id,sort_seq,node_kind,parent_line,sub_item,child_item,child_name,qty,gubun,vendor_code)
                             OUTPUT INSERTED.line_id VALUES(?,?,?,?,?,?,?,?,?,?)""",
                          rid,s,'SUB',parent_line,canon,canon,f"SUB {canon}",qty,a['g'],a['ven'] or '')
                lid=w.fetchone()[0]
                emit(ch, lid, seen, depth+1)           # SUB 하위 부품
            else:
                if a and a['cat'] in ('LEAF','STUB'):
                    gubun=a['g']; ven=a['ven'] or ''
                elif '-' in ch and ch not in ALIAS:
                    ISSUES.append((item,'변형이 sub_alias에 없음(미정규)',ch)); gubun=''; ven=''
                else:
                    gubun=''; ven=''
                w.execute("""INSERT INTO nx.sourcing_route_line(route_id,sort_seq,node_kind,parent_line,child_item,child_name,qty,gubun,vendor_code)
                             VALUES(?,?,?,?,?,?,?,?,?)""", rid,s,'PART',parent_line,ch,NAME.get(ch,'')[:118],qty,gubun,ven)
                leafset.add(ch)
    emit(item, None, set(), 0)
    return rid, leafset

# 레거시 리프셋 — emit과 동일 그레인(변형SUB/해체만 재귀, 실품번·직접부품·LEAF변형=멈춤, 용접봉 제외)
def legacy_leaf(item, seen=None):
    if seen is None: seen=set()
    if item in seen: return set()
    seen=seen|{item}; out=set()
    for ch,_ in EDGES.get(item,[]):
        if is_weld(ch): continue
        a=ALIAS.get(ch)
        if a and a['cat'] in ('SUB','SUB_SHARED','DISSOLVED'):
            out|=legacy_leaf(ch,seen)
        else:
            out.add(ch)
    return out

print(f"{'제품':<16}{'route라인':>8}{'nxR01리프':>10}{'레거시리프':>10}  리프일치")
for p in picks:
    rid,leaf=build(p)
    w.execute("SELECT COUNT(*) FROM nx.sourcing_route_line WHERE route_id=?", rid); nline=w.fetchone()[0]
    legleaf=legacy_leaf(p)
    match = '✔' if leaf==legleaf else f'✖ diff={sorted((leaf^legleaf))[:4]}'
    print(f"  {p:<16}{nline:>7}{len(leaf):>10}{len(legleaf):>10}  {match}")
nx.commit()
print(f"\n===== 이슈 로그 ({len(ISSUES)}) =====")
from collections import Counter
cnt=Counter(i[1] for i in ISSUES)
for k,v in cnt.items(): print(f"  [{k}] {v}건  예:{[i[2] for i in ISSUES if i[1]==k][:4]}")
nx.close(); print("DONE")
