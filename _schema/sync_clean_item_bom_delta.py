# -*- coding: utf-8 -*-
"""클린 정본(nx.item · nx.bom_header/bom_line) 델타 동기화 — 라이브 신규 등록분 반영
   (2026-09-01 신설)

왜 필요한가
  편성 STEP6/7 이 읽는 것은 **`nx.v_pr_bom` 뷰 = `nx.bom_header`+`nx.bom_line`(클린)** 이다
  (planrev.py `_ensure_bom_snap`). 미러(`nx.PR_M_ITEM_BOM`)를 채워도 **뷰는 안 본다.**
  ⟹ `sync_item_bom_delta.py`(미러) 만으로는 계획이 안 고쳐진다. 이 스크립트가 짝이다.

    실측 2026-09-01 — `AJR30100102-19-1`('명진 SUB', 2306, 08:40 손진욱 등록)
      라이브 BOM :  AJR30100102 → **AJR30100102-19-1** → 부품 10
      클린  BOM :  AJR30100102 → 부품(MJU3907432x…) **직접**   ← -19-1 단계가 없다
      ⟹ 웹이 `-19-1` 을 건너뛰고 7종으로 전개해 명진 자재소요가 제번당 7배로 부풀었다
         (6I2M03K2 +240 · 6I2M03VG +300 … 13제번 +590). 레거시는 정상.

★★이 스크립트가 하는 일 = **라이브 BOM 을 그대로 반영**한다
  단순히 `-19-1` 을 추가만 하면 상위에 **부품과 -19-1 이 동시에** 달려 이중계상된다.
  라이브에서 상위→부품 링크가 사라졌다면 클린에서도 사라져야 한다.
  ⟹ 대상 상위품목에 한해 **라이브 상태로 맞춘다**(추가 + 라이브에 없는 링크 제거).

★안전 원칙 (2026-08-31 사고 재발방지)
  · 라이브는 **읽기만**(§1-1). 쓰기는 nx 뿐.
  · `--apply` 없이는 조회만(기본 dry-run).
  · 실행 전 백업.
  · **삭제는 `--item` 으로 지정한 상위품목 스코프 안에서만**(§1-3 근거키 스코프).
    전역 삭제 금지 — 과거 `ADM74930507→-STS` 를 잉여로 오판해 지웠다가
    가상도번 경로가 끊겨 18개가 누락된 사고가 있었다.
  · 삭제 대상은 실행 전에 **전량 출력**하고, 그 링크를 통해야만 닿는 하위가 있는지
    (= 경로가 끊기는지) 사전 점검한다.

사용
    python _schema/sync_clean_item_bom_delta.py --item AJR30100102
    python _schema/sync_clean_item_bom_delta.py --item AJR30100102 --apply
"""
import sys, os, io, argparse, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                              errors='replace', line_buffering=True)
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, '..', 'PNC_ERP_Web', 'backend'))
sys.path.insert(0, os.path.join(_HERE, '..', '..', 'New_ERP'))

AP = argparse.ArgumentParser()
AP.add_argument('--item', action='append', required=True,
                help='동기화할 상위품목 코드(여러 번 지정 가능)')
AP.add_argument('--apply', action='store_true', help='실제 반영(없으면 조회만)')
ARG = AP.parse_args()
ITEMS = [str(x).strip() for x in ARG.item if str(x).strip()]

import pyodbc, db_client

CS = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
      f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
STAMP = datetime.datetime.now().strftime('%y%m%d_%H%M')
LB = 'PARTNER_ERP.dbo.PR_M_ITEM_BOM'
LI = 'PARTNER_ERP.dbo.PR_M_ITEM'

cn = pyodbc.connect(CS, autocommit=False)
cur = cn.cursor()

print('=' * 78)
print(' 클린 BOM 델타 동기화  ' + ('[APPLY]' if ARG.apply else '[DRY-RUN — 조회만]'))
print(' 대상 상위품목: ' + ', '.join(ITEMS))
print('=' * 78)


def live_kids(p):
    cur.execute(f"""SELECT RTRIM(MAT_CODE), CAST(ISNULL(USE_QTY,0) AS float),
                           RTRIM(ISNULL(FROM_APPLY_YMD,'')), RTRIM(ISNULL(TO_APPLY_YMD,'')),
                           ISNULL(BOM_SEQ,0), ISNULL(RTRIM(EXCEPT_FLAG),'0'),
                           ISNULL(RTRIM(VIR_ITEM_FLAG),'0'), ISNULL(RTRIM(CUST_CODE),'')
                      FROM {LB} WITH(NOLOCK) WHERE RTRIM(ITEM_CODE)=? ORDER BY MAT_CODE""", p)
    return {str(r[0]).strip(): r for r in cur.fetchall()}


def clean_kids(p):
    cur.execute("""SELECT RTRIM(b.child_item), CAST(b.qty AS float), b.bom_id, b.seq
                     FROM nx.bom_line b JOIN nx.bom_header h ON h.bom_id=b.bom_id
                     JOIN (SELECT item_code, MAX(ISNULL(version,1)) mv FROM nx.bom_header
                            GROUP BY item_code) mx
                       ON mx.item_code=h.item_code AND ISNULL(h.version,1)=mx.mv
                    WHERE RTRIM(h.item_code)=? ORDER BY b.child_item""", p)
    return {str(r[0]).strip(): r for r in cur.fetchall()}


# 대상 = 지정 품목 + 그 아래 새로 생기는 -19-1 등(라이브에 있고 클린에 없는 중간노드)
targets = list(ITEMS)
for p in ITEMS:
    for k in live_kids(p):
        if k not in clean_kids(p):
            targets.append(k)                    # 새로 생기는 중간노드도 채워야 한다
targets = list(dict.fromkeys(targets))

plan_add, plan_del, plan_item = [], [], []
print('\n① 품목마스터(nx.item) 누락 점검')
print('   ※값은 지어내지 않는다 — 라이브에서 읽고, nx.item 전용 컬럼은')
print('     같은 접미사 형제(-19-1 등)의 값을 그대로 본뜬다.')
for c in targets:
    cur.execute("SELECT COUNT(*) FROM nx.item WITH(NOLOCK) WHERE RTRIM(item_code)=?", c)
    if int(cur.fetchone()[0] or 0) == 0:
        cur.execute(f"""SELECT ISNULL(RTRIM(ITEM_DESC),''), ISNULL(RTRIM(IN_CUST_CODE),''),
                               ISNULL(PROD_RATE,100), ISNULL(RTRIM(UNIT),'')
                          FROM {LI} WITH(NOLOCK) WHERE RTRIM(ITEM_CODE)=?""", c)
        r = cur.fetchone()
        if not r:
            print(f'   ★{c:22s} 라이브에도 없음 — 건너뜀')
            continue
        # 형제(같은 접미사)에서 nx.item 전용 컬럼을 본뜬다
        suf = c[c.rfind('-'):] if '-' in c else ''
        cur.execute("""SELECT TOP 1 item_type, unit, silver_flag, status, has_gagong
                         FROM nx.item WITH(NOLOCK)
                        WHERE item_code LIKE ? AND item_code<>? ORDER BY item_code""",
                    '%' + suf, c)
        sib = cur.fetchone()
        if not sib:
            cur.execute("""SELECT TOP 1 item_type, unit, silver_flag, status, has_gagong
                             FROM nx.item WITH(NOLOCK) WHERE RTRIM(item_code)=?""",
                        c.split('-')[0])
            sib = cur.fetchone()
        if not sib:
            print(f'   ★{c:22s} 본뜰 형제가 없음 — 수동 확인 필요, 건너뜀')
            continue
        plan_item.append((c, str(r[0]).strip(), str(r[1]).strip(), float(r[2] or 100),
                          (str(r[3]).strip() or str(sib[1]).strip()), sib))
        print(f'   + {c:22s} {str(r[0]).strip()[:24]:26s} 매입처 {str(r[1]).strip()}'
              f'  (본뜬형제: type={sib[0]} unit={sib[1]} status={sib[3]})')
if not plan_item:
    print('   (누락 없음)')

print('\n② BOM 링크 차이 (라이브 기준)')
for p in targets:
    lk, ck = live_kids(p), clean_kids(p)
    add = [k for k in lk if k not in ck]
    dele = [k for k in ck if k not in lk]
    if not add and not dele:
        continue
    print(f'\n   [{p}]  라이브 {len(lk)} / 클린 {len(ck)}')
    for k in add:
        print(f'      + 추가  {k:24s} x{lk[k][1]:<8} 적용 {lk[k][2]}~{lk[k][3]}')
        plan_add.append((p, k, lk[k]))
    for k in dele:
        print(f'      - 제거  {k:24s} x{ck[k][1]}')
        plan_del.append((p, k, ck[k]))

# ★경로 단절 점검 — 지울 링크를 통해야만 닿는 하위가 있나
if plan_del:
    print('\n③ ★경로 단절 점검 (지우면 못 닿게 되는 하위가 있나)')
    for p, k, _ in plan_del:
        cur.execute("""SELECT COUNT(*) FROM nx.bom_line b JOIN nx.bom_header h ON h.bom_id=b.bom_id
                        WHERE RTRIM(h.item_code)=?""", k)
        kids = int(cur.fetchone()[0] or 0)
        cur.execute("""SELECT COUNT(DISTINCT RTRIM(h.item_code))
                         FROM nx.bom_line b JOIN nx.bom_header h ON h.bom_id=b.bom_id
                        WHERE RTRIM(b.child_item)=?""", k)
        ups = int(cur.fetchone()[0] or 0)
        if ups > 1:
            flag = 'OK(다른 상위 있음)'
        elif not kids:
            flag = 'OK(하위 없음)'
        else:
            # ★유일경로처럼 보여도 '교체' 일 수 있다 — 같은 부모에 새로 추가되는 노드가
            #   그 하위를 대신 커버하면 실제로 잃는 것은 차집합뿐이다.
            #   (2026-09-01: AJR33796526-19-1 → AJR30100102-19-1 교체를 '단절' 로 오판했다.
            #    옛 코드는 라이브 상위연결 0·레거시 자재소요 0 = 이미 은퇴한 코드였다.)
            cur.execute("""SELECT RTRIM(b.child_item) FROM nx.bom_line b
                             JOIN nx.bom_header h ON h.bom_id=b.bom_id
                            WHERE RTRIM(h.item_code)=?""", k)
            oldk = {str(x[0]).strip() for x in cur.fetchall()}
            newk = set()
            for pp, kk, _lr in plan_add:
                if pp != p:
                    continue
                cur.execute("""SELECT RTRIM(b.child_item) FROM nx.bom_line b
                                 JOIN nx.bom_header h ON h.bom_id=b.bom_id
                                WHERE RTRIM(h.item_code)=?""", kk)
                newk |= {str(x[0]).strip() for x in cur.fetchall()}
                newk |= {m for m in live_kids(kk)}
            lost = sorted(oldk - newk)
            if not lost:
                flag = 'OK(교체 — 하위 전부 새 노드가 커버)'
            else:
                flag = f'★확인필요 — 잃는 하위 {len(lost)}: {", ".join(lost[:5])}'
        print(f'      {p} → {k:24s} 하위 {kids:3d} · 상위 {ups} → {flag}')

if not (plan_item or plan_add or plan_del):
    print('\n   ✅ 이미 라이브와 동기 상태입니다.')
    cn.close(); sys.exit(0)

print(f'\n④ 요약   품목 +{len(plan_item)} · BOM +{len(plan_add)} / -{len(plan_del)}')

if not ARG.apply:
    print('\n※ DRY-RUN 입니다. 실제로 반영하려면 --apply 를 붙이세요.')
    cn.close(); sys.exit(0)

# ───────────────────────── APPLY ─────────────────────────
print('\n⑤ 백업')
bk1 = f'nx.bk_item_{STAMP}'
bk2 = f'nx.bk_bomline_{STAMP}'
cur.execute(f'SELECT * INTO {bk1} FROM nx.item');      print(f'   {bk1} ({cur.rowcount:,}행)')
cur.execute(f'SELECT * INTO {bk2} FROM nx.bom_line');  print(f'   {bk2} ({cur.rowcount:,}행)')

print('\n⑥ 반영')
# nx.item — NOT NULL 컬럼(item_name·item_type·unit·silver_flag·status·has_gagong)은
#   형제에서 본뜬 값을 쓴다. item_name 만 라이브 ITEM_DESC.
for c, desc, cust, pr, unit, sib in plan_item:
    cur.execute("""INSERT INTO nx.item(item_code, item_name, item_type, unit,
                                       silver_flag, status, has_gagong, prod_rate)
                   VALUES(?,?,?,?,?,?,?,?)""",
                c, desc, sib[0], (unit or sib[1]), sib[2], sib[3], sib[4], pr)
print(f'   품목 +{len(plan_item)}행')

for p, k, lr in plan_add:
    cur.execute("""SELECT TOP 1 h.bom_id FROM nx.bom_header h
                    JOIN (SELECT item_code, MAX(ISNULL(version,1)) mv FROM nx.bom_header
                           GROUP BY item_code) mx
                      ON mx.item_code=h.item_code AND ISNULL(h.version,1)=mx.mv
                   WHERE RTRIM(h.item_code)=?""", p)
    r = cur.fetchone()
    if not r:
        # ★apply_from 은 NOT NULL(date). 형제 -19-1 헤더가 전부 '2000-01-01'·status '확정' 이라
        #   그 관행을 그대로 따른다(값을 지어내지 않는다 — 실측 근거).
        cur.execute("""SELECT TOP 1 apply_from, status FROM nx.bom_header
                        WHERE item_code LIKE '%-19-1' ORDER BY bom_id""")
        hs = cur.fetchone()
        af = hs[0] if hs else '2000-01-01'
        st = str(hs[1]) if hs else '확정'
        cur.execute("INSERT INTO nx.bom_header(item_code, version, apply_from, status) VALUES(?,1,?,?)",
                    p, af, st)
        cur.execute("SELECT TOP 1 bom_id FROM nx.bom_header WHERE RTRIM(item_code)=? ORDER BY bom_id DESC", p)
        r = cur.fetchone()
    bid = r[0]
    cur.execute("SELECT ISNULL(MAX(seq),0)+1 FROM nx.bom_line WHERE bom_id=?", bid)
    nseq = int(cur.fetchone()[0] or 1)
    # node_type 은 NOT NULL — 같은 부모의 기존 행에서 본뜬다(없으면 자식 어디서든).
    cur.execute("SELECT TOP 1 node_type FROM nx.bom_line WHERE bom_id=?", bid)
    nt = cur.fetchone()
    if not nt:
        cur.execute("SELECT TOP 1 node_type FROM nx.bom_line WHERE RTRIM(child_item)=?", k)
        nt = cur.fetchone()
    ntv = str(nt[0]) if nt else 'M'
    cur.execute("""INSERT INTO nx.bom_line(bom_id, seq, child_item, qty, qty_pr, node_type,
                                           from_ymd, to_ymd, except_flag, vir_item, cust_code,
                                           cs_calc_except, lme_except, sagub_default,
                                           is_optional, set_except, kitting)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,0,0,0,0,0,0)""",
                bid, nseq, k, float(lr[1]), float(lr[1]), ntv,
                str(lr[2]).strip(), str(lr[3]).strip(),
                1 if str(lr[5]).strip() == '1' else 0,
                1 if str(lr[6]).strip() == '1' else 0, str(lr[7]).strip())
print(f'   BOM +{len(plan_add)}행')

for p, k, cr in plan_del:
    cur.execute("DELETE FROM nx.bom_line WHERE bom_id=? AND RTRIM(child_item)=?", cr[2], k)
print(f'   BOM -{len(plan_del)}행')

cn.commit()

print('\n⑦ 검증 — 뷰(nx.v_pr_bom)에서 확인')
print('   ※뷰는 bom_line + proc_weld(용접) UNION 이라 용접분만큼 라이브보다 많을 수 있다')
print('     (실측: AJR30100102 → RAC30599301-1 이 BOM 0.0012 · 용접 0.0098 로 2행 = 정상)')
for p in targets:
    cur.execute("""SELECT COUNT(*) FROM nx.v_pr_bom WHERE RTRIM(ITEM_CODE)=?
                     AND REMARKS<>'[weld]'""", p)
    a = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM nx.proc_weld WHERE RTRIM(parent_item)=?", p)
    w = int(cur.fetchone()[0] or 0)
    lk = len(live_kids(p))
    print(f'   {p:24s} 뷰(BOM분) {a:3d} / 라이브 {lk:3d} · 용접 {w}   '
          + ('✅' if a == lk else '★차이'))

print(f'\n   되돌리려면: {bk1} · {bk2} 참조')
print('   ⚠ 편성(④파트별 → ⑤자재소요)을 다시 돌려야 계획에 반영됩니다.')
cn.close()
