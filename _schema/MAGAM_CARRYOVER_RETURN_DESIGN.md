# 마감 이월·반품 설계 (MAGAM_CARRYOVER_RETURN_DESIGN)

> 2026-09-01 사용자 확정. 브랜치 `feat/magam-edit`(dev·미배포). 매출마감(salemagam)·매입마감(purmagam) 공용.
> 코드: `common.py`(_carry_win·_open_days·_ledger_return) · `routers/salemagam.py`·`routers/purmagam.py`(carryover·opendays·return_save) · `js/core.js`(_mkMagam 모달).

## 0. 원칙 (사용자 확정 + 회계 표준)
- **재고(수불장)와 정산(마감)은 별개 축.** 협력사별 마감일(25일/말일 = `nx.CM_M_CUST_MAGAM.MAGAM_DAY`)은 **정산 컷오프**지 재고 컷오프가 아님.
- **이월 = 정산기간 재귀속(표시만).** 마감일 이후 입고분은 이번 마감에서 자동 제외(`_sale_win`)되어 차월 마감에 자동 포함 → 재고는 실일자로 이미 정확. **수불장 전표를 만들지 않는다**(안 움직인 재고를 장부상 이중이동하는 오류 방지 = 하드룰 원장 이중계상 금지).
- **반품 = 실제 재고 이동 → 수불장 전표.** 매출반품=재고 복귀(+), 매입반품=재고 출고(−). **사용자가 고른, 일마감 안 된 오픈일자**에 기록.
- 25일 마감 협력사 = **26일 입고분부터 전량 이월**(사용자 실무). 매출·매입 마감 둘 다 동일.

## 1. 백엔드
### 공용(common.py)
- `_carry_win()` = `A.MAINT_YMD > '{ym}'+mg.MAGAM_DAY AND A.MAINT_YMD <= '{ym}'+'31'` (당월 마감일 이후~말일 = 이월 대상 창).
- `_open_days(ym, months=2, domain='MAT')` = ym부터 months개월의 **일마감(월마감) 안 된** 일자(YYMMDD). 판정=`nx.period_close(domain, ptype 'D'/'M', close_flag)`. 월마감이면 그 달 통째 제외.
- `_ledger_return(cur, ymd, mat, qty_signed, cost, cust_code, remarks)` = `nx.stock_ledger` 단일 전표(MAINT_TAG='RT', 부호 그대로) + `PU_T_MAT_STOCK_WH`(Z99990/IS0001) 잔액 반영. stock_save와 동일 패턴(seq UPDLOCK·금액=|수량|×단가·부가세 10%).

### 엔드포인트(양 라우터 대칭)
| 경로 | 동작 |
|---|---|
| `GET /api/{base}/carryover?ym=&cc=` | 이월 대상. cc 지정=품목·일자별, 미지정=업체별 집계. next_ym 포함. 조회만(무전표). |
| `GET /api/{base}/opendays?ym=&months=` | 일마감 안 된 일자 목록(반품 대상일). |
| `POST /api/{base}/return_save` | `{ym,cust_code,ymd,lines:[{mat_code,qty,cost,remarks}]}` → 수불장 RT 전표. 매출=+·매입=−. **오픈일자 게이트**(_closed 재검증), 입력검증. |

## 2. 프론트(core.js _mkMagam 모달)
- 모달 열 때 carryover·opendays 병렬 로드. **이월 품목** 섹션(접이식·읽기전용·합계·"→ 차월 이월, 수불장 전표 없음" 명시) + **반품 처리** 섹션(오픈일자 드롭다운=일마감 안 된 일자·품목행 자도번 datalist·수량·단가·비고·저장).
- 반품 저장 = `/return_save` → 성공 시 알림·행 초기화. 매입/매출 부호 안내(재고 출고−/복귀+).
- 월 입력 버그 별도 수정: 네이티브 월 입력 연도-먼저 → 연도 가드 + ◀▶ 월 이동 버튼(_mkMagam 툴바).

## 3. 검증 (magam_carryreturn_testbed.py) — FLOW식 no-commit·실엔드포인트·롤백·오염0
**PASS 18 / FAIL 0**: opendays(8월초 일마감 제외·9월 포함·원장 대조 침범0) · carryover(업체별 10·대원산업2148 품목별 101행 전부 마감일25 이후·조회 무전표) · 매출반품(+5 복귀·RT전표·버킷 304→309) · 매입반품(−3 출고·RT전표·버킷 71→68) · 마감일자 반품 차단 · 입력검증(빈품목·잘못된일자).

## 4. 남은 것
- **브라우저 실동작 눈확인**(사용자) → 승인 후 배포(PR). CLAUDE.md §6.
- (검토) 매출/매입 반품이 **정산액(마감 금액)에도** 반영돼야 하는가? 현재는 수불장 전용(사용자 명시 범위). 필요 시 반품월 sale_adjust/pur_adjust 연동(중복계상 주의).

## 변경 이력
- 2026-09-01: 초안·구현·검증완(dev). 이월=귀속표시/반품=수불장전표·오픈일자. 월입력 버그 수정 동반.
