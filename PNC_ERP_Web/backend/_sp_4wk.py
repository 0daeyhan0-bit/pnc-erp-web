# -*- coding: utf-8 -*-
# 레거시 정본 SP_PR_4주간_가공계획현황_250703 본문 인라인(EXEC 권한없어 SELECT 재현). 자동생성.
SQL_4WK = r'''WITH TEMP_PLAN (PLAN_YMD, WORK_ORDER, SPLIT_WORK_ORDER, C_ITEM_CODE, WORK_CODE, USE_QTY, MODEL_NO, LINE_NO, CLS_YMD, AM_PM, OUTPUT_HM, 

							LOT_QTY, PLAN_QTY, REMARKS1, REMARKS2, EXCEL_SEQ, TOOLS_DESC, FROM_SEQ, TO_SEQ, CHANGE_DAY, CR_FLAG, 

							ORG_PLAN_YMD, ORG_OUTPUT_HM, ITEM_ORG_PLAN_YMD, ITEM_ORG_OUTPUT_HM, AVG_PLAN_FLAG, PROD_AVG_FLAG, PROD_TAG)

		as (

				SELECT T.PART_PLAN_YMD, A.WORK_ORDER, A.SPLIT_WORK_ORDER, A.C_ITEM_CODE, A.WORK_CODE, A.USE_QTY, A.MODEL_NO, A.LINE_NO, A.CLS_YMD, 'A' AM_PM, T.PART_OUTPUT_HM, 

						A.LOT_QTY, A.PLAN_QTY, A.REMARKS1, A.REMARKS2, A.EXCEL_SEQ, A.TOOLS_DESC, A.FROM_SEQ, A.TO_SEQ, A.CHANGE_DAY, A.CR_FLAG, 

						A.ORG_PLAN_YMD, A.ORG_OUTPUT_HM, A.ITEM_ORG_PLAN_YMD, A.ITEM_ORG_OUTPUT_HM, A.AVG_PLAN_FLAG, A.PROD_AVG_FLAG, A.PROD_TAG

				FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_PART_DTL_FOR_CUST t WITH (NOLOCK)

				join PARTNER_ERP_TEST3.nx.pr_t_plan_item_dtl a WITH (NOLOCK)   on a.plan_ymd = t.plan_ymd

																		and a.work_order = t.work_order

																		and a.split_work_order = t.split_work_order

																		and a.c_item_code = t.item_code

				join PARTNER_ERP_TEST3.nx.pr_m_item c  WITH (NOLOCK)				on a.c_item_code	= c.item_code

			  WHERE a.c_item_code			like @@ITEM@@

				 and t.proc_seq				= 1

				 and t.gc_gubun				= 'P'			/*생산파트*/



				UNION ALL



				SELECT T.PART_PLAN_YMD, A.WORK_ORDER, A.WORK_ORDER, A.ITEM_CODE, C.WORK_CODE, 1 USE_QTY, '' MODEL_NO, A.LINE_NO, '' CLS_YMD, 'A' AM_PM, T.PART_OUTPUT_HM, 

						A.PLAN_QTY, A.PLAN_QTY, '' REMARKS1, '' REMARKS2, 0 EXCEL_SEQ, '' TOOLS_DESC, 0 FROM_SEQ, 0 TO_SEQ, '0' CHANGE_DAY, '' CR_FLAG, 

						A.PLAN_YMD, A.OUTPUT_HM, A.PLAN_YMD, A.OUTPUT_HM, '0' AVG_PLAN_FLAG, '0' PROD_AVG_FLAG, A.PROD_TAG

				FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_PART_DTL_FOR_CUST t WITH (NOLOCK)

				join PARTNER_ERP_TEST3.nx.PR_T_PLAN_INPUT a  WITH (NOLOCK)     on a.plan_ymd = t.plan_ymd

																		and a.work_order = t.work_order

																		and a.work_order = t.split_work_order

																		and a.item_code = t.item_code

				join PARTNER_ERP_TEST3.nx.pr_m_item c WITH (NOLOCK) 				on a.item_code	= c.item_code

			  WHERE a.item_code		like @@ITEM@@

				 and t.proc_seq				= 1

				 and t.gc_gubun				= 'P'			/*생산파트*/



				UNION ALL



				SELECT a.PLAN_YMD, A.WORK_ORDER, A.SPLIT_WORK_ORDER, A.C_ITEM_CODE, A.WORK_CODE, A.USE_QTY, A.MODEL_NO, A.LINE_NO, A.CLS_YMD, 'A' AM_PM, a.OUTPUT_HM, 

						A.LOT_QTY, A.PLAN_QTY, A.REMARKS1, A.REMARKS2, A.EXCEL_SEQ, A.TOOLS_DESC, A.FROM_SEQ, A.TO_SEQ, A.CHANGE_DAY, A.CR_FLAG, 

						A.ORG_PLAN_YMD, A.ORG_OUTPUT_HM, A.ITEM_ORG_PLAN_YMD, A.ITEM_ORG_OUTPUT_HM, A.AVG_PLAN_FLAG, A.PROD_AVG_FLAG, A.PROD_TAG

				FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_ITEM_DTL a WITH (NOLOCK)

				join PARTNER_ERP_TEST3.nx.pr_m_item c  WITH (NOLOCK) on a.C_ITEM_CODE	= c.item_code

				WHERE A.PLAN_YMD		>= @@FROM@@

				  AND C.IN_CUST_CODE > ''



				UNION ALL



				SELECT a.PLAN_YMD, A.WORK_ORDER, A.WORK_ORDER, A.ITEM_CODE, C.WORK_CODE, 1 USE_QTY, '' MODEL_NO, A.LINE_NO, '' CLS_YMD, 'A' AM_PM, a.OUTPUT_HM, 

						A.PLAN_QTY, A.PLAN_QTY, '' REMARKS1, '' REMARKS2, 0 EXCEL_SEQ, '' TOOLS_DESC, 0 FROM_SEQ, 0 TO_SEQ, '0' CHANGE_DAY, '' CR_FLAG, 

						A.PLAN_YMD, A.OUTPUT_HM, A.PLAN_YMD, A.OUTPUT_HM, '0' AVG_PLAN_FLAG, '0' PROD_AVG_FLAG, A.PROD_TAG

				FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_INPUT a WITH (NOLOCK)

				join PARTNER_ERP_TEST3.nx.pr_m_item c  WITH (NOLOCK) on a.ITEM_CODE	= c.item_code

				WHERE A.PLAN_YMD		>= @@FROM@@

				  AND C.IN_CUST_CODE > ''



				UNION ALL



				SELECT a.PLAN_YMD, A.WORK_ORDER, A.WORK_ORDER, A.ITEM_CODE, C.WORK_CODE, 1 USE_QTY, '' MODEL_NO, A.LINE_NO, '' CLS_YMD, 'A' AM_PM, a.OUTPUT_HM, 

						A.PLAN_QTY, A.PLAN_QTY, '' REMARKS1, '' REMARKS2, 0 EXCEL_SEQ, '' TOOLS_DESC, 0 FROM_SEQ, 0 TO_SEQ, '0' CHANGE_DAY, '' CR_FLAG, 

						A.PLAN_YMD, A.OUTPUT_HM, A.PLAN_YMD, A.OUTPUT_HM, '0' AVG_PLAN_FLAG, '0' PROD_AVG_FLAG, A.PROD_TAG

				FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_INPUT a WITH (NOLOCK)

				join PARTNER_ERP_TEST3.nx.pr_m_item c  WITH (NOLOCK) on a.ITEM_CODE	= c.item_code

				WHERE A.PLAN_YMD		>= @@FROM@@

				  AND C.WORK_CODE = 'P2'

		),





		CTE_BOM(level_no, item_code, mat_code, mat_spec, work_code, in_cust_code, mat_work_center_code, cum_use_qty, cum_in_cust_code, mat_flag)

		AS

			(

				/*앵커멤버-생산계획*/

				select 1 as level_no, *

				  from (

							SELECT distinct

									a.c_item_code as item_code,

									a.c_item_code as mat_code,

									c.item_spec as mat_spec,

									c.work_code,

									c.in_cust_code,

									case when c.work_code > '' then c.work_code else c.in_cust_code end as mat_work_center_code,

									convert(decimal(18,5),1) as cum_use_qty,

									convert(varchar(500),'||' + case when c.work_code > '' then c.work_code else c.in_cust_code end + '|') as cum_in_cust_code,

									isnull((select '2' from PARTNER_ERP_TEST3.nx.pr_m_mat where mat_code = a.c_item_code),'1') as mat_flag

							FROM TEMP_PLAN a

							join PARTNER_ERP_TEST3.nx.pr_m_item c 				on a.c_item_code	= c.item_code

							WHERE a.plan_ymd 		<= convert(varchar,convert(datetime,@@TO@@) + 10,12)

						) tt

				

				union all

		

				/*재귀멤버-BOM하위추출*/

				SELECT cb.level_no +1,

						cb.item_code,

						b.mat_code,

						m.item_spec as mat_spec,

						m.work_code,

						m.in_cust_code,

						case when m.work_code > '' then m.work_code else m.in_cust_code end as mat_work_center_code,

						convert(decimal(18,5),case when cb.cum_use_qty = 0 then 0

												else CONVERT(decimal(18,5), cb.cum_use_qty * b.use_qty) end) cum_use_qty,

						convert(varchar(500),cb.cum_in_cust_code + '|' + case when m.work_code > '' then m.work_code else m.in_cust_code end + '|') as cum_in_cust_code,

						isnull((select '2' from PARTNER_ERP_TEST3.nx.pr_m_mat where mat_code = b.mat_code),'1') as mat_flag

				FROM CTE_BOM cb

				join PARTNER_ERP_TEST3.nx.pr_m_item_bom b			on cb.mat_code	= b.item_code

				join PARTNER_ERP_TEST3.nx.pr_m_item m 				on b.mat_code 	= m.item_code

				WHERE isnull(b.EXCEPT_FLAG,'0') = '0'

				  and cb.level_no < 10

			)	



	SELECT T.*, (select work_desc from PARTNER_ERP_TEST3.nx.pr_m_work where work_code=T.mat_work_code) as mat_work_desc FROM (

			/*영업계획*/

			SELECT '1' as data_gubun,

					m.work_code as mat_work_code,

					a.line_no,

					a.work_order,

					a.split_work_order,

					max(a.model_no) as model_no,

					'1' as item_gubun,		/*1=세트입고, 2=세트입고제외*/

					a.output_hm,

					a.c_item_code as c_item_code,

					isnull((case when c.in_cust_code>'' then (select cust_desc from PARTNER_ERP_TEST3.nx.cm_m_cust WITH (NOLOCK) where cust_code=c.in_cust_code)

																	else (select top 1 b1.gagong_proc_desc from PARTNER_ERP_TEST3.nx.pr_m_item_proc_gagong a1

																														join PARTNER_ERP_TEST3.nx.pr_m_proc_gagong b1 on a1.gagong_proc_code = b1.gagong_proc_code

																														where a1.item_code = a.c_item_code

																														order by a1.proc_seq) end),'000') as work_center,

					c.work_code as work_code,

					c.in_cust_code as in_cust_code,

					(case when c.in_cust_code>'' then c.in_cust_code else c.work_code end) as work_center_code,

					min(a.plan_ymd) as plan_ymd,

					max(a.lot_qty) as lot_qty,

					sum(ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100)) as plan_qty,

					isnull(max(a.use_qty),1) as use_qty,

					isnull(max(c.prod_rate),100) as prod_rate,

					sum(case when a.plan_ymd <= @@FROM@@																then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_01,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 1, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_02,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 2, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_03,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 3, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_04,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 4, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_05,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 5, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_06,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 6, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_07,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 7, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_08,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 8, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_09,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 9, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_10,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 10, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_11,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 11, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_12,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 12, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_13,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 13, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_14,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 14, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_15,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 15, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_16,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 16, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_17,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 17, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_18,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 18, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_19,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 19, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_20,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 20, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_21,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 21, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_22,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 22, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_23,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 23, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_24,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 24, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_25,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 25, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_26,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 26, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_27,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 27, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_28,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 28, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_29,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 29, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_30,

					sum(case a.plan_ymd when convert(varchar, convert(datetime, @@FROM@@, 12) + 30, 12) then ceiling(convert(float,a.plan_qty) * isnull(a.use_qty,1) * isnull(c.prod_rate,100) / 100) else 0 end) as plan_qty_31,

					max(a.change_day) as change_day,

					isnull(max(a.remarks2),'') as remarks2,

					max(a.org_plan_ymd) as org_plan_ymd,

					max(a.org_output_hm) as org_output_hm,

					min(a.excel_seq) as excel_seq

			FROM TEMP_PLAN 	a

			join (select distinct work_code, item_code

					  from CTE_BOM

					 where item_code			like @@ITEM@@

						and mat_code			like @@MAT@@

						and work_code			= @@WC@@

						and in_cust_code		= ''

						and charindex('||' + mat_work_center_code + '||', cum_in_cust_code) = 0

						and mat_flag		= @@FLAG@@

					group by item_code, mat_code, mat_spec, work_code, in_cust_code, mat_work_center_code) m on a.c_item_code = m.item_code

			join PARTNER_ERP_TEST3.nx.pr_m_item c 				on a.c_item_code	= c.item_code

			where a.plan_ymd 		<= @@TO@@

			group by m.work_code, a.line_no, a.work_order, a.split_work_order, a.output_hm, a.c_item_code, c.work_code, c.in_cust_code

		) T

OPTION (MAXRECURSION 0)'''
