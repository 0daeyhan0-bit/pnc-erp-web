# 마감 이월·일자별 재배정 설계 (MAGAM_CARRYOVER_DESIGN)

> 2026-09-01 사용자 확정. 브랜치 `feat/magam-edit`(dev·미배포). 매출마감(salemagam)·매입마감(purmagam) 공용.
> 코드: `common.py`(_carry_win·_sale_win_ovr·_carry_win_ovr·_ensure_carry_ovr·_carry_ovr_set) · `salemagam.py`/`purmagam.py`(carryover·daylist·carry_set) · `js/core.js`(_mkMagam 모달).
> ★반품 기능은 초기 구현 후 사용자 요청으로 **제거**(2026-09-01). 이월/재배정만 유지.

## 0. 원칙
- **재고(수불장)와 정산(마감)은 별개 축.** 협력사별 마감일(25일/말일=`nx.CM_M_CUST_MAGAM.MAGAM_DAY`)은 정산 컷오프.
- **이월 = 정산 귀속·표시.** 마감일 이후 입고분은 이번 마감에서 제외 → 차월 마감 자동 포함. 25일 마감 협력사=26일부터 이월.
- **일자별 재배정(override)**: 사용자가 일자별 조회에서 특정 (품목·입고일)을 **이월↔당월** 전환. 마감 정산 금액에 즉시 반영.

## 1. 이월 재배정 모델 (교차월 이중계상 없음 · diff0)
- **테이블 `nx.magam_carry_ovr`**(kind SALE/PUR, cust_code, mat_code, maint_ymd, assign_ym, ins_user, ins_dt · PK 4키). 거래의 **귀속 마감월**을 저장.
- **유효 귀속월** = override(assign_ym) 있으면 그 값, 없으면 마감일 자동판정(natural). 모든 달의 마감이 `유효귀속월==그달`로 판정 → **override 0건이면 현행 _sale_win/_carry_win 과 완전 diff0**, PULL(당월로 당김)한 거래는 차월에서도 자동 제외(이중계상 없음).
- **성능**: 자연판정은 이미 조인된 마감일 CTE(mg.MAGAM_DAY/JUN_MAGAM_DAY)로, override는 **PK 인덱스 단일 EXISTS**만 추가. (초기 per-row 서브쿼리안은 2분+ → CTE+단일EXISTS로 <1s.)
  - `_sale_win_ovr(kind)` = (자연당월 AND NOT 밀림) OR (자연이월 AND 당김).  `_carry_win_ovr(kind)` = (자연이월 AND NOT 당김) OR (당월달력 마감일이내 AND 밀림).
- **`_carry_ovr_set`**: carry=True→차월(assign ym+1) / False→당월(assign ym). **자연상태와 같으면 override 삭제**(diff0 유지).

## 2. 엔드포인트 (매출/매입 대칭)
| 경로 | 동작 |
|---|---|
| `GET /{base}/carryover?ym=&cc=` | 이월 대상(마감일 이후분). override 반영. |
| `GET /{base}/daylist?ym=&cc=` | 일자별 조회 = 당월 달력월 입고 (품목×입고일) + `carry` 표시(1=이월). 당월+이월 한 표. carry는 마감일+override로 Python 판정(집계 안 서브쿼리 불가). |
| `POST /{base}/carry_set` | `{ym,cust_code,mat_code,maint_ymd,carry}` → 재배정 저장(이월↔당월). |
| list·detail·lines | `_sale_win()`→`_sale_win_ovr(kind)` 스왑 → 마감 집계가 override 반영. |

## 3. 프론트 (core.js _mkMagam 모달)
- **일자별 조회·이월 관리** 섹션(접이식): daylist 로드, 당월+이월 한 표. **입고일자별(기본)/품목별 토글**.
- 입고일자별: 입고일 그룹 + 품목행. **이월 행 = 주황 배경 + '이월' 배지**. **행 클릭 = 이월/이월해제**(carry_set) → 상세(마감 금액)+daylist 재로드. (권한 있고 미마감일 때만.)
- 품목별: 품번 집계 + 구분(당월/이월/일부이월) 표시(읽기). 전환은 입고일자별에서.
- 월 입력 버그: 네이티브 월 입력 연도-먼저 → 연도 가드 + ◀▶ 월 이동.

## 4. 검증 (오염0·롤백, FLOW식 no-commit)
- `magam_carryreturn_testbed.py` — 이월 목록/토글 데이터 **10/10 PASS**.
- `magam_carryovr_testbed.py` — 재배정 override **14/14 PASS**: override 0건 diff0(당월 422,096,411·이월 87,137,799 old==new) · daylist 531=이월101+당월430 · 이월→당월 +1,398,600/−1,398,600 총합불변 · 복귀=자연상태 override삭제 diff0복원 · 당월→이월 밀기 · 매입 daylist.
  · ★하네스 주의: 마감 조회가 `_conn`(라이브)로 읽으므로 override 쓰기(_nx)를 보려면 테스트에서 `_conn`도 공유 RAW로 패치(마감 쿼리 전부 PARTNER_ERP_TEST3.nx.* 라 가능). 실서버는 정상.

## 5. 남은 것
- 브라우저 실동작 눈확인(사용자)→승인 후 배포(PR). CLAUDE.md §6.
- lines(P/No 뷰)도 _sale_win_ovr 스왑됨(override 반영). 검증은 list/detail 중심으로 완료.

## 변경 이력
- 2026-09-01: 이월(정산귀속)+월버그 → 반품 추가 → 반품 제거 → 일자별 재배정(override) 추가. 최종=이월 표시/재배정.
