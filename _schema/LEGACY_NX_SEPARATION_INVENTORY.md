# 레거시/nx 분리 인벤토리 & 로드맵 (2026-08-16)

> 목표: 웹 ERP가 라이브 레거시 `PARTNER_ERP`(dbo) 없이 **nx(`PARTNER_ERP_TEST3.nx`) 단독**으로 동작. = 컷오버 완성·레거시 서버 은퇴.
> 원칙: 조회=nx미러(델타싱크) ∪ nx웹, 쓰기=nx웹전용([[newerp-cutover-writescreen-mirror-union]]). 프론트=wrShell `nxOnly:true`(토글 제거).
> 관문 증명 = 원가 전수스윕 82.3% PASS·0.011% 오차(_schema/COST_SWEEP_260630_ANALYSIS.md). nx 사실상 정확.

## A. 백엔드 = 진짜 분리 관문 (라이브 PARTNER_ERP.dbo 직독 → nx repoint)
`PARTNER_ERP.dbo.<T>` 직독(≠TEST3.nx)이 실제 레거시 의존. 집중 라우터: **soyo(18)·kitting(8)·gagong(3)·salesplan(1)**.

| 레거시테이블 | 읽는 곳(건) | nx 등가물 | repoint |
|---|---|---|---|
| PR_M_ITEM | 6 | ✅ nx.PR_M_ITEM | 가능(검증필요) |
| PR_T_INDI_WELD_SHEET_DTL | 4 | ✅ | 가능 |
| HR_M_CALENDAR | 4 | 확인필요 | — |
| CM_M_CUST | 3 | ✅ nx.CM_M_CUST | 가능 |
| PR_M_MODEL_BOM(+EXCEPT) | 3 | 확인필요 | — |
| CS_M_ITEM_BOM | 2 | ✅ | 가능(원가정본, 주의) |
| PR_T_INDI_WELD_SHEET | 1 | ✅류 | 가능 |
| PR_M_WORK | 1 | ✅ nx.PR_M_WORK | 가능 |
| CM_M_MASTER_DETAIL | 1 | 확인필요 | — |

- **repoint 방법**: `PARTNER_ERP.dbo.X` → `PARTNER_ERP_TEST3.nx.X`. 대부분 nx 존재.
- **★위험/주의**: 단순 치환 아님 — nx 미러가 라이브와 값 일치해야 결과 불변. **엔드포인트별 before/after 결과 대조 후** 전환(성급일반화 금지). soyo(소요량)·kitting은 계산 민감 → 개별 검증.
- **커넥션 자체**: `_conn()`가 PARTNER_ERP DB에 붙음(cross-db로 nx읽기 다수=데이터는 nx). 완전은퇴 시 커넥션도 nx 독립 DB로. (인프라 결정)

## B. 프론트 = 레거시 라이브 토글 제거 (wrShell nxOnly)
wrShell 화면 5개 중 **레거시토글 잔존 3개**:
| 화면(sid) | 위치 | 상태 |
|---|---|---|
| gongsu(공수등록) | screens.prod.js:1478 | ✅ **nxOnly 완료(2026-08-16)** — 미러∪웹 통합+인원정보호출 |
| qcerror(불량) | screens.qc.js:109 | ✅ nxOnly |
| partstockadj(생산재고조정) | screens.prod.js:653 | ⬜ 토글잔존 → nxOnly 전환대상 |
| partissue(자재출고) | screens.prod.js:695 | ⬜ 토글잔존 → nxOnly 전환대상 |
| procresult(공정별실적) | screens.prod.js:1558 | ⬜ 토글잔존 → nxOnly 전환대상 |

- **전환패턴(gongsu 검증됨)**: `nxOnly:true` + 조회를 미러∪웹 union으로 + (쓰기화면은 mirror-union). 세 화면은 [[newerp-prod-write-screens]] 재고원장 연동 = **민감**, 개별 백엔드 union 지원+왕복검증 후 전환. **미외출중 자동전환 안 함**(재고원장 위험) → 승인후.
- 그 외 qcRead(라이브조회 헬퍼)는 순수 조회 → nx미러 읽기로 바꾸면 무해.

## C. 분리 진행 순서 제언
1. **백엔드 repoint**(soyo·kitting·gagong·salesplan): 테이블별 nx 존재 확인된 것부터, 엔드포인트 결과 before/after diff0 검증하며 하나씩.
2. **프론트 3화면 nxOnly**: 백엔드 union 준비→gongsu 패턴 적용→왕복검증.
3. **HR_M_CALENDAR·PR_M_MODEL_BOM·CM_M_MASTER_DETAIL nx 적재 확인**(없으면 미러 추가).
4. 원가 6건 구조갭(COST_SWEEP_260630_ANALYSIS.md) = 재현 vs 편차기록 결정.
5. 커넥션 nx독립 전환(인프라).

## 도구
- 백엔드 스캔: `grep PARTNER_ERP.dbo routers/*.py`. 프론트: `grep wrShell/nxOnly js/*.js`.
- 원가관문: scratchpad/full_sweep.py.

## ★진행: 마스터 repoint 완료 (2026-08-17)
**안전 마스터 = nx미러 레거시와 바이트 동일 검증 완료**(행-해시 XOR폴드): HR_M_CALENDAR·CM_M_CUST·PR_M_ITEM(24114)·PR_M_WORK·PR_M_MODEL_BOM(62849)·PR_M_MODEL_BOM_EXCEPT·CS_M_ITEM_BOM(42407) 전부 컬럼·행수·내용 완전일치.
- **repoint 완료 20건**: salesplan CM_M_MASTER_DETAIL(1, before/after hash 5e95c418 일치검증) + gagong HR_M_CALENDAR(2) + kitting HR_M_CALENDAR(2) + soyo 마스터(15: CM_M_CUST·PR_M_ITEM·PR_M_WORK·PR_M_MODEL_BOM(_EXCEPT)·CS_M_ITEM_BOM). `PARTNER_ERP.dbo.X`→`PARTNER_ERP_TEST3.nx.X`. 내용 바이트동일→출력불변 보장. 스모크(salesplan1938·forecast679·sourcing6·plan4w352) 전부 200.
- **남은 레거시읽기 = 트랜잭션만**(운영컷오버 필요, nx가 운영저장소 돼야): gagong SA_T_ITEM_STOCK·PU_T_READY_STOCK·SA_T_SALE_DTL / kitting PR_T_INDI_WELD_SHEET(_DTL)×5 / coopplan SA_T_*·PU_T_*×6. = 실시간 재고/매출/용접시트라 미러최신성 전제.
- 도구 rowhash.py(내용검증)·repoint.py(일괄치환, 한글주석보호 utf-8). 배포보류(dev만).
