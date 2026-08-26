# Dev 변경 매니페스트 (2026-08-16~17) — 정합성 점검 통과, 배포대기

> 이번 세션 dev 변경 전체. **미배포**(사용자 일괄배포 대기). 정합성 점검: 백엔드 컴파일 OK·385 엔드포인트·11 변경API 스모크 OK·프론트 3파일 균형 OK.

## A. 원가 엔진 (_harness/nx_cost_engine.py) — ★배포시 백엔드 재기동 필요(직접 import)
- `_load_hasbom()` **whitespace-fix**: `str(r[0]).strip()` 정규화. bom_header 트레일링스페이스 2건(5211A21333E·MJU65026409)로 전개누락→재료0 방지. 큰갭 3건 해결.
- **전 품목 재검증**: PASS 82.5%, 회귀0. 나머지 큰갭 1(AJR30133707 드리프트)만.

## B. 원가 데이터 수정 (nx DB, 이미 반영)
- proc_weld use_qty 2행(AJR30100102·33796526 용접봉)·운반 uph(AJR33796512·ADM72950717 2679→50)·용접 proc 리매핑(AJR73942804)·lgroup ''→'E'(AJR73942805)·proc_weld except+use_qty(AJR75563402 한국용접). 백업 scratchpad/*.json.

## C. 레거시/nx 분리 — 백엔드 (routers/)
- **마스터 20건 repoint** `PARTNER_ERP.dbo.X`→`PARTNER_ERP_TEST3.nx.X`: salesplan(CM_M_MASTER_DETAIL) gagong·kitting(HR_M_CALENDAR) soyo(CM_M_CUST·PR_M_ITEM·PR_M_WORK·PR_M_MODEL_BOM(_EXCEPT)·CS_M_ITEM_BOM). 7마스터 내용 바이트동일 검증→출력불변.
- **prodwrite.py union**: stockmaint/matissue/procreg list = 웹∪미러이력(미러 ID=null 읽기전용).
- 트랜잭션읽기(SA_T/PU_T/WELD)=**라이브 유지**(병행 1:1검증, 컷오버시 전환).

## D. 레거시/nx 분리 — 프론트 (js/)
- **core.js**: wrCrud 라벨 "라이브"→"📁이력"(공용, 하위호환).
- **screens.prod.js**: partstockadj·partissue·procresult `nxOnly:true`+sub정정. gongsu 재구성(nxOnly union+인원정보호출).
- **screens.base.js**: 파트마스터 작업자 통째편집(worker_save_all)+편집버튼 sticky.

## E. 신규 기능 (백엔드+프론트)
- **partmaster.py**: worker_save/worker_save_all/worker_delete (파트별 작업자 CRUD).
- **gongsu.py**: 통합list(미러∪웹)·persons(인원정보호출)·save_bulk.

## 배포 절차 (승인 후)
1. deploy.ps1 (백엔드 트리 세트미러) — routers/·nx_cost_engine.py(_harness) 포함 확인
2. 프론트 index.html ?v= 갱신됨(core/screens.base/screens.prod=260817sepnx 등)
3. 184 재기동 → 엔드포인트 385 확인 → 변경 API fetch 검증
4. ★원가엔진은 _harness 직접import라 백엔드 재기동으로 반영

## 미배포/보류 상태 재확인
- 전부 dev(178 로컬)만. 라이브(184) 미반영. 사용자 명시 허락시 일괄배포.
