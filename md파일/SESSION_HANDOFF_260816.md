# 세션 핸드오프 — 2026-08-16 (사용자 외출 중 자율작업)

## 이번 세션에 완료한 것 (dev만, 배포 안 함 — 사용자 "로컬만 수정 나중 일괄배포")

### 1. 원가 검증 마무리 (용접/가공/운반 클러스터)
사용자 화면검증 협업으로 **8품목 완전 diff0**: AJR30100102·33796526·33796512(용접봉 use_qty·운반 오복사)·ADM72950717(운반 uph 2679쓰레기값→50)·AJR73942804·74962904·5211A23363A·23366A(용접 가공 p_item 귀속오류+3%용접봉 누락). durable _schema/GAGONG_ROUTING_MIGRATION.md. **회귀 재확인=무회귀 유지**.

### 2. 원가 전수 스윕 (분리 관문) → _schema/COST_SWEEP_260630_ANALYSIS.md
- 완제품 2476 **PASS 82.3%·오차 0.011%**. FAIL 426건=반올림(<50원)·큰갭 6건뿐(전체오차 84%). nx=분리가능 수준.
- 6건 성격 규명(제작품전개차3·드리프트1·엔진lgroup1·앵커1)=전부 엔진로직/구조 → **승인/조사 필요, 무단수정 안 함**.

### 3. 파트 마스터 작업자 편집 (screens.base.js + routers/partmaster.py)
좌(파트)=풀CRUD+편집버튼 sticky고정, 우(작업자)=리스트 통째편집(worker_save_all·실작업자 클릭토글). 실DB 왕복검증 PASS.

### 4. 공수등록 재구성 (screens.prod.js + routers/gongsu.py)
레거시라이브 제거(wrShell nxOnly)+미러∪웹 통합조회+**인원정보호출**(파트별 등록작업자 자동채움·근태편집·일괄저장). e2e 검증 PASS.

### 5. 레거시/nx 분리 인벤토리 → _schema/LEGACY_NX_SEPARATION_INVENTORY.md
백엔드 PARTNER_ERP.dbo 직독(soyo/kitting/gagong/salesplan ~30건, nx등가물 대부분존재)+프론트 wrShell 잔존3화면(partstockadj·partissue·procresult). repoint/전환 로드맵.

## 사용자 판단·확인 대기 (외출 복귀 후)
1. **원가 소액잔차 정책**: tol<10원 수용? (426건 반올림)
2. **원가 큰갭 6건**: 지금 재현 vs 편차기록 후 분리. (5211A21333E·MJU65026409·AJJ76238416 제작품전개, AJR30133707 드리프트, AJR73942805 엔진lgroup, AJR75563402 앵커)
3. **분리 백엔드 repoint** 착수 승인 (soyo/kitting 계산민감=결과대조 후 하나씩)
4. **프론트 3화면 nxOnly 전환** 승인 (재고원장 연동=민감)
5. **배포**: 이번 dev 수정분(partmaster·gongsu·gagong routing 등) 일괄배포 시점
6. **MEMORY.md 압축** 필요(20.3KB, 24.4KB 한계 근접)

## 무단으로 안 한 것 (안전규칙 준수)
- 배포 안 함 · nx 원장/bom_line 대량변경 안 함 · 재료단가(마감전용) 안 건드림 · 계산엔드포인트 repoint·재고화면 전환 안 함(미러드리프트 사일런트오류 위험) · 원가 6건 구조갭 무단수정 안 함.

## 백엔드 상태
8010 detached 재기동됨(partmaster worker_*·gongsu persons/save_bulk 반영). 로그 backend/_uvicorn_8010.log.
