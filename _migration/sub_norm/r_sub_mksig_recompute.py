# -*- coding: utf-8 -*-
"""S3: SUB 시그니처 make_type 재계산 (forward-only 정본화 §5).
   방식: 새 sig를 재귀로 전부 in-memory 계산(자식 keep=자식 새 sig, 등록·비keep=frozen registry sig, 미등록=L:코드)
         → 일괄 반영(순서무관). 분할(한 sub_code의 raw들이 새 sig로 갈림)=소수 갈래에 신규 sub_code+repoint.
   self-check: 반영 후 실제 bom.py._sub_signature(cur,...)로 표본 재계산 == 저장 sig (mint 정합 증명).
   유지 keep(BOM보유·make_type∈{1,2}·자식>=2)만. 탈락 무접촉. own_mk=품목 make_type(신규는 mint서 gubun→저장).
   기본 DRY(트랜잭션 롤백). --commit 시 백업 후 반영.
   실행: python r_sub_mksig_recompute.py [--commit]"""
import sys, os, hashlib
BACK = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'PNC_ERP_Web', 'backend')
sys.path.insert(0, BACK)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'New_ERP'))
import db_client, pyodbc
from collections import defaultdict
from routers.bom import _sub_signature   # mint과 동일 함수(self-check용)

def _nx():
    return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
        f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)

def main(commit):
    cn = _nx(); cur = cn.cursor()
    cur.execute("SELECT item_code,ISNULL(make_type,'') FROM nx.item")
    MK = {(r[0] or '').strip(): (r[1] or '').strip() for r in cur.fetchall()}
    cur.execute("SELECT h.item_code,l.child_item,l.qty FROM nx.bom_line l JOIN nx.bom_header h ON h.bom_id=l.bom_id WHERE l.child_item NOT LIKE 'RAC%'")
    CH = defaultdict(list)
    for r in cur.fetchall(): CH[(r[0] or '').strip()].append(((r[1] or '').strip(), float(r[2] or 1)))
    cur.execute("SELECT parent_item,weld_item,ISNULL(weld_st,0),ISNULL(use_qty,0) FROM nx.proc_weld")
    WD = defaultdict(list)
    for r in cur.fetchall(): WD[(r[0] or '').strip()].append(((r[1] or '').strip(), round(float(r[2] or 0),4), round(float(r[3] or 0),6)))
    HAS = set(CH)
    cur.execute("SELECT raw_item,sub_code FROM nx.sub_code_map"); RAW2SC = {(r[0] or '').strip():(r[1] or '').strip() for r in cur.fetchall()}
    cur.execute("SELECT sub_code,sig FROM nx.sub_registry"); SC2SIG = {(r[0] or '').strip():(r[1] or '').strip() for r in cur.fetchall()}
    def is_sub(n): return n in HAS and MK.get(n,'') in ('1','2') and len(CH.get(n,[]))>=2
    memo = {}
    def newsig(n, seen):
        if n in memo: return memo[n]
        if n in seen: return 'L:'+n
        seen = seen | {n}; items=[]
        for c,q in CH.get(n,[]):
            if c.upper().startswith('RAC'): continue
            if is_sub(c): key = newsig(c, seen)
            elif c in RAW2SC: key = SC2SIG.get(RAW2SC[c], 'L:'+c)
            else: key = 'L:'+c
            items.append((c, round(q,6), key))
        items.sort(key=lambda x:(x[0],x[1]))
        parts = [f"{k}#{q}" for _,q,k in items]
        ws = ';'.join(f"{wi}|{st}|{uq}" for wi,st,uq in sorted(WD.get(n,[])))
        v = 'S:'+hashlib.md5(f"C[{','.join(parts)}]W[{ws}]MK[{MK.get(n,'')}]".encode()).hexdigest()[:12]
        memo[n]=v; return v
    keep = [rw for rw in RAW2SC if is_sub(rw)]
    raw_new = {rw: newsig(rw, set()) for rw in keep}
    print(f"keep raw: {len(keep)} · 새 sig 유일: {len(set(raw_new.values()))}")
    # sub_code별 raw→새sig 그룹 (분할 판정)
    sc2groups = defaultdict(lambda: defaultdict(list))
    for rw, s in raw_new.items(): sc2groups[RAW2SC[rw]][s].append(rw)
    splits = {sc: g for sc, g in sc2groups.items() if len(g) > 1}
    print(f"분할 sub_code: {len(splits)} · 병합: 0(설계상 신규 sig는 유일)")
    try:
        if commit:
            cur.execute("IF OBJECT_ID('nx.sub_registry_bak_mksig','U') IS NULL SELECT * INTO nx.sub_registry_bak_mksig FROM nx.sub_registry")
            cur.execute("IF OBJECT_ID('nx.sub_code_map_bak_mksig','U') IS NULL SELECT * INTO nx.sub_code_map_bak_mksig FROM nx.sub_code_map")
        cur.execute("SELECT ISNULL(MAX(CAST(SUBSTRING(sub_code,2,10) AS INT)),0) FROM nx.sub_registry WHERE sub_code LIKE 'S[0-9][0-9][0-9][0-9][0-9]'")
        nextn = int(cur.fetchone()[0]) + 1
        # 비분할: sig UPDATE
        n_upd = 0
        for sc, g in sc2groups.items():
            if sc in splits: continue
            sig = next(iter(g))
            cur.execute("UPDATE nx.sub_registry SET sig=? WHERE sub_code=?", sig, sc)
            n_upd += 1
        # 분할: 최대 갈래=기존 sub_code 유지, 나머지=신규 sub_code+repoint
        n_new = 0; repoint = 0
        for sc, g in splits.items():
            branches = sorted(g.items(), key=lambda x: -len(x[1]))
            keep_sig, keep_raws = branches[0]
            cur.execute("UPDATE nx.sub_registry SET sig=? WHERE sub_code=?", keep_sig, sc)
            for sig, raws in branches[1:]:
                code = f"S{nextn:05d}"; nextn += 1; n_new += 1
                rep = sorted(raws)[0]
                cur.execute("INSERT INTO nx.sub_registry(sub_code,sig,rep_item,nm,members) VALUES(?,?,?,?,1)", code, sig, rep[:50], rep[:50])
                for rw in raws:
                    cur.execute("UPDATE nx.sub_code_map SET sub_code=? WHERE raw_item=?", code, rw); repoint += 1
        print(f"sig UPDATE(비분할): {n_upd} · 분할 신규코드: {n_new} · repoint: {repoint}")
        # self-check: 표본 raw를 실제 _sub_signature로 재계산 → 저장 sig 일치?
        import random
        samp = random.sample(keep, min(8, len(keep)))
        ok = 0
        for rw in samp:
            children = [{"item": c, "qty": q} for c, q in CH.get(rw, []) if not c.upper().startswith('RAC')]
            weld = [{"weld_item": wi, "weld_st": st, "use_qty": uq} for wi, st, uq in WD.get(rw, [])]
            calc = _sub_signature(cur, children, weld, own_mk=MK.get(rw, ''))
            cur.execute("SELECT r.sig FROM nx.sub_code_map m JOIN nx.sub_registry r ON r.sub_code=m.sub_code WHERE m.raw_item=?", rw)
            row = cur.fetchone(); stored = (row[0] or '').strip() if row else None
            if stored == calc: ok += 1
            else: print(f"    MISMATCH {rw}: stored={stored} calc={calc}")
        print(f"self-check(_sub_signature==저장): {ok}/{len(samp)}")
        if commit and ok == len(samp):
            cn.commit(); print("COMMITTED (백업 완료)")
        else:
            cn.rollback(); print("DRY 롤백(nx 무변경)" if not commit else "self-check 실패→롤백")
    except Exception as e:
        cn.rollback(); print("ERROR·롤백:", e); raise
    finally:
        cn.close()

if __name__ == "__main__":
    main("--commit" in sys.argv)
