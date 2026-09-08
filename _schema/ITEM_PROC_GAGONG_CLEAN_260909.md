# 품목별 생산공정(PR_M_ITEM_PROC_GAGONG) 클린 단일화 — 컷오버 blocker (2026-09-09)

> 요구 = CUTOVER_MUSTDO_260909 A2 (a)레거시-fed 미러 직독 blocker.
> THE원칙(단일데이터셋)·§1-9-1(폴백금지)·생산계획 절대정확.
> 대표 지시("가") = "PR_M_ITEM_PROC_GAGONG 클린 population + 16 reads repoint + diff0. 컷오버때에도 정확하게."

## 1. 결론 — 새 테이블 불필요. R01 클린 홈 = 이미 있는 `nx.prodinfo_proc`
- 처음 후보였던 `nx.route_proc_gagong`(route_id 축)은 **route별(R02+) 전용**이고 STEP6에서 identity-safe로
  route_id>0일 때만 조인(활성 route 없으면 route_id=0). **현행 R01 생산정보의 클린 홈이 아니다.**
- **정답 = `nx.prodinfo_proc`**(prodinfo.py `_pi_proc_rows`/`_save`가 route_no=1일 때 쓰는 R01 클린 store).
  - 동일 18 데이터컬럼(소문자). SQL Server 식별자 case-insensitive → 미러의 대문자 컬럼 SELECT 그대로 동작(테이블명만 교체=repoint).
  - route_proc_gagong = R02+ / prodinfo_proc = R01. 이미 분리 설계됨(prodinfo `_pi_proc_rows` L86~94).

## 2. 현황 실측 (2026-09-09)
| 테이블 | 행 | 품목 | 성격 |
|---|---|---|---|
| 미러 `nx.PR_M_ITEM_PROC_GAGONG` | 9,899 | 4,187 | 레거시-fed(컷오버 동결=stale) |
| 클린 `nx.prodinfo_proc` | 9,902 | 4,189 | 웹 store(prodinfo가 씀)·**이미 거의 완전** |
| `nx.route_proc_gagong` | 0 | — | R02+ route별(빈=정상) |

**행단위 diff (18 데이터컬럼·(item,proc_seq)키):**
- 미러에만 = **1행** `AJR30133611`(proc_seq1) → **seed 필요**.
- 클린에만 = 4행 `AJR73364009`·`AJR73364010`·`AJR73965506`(seq1,2) = 웹 신규등록(보존·정답).
- 값 다름 = 1행 `AJR30133602` (mix_gagong NULL↔0·gagong_proc_flag '1'↔NULL) = STEP6 **미사용 컬럼**·무영향.

## 3. 생산계획(STEP6) 영향 검증 — 샌드박스 재실행 diff (실테이블 무변경)
STEP6(soyo.py:565 / planrev.py:180) plan_part_gagong 를 **미러 base vs prodinfo_proc(+seed) base** 두 방식 재실행:
```
행수: 미러 base=5,775 · prodinfo_proc(+seed) base=5,777
사라지는 계획공정 행: 0     ← seed 후 미러의 모든 계획공정 보존(손실 0)
새로 생기는 행: 2 = AJR73965506 (S5·S5-2)
```
- 유일 변화 = `AJR73965506`가 **웹에 등록된 생산정보(S5/S5-2)를 계획에서 되찾음**. 미러엔 없어 지금 계획은 이 제품 공정이 **누락**돼 있었음 → **회귀 아님·교정**(컷오버 정확성 목표에 부합).
- route_proc_gagong 비어있어 STEP6 UNION 2번째팔·CASE 무효(항상 route_id=0) → 나머지 전부 byte 동일.

## 4. 조치 (순차·각 diff0 검증)
1. **seed**: `AJR30133611` 미러→prodinfo_proc 1행(멱등: 미러 있고 클린 없는 품목만). ⟹ prodinfo_proc ⊇ 미러.
2. **repoint**: 미러 직독 전부 → `nx.prodinfo_proc` (컬럼 case-insensitive라 테이블명만 교체).
   - 직독 스왑: backflush(128·214)·gagong(271·741·750)·item(91)·kitting(126·673)·prodsheet(11곳)·ready(413)·**STEP6 base**(soyo:569·planrev:184).
   - 폴백 제거(§1-9-1): sourcing `_missing_prodinfo`(2818 미러꼬리 제거)·bom `_copy_prodinfo`(1465 else 제거)·prodinfo `_pi_proc_rows`(93 use_nx 폴백 제거).
   - 레거시-SP 리포인트맵: salesplan(89)·sales(1486) → prodinfo_proc 로 매핑(컬럼 교집합 확인).
3. **잔존 정당한 미러 참조**: prodinfo `_save`/`route_proc_gagong` INSERT(쓰기경로)·주석. 미러 read=0 목표.

## 5. 검증 게이트
- seed 후 prodinfo_proc ⊇ 미러 (미러 품목 100% 포함) 확인.
- 각 repoint: 스칼라/집계 read = 미러 대비 diff(= 위 5품목만·설명됨) 확인.
- STEP6 = 위 §3 (사라짐0·새행=AJR73965506 교정) 재확인.
- 컴파일·openapi 엔드포인트수 유지.

## 5-R. 검증 결과 (2026-09-09 · 완료)
- **seed**: `_migration/seed_prodinfo_proc_r01.py --commit` → AJR30133611 1행 보충. prodinfo_proc 9,903행/4,190품목 · **미러대비 잔여미포함 0(⊇미러)**.
- **STEP6 계획(샌드박스 재실행 diff)**: 사라지는 계획공정 **0** · 새로 생김 **2**=AJR73965506(S5·S5-2 웹등록 교정). 그 외 byte 동일.
- **집계 read diff(품목별 SUM TOT_ST 미러 vs 클린)**: 차이 = **웹추가 3품목만**(AJR73364009=183.46·AJR73364010=57.37·AJR73965506=402.08, 모두 미러=None). 예상외 변화 0.
- **기능 스모크**: backflush(COUNT·완성공정)·gagong(SUM)·prodsheet(MAX PROC_SEQ)·item(EXISTS) 전부 prodinfo_proc에서 정상.
- **repoint 전수(operational read 0)**: backflush(128·214)·gagong(271·741·750)·item(91)·kitting(126·673)·prodsheet(11)·ready(413)·**STEP6 soyo:569·planrev:184**·sales(1486)·salesplan(_REPOINT). 폴백제거: prodinfo(93)·sourcing(2818)·bom(_copy_prodinfo else). **전 백엔드+_harness FROM/JOIN 미러 read=0·쓰기=0**. 컴파일 통과.
- 커넥션: _conn/_nx 양쪽 DB=PARTNER_ERP_TEST3·nx.prodinfo_proc 해석 확인(스왑 커넥션-안전).
- 잔존 미러 문자열 = 주석 + salesplan 런타임 치환 템플릿(nx모드→prodinfo_proc) + src=live 대조경로(의도된 dev 대조·기본경로 아님).

## 6. 컷오버 정확성
컷오버 시 미러 PR_M_ITEM_PROC_GAGONG 동결되어도 **읽는 코드가 없음** → 옛값 stale 사고 원천 차단.
등록·수정은 prodinfo 화면이 `nx.prodinfo_proc`(R01)·`nx.route_proc_gagong`(R02+)에 직접. 단일 소스.
