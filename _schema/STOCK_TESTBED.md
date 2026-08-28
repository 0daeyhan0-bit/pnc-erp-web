# 공용 재고이동 테스트베드 (STOCK_TESTBED)

작성 2026-08-27. 목적: **어떤 입출고 프로그램이든 "재고가 정확히 움직이는지"를 몇 줄로 검증**(오염0). 용접봉 백플러시 검증에 쓴 패턴을 자재/생산/영업 입출고 전반에 재활용.

- 모듈: `_harness/stock_testbed.py`
- 예제: `_harness/stock_testbed_examples.py` (용접봉 백플러시 3시연)
- 근거: `STOCK_CLOSE_HANDOFF.md` §7-2(불변식)·§7-5(재고점 소스맵) · `DO_NOT_USE_FIELDS.md` §16

---

## 1. 핵심 3요소

| 요소 | 하는 일 |
|---|---|
| `read_stock(cur, point, item, loc)` | 재고점별 잔량 통합 리더 (아래 소스맵) |
| `sandbox()` (with문) | 쓰기 트랜잭션 열고 **끝나면 무조건 롤백** → 라이브/nx 오염0 |
| `check_invariant(base,inp,out,adj,end,adj_sign)` | 불변식 `기초+입−출±조정=기말` 검증 |
| `Tracker` | 여러 (재고점·품목) 잔량 before/after 캡처·델타 |
| `seed(cur,item,qty,gpc)` | 테스트 재고를 stock_ledger에 시드 |
| `assert_delta(tracker, expected)` | 델타가 기대치와 일치하는지 |

## 2. 재고점 소스맵 (`POINT_SOURCES`, handoff §7-5)

| point | 소스 |
|---|---|
| **MAT** | 자재 현재고 = `nx.mat_stock_daily` (이동평균 일마감, §16 정본) |
| **PRODWH** | 생산창고(공정) 재고 = `SUM(stock_ledger MAT·GAGONG_PROC_CODE=loc)` — 용접봉 Q1000 등 |
| **RDY/SAG/PRD/ASY** | 준비/사급/생산/완성 = `SUM(stock_ledger STOCK_POINT·ITEM_CODE)` |
| **PARTWH** | 파트창고 재고 = `_prod_stock_map(by_part)` 이력계산(라이브∪nx) — loc=파트 |
| **FIN** | 영업완성 재고 = `nx.SA_T_ITEM_STOCK.STOCK_QTY` |

★자재(MAT)만 스냅샷(§16), 나머지는 stock_ledger 실시간. 컷오버 후 MAT도 stock_ledger 승격 예정.

## 3. 사용 패턴 (5단계)

```python
from stock_testbed import sandbox, seed, Tracker, assert_delta
with sandbox() as (nx, cur):
    seed(cur, '자재코드', 100, gpc='Q1000')        # ① 시드(기초재고)
    t = Tracker(cur).watch('생산창고','PRODWH','자재코드','Q1000')
    t.snap('before')                               # ② before
    <프로그램 동작 = 엔드포인트/함수 호출>            # ③ 동작
    t.snap('after')
    r = assert_delta(t, {'생산창고': -0.28})        # ④ 불변식/델타 검증
    print(r['ok'], r['deltas'])
# ⑤ with 종료 → 자동 롤백(오염0)
```

## 4. 활용 예 (자재/생산/영업 입출고)

| 프로그램 | 검증 |
|---|---|
| **자재출고**(matissue) | FROM파트 −, TO파트 + · net0 |
| **생산실적**(procbc) | 자재 −P4 · 용접봉 −W(생산창고) · 완성품 +ASY/PRD (2026-08-27 실증) |
| **영업출고**(saleout) | 완성재고(FIN/ASY) − · 매출 tag5 |
| **자재입고**(purchase) | 자재재고 + · 단가 |
| 공통 | **불변식 위반·이중차감·음수누수** 자동 탐지 |

## 5. 실증된 시연 (예제 파일, 전부 롤백)

1. **실시간 연속소진 → 자동차단**: 생산창고 소량 시드 후 반복생산 → 재고 실시간 tick down → 소진 시 차단. (스냅샷 모델론 불가한 영구재고의 진가)
2. **다종 용접봉 부분부족**: 2종 중 1종만 부족해도 그 종 지목해 차단.
3. **사내한정**: 외주서브 용접봉은 미수집(사급출고로 이미 −재고, 이중차감 방지).

## 6. 규칙

- **라이브 PARTNER_ERP 무접촉.** 쓰기 nx만, sandbox면 롤백.
- **엔드포인트(HTTP) 검증은 커밋됨** → sandbox 안 됨. 그땐 **근거키(WORK_ORDER/INSERT_USER_ID)로 사후정리** + 손상 시 즉시 복원 (용접봉 e2e 때 실적 복원 사례 참고). ★실 데이터(생산실적 등) 건드리는 e2e는 반드시 net0 순환+정리.
- 음수 차단은 **각 프로그램 게이트**의 책임(handoff §2-1). 이 하네스는 그게 맞게 작동하는지 **검증**만.
