# 조달 프로파일 + BOM flag 통합 작업 마스터 (2026-08-19)

> 조달 프로파일 재설계에서 출발 → 구분→계획 반영 검증 → BOM flag 필수수정 발견·해결. 이 문서가 전체 작업·상태·복귀경로 정본.

## 1. 조달 프로파일 / 조달경로 재설계 (원래 스코프) — ✅ 거의 완료
- A1 R01 다중업체+배분% · 매입처 다중업체+비율 표시 ✅
- A2 **경로 택1(운영100%)** — 2계층(경로×업체)에서 단순화(동시 2경로 불가·2계획 불가 결정) ✅
- A3 구분컬럼·현행유지버튼 제거 · R01/R02 트리 전환 ✅
- A4 VENDOR 게이트(활성 대안경로 매입/사급 부품 업체 미지정→저장차단) ✅
- A5 R02 업체지정 = R01 발주업체·배분 모달 복제(→sourcing_profile) ✅
- B1 후보등록(조달경로 통합검토): 헤더 구분/유효일자 제거·보관함 staging·개별수정 불가 ✅
- B2 부품/SUB별 제작/매입/사급 구분 selector(→sourcing_route_line.gubun) ✅

## 2. BOM flag / 계획편성 정합 (정확반영 **필수 선행** — 발견·해결)
- D1 except_flag stale 재싱크(현행 PR, 39행/14품목, 백업 nx.bom_line_exceptbak_260819) ✅
- D2 910 과다제외 교정(soyo.py _step7_sql: item_sgroup='910' → RAC 용접봉만) ✅
- D3 규칙 정립: **생산/조달=PR(except_flag) · 원가/자재/중량=CS(cs_calc_except)** — 별도 flag, PR≠CS 가능 ✅
- D4 컷오버 정기 재싱크 파이프라인 ⏳
- D5 compose HTTP 엔드포인트 크래시 안정화(무거운 STEP6·단일워커; 직접호출은 안정) ⏳

## 3. 구분/경로 → 하류 반영 **재검증** (전 영향 도메인) ★핵심 남은 일
- C1 생산계획(compose_mat→plan_part_mat) ✅ 검증(광범위 120품목 완전일치118·불일치0)
- C2 **협력사계획(coopplan)** ⚠ 미검증 (plan_part_mat 소비하니 따라와야 하나 실측 필요)
- C3 **자동발주·수동발주** ⚠ 경로택1 재정의 후 미검증
- C4 **원가(NxCostEngine·bom real·coopquote)** ⚠ cs_calc_except 별도=구조상 무영향, 실값 실측 권장
- C5 **자재/중량정산(weight_calc·자재마감)** ⚠ CS_M_ITEM_BOM·sagub 사용, except_flag 무관하나 실측 필요

## 4. 설계 결정 (확정)
- **경로 택1**: 동일 제품 동시 2경로 운영 불가(2계획 편성 불가). R02 활성=현행 전환.
- **구분 = 후보등록서 결정 / 업체 = 조달프로파일서 지정**.
- **전개제외(except_flag) = 병행 동안 레거시 PR 미러(우리가 편집·관리 안 함) / 통합 후 구분(매입SUB 통째조달 + 사급자식)으로 흡수·은퇴.** ★우리 필드로 신설 안 함.

## 5. 배포 (전부 dev만·**승인 대기**)
- 코드: soyo.py(910)·sourcing.py(경로택1·VENDOR게이트·route_order·line/gubun)·screens.pur.js·screens.dev.js
- 데이터: nx.bom_line except_flag 재싱크(dev nx)

## 6. 컷오버 필수 (→ _schema/BOM_FLAG_SYNC_CUTOVER.md)
- 직전 flag 전량 재싱크 · except_flag←PR/cs_calc_except←CS 각각 · 검증게이트(불일치0+샘플 우리plan=레거시) · 병행중 정기싱크

## 복귀 경로 (권장 순서)
1. **C2·C3 하류 재검증**(협력사계획·발주 — 경로택1·구분 기준 레거시 대조)
2. **C4·C5 원가·자재 무영향 실측**
3. **배포**(승인 후) → 4. 컷오버 준비(D4)

관련: PROCUREMENT_ALLOCATION_RULES.md · EXCEPT_FLAG_VENDOR_RULE.md · BOM_FLAG_SYNC_CUTOVER.md
