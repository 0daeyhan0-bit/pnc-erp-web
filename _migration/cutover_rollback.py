# -*- coding: utf-8 -*-
"""컷오버 롤백 도구 — 되돌릴 때 **무엇을 잃는지** 먼저 보여준다.

정본 = `_schema/CUTOVER_CHECKLIST.md` "16. 롤백 계획"

왜 이게 필요한가
  컷오버는 코드 flip(라이브 dbo 읽기 → nx 읽기)만이 아니다. 그 순간부터 **웹 입력이 nx 에만 쌓인다.**
  레거시에는 그 데이터가 없다. 그래서 "그냥 코드만 되돌리면 된다" 가 성립하지 않는다.
  ⟹ 롤백 판단의 전제는 **"지금 되돌리면 몇 건이 사라지는가"** 다. 그 수를 모르면 결정할 수 없다.

무엇을 하나
  --snapshot   컷오버 직전 상태를 파일로 남긴다(테이블별 행수 + 최대 키).
  --diff       스냅샷 이후 nx 에 들어온 쓰기를 센다 = **롤백 시 유실 후보**.
  --tables     대상 테이블 목록만 출력.

무엇을 안 하나
  **자동 복구는 하지 않는다.** 데이터 되돌리기는 사람이 판단하고 승인해야 하는 일이다
  (하드룰: 원장 대량삭제 금지 · 배포는 명시 허락때만).
  이 도구는 **판단 재료**를 만들 뿐이다.

사용
  python _migration/cutover_rollback.py --snapshot     # 컷오버 직전에 1회
  python _migration/cutover_rollback.py --diff         # 문제 생겼을 때
"""
import io, sys, os, json, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'PNC_ERP_Web', 'backend'))
from common import _nx

SNAP = os.path.join(HERE, 'cutover_rollback_snapshot.json')

# 웹이 실제로 쓰는 nx 테이블 (routers 의 INSERT/UPDATE/DELETE 실측 상위 + 트랜잭션 계열).
# 조회 전용 미러는 뺐다 — 되돌려도 잃을 게 없다.
TABLES = [
    ("stock_ledger", "MAINT_YMD"),          # 단일원장 — 웹 재고 이동 전부
    ("stock_snapshot", "period"),           # 확정 마감 스냅샷
    ("period_close", "period"),             # 마감 잠금
    ("sale_dtl", "sale_ymd"),               # 출하실적
    ("saleout_maint", "maint_ymd"),         # 판매출고
    ("proc_result", "PROD_YMD"),            # 공정별 생산실적
    ("price_item", "apply_ymd"),            # ★단가 마스터(2026-08-29 승격)
    ("item", None),                         # 품목 정본
    ("bom_line", None), ("model_bom", None), ("routing", None), ("proc_weld", None),
    ("sourcing_route", None), ("sourcing_route_line", None), ("sourcing_profile", None),
    ("coop_quote", None), ("coop_quote_v2", None),
    ("PU_T_STOCK_MAINT", "MAINT_YMD"),      # 자재수불(웹 쓰기 겸용)
    ("SA_T_STOCK_MAINT", "MAINT_YMD"),      # 완성 이동(웹 쓰기 겸용)
    ("PU_T_MAT_STOCK_WH", None),
    ("PR_T_STOCK_MAINT_MAT", "MAINT_YMD"),
]


def measure(cur):
    out = {}
    for t, ycol in TABLES:
        try:
            cur.execute(f"SELECT COUNT_BIG(*) FROM nx.{t}")
            n = int(cur.fetchone()[0] or 0)
            mx = None
            if ycol:
                cur.execute(f"SELECT MAX({ycol}) FROM nx.{t}")
                r = cur.fetchone()
                mx = str(r[0]).strip() if r and r[0] is not None else None
            out[t] = {"rows": n, "max": mx}
        except Exception as e:
            out[t] = {"error": str(e)[:80]}
    return out


def main():
    a = sys.argv
    if '--tables' in a:
        print(f"대상 {len(TABLES)}개")
        for t, y in TABLES:
            print(f"   nx.{t:<28} 일자컬럼={y or '-'}")
        return

    cn = _nx(); cur = cn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if '--snapshot' in a:
        cur.execute("SELECT FORMAT(GETDATE(),'yyMMdd')")
        d = {"taken_at": now, "ymd": cur.fetchone()[0], "tables": measure(cur)}
        io.open(SNAP, 'w', encoding='utf-8').write(json.dumps(d, ensure_ascii=False, indent=2))
        print(f"스냅샷 저장 {SNAP}")
        print(f"   시각 {now} · 테이블 {len(d['tables'])}개")
        for t, v in d["tables"].items():
            if "error" in v:
                print(f"   ★{t:<28} {v['error']}")
            else:
                print(f"    {t:<28} {v['rows']:>10,}행  최대 {v['max'] or '-'}")
        print("\n★이 파일을 컷오버 당일 보관할 것. --diff 가 이걸 기준으로 센다.")
        cn.close(); return

    if '--diff' in a:
        if not os.path.exists(SNAP):
            print("★스냅샷이 없다. 먼저 --snapshot 을 돌렸어야 한다."); sys.exit(1)
        base = json.loads(io.open(SNAP, encoding='utf-8').read())
        cur_state = measure(cur)
        print(f"기준 스냅샷 {base['taken_at']}  →  현재 {now}\n")
        print(f"{'테이블':<30}{'스냅샷':>12}{'현재':>12}{'증감':>12}")
        tot = 0
        for t, v in cur_state.items():
            b = base["tables"].get(t, {})
            if "error" in v or "error" in b:
                print(f"   {t:<27}{'(조회실패)':>36}"); continue
            d = v["rows"] - b["rows"]
            tot += max(d, 0)
            mark = "  ★" if d else ""
            print(f"   {t:<27}{b['rows']:>12,}{v['rows']:>12,}{d:>+12,}{mark}")
        print(f"\n★롤백하면 사라질 후보 = **{tot:,}행** (컷오버 이후 nx 에만 쌓인 분)")
        print("  이 데이터는 레거시에 없다. 되돌리기 전에 **어디로 옮길지** 먼저 정해야 한다.")
        print("  자동 복구는 하지 않는다 — 사람이 판단하고 승인할 일이다.")
        cn.close(); return

    print(__doc__)


if __name__ == "__main__":
    main()
