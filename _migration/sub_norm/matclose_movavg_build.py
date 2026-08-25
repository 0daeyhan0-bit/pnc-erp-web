# -*- coding: utf-8 -*-
"""자재 이동평균 일마감(nx.mat_stock_daily) append 재빌더 — 사라진 원빌더를 기록스펙대로 재작성.
   이동평균: new_avg=(전일qty×전일avg+매입amt)/(전일qty+매입qty), 매입=tag9,S + 도입P(×환율). net=전tag 부호합. amt=qty×avg.
   MODE=validate(쓰기없음, 260821→260822 재계산 대조) / commit(260823~ append, 멱등).
   ★소스=dbo 라이브. 검증본(260630~260822) 불변, append만."""
import sys, io, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import db_client, pyodbc
MODE = sys.argv[1] if len(sys.argv) > 1 else 'validate'

NX = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)
LV = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
nc, lc = NX.cursor(), LV.cursor()

def load_state(ymd):
    nc.execute("SELECT mat_code, stock_qty, avg_cost FROM nx.mat_stock_daily WHERE ymd=?", ymd)
    return {r[0]: [float(r[1] or 0), float(r[2] or 0)] for r in nc.fetchall()}

# 소모품(sgroup 99%) 집합 — 신규품목 제외용
nc.execute("SELECT ITEM_CODE FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM WHERE ITEM_SGROUP LIKE '99%'")
CONSUM = set(r[0] for r in nc.fetchall())

def day_moves(ymd):
    """dbo 라이브 그날 움직임 → {mat:{net,pos,neg,pq(매입qty),pamt(매입amt)}}"""
    m = {}
    lc.execute("""SELECT MAT_CODE,
          SUM(CAST(MAINT_QTY AS float)) net,
          SUM(CASE WHEN MAINT_QTY>0 THEN CAST(MAINT_QTY AS float) ELSE 0 END) pos,
          SUM(CASE WHEN MAINT_QTY<0 THEN -CAST(MAINT_QTY AS float) ELSE 0 END) neg,
          SUM(CASE WHEN MAINT_TAG IN('9','S') THEN CAST(MAINT_QTY AS float) ELSE 0 END) pq,
          SUM(CASE WHEN MAINT_TAG IN('9','S') THEN CAST(MAINT_AMT AS float) ELSE 0 END) pamt
        FROM dbo.PU_T_STOCK_MAINT WHERE MAINT_YMD=? GROUP BY MAT_CODE""", ymd)
    for r in lc.fetchall():
        m[r[0]] = {'net': r[1] or 0, 'pos': r[2] or 0, 'neg': r[3] or 0, 'pq': r[4] or 0, 'pamt': r[5] or 0}
    # 도입: P=수입입고(+, 매입, ×환율) / Q=수출출고(−)
    lc.execute("""SELECT MAT_CODE, DIVISION,
          SUM(CAST(MAINT_QTY AS float)) q, SUM(CAST(MAINT_AMT AS float)*ISNULL(CAST(EXCHANGE_RATE AS float),1)) amtk
        FROM dbo.PU_T_STOCK_MAINT_C WHERE MAINT_YMD=? GROUP BY MAT_CODE,DIVISION""", ymd)
    for mat, div, q, amtk in lc.fetchall():
        d = m.setdefault(mat, {'net': 0, 'pos': 0, 'neg': 0, 'pq': 0, 'pamt': 0})
        q = q or 0; amtk = amtk or 0
        if str(div).strip() == 'P':      # 수입 입고(매입, 환율적용)
            d['net'] += q; d['pos'] += q; d['pq'] += q; d['pamt'] += amtk
        else:                             # Q 수출 출고
            d['net'] -= q; d['neg'] += q
    return m

def step(state, moves):
    """하루 전개 → {mat:(qty,amt,avg,in,out)}. state는 in-place 갱신."""
    out = {}
    mats = set(state) | set(moves)
    for mat in mats:
        pq0, pa0 = state.get(mat, [0.0, 0.0])   # 전일 qty, avg
        mv = moves.get(mat, {'net': 0, 'pos': 0, 'neg': 0, 'pq': 0, 'pamt': 0})
        if mat in CONSUM and mat not in state:   # 신규 소모품 제외(기존은 유지)
            continue
        pur_q, pur_amt = mv['pq'], mv['pamt']
        if pur_q > 0:
            if pq0 > 0:
                navg = (pq0 * pa0 + pur_amt) / (pq0 + pur_q)
            else:
                navg = (pur_amt / pur_q) if pur_q else pa0   # ★버그②: 마이너스/0 재고 refill=단가리셋
        else:
            navg = pa0
        nqty = pq0 + mv['net']
        namt = nqty * navg
        state[mat] = [nqty, navg]
        # 움직임 있었거나 재고 유효면 저장(carry-forward). 완전 정지+동일이어도 일별저장(원빌더 패턴)
        out[mat] = (nqty, namt, navg, mv['pos'], mv['neg'])
    return out

# ---------- VALIDATE: 260821 base → 260822 재계산 vs 저장 ----------
if MODE == 'validate':
    base = load_state('260821')
    stored = {}
    nc.execute("SELECT mat_code, stock_qty, avg_cost FROM nx.mat_stock_daily WHERE ymd='260822'")
    for r in nc.fetchall(): stored[r[0]] = (float(r[1] or 0), float(r[2] or 0))
    mv = day_moves('260822')
    calc = step(dict((k, list(v)) for k, v in base.items()), mv)
    # 대조: 저장된 260822 각 품목 qty/avg vs 재계산
    ok = bad = 0; samples = []
    for mat, (sq, sa) in stored.items():
        cq, ca = (calc[mat][0], calc[mat][2]) if mat in calc else (base.get(mat, [0, 0])[0], base.get(mat, [0, 0])[1])
        if abs(cq - sq) < 0.5 and abs(ca - sa) < 1.0:
            ok += 1
        else:
            bad += 1
            if len(samples) < 8: samples.append((mat, sq, cq, sa, ca))
    print(f"[VALIDATE] 260821→260822 재계산 vs 저장: 일치 {ok} · 불일치 {bad} · 일치율 {ok/(ok+bad)*100:.2f}%")
    for s in samples: print(f"   ⚠ {s[0]}: 저장qty{s[1]:.0f}/재계산{s[2]:.0f} · 저장avg{s[3]:.2f}/재계산{s[4]:.2f}")
    NX.rollback(); NX.close(); LV.close()

# ---------- COMMIT: 260823~ append (멱등) ----------
else:
    # 처리 일자 = 움직임 있는 260823~ (dbo)
    lc.execute("SELECT DISTINCT MAINT_YMD FROM dbo.PU_T_STOCK_MAINT WHERE MAINT_YMD>'260822' ORDER BY MAINT_YMD")
    days = [r[0] for r in lc.fetchall()]
    lc.execute("SELECT DISTINCT MAINT_YMD FROM dbo.PU_T_STOCK_MAINT_C WHERE MAINT_YMD>'260822'")
    days = sorted(set(days) | set(r[0] for r in lc.fetchall()))
    print(f"[COMMIT] append 대상일: {days}")
    state = load_state('260822')
    # 멱등: 260822 초과분 삭제(검증본 불변)
    nc.execute("DELETE FROM nx.mat_stock_daily WHERE ymd>'260822'"); print(f"   기존 260822초과 {nc.rowcount}행 삭제(멱등)")
    total = 0
    for D in days:
        mv = day_moves(D)
        out = step(state, mv)
        for mat, (q, a, avg, inq, outq) in out.items():
            nc.execute("""INSERT INTO nx.mat_stock_daily(ymd,mat_code,stock_qty,stock_amt,avg_cost,in_qty,in_amt,out_qty,out_amt)
                  VALUES(?,?,?,?,?,?,?,?,?)""", D, mat, q, round(a,2), round(avg,4), inq, round(inq*avg,2), outq, round(outq*avg,2))
            total += 1
        print(f"   {D}: {len(out)}품목 저장")
    NX.commit()
    nc.execute("SELECT MIN(ymd),MAX(ymd),COUNT(*) FROM nx.mat_stock_daily"); r=nc.fetchone()
    print(f"[COMMIT 완료] 총 {total}행 append · mat_stock_daily {r[0]}~{r[1]} {r[2]:,}행")
    NX.close(); LV.close()
