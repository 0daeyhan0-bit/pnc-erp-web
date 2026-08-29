# -*- coding: utf-8 -*-
"""컷오버 게이트 — 마감잠금 전면 감사 (체크리스트 11번).

재고를 움직이는 쓰기 엔드포인트가 **전부** `_assert_open`(또는 `_lock_msg`/`_closed`)을
부르는지 전수 확인한다. 하나라도 빠지면 마감된 달에 전표가 들어간다.

실제 사고: 2026-08-28 TestBed 확장이 발견 — 생산파트재고조정·발주입고이 마감월 2607 을 통과했다.
          `_closed()` 가 구 잠금원(`nx.stock_close`)만 보고 있었다.

★주석은 걷어내고 센다. 안 그러면 설명문에 적힌 테이블명까지 잡혀 오탐이 난다
  (2026-08-29: `procbc/save` 의 "⑦ PR_T_STOCK_MAINT_MAT …" 설명이 잡혔다).
★GET 은 대상이 아니다(조회).

사용:  python _migration/cutover_lock_audit.py
"""
import io, os, re, glob, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
BE = os.path.join(HERE, '..', 'PNC_ERP_Web', 'backend')
os.chdir(BE)

# 재고를 움직이는 테이블 — 여기에 INSERT/UPDATE/DELETE 하면 잠금 대상
STOCK_T = ['stock_ledger', 'PU_T_STOCK_MAINT', 'SA_T_STOCK_MAINT', 'PR_T_STOCK_MAINT_MAT',
           'PU_T_MAT_STOCK_WH', 'PR_T_MAT_STOCK_WH', 'PU_T_MAT_STOCK', 'PR_T_MAT_STOCK',
           'PU_T_READY_STOCK', 'PU_T_READY_STOCK_MAINT', 'PU_T_SET_STOCK_MAINT_GAGONG',
           'SA_T_ITEM_STOCK', 'sale_dtl', 'saleout_maint', 'proc_result']
WRITE = re.compile(r"(?is)\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(?:PARTNER_ERP_TEST3\.)?nx\.(%s)\b"
                   % "|".join(re.escape(t) for t in STOCK_T))
ROUTE = re.compile(r"@router\.(get|post|put|delete)\(\s*[\"']([^\"']+)")
LOCK = re.compile(r"_assert_open|_lock_msg|_closed\s*\(")

rows = []
for f in sorted(glob.glob("routers/*.py")):
    src = io.open(f, encoding='utf-8', errors='replace').read()
    marks = [(m.start(), m.group(2), m.group(1)) for m in ROUTE.finditer(src)]
    if not marks:
        continue
    marks.append((len(src), None, None))
    for i in range(len(marks) - 1):
        a, path, meth = marks[i]
        b = marks[i + 1][0]
        body = src[a:b]
        body = "\n".join(x for x in body.split("\n") if not x.lstrip().startswith("#"))
        if meth == 'get':
            continue
        w = WRITE.findall(body)
        if not w:
            continue
        rows.append((f.replace("routers/", ""), path, bool(LOCK.search(body)),
                     sorted({t for _, t in w})))

ok = [r for r in rows if r[2]]
bad = [r for r in rows if not r[2]]
print(f"=== 재고 이동 쓰기 엔드포인트 {len(rows)}개 ===\n")
print(f"  마감잠금 있음 {len(ok)}")
print(f"  ★없음 {len(bad)}\n")
if bad:
    print("=== ★마감잠금 없는 엔드포인트 ===")
    for f, p, _, tabs in bad:
        print(f"   {f:<22} {p:<38} -> {', '.join(tabs)[:60]}")
    print("\n  ⟹ 재고가 정말 움직이는지 본문을 확인하고, 움직이면 _assert_open 을 건다.")
else:
    print("  ★전부 결선됨.")
