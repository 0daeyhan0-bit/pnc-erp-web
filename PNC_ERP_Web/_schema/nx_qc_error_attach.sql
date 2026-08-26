/* ============================================================================
   품질불량관리 첨부파일 3종 — 2026-08-26
   ----------------------------------------------------------------------------
   레거시 w_qa_input_025 와 동일하게 [첨부파일#1 / 대책서#1 / 대책서#2] 3칸.

   ★파일 실체는 DB 에 넣지 않는다.
     레거시가 blob 으로 넣은 결과 DRAWING.PR_M_DWG 9.08GB +
     QA_T_SPEC_REV_BLOB 6.63GB = 약 15.7GB 로 불어나 백업·복구 부담이 컸다.
     → 웹은 실파일을 디스크(운영 NAS = DOC_STORAGE_PATH, 기본 F:\NEW_ERP_FILES)에
       두고, DB 에는 기존 nx.doc(메타: 경로·원본파일명·크기·sha256)만 남긴다.
     → qc_error 는 그 nx.doc 의 doc_id 3개만 들고 있는다.

   다운로드는 기존 엔드포인트 재사용: /api/doc/download?src=doc&key=<doc_id>
   저장 하위경로: <DOC_STORAGE_PATH>\QC_ERROR\<qc_error.id>\<slot>_<sha12>_<원본명>
   ============================================================================ */

IF COL_LENGTH('nx.qc_error','attach_doc_id') IS NULL
    ALTER TABLE nx.qc_error ADD attach_doc_id int NULL;   -- 첨부파일#1
GO
IF COL_LENGTH('nx.qc_error','plan1_doc_id') IS NULL
    ALTER TABLE nx.qc_error ADD plan1_doc_id int NULL;    -- 대책서#1
GO
IF COL_LENGTH('nx.qc_error','plan2_doc_id') IS NULL
    ALTER TABLE nx.qc_error ADD plan2_doc_id int NULL;    -- 대책서#2
GO
