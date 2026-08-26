# 사급차액(유상사급 실출고−실입고) 손익반영 설계 · 검증

작성 2026-08-14 · 엔진 `_harness/nx_cost_engine.py` · 백엔드 `backend/routers/cost.py` · 프론트 `js/screens.dev.js`

## 1. 개념
- **사급차액(개당) = 실출고가 − 실입고가** (거래 기반, 음수=손해).
  - 실입고가 = 그달 매입 입고(tag `9,S,C,G,H` · `MAINT_QTY>0` · `MAINT_COST>0`) 금액/수량 평균.
  - 실출고가 = 그달 유상사급 출고(tag `5` · `MAINT_COST>0`) 금액/수량 평균.
  - 원장 = `nx.PU_T_STOCK_MAINT`, 월 = `LEFT(MAINT_YMD,4)` (YYMM).
  - 제외: sgroup `210/220/910/991/992/993`, `RAC%`(용접봉) — 단 **용접링(ITEM_DESC LIKE '%용접링%')은 유지**.
  - `_sagub_diff_map(cur, ym)` (cost.py) = {부품:개당차액}. `_SAGUB_MAP_CACHE` 월별 캐시.
- **★입고가 버그 수정**: tag `C`(가공이동, cost 0)가 입고가를 희석 → `MAINT_COST>0` 필터로 방지(양쪽).

## 2. 손익 반영 규칙 (이중계상 방지가 핵심)
실원가는 사급부품을 **둘 중 하나**로 이미 계상한다:
- **(A) 직접 leaf** — 제작품 아래 매입부품을 **입고가**로 계상(실원가 재료비에 포함) → **이미 반영 → 사급차액 더하면 이중계상 → 제외.**
- **(B) 매입 SUB 안에 묻힘** — 실원가가 그 SUB를 매입가(≈사급가=출고가)로 계상하고 정지 → 개당차액 미반영 → **가산.**

→ **완제품 손익 반영액 = Σ (B묻힘 사급부품) 개당차액 × 누적소요**.
→ **손익(사급반영) = (LG판가 − 실원가) + 사급차액합**.

### 다중경로 방어 (2026-08-14 강화)
변형SUB 미정규화(`nx.bom_line`에 `-01/-20-1/-JS` 등 중복경로 잔존, 옆 세션은 **S코드 표시정규화만** 함)로
**같은 사급부품이 직접경로 + 묻힘경로 둘 다로 도달**할 수 있다 → crossed(로컬경로)만 보면 묻힘분을 이중계상.
**규칙: 어느 경로로든 un-crossed(직접계상)로 도달하면 그 부품은 사급차액에서 전면 제외**(`_sagub_hits`의 `direct` 플래그).
- 영향: 다중경로 품목만 교정(AJR30012009 −307→0, AHQ73469301 5014A20009A 제외). 깨끗한 품목 불변(AJR30078601 −1771, AJR30100101 −420).
- 보수적 선택(과다계상 방지 우선). 잔여 미세: 진짜 "직접+묻힘 혼재" 부품(희소)은 묻힘분까지 제외 → 소폭 과소. 변형SUB 구조 dedup 시 자연 해소.

## 3. 엔진 API
- `_sagub_hits(item, diffmap)` → {code:{unit,amt,qty,direct}}. 단일 walk, direct=un-crossed 도달여부.
- `sagub_sum(item, diffmap)` → Σ amt (direct 제외). 완제품 손익용.
- `sagub_nodes(item, diffmap)` → {code:{unit,qty,amt}} (direct 제외·amt≠0). 실원가 그리드 행표시용.

## 4. 화면
### 품목별 원가분석 (SCREEN.costanalysis)
- NUM[17] '사급차액' 컬럼, 손익 = `son2 = sonik + sagub`. bulk `/api/cost/nx/bulk` `{parts,ymd,ym}` → `out[it].sagub`.
### 품목 BOM관리 › 실원가 (SCREEN.unifybom, sil탭)
- **단가기준일 = 당일**(`_naeToday`, YYMMDD).
- **사급 리시빙월 선택기**(type=month, 기본=직전 완성월 `_prevYm`; 당월은 월초라 입·출고 교집합 희소).
- **가공비 옆 '사급차액(개당)' 컬럼** — 묻힌 사급부품(별도행, kind='사급차액' 또는 기존 LME동부품 행에 병합).
- **요약카드**: '사급차액' + '손익(사급반영)'. `/api/cost/sil?item&ymd&ym` → `sagub_total`·`agg.sagub`.

## 5. 검증 (2026-08-14, ym=2607)
- 앵커: AJR30078601 −1771(이젠터→대원 임베디드 MJU66930201/202), AJR30012009 0(전부 직접·다중경로), AJR30100101 −420.
- 배치 60품목: **이중계상 불변식 위반 0 · API(sil) vs 엔진 sagub 0 불일치**.
- 광범위 배치(150) → `scratchpad/batch150.txt`.
- 검증 스크립트: `scratchpad/verify_batch_final.py`(불변식+API대조), `verify_engine_sagub.py`.

## 6. 잔여 이슈
- **변형SUB 구조 dedup 미완**(옆 세션=S코드 표시만·이미 종료). `nx.bom_line` 중복경로(예 AJR30012011의 4A00114C 2경로) 잔존 → **원가(재료/가공) 미세 과다 + 사급차액 다중경로**의 공통 뿌리. 구조 dedup 시 원가 diff0 개선 + 사급차액 정밀도 동시 해소.
- 현재 사급차액은 **다중경로 direct-제외로 과다계상은 차단**(보수적). 완전 정밀은 구조 dedup 후.
