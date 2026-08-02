# -*- coding: utf-8 -*-
"""
차세대 ERP · 원가 검증 하네스 (오라클 = 레거시 실원가용/내부용 SP)
목적: nx 이관·교정·엔진이 레거시 원가를 diff0로 재현하는지 자동검증하는 게이트.
  - 오라클 = SP_CS_견적서(실원가용)_250910 + (내부용)_250704 결과 (정답 ground truth)
  - 실원가 = TOT_AMT = 재료(JAI_COST)+가공(GAGONG_AMT)+일반(ILBAN_AMT)+운반(UNBAN_AMT)+이윤(PROFIT_AMT)
  - 손익 = LG_COST − TOT_AMT
  - 구조(현행 BOM) = 전 행 (level, C_ITEM_CODE, USE_QTY) — CS_CALC_EXCEPT_FLAG=0 반영된 실원가용 전개
  - 용접봉 소요 = RAC leaf qty
사용:
  from cost_oracle import get_oracle, snapshot, verify
  o = get_oracle('AJR75563402','260630')
  verify(o, candidate_dict)          # 후보(nx엔진 결과)와 비교 → {ok, diffs}
CLI:
  python cost_oracle.py anchors                 # 앵커 검증
  python cost_oracle.py snapshot <ymd> [file]   # 표본 오라클 스냅샷
"""
import sys, os, io, json
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client

SP_SIL = 'SP_CS_견적서(실원가용)_250910'
SP_NAE = 'SP_CS_견적서(내부용)_250704'

def _conn():
    return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
                          f'DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')

def _run(cur, sp, item, ymd):
    cur.execute("SET NOCOUNT ON; EXEC [dbo].[" + sp + "] ?, ?", item, ymd)
    cols = rows = None
    while True:
        if cur.description:
            cols = [d[0] for d in cur.description]
            try: rows = cur.fetchall()
            except Exception: rows = []
        if not cur.nextset(): break
    return cols or [], rows or []

def _num(x):
    try: return round(float(x), 2)
    except Exception: return 0.0

def get_oracle(item, ymd, cur=None):
    """품목 1개 오라클(실원가용+내부용 성분 + 구조 + 용접봉)."""
    own = cur is None
    cn = _conn() if own else None
    cur = cn.cursor() if own else cur
    try:
        sc, sr = _run(cur, SP_SIL, item, ymd)
        six = {c: i for i, c in enumerate(sc)}
        def g0(rows, ix, col):
            r0 = next((r for r in rows if str(r[ix.get('C_ITEM_LEVEL', -1)]) == '0'), rows[0] if rows else None)
            return _num(r0[ix[col]]) if (r0 is not None and col in ix) else 0.0
        sil = {
            "jae": g0(sr, six, 'JAI_COST'), "gagong": g0(sr, six, 'GAGONG_AMT'),
            "ilban": g0(sr, six, 'ILBAN_AMT'), "unban": g0(sr, six, 'UNBAN_AMT'),
            "profit": g0(sr, six, 'PROFIT_AMT'), "silwon": g0(sr, six, 'TOT_AMT'),
            "won": g0(sr, six, 'WON_JAI_AMT'), "bu": g0(sr, six, 'BU_JAI_AMT'),
            "lme": g0(sr, six, 'LME_CHA_AMT'), "lg": g0(sr, six, 'LG_COST'),
        }
        sil["sonik"] = round(sil["lg"] - sil["silwon"], 2)
        # 구조(현행 BOM 전개) + 용접봉
        struct, weld = [], {}
        if 'C_ITEM_CODE' in six:
            for r in sr:
                lv = r[six.get('C_ITEM_LEVEL', -1)]; code = str(r[six['C_ITEM_CODE']] or '').strip()
                uq = _num(r[six['USE_QTY']]) if 'USE_QTY' in six else 0.0
                struct.append({"lv": int(lv or 0), "code": code, "qty": uq})
                if code.startswith('RAC'):
                    weld[code] = weld.get(code, 0.0) + (_num(r[six['USE_QTY']]) if 'USE_QTY' in six else 0.0)
        nc, nr = _run(cur, SP_NAE, item, ymd)
        nix = {c: i for i, c in enumerate(nc)}
        nae = {"jae": g0(nr, nix, 'JAI_COST'), "naewon": g0(nr, nix, 'TOT_AMT'),
               "won": g0(nr, nix, 'WON_JAI_AMT'), "bu": g0(nr, nix, 'BU_JAI_AMT')}
        return {"item": item, "ymd": ymd, "sil": sil, "nae": nae,
                "struct_n": len(struct), "struct": struct, "weld": weld}
    finally:
        if own: cn.close()

# 검증 대상 성분(실원가용/내부용) — diff 비교 키
_SIL_KEYS = ["jae", "gagong", "ilban", "unban", "profit", "silwon", "lg", "sonik", "won", "bu"]
_NAE_KEYS = ["jae", "naewon", "won", "bu"]

def load_corrections(path=None):
    """수정 등록부(레거시 버그 의도적 수정) 로드.
       구조: { item: { "grp.key": {"legacy":x,"corrected":y,"reason":..,"approver":..,"date":..} } }
       미존재/미지정 시 빈 등록부(=순수 레거시 diff0 게이트)."""
    path = path or os.path.join(os.path.dirname(__file__), 'corrections.json')
    if os.path.exists(path):
        try: return json.load(open(path, encoding='utf-8'))
        except Exception: return {}
    return {}

def verify(oracle, cand, tol=1.0, corrections=None):
    """오라클 vs 후보(nx엔진) 비교.
       - 수정 등록부(corrections)에 있는 성분 → '수정값(corrected)'과 비교(=승인된 의도적 변경)
       - 나머지 → 레거시 오라클과 diff0
       - 미등록 divergence = 위반(violation) → FAIL
       반환 {ok, violations[], applied_corrections[]}."""
    corr = (corrections or {}).get(oracle.get("item"), {})
    violations, applied = [], []
    for grp, keys in [("sil", _SIL_KEYS), ("nae", _NAE_KEYS)]:
        o = oracle.get(grp, {}); c = (cand or {}).get(grp, {})
        for k in keys:
            ov = float(o.get(k, 0) or 0); cv = float(c.get(k, 0) or 0)
            ck = corr.get(f"{grp}.{k}")
            expected = float(ck["corrected"]) if ck else ov   # 등록된 수정이면 수정값이 기대치
            if abs(expected - cv) > tol:
                v = {"grp": grp, "key": k, "expected": expected, "cand": cv, "diff": round(cv - expected, 2)}
                if ck: v["corrected_from_legacy"] = ov; v["reason"] = ck.get("reason", "")
                violations.append(v)
            elif ck:
                applied.append({"key": f"{grp}.{k}", "legacy": ov, "corrected": cv,
                                "reason": ck.get("reason", ""), "approver": ck.get("approver", "")})
    if "struct" in cand:
        oset = {s["code"] for s in oracle.get("struct", [])}
        cset = {s["code"] for s in cand.get("struct", [])}
        # 구조 수정(예: 용접봉 leaf 제거)도 corrections에 struct.* 로 등록 가능. 여기선 단순비교.
        miss = oset - cset; extra = cset - oset
        if (miss or extra) and not corr.get("struct.itemset"):
            violations.append({"grp": "struct", "key": "itemset", "missing": sorted(miss)[:10], "extra": sorted(extra)[:10]})
    return {"ok": not violations, "violations": violations, "applied_corrections": applied}

def snapshot(items, ymd, out_path=None):
    """표본 오라클 배치 스냅샷 → JSON."""
    cn = _conn(); cur = cn.cursor(); out = {}
    try:
        for i, it in enumerate(items):
            try: out[it] = get_oracle(it, ymd, cur)
            except Exception as e: out[it] = {"error": str(e)[:80]}
            if (i + 1) % 20 == 0: print(f"  ...{i+1}/{len(items)}")
    finally:
        cn.close()
    if out_path:
        json.dump(out, open(out_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print("저장:", out_path)
    return out

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'anchors'
    if cmd == 'anchors':
        # 앵커: 실원가 성분식 자체검증(재료+가공+일반+운반+이윤=실원가) + 손익
        for it, ymd in [('AJR75563402', '260630'), ('AJR75563503', '260630'), ('AJR30077403', '260630')]:
            o = get_oracle(it, ymd); s = o['sil']
            calc = round(s['jae'] + s['gagong'] + s['ilban'] + s['unban'] + s['profit'], 2)
            ok = abs(calc - s['silwon']) < 0.5
            print(f"[{it}] 실원가={s['silwon']} (재료{s['jae']}+가공{s['gagong']}+일반{s['ilban']}+운반{s['unban']}+이윤{s['profit']}={calc}) {'✓' if ok else '✗불일치'}")
            print(f"        LG={s['lg']} 손익={s['sonik']} | 내부재료={o['nae']['jae']} 내부원가={o['nae']['naewon']} | 구조{o['struct_n']}행 용접봉{o['weld']}")
    elif cmd == 'snapshot':
        ymd = sys.argv[2] if len(sys.argv) > 2 else '260630'
        out = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(__file__), f'oracle_{ymd}.json')
        # 표본: AJR75563402 계열 + 대표 복잡품목(추후 리시빙 589로 확장)
        items = ['AJR75563402', 'AJR75563402-19-1', 'AJR75563402-F&T', 'AJR75563503',
                 'AJR30077403', 'AJR30008101', 'AJR75462802', 'AJR77224501']
        snapshot(items, ymd, out)
