# -*- coding: utf-8 -*-
"""nx 재료비 엔진 (durable) — nx 테이블만으로 실원가용 재료비 재현.
규칙(오라클 역설계):
  - top에서 bom_line(cs_calc_except=0) 전개
  - 자식이 매입가 보유(매입완성/구매품) → 매입단가(기준일 as-of, 지정 매입처 in_cust) × 누적qty, 전개중단
  - 자식이 자체 BOM 보유(사내 sub) → 재귀전개
  - 동파이프(사내소재) → 후속(LME/중량) 처리 TODO
게이트: material(item,ymd) == oracle.sil['jae'] (실원가 재료)."""
import sys, io, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'New_ERP'))  # Projects\New_ERP
import db_client, pyodbc

def _nx():
    return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
        f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')

class NxCostEngine:
    def __init__(self, cur=None):
        self.own = cur is None
        self.cn = _nx() if self.own else None
        self.cur = self.cn.cursor() if self.own else cur
        self._hdr={}; self._lines={}; self._pur={}; self._item={}; self._hasbom=None
        self._matc={}; self._gagc={}; self._lmec={}   # 단위(mult=1) 결과 메모이제이션 (성능)

    def close(self):
        if self.own and self.cn: self.cn.close()

    def reconnect(self):
        """커넥션만 재연결(메모캐시 _item/_lines/_pur/_matc/_gagc/_hdr/_top_lg 전부 보존).
           FastAPI 스레드풀 전환·유휴로 pyodbc 커넥션이 죽었을 때(10054) 엔진을 통째 버리는 fresh 재생성(빈캐시 재적재=수초) 대신
           커넥션만 갈아끼워 회복 → 값 불변·속도만 회복. pyodbc 풀링으로 재연결 자체는 near-instant."""
        if not self.own: return   # 외부 커서 주입 모드는 재연결 불가(호출측 책임)
        try:
            if self.cn: self.cn.close()
        except Exception: pass
        self.cn = _nx(); self.cur = self.cn.cursor()

    def alive(self):
        """커넥션 헬스체크. 살아있으면 True, 죽었으면 reconnect 후 False(=재연결됨) 반환. 캐시는 항상 보존."""
        try:
            self.cur.execute("SELECT 1"); self.cur.fetchone(); return True
        except Exception:
            try: self.reconnect()
            except Exception: pass
            return False

    def _prime_caches(self, item):
        """★성능: 서브트리 전 노드의 item/routing/proc_weld/bom_header를 **서버측 CTE-JOIN**으로 일괄 로드(클라 IN(N)은 드라이버 오버헤드 ~520ms/쿼리라 회피).
           채우는 캐시(_item·_pc·_rc·_wlc·_hdr)는 per-node 메서드와 동일 구조·동일 값 → 결과 불변(속도만).
           미프라임 노드는 기존 per-node 쿼리로 폴백(정확성 무손상). _reset 시 새 엔진=재프라임."""
        # ★lgroup-fix(2026-08-13): 상위품목 lgroup 확정(SP @LS_ITEM_GROUP=최상위품목 ITEM_LGROUP). proc_amt가 이걸로 공정필터.
        #   전 public 진입(silwon/naewon/*_nodes/*_grid)이 여기로 옴. top_lg 바뀌면 가공비 결과캐시(top_lg 의존) 무효화(bulk 엔진재사용 안전).
        _lg=self._load_item(item).get('lgroup','')
        if getattr(self,'_top_lg',None)!=_lg:
            self._top_lg=_lg; self._gagc={}; self._gagcn={}
        return   # ★비활성화(2026-08-04): 다중경로/SUB 구조에서 캐시 프라임이 미묘한 중복 유발(43 baseline 59 이탈) → 정확성 위해 OFF.
                 #   속도 최적화는 nx.routing 인덱스(ix_routing_item)로 대체(값 불변·seek). 아래 프라임 로직은 보존(추후 dedup 완성 후 재활성).
        if not hasattr(self, '_primed'): self._primed = set()
        if item in self._primed: return
        self._primed.add(item)
        if not hasattr(self, '_wlc'): self._wlc = {}
        if not hasattr(self, '_pc'): self._pc = {}
        if not hasattr(self, '_rc'): self._rc = {}
        # 서브트리(bom_line 재귀) + 용접봉(RAC) 코드 = allc. 각 테이블 CTE-JOIN(서버측)로 1쿼리씩.
        CTE = ("WITH t AS (SELECT CAST(? AS varchar(30)) c "
               "UNION ALL SELECT CAST(bl.child_item AS varchar(30)) FROM t "
               "JOIN nx.bom_header h ON h.item_code=t.c JOIN nx.bom_line bl ON bl.bom_id=h.bom_id), "
               "allc AS (SELECT c FROM t UNION SELECT CAST(pw.weld_item AS varchar(30)) FROM nx.proc_weld pw JOIN t ON pw.parent_item=t.c) ")
        TAIL = " OPTION(MAXRECURSION 60)"
        try:
            self.cur.execute(CTE + "SELECT DISTINCT c FROM allc" + TAIL, item)
            codes = set(str(r[0]).strip() for r in self.cur.fetchall() if str(r[0]).strip())
            if not codes: return
            # proc_weld
            self.cur.execute(CTE + """SELECT pw.parent_item, pw.weld_item, ISNULL(pw.use_qty,0), ISNULL(pw.cs_calc_except,0),
                ISNULL(pw.from_ymd,''), ISNULL(pw.to_ymd,''), ISNULL(pw.lme_except,0)
                FROM nx.proc_weld pw JOIN allc s ON pw.parent_item=s.c ORDER BY pw.parent_item, pw.weld_item""" + TAIL, item)
            for r in self.cur.fetchall():
                self._wlc.setdefault(str(r[0]).strip(), []).append(
                    (str(r[1]).strip(), float(r[2] or 0), bool(r[3]), str(r[4] or ''), str(r[5] or ''), bool(r[6])))
            for c in codes:
                if c not in self._wlc: self._wlc[c] = []
            # item
            self.cur.execute(CTE + """SELECT i.item_code, ISNULL(i.in_cust,''), ISNULL(i.make_type,''), ISNULL(i.cost_gubun,''),
                ISNULL(i.metal_gubun,''), ISNULL(i.diam,0), ISNULL(i.thick,0), ISNULL(i.net_weight,0), ISNULL(i.has_gagong,0),
                ISNULL(i.silver_flag,0), ISNULL(i.unit,''), ISNULL(i.lgroup,'') FROM nx.item i JOIN allc s ON i.item_code=s.c""" + TAIL, item)
            for r in self.cur.fetchall():
                self._item[str(r[0]).strip()] = {'in_cust': r[1].strip(), 'make_type': r[2].strip(), 'cost_gubun': r[3].strip(),
                    'metal': r[4].strip(), 'diam': float(r[5] or 0), 'thick': float(r[6] or 0), 'wt': float(r[7] or 0),
                    'has_gagong': bool(r[8]), 'silver': bool(r[9]), 'unit': r[10].strip(), 'lgroup': r[11].strip()}
            # routing → _pc(공정, 91/92/93/98/99 제외) + _rc(91/92/93)
            for c in codes: self._pc[c] = []
            self.cur.execute(CTE + """SELECT r.item_code, r.proc_code, ISNULL(r.work_qty,0), ISNULL(r.prod_uph,0), ISNULL(r.calc_gubun,''), ISNULL(r.p_item,'')
                FROM nx.routing r JOIN allc s ON r.item_code=s.c""" + TAIL, item)
            for r in self.cur.fetchall():
                code = str(r[0]).strip(); proc = str(r[1]); wq = float(r[2] or 0); uph = float(r[3] or 0)
                cg = str(r[4] or '').strip(); pit = str(r[5] or '').strip()
                if proc in ('91', '92', '93'):
                    self._rc.setdefault((code, proc), []).append((uph, wq, pit))
                elif proc not in ('98', '99'):
                    self._pc.setdefault(code, []).append((proc, wq, uph, cg, pit))
            for c in codes:
                for pc in ('91', '92', '93'):
                    if (c, pc) not in self._rc: self._rc[(c, pc)] = []
            # bom_header → _hdr (max version)
            best = {}
            self.cur.execute(CTE + "SELECT bh.item_code, bh.bom_id, ISNULL(bh.version,1) FROM nx.bom_header bh JOIN allc s ON bh.item_code=s.c" + TAIL, item)
            for r in self.cur.fetchall():
                code = str(r[0]).strip(); ver = int(r[2] or 1)
                if code not in best or ver > best[code][0]: best[code] = (ver, r[1])
            for c in codes:
                self._hdr[c] = best[c][1] if c in best else None
        except Exception:
            return   # CTE 실패(순환 등) → 프라임 스킵, per-node 폴백(정확성 무손상)

    def warm_all(self):
        """★글로벌 벌크로드(opt-in, 2026-08-23): 구조 캐시(_item·_hdr·_lines·_pc·_rc·_wlc)를 전 테이블 1회씩 예열 →
        재귀가 노드별 DB 왕복 없이 순수 in-memory(N+1 제거). lazy와 **동일 키·필드·필터·정규화**로 채워 결과 불변.
        ★옛 per-item 예열(L56 비활성)은 _item에 sgroup 누락(11필드)으로 이탈했음 → 여기선 12필드 완전복제.
        가격(_pm/_pms/_pur/_lg/_fxc/_lr)은 float키(diam/thick) 불일치 위험 회피 위해 lazy 유지(배치 내 자동예열).
        호출 안 하면 엔진 무변경(검증정확도 유지). 누락 키는 lazy 폴백. ★적용 전 diff0 검증 필수."""
        c = self.cur
        for a in ('_item', '_hdr', '_lines', '_pc', '_rc', '_wlc'):
            if not hasattr(self, a): setattr(self, a, {})
        # item — lazy _load_item과 동일 12필드(sgroup 포함)
        c.execute("""SELECT item_code,ISNULL(in_cust,''),ISNULL(make_type,''),ISNULL(cost_gubun,''),
            ISNULL(metal_gubun,''),ISNULL(diam,0),ISNULL(thick,0),ISNULL(net_weight,0),ISNULL(has_gagong,0),
            ISNULL(silver_flag,0),ISNULL(unit,''),ISNULL(lgroup,''),ISNULL(sgroup,'') FROM nx.item""")
        for r in c.fetchall():
            self._item[str(r[0]).strip()] = {'in_cust': r[1].strip(), 'make_type': r[2].strip(), 'cost_gubun': r[3].strip(),
                'metal': r[4].strip(), 'diam': float(r[5] or 0), 'thick': float(r[6] or 0), 'wt': float(r[7] or 0),
                'has_gagong': bool(r[8]), 'silver': bool(r[9]), 'unit': r[10].strip(), 'lgroup': r[11].strip(), 'sgroup': r[12].strip()}
        # bom_header → _hdr(품목별 최대 version), 없는 품목=None(리프 bom_id 조회 제거)
        best = {}
        c.execute("SELECT item_code,bom_id,ISNULL(version,1) FROM nx.bom_header")
        for r in c.fetchall():
            code = str(r[0]).strip(); ver = int(r[2] or 1)
            if code not in best or ver > best[code][0]: best[code] = (ver, r[1])
        for code in best: self._hdr[code] = best[code][1]
        for it in self._item:
            if it not in self._hdr: self._hdr[it] = None
        # bom_line → _lines(bom_id별, RAC 제외·seq 순) = lazy lines()와 동일
        c.execute("SELECT bom_id,child_item,qty,cs_calc_except,from_ymd,to_ymd,ISNULL(lme_except,0) FROM nx.bom_line WHERE child_item NOT LIKE 'RAC%' ORDER BY bom_id,seq")
        for r in c.fetchall():
            self._lines.setdefault(r[0], []).append((str(r[1]).strip(), float(r[2] or 0), bool(r[3]), str(r[4] or ''), str(r[5] or ''), bool(r[6])))
        # routing → _pc/_rc = lazy _procs/_rate_proc 필터와 동일(91/92/93=_rc, 98/99제외 나머지=_pc)
        c.execute("SELECT item_code,proc_code,ISNULL(work_qty,0),ISNULL(prod_uph,0),ISNULL(calc_gubun,''),ISNULL(p_item,'') FROM nx.routing")
        for r in c.fetchall():
            code = str(r[0]).strip(); proc = str(r[1]); wq = float(r[2] or 0); uph = float(r[3] or 0); cg = str(r[4] or '').strip(); pit = str(r[5] or '').strip()
            if proc in ('91', '92', '93'): self._rc.setdefault((code, proc), []).append((uph, wq, pit))
            elif proc not in ('98', '99'): self._pc.setdefault(code, []).append((proc, wq, uph, cg, pit))
        # proc_weld → _wlc = _weld_lines()와 동일
        c.execute("SELECT parent_item,weld_item,ISNULL(use_qty,0),ISNULL(cs_calc_except,0),ISNULL(from_ymd,''),ISNULL(to_ymd,''),ISNULL(lme_except,0) FROM nx.proc_weld ORDER BY parent_item,weld_item")
        for r in c.fetchall():
            self._wlc.setdefault(str(r[0]).strip(), []).append((str(r[1]).strip(), float(r[2] or 0), bool(r[3]), str(r[4] or ''), str(r[5] or ''), bool(r[6])))
        self._warmed = True
        return self

    # --- 단위(mult=1) 메모이제이션: material/gagong/lme는 mult에 선형 → 단위값 캐시 후 ×mult ---
    def material_u(self, item, ymd):
        k=(item,ymd)
        if k not in self._matc: self._matc[k]=self.material(item,ymd,1.0)
        return self._matc[k]
    def gagong_u(self, item, ymd, parent):
        k=(item,ymd,parent)
        if k not in self._gagc: self._gagc[k]=self.gagong(item,ymd,1.0,None,parent)
        return self._gagc[k]
    def lme_u(self, item, ymd):
        k=(item,ymd)
        if k not in self._lmec: self._lmec[k]=self.lme_total(item,ymd,1.0)
        return self._lmec[k]

    def _load_hasbom(self):
        if self._hasbom is None:
            self.cur.execute("SELECT DISTINCT item_code FROM nx.bom_header")
            self._hasbom=set(str(r[0]).strip() for r in self.cur.fetchall())   # ★whitespace-fix: bom_header 트레일링스페이스(2건 5211A21333E·MJU65026409)로 멤버십 실패→전개누락 방지. bom_id()는 SQL이라 공백무시=일관성회복
        return self._hasbom

    def bom_id(self, item):
        if item not in self._hdr:
            self.cur.execute("SELECT TOP 1 bom_id FROM nx.bom_header WHERE item_code=? ORDER BY version DESC", item)
            r=self.cur.fetchone(); self._hdr[item]=r[0] if r else None
        return self._hdr[item]

    def _weld_lines(self, item):
        """용접봉(RAC)=공정종속 자재 → nx.proc_weld에서 주입(BOM 구성행 아님). use_qty·cs_calc_except·lme_except 보존 = 재배치 전과 동일.
           proc_weld 미존재/미적재 시 빈=[] (그 경우 lines()가 bom_line RAC를 그대로 사용 → 하위호환)."""
        if not hasattr(self,'_wlc'): self._wlc={}
        if item not in self._wlc:
            try:
                self.cur.execute("""SELECT weld_item, use_qty, ISNULL(cs_calc_except,0), ISNULL(from_ymd,''), ISNULL(to_ymd,''), ISNULL(lme_except,0)
                    FROM nx.proc_weld WHERE parent_item=? ORDER BY weld_item""", item)
                self._wlc[item]=[(str(r[0]).strip(),float(r[1] or 0),bool(r[2]),str(r[3] or ''),str(r[4] or ''),bool(r[5])) for r in self.cur.fetchall()]
            except Exception:
                self._wlc[item]=[]
        return self._wlc[item]

    def lines(self, item):
        bid=self.bom_id(item)
        wk=self._weld_lines(item)   # 용접봉=proc_weld 주입(공정종속). 아래 bom_line 읽기는 RAC 제외(중복방지)
        if bid is None: return list(wk)
        if bid not in self._lines:
            self.cur.execute("""SELECT child_item,qty,cs_calc_except,from_ymd,to_ymd,ISNULL(lme_except,0)
                FROM nx.bom_line WHERE bom_id=? AND child_item NOT LIKE 'RAC%' ORDER BY seq""", bid)
            self._lines[bid]=[(str(r[0]).strip(),float(r[1] or 0),bool(r[2]),str(r[3] or ''),str(r[4] or ''),bool(r[5])) for r in self.cur.fetchall()]
        return self._lines[bid]+wk

    def _load_item(self, item):
        if item not in self._item:
            self.cur.execute("""SELECT ISNULL(in_cust,''),ISNULL(make_type,''),ISNULL(cost_gubun,''),
                ISNULL(metal_gubun,''),ISNULL(diam,0),ISNULL(thick,0),ISNULL(net_weight,0),ISNULL(has_gagong,0),
                ISNULL(silver_flag,0),ISNULL(unit,''),ISNULL(lgroup,''),ISNULL(sgroup,'')
                FROM nx.item WHERE item_code=?""", item)
            r=self.cur.fetchone()
            self._item[item]=({'in_cust':r[0].strip(),'make_type':r[1].strip(),'cost_gubun':r[2].strip(),
                'metal':r[3].strip(),'diam':float(r[4] or 0),'thick':float(r[5] or 0),'wt':float(r[6] or 0),
                'has_gagong':bool(r[7]),'silver':bool(r[8]),'unit':r[9].strip(),'lgroup':r[10].strip(),'sgroup':r[11].strip()} if r
                else {'in_cust':'','make_type':'','cost_gubun':'','metal':'','diam':0,'thick':0,'wt':0,'has_gagong':False,'silver':False,'unit':'','lgroup':'','sgroup':''})
        return self._item[item]

    def labor_rate(self, ym):
        if not hasattr(self,'_lr'):
            self.cur.execute("SELECT apply_ym,rate FROM nx.labor_rate WHERE labor_tag='3'")
            self._lr=sorted((str(r[0]).strip(),float(r[1] or 0)) for r in self.cur.fetchall())
        cands=[r for r in self._lr if r[0]<=ym]
        return (max(cands,key=lambda r:r[0])[1] if cands else (self._lr[0][1] if self._lr else 0.0))

    def _valid_procs(self, lgroup):
        """★lgroup-fix(2026-08-13): 레거시 SP는 가공비를 `CS_M_PROC.ITEM_LGROUP IN(@LS_ITEM_GROUP=상위품목lgroup,'J')`
           공정만 계상(R_SORT_SEQ 매칭). 상위품목과 다른 그룹 부품의 공정(예 E품목에 든 G그룹 BOX공정)은 제외.
           반환=해당 lgroup에서 유효한 proc_code 집합(91/92/93/98/99=overhead·별도처리 제외)."""
        if not hasattr(self,'_vpc'): self._vpc={}
        lg=lgroup or ''
        if lg not in self._vpc:
            self.cur.execute("SELECT proc_code FROM nx.CS_M_PROC WHERE item_lgroup IN (?,'J') AND proc_code NOT IN ('91','92','93','98','99')", lg)
            self._vpc[lg]=set(str(r[0]) for r in self.cur.fetchall())
        return self._vpc[lg]

    def _procs(self, node):
        """가공공정(91/92/93/98/99 제외) routing rows: (proc,work_qty,uph,calc_gubun,p_item)."""
        if not hasattr(self,'_pc'): self._pc={}
        if node not in self._pc:
            self.cur.execute("""SELECT proc_code,work_qty,prod_uph,calc_gubun,ISNULL(p_item,'')
                FROM nx.routing WHERE item_code=? AND proc_code NOT IN ('91','92','93','98','99')""", node)
            self._pc[node]=[(str(r[0]),float(r[1] or 0),float(r[2] or 0),str(r[3] or '').strip(),str(r[4] or '').strip()) for r in self.cur.fetchall()]
        return self._pc[node]

    def _rate_proc(self, node, code):
        """91/92/93 공정의 PROD_AMT(=UPH×WORK). 91=일반율·92=운반·93=이윤율."""
        if not hasattr(self,'_rc'): self._rc={}
        key=(node,code)
        if key not in self._rc:
            self.cur.execute("""SELECT ISNULL(prod_uph,0),ISNULL(work_qty,0),ISNULL(p_item,'') FROM nx.routing
                WHERE item_code=? AND proc_code=?""", node, code)
            self._rc[key]=[(float(r[0]),float(r[1]),str(r[2]).strip()) for r in self.cur.fetchall()]
        return self._rc[key]

    def proc_amt(self, node, info, ym, parent=''):
        """노드 1개 가공비(사내 INNER_PROD=1만). Σ 공정 PROD_AMT.
           은납/용접품 공정은 routing p_item=부모로 저장(부모별 용접), 그외 p_item=''."""
        if not self._inner_gagong(info): return 0.0
        labor=self.labor_rate(ym); db_item = parent if info['silver'] else ''
        vp=self._valid_procs(getattr(self,'_top_lg',''))   # ★lgroup-fix: 상위품목 lgroup 공정만
        tot=0.0
        for proc,wq,uph,cg,pit in self._procs(node):
            if pit!=db_item or wq==0 or proc not in vp: continue
            if cg=='3':   tot += round(labor/uph*wq,0) if uph else 0.0   # 임율기반
            elif cg=='8': tot += info['wt']*uph*wq                        # 중량기반
            elif cg=='9': tot += uph*wq                                   # 적용율
            # '7' 세척 → 0
        return tot

    def gagong(self, item, ymd, mult=1.0, seen=None, parent=''):
        """실원가 가공비. 사내노드(INNER_PROD=1)만 proc_amt+하위재귀. 구매/외주완성=0(매입가 포함).
           은납/용접봉은 INNER_PROD=1(우리가 용접), 공정은 부모별(p_item=부모)."""
        if seen is None: seen=set()
        info=self._load_item(item)
        if not self._inner_gagong(info): return 0.0
        ym='20'+ymd[:4]
        tot=self.proc_amt(item, info, ym, parent) * mult
        for child,qty,cx,f,t,lx in self.lines(item):
            if cx or child in seen: continue
            cinfo=self._load_item(child)
            eaq = qty if cinfo['unit']=='EA' else 1.0   # SP: GAGONG × IIF(UNIT='EA',USE_QTY,1)
            tot += self.gagong(child, ymd, mult*eaq, seen|{child}, parent=item)
        return round(tot,2)

    def _inner_prod(self, info):
        """사내생산여부 (SP INNER_PROD_FLAG, 재료비용): make_type='1'→T, ''→(in_cust='' or has_gagong), 2/3→F.
           ※은납 override(SP 352행)는 재료비 계산 後·가공 계산 前이라 재료엔 미적용. 가공은 _inner_gagong."""
        mk=info['make_type']
        if mk=='1': return True
        if mk=='': return (info['in_cust']=='' or info['has_gagong'])
        return False

    def _inner_gagong(self, info):
        """가공비용 사내판정 = 재료 INNER_PROD + 은납(용접)품 override(우리가 용접)."""
        return info['silver'] or self._inner_prod(info)
    def item_incust(self, item): return self._load_item(item)['in_cust']
    def item_maketype(self, item): return self._load_item(item)['make_type']

    def std_metal_price(self, metal, diam, thick, ymcut):
        """원소재 소재단가 = nx.price_metal.std_price by (metal,diam,thick, apply_ym<=ymcut 최신)."""
        key=(metal,round(diam,4),round(thick,4))
        if not hasattr(self,'_pm'): self._pm={}
        if key not in self._pm:
            self.cur.execute("""SELECT apply_ym,std_price FROM nx.price_metal
                WHERE metal_gubun=? AND diam=? AND thick=?""", metal, diam, thick)
            self._pm[key]=[(str(r[0]).strip(),float(r[1] or 0)) for r in self.cur.fetchall()]
        cands=[c for c in self._pm[key] if c[0]<=ymcut]
        if cands: return max(cands,key=lambda c:c[0])[1]
        dated=self._pm[key]
        return min(dated,key=lambda c:c[0])[1] if dated else 0.0

    def _fx(self, currency, ymd):
        """통화환산율(nx.fx_rate, apply_ymd<=ymd 최신). KRW/빈값=1.0. 2026 데이터 없으면 최신(SP 동일)."""
        cur=(currency or 'KRW').strip().upper()
        if cur in ('','KRW'): return 1.0
        if not hasattr(self,'_fxc'): self._fxc={}
        if cur not in self._fxc:
            self.cur.execute("SELECT apply_ymd,rate FROM nx.fx_rate WHERE currency=?", cur)
            self._fxc[cur]=[(str(r[0] or '').strip(),float(r[1] or 0)) for r in self.cur.fetchall()]
        cands=[c for c in self._fxc[cur] if c[0] and c[0]<=ymd]
        if cands: return max(cands,key=lambda c:c[0])[1]
        return 1.0

    def pur_price(self, item, ymd, vendor=None):
        """매입단가 as-of ymd × 환율(SP line297: ITEM_COST × BAS). vendor 우선, 없으면 최신 as-of(모든 vendor)."""
        key=item
        if key not in self._pur:
            # ★zeroprice-fix(2026-08-13): 0원 행 포함(제외 금지). SP는 TOP1 최신 as-of를 쓰므로 나중 0원(단가소멸/사급전환)이
            #   과거 비-0을 대체. 0원 제외하면 옛 단가 오적재(MJX65072213 최신260214=0인데 옛251210=13893 오계상).
            self.cur.execute("""SELECT vendor_code,apply_ymd,price,ISNULL(currency,'KRW') FROM nx.price_item
                WHERE item_code=? AND price_type='매입' AND price IS NOT NULL""", item)
            self._pur[key]=[(str(r[0]).strip(),str(r[1] or '').strip(),float(r[2] or 0),str(r[3] or 'KRW').strip()) for r in self.cur.fetchall()]
        rows=self._pur[key]
        if not rows: return None
        def asof(cands):
            valid=[c for c in cands if c[1] and c[1]<=ymd]
            return max(valid,key=lambda c:c[1]) if valid else None
        # ★fx-fix(2026-08-13): 매입단가 통화환산(USD/YEN/EUR/RMB × nx.fx_rate). 6851AR3278W 6.17USD×1359=8385.03 SP정합.
        # ★vendorstrict-fix(2026-08-13): SP line303·309 `cust_code=T.IN_CUST_CODE AND IN_CUST_CODE>''` 정합 —
        #   지정 vendor(=자식 in_cust) 정확매칭만. 빈 vendor/불일치→0(None). 전vendor 폴백 제거(폴백이 빈in_cust 노드에 매입가 오적재→과대계상, AJR74983905-12-X 등).
        if vendor:
            v=asof([c for c in rows if c[0]==vendor])
            if v: return v[2]*self._fx(v[3],ymd)
        # ★asof-fix(2026-08-12): as-of(≤원가일) 단가 없으면 0(None). 미래단가 폴백 금지(SP=PUR_COST 0 정합).
        return None

    def _metal_sub(self, metal, diam, thick, ymcut):
        """LME 사급차액단가 = std_price − partner_price (TOT_COST − TOT_COST_SUB)."""
        key=(metal,round(diam,4),round(thick,4))
        if not hasattr(self,'_pm'): self._pm={}
        if key not in self._pm: self.std_metal_price(metal,diam,thick,ymcut)  # 캐시적재
        # partner도 필요 → 별도 조회 캐시
        if not hasattr(self,'_pms'): self._pms={}
        if key not in self._pms:
            self.cur.execute("""SELECT apply_ym,std_price,partner_price FROM nx.price_metal
                WHERE metal_gubun=? AND diam=? AND thick=?""", metal, diam, thick)
            self._pms[key]=[(str(r[0]).strip(),float(r[1] or 0),float(r[2] or 0)) for r in self.cur.fetchall()]
        cands=[c for c in self._pms[key] if c[0]<=ymcut]
        row=max(cands,key=lambda c:c[0]) if cands else (min(self._pms[key],key=lambda c:c[0]) if self._pms[key] else None)
        return (row[1]-row[2]) if row else 0.0

    def _lme(self, info, q, ymcut):
        """LME 사급차액 = (std−partner)×중량×q. 구매(매입가) 동부품·중량보유만(_leaf_val 매입가 분기서 호출).
           SP: INNER_PROD=0 → cost_gubun 동적 '2' → LME대상. 소재단가('3' 사내)엔 미적용."""
        if info['wt']>0 and info['metal']:
            return self._metal_sub(info['metal'], info['diam'], info['thick'], ymcut) * info['wt'] * q
        return 0.0

    def lme_total(self, item, ymd, mult=1.0, seen=None):
        """LME차액 총합(전 서브트리). SP: 최말단 구매(INNER_PROD=0) 동부품(중량>0·사급거래처)만
           (소재단가−사급단가)×중량×누적qty. 외주완성 경계도 뚫고 전개(cost_gubun 5만 정지)."""
        # ★jiknap-root-fix(2026-08-16, 승인·화면검증): 직납(cost_gubun=5) 품목은 직납가 고정 → 내부 LME 없음.
        #   루프는 직납 '자식'만 정지하고 '루트'가 직납일 땐 자식(동)까지 파고들어 LME 오적용(AJR77223106·STS 6품목).
        #   레거시는 직납 루트를 직납가로 멈춤(LME=0). 직납 138품목 전수 무회귀 검증.
        if self._load_item(item)['cost_gubun']=='5': return 0.0
        if seen is None: seen=set()
        ymcut='20'+ymd[:4]
        total=0.0
        for child,qty,cx,f,t,lx in self.lines(item):
            if cx: continue
            q=qty*mult
            info=self._load_item(child)
            kids=[l for l in self.lines(child) if not l[2]] if (child in self._load_hasbom() and child not in seen) else []
            expandable = (info['cost_gubun']!='5') and kids
            if expandable:
                total += self.lme_total(child, ymd, q, seen|{child})
            elif (not lx) and (not self._inner_prod(info)) and info['wt']>0 and info['metal'] and info['in_cust']:
                total += self._metal_sub(info['metal'],info['diam'],info['thick'],ymcut) * info['wt'] * q
        return round(total,2)

    def _leaf_val(self, node, info, q, ymd, ymcut):
        """최말단 재료비 base(LME제외): 사내(INNER_PROD=1)=cost_gubun='3'→소재단가×중량, 그외 0(매입가 안씀).
           INNER_PROD=0(구매/외주완성)=매입단가. LME는 lme_total()에서 전서브트리 별도합산.
           ★innerleaf-fix(2026-08-13): SP는 매입단가를 INNER_PROD='0'에만 적용(#TEMP_MAT: cost_gubun∉('3','4') AND INNER_PROD='0').
             사내제작(mk='1') leaf가 자식없고 cg≠'3'이면 SP=0(예 MAZ66263602 mk1·cg1·자식0: SP 0, 기존엔진 매입가7894 오적재)."""
        if self._inner_prod(info):
            if info['cost_gubun']=='3':
                return self.std_metal_price(info['metal'], info['diam'], info['thick'], ymcut) * info['wt'] * q
            return 0.0
        price=self.pur_price(node, ymd, info['in_cust'])   # 구매품(INNER_PROD=0)=구매단가
        return (price or 0)*q

    def _expandable(self, node, info, seen):
        """전개 대상? 사내생산(INNER_PROD=1) & 직납(5) 아님 & cs_calc_except=0 자식 존재."""
        if not self._inner_prod(info) or info['cost_gubun']=='5': return None   # 구매/외주완성/직납 → 정지
        kids=[l for l in self.lines(node) if not l[2]] if (node in self._load_hasbom() and node not in seen) else []
        return kids or None

    def _value_node(self, node, q, ymd, ymcut, seen):
        """노드 1개 재료비 기여. 사내+자식→전개, 그외(구매/외주완성/원소재)→매말단 계상."""
        info=self._load_item(node)
        # ★cg3fix(2026-08-12, 승인): 레거시 SP는 make_type='1'(제작)이면 전개(cg 무관). cg='3'인 제작SUB(원소재단가 표시)도 전개해야 함(AJR74482401 등 22SUB·60제품).
        if (info['cost_gubun']!='3' or info['make_type']=='1') and self._expandable(node, info, seen):
            return sum(self._value_node(c, qty*q, ymd, ymcut, seen|{node}) for c,qty,cx,f,t,lx in self.lines(node) if not cx)
        return self._leaf_val(node, info, q, ymd, ymcut)

    def _oh_rate(self, item, code, parent=''):
        """91일반율·92운반금액·93이윤율. SP: 91/92/93 PROD_AMT = PROD_UPH 그대로(work_qty 무관).
           은납품은 p_item=부모, 그외 p_item=''."""
        info=self._load_item(item)
        if not self._inner_gagong(info): return 0.0
        db_item = parent if info['silver'] else ''
        for uph,work,p in self._rate_proc(item, code):
            if p==db_item: return uph
        return 0.0

    def overhead(self, item, ymd, muse=1.0, mea=1.0, seen=None, parent=''):
        """일반·운반·이윤 (노드별 율×(그노드 재료+가공), 롤업).
           muse=재료 누적use_qty, mea=가공 누적EA-qty. 반환 (ilban,unban,profit)."""
        if seen is None: seen=set()
        info=self._load_item(item)
        if not self._inner_gagong(info): return (0.0,0.0,0.0)
        ym='20'+ymd[:4]
        # SP: 각 사내노드 ILBAN=율91×(그노드 롤업 재료−LME+가공), PROFIT=율93×(가공+일반), 롤업합산.
        r91=self._oh_rate(item,'91',parent); r93=self._oh_rate(item,'93',parent)
        if r91 or r93:
            jn=(self.material_u(item,ymd)-self.lme_u(item,ymd))*muse
            gn=self.gagong_u(item,ymd,parent)*mea   # 은납/용접봉 공정=부모별, parent 전달필수
        else:
            jn=0.0; gn=self.proc_amt(item, info, ym, parent)*mea
        ilban=round(r91*(jn+gn),0) if r91 else 0.0
        unban=round(self._oh_rate(item,'92',parent)*mea,0)
        profit=round(r93*(gn+ilban),0) if r93 else 0.0
        for child,qty,cx,f,t,lx in self.lines(item):
            if cx or child in seen: continue
            cinfo=self._load_item(child)
            cmea = mea*(qty if cinfo['unit']=='EA' else 1.0)
            ci,cu,cp=self.overhead(child, ymd, muse*qty, cmea, seen|{child}, parent=item)
            ilban+=ci; unban+=cu; profit+=cp
        return (ilban,unban,profit)

    def lg_cost(self, item, ymd):
        """LG판가 = price_item vendor IN(1010/1020/1030 LG), TAGE/TAGS, 기준일 as-of 최신."""
        if not hasattr(self,'_lg'): self._lg={}
        if item not in self._lg:
            self.cur.execute("""SELECT apply_ymd,price FROM nx.price_item
                WHERE item_code=? AND vendor_code IN ('1010','1020','1030') AND price_type IN ('TAGE','TAGS')""", item)
            self._lg[item]=[(str(r[0]).strip(),float(r[1] or 0)) for r in self.cur.fetchall()]
        cands=[c for c in self._lg[item] if c[0] and c[0]<=ymd]
        return (max(cands,key=lambda c:c[0])[1] if cands else 0.0)

    def silwon(self, item, ymd):
        self._prime_caches(item)
        """실원가 = 재료+가공+일반+운반+이윤. 손익 = LG판가 − 실원가."""
        jae=self.material_u(item,ymd); gag=self.gagong_u(item,ymd,'')
        ilban,unban,profit=self.overhead(item,ymd)
        sil=round(jae+gag+ilban+unban+profit,2)
        lg=self.lg_cost(item,ymd)
        return {'jae':round(jae,2),'gagong':round(gag,2),'ilban':ilban,'unban':unban,'profit':profit,
                'silwon':sil,'lg':round(lg,2),'sonik':round(lg-sil,2)}

    def material(self, item, ymd, mult=1.0, depth=0, seen=None):
        """실원가 재료비 (SP_실원가용 산식). ymd=YYMMDD.
           ★2026-08-24 통일엔진 전환(SOYO_ENGINE_UNIFY §3 Step3): 로직 정본 = nx_soyo_engine.cost_material.
           전 스코프 diff0 검증(사용중 1052/1052·넓은스코프 60/60·비사용중 포함). mult/depth/seen=하위호환
           시그니처(실사용 mult=1.0). 롤백=아래 _material_legacy 호출로 1줄 교체."""
        import nx_soyo_engine as _se
        v = _se.cost_material(self, item, ymd)
        return v if mult == 1.0 else round(v * mult, 2)

    def _material_legacy(self, item, ymd, mult=1.0, depth=0, seen=None):
        """전환 전 원본 material 로직 — 롤백·대조용 보존(2026-08-24). 통일엔진 cost_material와 diff0."""
        ymcut='20'+ymd[:4]
        info=self._load_item(item)
        if (info['cost_gubun']!='3' or info['make_type']=='1') and self._expandable(item, info, set()):   # ★cg3fix
            base=sum(self._value_node(c, qty*mult, ymd, ymcut, {item}) for c,qty,cx,f,t,lx in self.lines(item) if not cx)
        else:
            base=self._leaf_val(item, info, mult, ymd, ymcut)
        return round(base + self.lme_u(item, ymd)*mult, 2)   # 재료 = base(구매/소재단가) + LME차액 전서브트리

    def material_split(self, item, ymd):
        """재료비(base, LME제외)를 최말단 leaf의 sgroup별로 분리 — SP WON/BU/SA_JAI_AMT 정합(SP 860-862).
           원자재(won)=110/120/130/220, 부자재(bu)=230/910, 사급(sa)=310, 기타(210 등)→won 캐치올. won+bu+sa=material base."""
        ymcut='20'+ymd[:4]; b={'won':0.0,'bu':0.0,'sa':0.0}
        def acc(sg, v):
            if sg in ('230','910'): b['bu']+=v
            elif sg=='310': b['sa']+=v
            else: b['won']+=v
        def walk(node, q, seen):
            info=self._load_item(node)
            if (info['cost_gubun']!='3' or info['make_type']=='1') and self._expandable(node, info, seen):
                for c,qty,cx,f,t,lx in self.lines(node):
                    if cx: continue
                    walk(c, qty*q, seen|{node})
            else:
                acc(info.get('sgroup',''), self._leaf_val(node, info, q, ymd, ymcut))
        info=self._load_item(item)
        if (info['cost_gubun']!='3' or info['make_type']=='1') and self._expandable(item, info, set()):
            for c,qty,cx,f,t,lx in self.lines(item):
                if cx: continue
                walk(c, qty, {item})
        else:
            walk(item, 1.0, set())
        return {k: round(v,2) for k,v in b.items()}

    def cosp_price(self, item, ymd):
        """사급가(COSP) = nx.price_item(price_type='매입', vendor='LG') as-of ymd 최신. LG가 청구하는 실 사급단가."""
        if not hasattr(self, '_cospc'): self._cospc = {}
        if item not in self._cospc:
            self.cur.execute("SELECT ISNULL(apply_ymd,''), price FROM nx.price_item WHERE item_code=? AND price_type=N'매입' AND vendor_code='LG'", item)
            self._cospc[item] = [(str(r[0]).strip(), float(r[1] or 0)) for r in self.cur.fetchall()]
        cands = [c for c in self._cospc[item] if c[0] and c[0] <= ymd]
        return max(cands, key=lambda c: c[0])[1] if cands else 0.0

    def sagub_whole(self, item, ymd):
        """★실사급금액(통째) = Σ(사급부품[소분류310] 소요 × 사급가 COSP@ymd). 사급부품을 분해 안 하고 통째로.
           ※read-only 별도 메서드 — material()/실원가/손익 무영향(레거시 diff0 보존). 품목원가 '나란히 표시'용.
           소요=CS_M_ITEM_BOM 전개(조달경로변형 배제=예상 사급금액과 동일 소스). 엔진 nx.bom_line은 외주완성에서 정지해
           사급부품(예 AJR30077403→MJX65072203)을 못 잡음 → CS로 완전전개해야 실제 OSP 정합."""
        if not hasattr(self, '_sag310'):
            self.cur.execute("SELECT DISTINCT LTRIM(RTRIM(ITEM_CODE)) FROM PARTNER_ERP.dbo.PR_M_ITEM WHERE LTRIM(RTRIM(ITEM_SGROUP))='310'")
            self._sag310 = set(r[0] for r in self.cur.fetchall())
        self.cur.execute("""WITH expl AS (
            SELECT LTRIM(RTRIM(MAT_CODE)) part, CAST(USE_QTY AS float) cum, 1 lvl FROM PARTNER_ERP.dbo.CS_M_ITEM_BOM WHERE LTRIM(RTRIM(ITEM_CODE))=? AND ISNULL(CS_CALC_EXCEPT_FLAG,'0')<>'1'
            UNION ALL SELECT LTRIM(RTRIM(b.MAT_CODE)), e.cum*CAST(b.USE_QTY AS float), e.lvl+1 FROM expl e JOIN PARTNER_ERP.dbo.CS_M_ITEM_BOM b ON LTRIM(RTRIM(b.ITEM_CODE))=e.part AND ISNULL(b.CS_CALC_EXCEPT_FLAG,'0')<>'1' WHERE e.lvl<8)
            SELECT part, SUM(cum) FROM expl GROUP BY part OPTION(MAXRECURSION 30)""", item)
        soyos = [(str(p or '').strip(), float(s or 0)) for p, s in self.cur.fetchall()]
        tot = 0.0
        for p, s in soyos:
            if p in self._sag310: tot += s * self.cosp_price(p, ymd)
        return round(tot, 2)

    def sagub_sum(self, item, diffmap):
        """완제품 손익에 반영할 사급차액 합 = Σ diffmap[사급부품] × 누적소요qty.
           diffmap={부품:사급차액(=실출고가−실입고가, 음수=손해)}.
           ★이중계상 방지 규칙(검증됨: crossed==silwon_nodes 직접계상과 상보):
             실원가는 사급부품을 둘 중 하나로 계상 —
              (A) **직접 leaf**(제작 아래 매입부품, 입고가) → 이미 반영 → 제외.
              (B) **매입 SUB 안에 묻힘**(SUB를 매입가≈사급가로 계상) → 개당차액 미반영 → **가산**.
           crossed = 실원가 정지경계(매입/외주완성/원소재=전개안됨)를 지나 도달 = (B)묻힘.
           ★다중경로 방어(2026-08-14): 변형SUB 미정규화로 같은 사급부품이 직접경로+묻힘경로 둘 다로 도달 가능.
             '어느 경로로든 un-crossed(직접계상)로 도달하면' 그 부품은 전면 제외(이중계상 절대방지). AHQ73469301."""
        return round(sum(h['amt'] for h in self._sagub_hits(item, diffmap).values() if not h['direct']), 2)

    def _sagub_hits(self, item, diffmap):
        """사급부품별 {code:{'unit':개당,'amt':묻힘경로 누적기여,'qty':묻힘누적,'direct':직접계상경로 존재}}.
           direct=True(어느 경로로든 실원가 직접계상)면 사급차액 제외 대상."""
        hits={}
        def walk(node, q, seen, crossed, d):
            if node in diffmap:
                h=hits.get(node)
                if h is None: h=hits[node]={'unit':round(diffmap[node],2),'amt':0.0,'qty':0.0,'direct':False}
                if crossed: h['amt']+=diffmap[node]*q; h['qty']+=q
                else: h['direct']=True   # 직접계상(실원가 재료비에 이미 입고가로 반영) → 제외
                return
            if d>14: return
            info=self._load_item(node)
            expands=(info['cost_gubun']!='3' or info['make_type']=='1') and bool(self._expandable(node, info, seen))
            b=not expands
            for c,qty,cx,f,t,lx in self.lines(node):
                if cx or c in seen: continue
                walk(c, qty*q, seen|{node}, crossed or b, d+1)
        walk(item, 1.0, set(), False, 0)
        for h in hits.values(): h['amt']=round(h['amt'],2); h['qty']=round(h['qty'],4)
        return hits

    def sagub_nodes(self, item, diffmap):
        """실원가 그리드용: 매입 SUB 안에 묻힌(crossed) 사급부품별 개당차액·누적qty·기여액.
           sagub_sum과 동일 규칙(묻힌것만·이중계상 방지·다중경로 direct 제외). Σ amt == sagub_sum.
           반환 {code:{'unit':개당차액, 'qty':누적소요, 'amt':개당×누적}}."""
        return {c: {'unit':h['unit'],'qty':h['qty'],'amt':h['amt']}
                for c,h in self._sagub_hits(item, diffmap).items() if (not h['direct']) and abs(h['amt'])>0.005}

    def _lme_nodes(self, item, ymd, mult=1.0, seen=None, out=None):
        """lme_total과 동일 로직으로 per-node LME 사급차액 수집(그리드 방출용). out[node] += (std−partner)×중량×누적q."""
        if seen is None: seen=set()
        if out is None: out={}
        ymcut='20'+ymd[:4]
        for child,qty,cx,f,t,lx in self.lines(item):
            if cx: continue
            q=qty*mult
            info=self._load_item(child)
            kids=[l for l in self.lines(child) if not l[2]] if (child in self._load_hasbom() and child not in seen) else []
            expandable = (info['cost_gubun']!='5') and kids
            if expandable:
                self._lme_nodes(child, ymd, q, seen|{child}, out)
            elif (not lx) and (not self._inner_prod(info)) and info['wt']>0 and info['metal'] and info['in_cust']:
                amt=self._metal_sub(info['metal'],info['diam'],info['thick'],ymcut)*info['wt']*q
                out[child]=out.get(child,0.0)+amt
        return out

    def silwon_nodes(self, item, ymd):
        self._prime_caches(item)
        """실원가 노드별 방출(그리드용). 현재 매핑된 BOM을 지정된 조달방식대로: 사내(INNER_PROD=1)+원소재(cg3)=소재단가×중량,
           그외(외주완성/구매)=매입단가, 가공비=사내노드만, LME 사급차액=구매 동부품별. Σ(mat+lme+gag)+overhead=silwon 정합."""
        ymcut='20'+ymd[:4]; ym=ymcut
        rows=[]
        def walk(node, cum_q, cum_ea, lvl, parent, seen):
            info=self._load_item(node); cg=info['cost_gubun']
            inner=self._inner_prod(info)
            exp=(cg!='3' or info['make_type']=='1') and bool(self._expandable(node,info,seen))   # ★cg3fix: 제작SUB(cg3)도 전개
            if exp:
                won=0.0; mat=0.0
            elif inner and cg=='3':
                won=self.std_metal_price(info['metal'],info['diam'],info['thick'],ymcut); mat=round(won*info['wt']*cum_q,2)
            elif inner:
                won=0.0; mat=0.0   # ★innerleaf-fix(2026-08-13): 사내제작 leaf·cg≠3 = SP 0(매입가 안씀)
            else:
                won=self.pur_price(node,ymd,info['in_cust']) or 0.0; mat=round(won*cum_q,2)
            gag=round(self.proc_amt(node,info,ym,parent)*cum_ea,2)
            kind='매입' if (not inner) else ('원소재' if cg=='3' else '제작')
            rows.append({'level':lvl,'code':node,'cost_gubun':cg,'qty':round(cum_q,4),'won':round(won,4),
                'mat':mat,'lme':0.0,'gag':gag,'inner':inner,'kind':kind,'in_cust':info['in_cust'],
                'metal':info['metal'],'diam':info['diam'],'thick':info['thick'],'weight':round(info['wt'],4),
                'silver':info['silver'],'haskids':bool(exp)})
            if exp:
                for c,qty,cx,f,t,lx in self.lines(node):
                    if cx: continue
                    cinfo=self._load_item(c); ea=qty if cinfo['unit']=='EA' else 1.0
                    walk(c, cum_q*qty, cum_ea*ea, lvl+1, node, seen|{node})
        walk(item,1.0,1.0,0,'',set())
        # LME 사급차액 per-node 병합(매입 완제품 내부 동부품은 별도행)
        lmemap=self._lme_nodes(item,ymd)
        bycode={}
        for r in rows: bycode.setdefault(r['code'],r)   # 첫 등장 노드
        for code,amt in lmemap.items():
            if code in bycode:
                bycode[code]['lme']=round(bycode[code]['lme']+amt,2)
            else:
                info=self._load_item(code)
                rows.append({'level':1,'code':code,'cost_gubun':info['cost_gubun'],'qty':0,'won':0,
                    'mat':0.0,'lme':round(amt,2),'gag':0.0,'inner':False,'kind':'사급(LME)','in_cust':info['in_cust'],
                    'metal':info['metal'],'diam':info['diam'],'thick':info['thick'],'weight':round(info['wt'],4),
                    'silver':False,'haskids':False})
        codes=list({r['code'] for r in rows})
        meta={}
        for i in range(0,len(codes),900):
            ch=codes[i:i+900]; ph=','.join('?'*len(ch))
            self.cur.execute("SELECT i.item_code, ISNULL(i.item_name,''), ISNULL(i.item_spec,''), ISNULL(i.unit,'') FROM nx.item i JOIN STRING_SPLIT(?,',') s ON i.item_code=s.value", ",".join(ch))  # ★IN(N) 드라이버 오버헤드(520ms) 회피=STRING_SPLIT 단일파라미터(표시전용·원가무관)
            for r in self.cur.fetchall(): meta[r[0]]={'nm':r[1],'spec':r[2],'unit':r[3]}
        for r in rows:
            d=meta.get(r['code'],{}); r['name']=d.get('nm',''); r['spec']=d.get('spec',''); r['unit']=d.get('unit','')
        return {'rows':rows,'agg':self.silwon(item,ymd)}

    def silwon_proc_grid(self, item, ymd):
        self._prime_caches(item)
        """실원가 공정별 집계. ★수량(wq)=내부원가와 동일(전 노드·외주 포함 — 조달후보 비교·표시 통일).
           원가(amt)=자체노드(INNER_PROD)만(외주=매입가로 대체·공임 미계상). Σamt=silwon.gagong(원가 불변).
           STEP B(2026-08-04): 외주 공정도 수량은 유지, 원가는 매입가. silwon() 원가엔진은 불변."""
        ym='20'+ymd[:4]; labor=self.labor_rate(ym)
        agg={}   # 원가 amt = 자체노드(INNER)만 (현행 로직 보존 = silwon.gagong 정합)
        def walk(node, cum_ea, parent, seen):
            info=self._load_item(node); cg0=info['cost_gubun']
            if self._inner_gagong(info):
                db_item=parent if info['silver'] else ''
                for proc,wq,uph,cg,pit in self._procs(node):
                    if pit!=db_item or wq==0: continue
                    if cg=='3':   amt=(round(labor/uph*wq,0) if uph else 0.0)
                    elif cg=='8': amt=info['wt']*uph*wq
                    elif cg=='9': amt=uph*wq
                    else: amt=0.0
                    agg[proc]=agg.get(proc,0.0)+amt*cum_ea
            exp=(cg0!='3') and bool(self._expandable(node,info,seen))
            if exp:
                for c,qty,cx,f,t,lx in self.lines(node):
                    if cx: continue
                    cinfo=self._load_item(c); ea=qty if cinfo['unit']=='EA' else 1.0
                    walk(c, cum_ea*ea, node, seen|{node})
        walk(item,1.0,'',set())
        # ★수량 wq = 내부원가(전노드) proc_grid — 실원가 공정/용접 수량 == 내부원가 수량. 원가 amt는 위 자체분.
        naeg=self.proc_grid(item,ymd)
        out={}
        for proc,ng in naeg.items():
            out[proc]={'wq':ng['wq'],'amt':round(agg.get(proc,0.0),2),'uph':ng['uph'],'cg':ng['cg'],'labor':labor}
        for proc,amt in agg.items():   # 안전망: 자체 amt인데 naeg 미포함(이론상 없음)
            if proc not in out: out[proc]={'wq':0.0,'amt':round(amt,2),'uph':0,'cg':'3','labor':labor}
        return out

    # ===================== 내부용(내부원가) 모드 =====================
    # 내부용 = 전 공정을 우리가 한다고 가정: INNER_PROD 게이팅 없이 전 노드 전개+가공비 계상, LME 없음.
    # 레거시 SP_CS_견적서(내부용)_250704 재현. 재료 leaf는 cost_gubun만으로 판정(실원가의 inner_prod 조건 없음).
    # ★검증상태: 라이브 SP EXECUTE 권한 부재로 SP-diff0 사인오프 보류(PENDING). 자체정합성으로 선검증.
    def _expandable_nae(self, node, seen):
        """내부용 전개대상: 직납(5) 아님 & cs_calc_except=0 자식 존재. make_type/INNER_PROD 무관(전공정 가정)."""
        info=self._load_item(node)
        if info['cost_gubun']=='5': return None
        kids=[l for l in self.lines(node) if not l[2]] if (node in self._load_hasbom() and node not in seen) else []
        return kids or None

    def _leaf_val_nae(self, node, info, q, ymd, ymcut):
        """내부용 최말단 재료비: cost_gubun='3'→소재단가×중량, 그외→구매(매입)단가. (inner_prod 조건 없음)
           ★SP 정합: 재료 JAI는 WHERE COST_GUBUN > '' 에서만 계상 → 빈 cost_gubun leaf = 0 (레거시 데이터갭이나 SP 재현)."""
        cg=info['cost_gubun']
        if cg=='': return 0.0
        if cg=='3':
            return self.std_metal_price(info['metal'], info['diam'], info['thick'], ymcut) * info['wt'] * q
        price=self.pur_price(node, ymd, info['in_cust'])
        return (price or 0)*q

    def _value_node_nae(self, node, q, ymd, ymcut, seen):
        info=self._load_item(node)
        if info['cost_gubun']!='3' and self._expandable_nae(node, seen):
            return sum(self._value_node_nae(c, qty*q, ymd, ymcut, seen|{node}) for c,qty,cx,f,t,lx in self.lines(node) if not cx)
        return self._leaf_val_nae(node, info, q, ymd, ymcut)

    def material_nae(self, item, ymd, mult=1.0):
        """내부용 재료비: 전개-all(직납/except만 정지), LME 없음.
           ★2026-08-24 통일엔진 전환#2: 로직 정본 = nx_soyo_engine.cost_material_nae (diff0 60/60).
           mult=하위호환(실사용 1.0). 롤백=_material_nae_legacy."""
        import nx_soyo_engine as _se
        v = _se.cost_material_nae(self, item, ymd)
        return v if mult == 1.0 else round(v * mult, 2)

    def _material_nae_legacy(self, item, ymd, mult=1.0):
        """전환 전 원본 material_nae 로직 — 롤백·대조용 보존(2026-08-24)."""
        ymcut='20'+ymd[:4]
        info=self._load_item(item)
        if info['cost_gubun']!='3' and self._expandable_nae(item, set()):
            base=sum(self._value_node_nae(c, qty*mult, ymd, ymcut, {item}) for c,qty,cx,f,t,lx in self.lines(item) if not cx)
        else:
            base=self._leaf_val_nae(item, info, mult, ymd, ymcut)
        return round(base, 2)   # LME 없음

    def material_nae_u(self, item, ymd):
        if not hasattr(self,'_matcn'): self._matcn={}
        k=(item,ymd)
        if k not in self._matcn: self._matcn[k]=self.material_nae(item,ymd,1.0)
        return self._matcn[k]

    def proc_amt_nae(self, node, info, ym, parent=''):
        """내부용 노드 가공비 — INNER_PROD 게이트 없이 전 노드 계상. 공정귀속=실원가와 동일(은납품=부모별)."""
        labor=self.labor_rate(ym); db_item = parent if info['silver'] else ''
        vp=self._valid_procs(getattr(self,'_top_lg',''))   # ★lgroup-fix: 상위품목 lgroup 공정만
        tot=0.0
        for proc,wq,uph,cg,pit in self._procs(node):
            if pit!=db_item or wq==0 or proc not in vp: continue
            if cg=='3':   tot += round(labor/uph*wq,0) if uph else 0.0
            elif cg=='8': tot += info['wt']*uph*wq
            elif cg=='9': tot += uph*wq
        return tot

    def _fasten_amt(self, node, ym):
        """체결 매트릭스(nx.item_fasten × nx.fasten_std) 가공비 = Σ(표준공수×횟수)÷3600×임율. 담당자 입력분(품목별). 데이터 없으면 0."""
        if not hasattr(self, '_fac'): self._fac = {}
        k = (node, ym)
        if k in self._fac: return self._fac[k]
        amt = 0.0
        try:
            self.cur.execute("""SELECT ISNULL(SUM(f.qty*s.std_st),0) FROM nx.item_fasten f
                JOIN nx.fasten_std s ON s.fcode=f.fcode WHERE f.item_code=?""", node)
            st = float(self.cur.fetchone()[0] or 0)
            amt = round(st / 3600.0 * self.labor_rate(ym), 2) if st else 0.0
        except Exception:
            amt = 0.0
        self._fac[k] = amt; return amt

    def gagong_nae(self, item, ymd, mult=1.0, seen=None, parent=''):
        if seen is None: seen=set()
        info=self._load_item(item)
        ym='20'+ymd[:4]
        tot=self.proc_amt_nae(item, info, ym, parent) * mult   # 체결은 nx.routing(FS코드)에 저장 → proc_amt_nae가 자동 계상(별도 합산 불필요)
        # ★direct5-fix(2026-08-13): 직납(cost_gubun='5')은 하위 안 품(SP CTE_BOM `cb.cost_gubun<>'5'` 정합).
        #   재료비(_expandable_nae)·실원가는 이미 '5' 정지. 내부 가공비/overhead만 누락 → 직납 넘어 공유용접봉·MJU 과다계상(내부 34→40/40).
        if info['cost_gubun']!='5':
            for child,qty,cx,f,t,lx in self.lines(item):
                if cx or child in seen: continue
                cinfo=self._load_item(child)
                eaq = qty if cinfo['unit']=='EA' else 1.0
                tot += self.gagong_nae(child, ymd, mult*eaq, seen|{child}, parent=item)
        return round(tot,2)

    def gagong_nae_u(self, item, ymd, parent):
        if not hasattr(self,'_gagcn'): self._gagcn={}
        k=(item,ymd,parent)
        if k not in self._gagcn: self._gagcn[k]=self.gagong_nae(item,ymd,1.0,None,parent)
        return self._gagcn[k]

    def _oh_rate_nae(self, item, code, parent=''):
        info=self._load_item(item)
        db_item = parent if info['silver'] else ''
        for uph,work,p in self._rate_proc(item, code):
            if p==db_item: return uph
        return 0.0

    def overhead_nae(self, item, ymd, muse=1.0, mea=1.0, seen=None, parent=''):
        """내부용 일반·운반·이윤. 내부용은 LME 없어 ILBAN=율91×(재료+가공)."""
        if seen is None: seen=set()
        info=self._load_item(item)
        ym='20'+ymd[:4]
        r91=self._oh_rate_nae(item,'91',parent); r93=self._oh_rate_nae(item,'93',parent)
        if r91 or r93:
            jn=self.material_nae_u(item,ymd)*muse
            gn=self.gagong_nae_u(item,ymd,parent)*mea
        else:
            jn=0.0; gn=self.proc_amt_nae(item, info, ym, parent)*mea
        ilban=round(r91*(jn+gn),0) if r91 else 0.0
        unban=round(self._oh_rate_nae(item,'92',parent)*mea,0)
        profit=round(r93*(gn+ilban),0) if r93 else 0.0
        # ★direct5-fix(2026-08-13): 직납(cost_gubun='5')은 하위 안 품(gagong_nae와 동일 정합).
        if info['cost_gubun']!='5':
            for child,qty,cx,f,t,lx in self.lines(item):
                if cx or child in seen: continue
                cinfo=self._load_item(child)
                cmea = mea*(qty if cinfo['unit']=='EA' else 1.0)
                ci,cu,cp=self.overhead_nae(child, ymd, muse*qty, cmea, seen|{child}, parent=item)
                ilban+=ci; unban+=cu; profit+=cp
        return (ilban,unban,profit)

    def naewon(self, item, ymd):
        self._prime_caches(item)
        """내부원가 = 재료+가공+일반+운반+이윤 (LME 없음). 손익 = LG − 내부원가."""
        jae=self.material_nae_u(item,ymd); gag=self.gagong_nae_u(item,ymd,'')
        ilban,unban,profit=self.overhead_nae(item,ymd)
        nae=round(jae+gag+ilban+unban+profit,2)
        lg=self.lg_cost(item,ymd)
        return {'jae':round(jae,2),'gagong':round(gag,2),'ilban':ilban,'unban':unban,'profit':profit,
                'naewon':nae,'lg':round(lg,2),'sonik':round(lg-nae,2)}

    def naewon_nodes(self, item, ymd):
        self._prime_caches(item)
        """내부원가 노드별 방출(그리드용). 각 노드 재료비(mat)·가공비(gag) 기여 = 총액과 정합.
           재료=leaf에만 계상(누적qty), 가공=proc_amt×누적EA. overhead(일반/운반/이윤)는 agg 요약에만."""
        ymcut='20'+ymd[:4]; ym='20'+ymd[:4]
        rows=[]
        def walk(node, cum_q, cum_ea, lvl, parent, eqty, seen):
            info=self._load_item(node)
            cg=info['cost_gubun']
            expandable = bool(self._expandable_nae(node, seen)) if cg!='3' else False
            if cg=='3':
                won=self.std_metal_price(info['metal'],info['diam'],info['thick'],ymcut)
                mat = 0.0 if expandable else round(won*info['wt']*cum_q,2)
            elif cg=='':
                won=0.0; mat=0.0
            else:
                won=self.pur_price(node,ymd,info['in_cust']) or 0.0
                mat = 0.0 if expandable else round(won*cum_q,2)
            gag=round(self.proc_amt_nae(node, info, ym, parent)*cum_ea,2)
            nproc=sum(1 for (p,wq,uph,c,pit) in self._procs(node) if pit==(parent if info['silver'] else '') and wq>0)
            rows.append({'level':lvl,'code':node,'parent':parent,'eqty':round(eqty,4),'cost_gubun':cg,'qty':round(cum_q,4),
                'won':round(won,4),'mat':mat,'gag':gag,'weight':round(info['wt'],4),'make_type':info['make_type'],
                'metal':info['metal'],'diam':info['diam'],'thick':info['thick'],
                'haskids':expandable,'nproc':nproc,'silver':info['silver']})
            if expandable:
                for c,qty,cx,f,t,lx in self.lines(node):
                    if cx: continue
                    cinfo=self._load_item(c)
                    ea=qty if cinfo['unit']=='EA' else 1.0
                    walk(c, cum_q*qty, cum_ea*ea, lvl+1, node, qty, seen|{node})
        walk(item,1.0,1.0,0,'',1.0,set())
        codes=list({r['code'] for r in rows})
        meta={}
        for i in range(0,len(codes),900):
            ch=codes[i:i+900]; ph=','.join('?'*len(ch))
            self.cur.execute("SELECT i.item_code, ISNULL(i.item_name,''), ISNULL(i.item_spec,''), ISNULL(i.unit,'') FROM nx.item i JOIN STRING_SPLIT(?,',') s ON i.item_code=s.value", ",".join(ch))  # ★IN(N) 드라이버 오버헤드(520ms) 회피=STRING_SPLIT 단일파라미터(표시전용·원가무관)
            for r in self.cur.fetchall(): meta[r[0]]={'nm':r[1],'spec':r[2],'unit':r[3]}
        for r in rows:
            d=meta.get(r['code'],{}); r['name']=d.get('nm',''); r['spec']=d.get('spec',''); r['unit']=d.get('unit','')
        return {'rows':rows,'agg':self.naewon(item,ymd)}

    def proc_grid(self, item, ymd):
        self._prime_caches(item)
        """내부용 공정별 가공비 집계 (레거시 보기구분=공정 그리드). naewon_nodes와 동일 전개로
           proc_code별 작업량·가공비 합산 → Σamt ≈ 가공비(naewon.gagong) 정합.
           용접·은납·부품부착·포장 등 조립공정(용접봉 노드에 얹혀있던 가공비 포함)을 공정 종류별로 모음.
           반환: {proc_code:{wq(작업량Σ), amt(가공비Σ), uph(대표), cg(계산구분), labor(임율)}}. 공정명은 백엔드가 CS_M_PROC로 매핑."""
        ym='20'+ymd[:4]; labor=self.labor_rate(ym)
        vp=self._valid_procs(getattr(self,'_top_lg',''))   # ★lgroup-fix: 상위품목 lgroup 공정만
        agg={}
        def walk(node, cum_ea, parent, seen):
            info=self._load_item(node); cg0=info['cost_gubun']
            db_item = parent if info['silver'] else ''
            for proc,wq,uph,cg,pit in self._procs(node):
                if pit!=db_item or wq==0 or proc not in vp: continue
                if cg=='3':   amt=(round(labor/uph*wq,0) if uph else 0.0)   # 임율기반
                elif cg=='8': amt=info['wt']*uph*wq                          # 중량기반
                elif cg=='9': amt=uph*wq                                     # 적용율
                else: amt=0.0                                                # '7' 세척 등
                a=agg.setdefault(proc,{'wq':0.0,'amt':0.0,'uph':uph,'cg':cg})
                a['wq']+=wq*cum_ea; a['amt']+=amt*cum_ea; a['uph']=uph; a['cg']=cg
            expandable = bool(self._expandable_nae(node, seen)) if cg0!='3' else False
            if expandable:
                for c,qty,cx,f,t,lx in self.lines(node):
                    if cx: continue
                    cinfo=self._load_item(c)
                    ea=qty if cinfo['unit']=='EA' else 1.0
                    walk(c, cum_ea*ea, node, seen|{node})
        walk(item,1.0,'',set())
        return {p:{'wq':round(v['wq'],3),'amt':round(v['amt'],2),'uph':v['uph'],'cg':v['cg'],'labor':labor}
                for p,v in agg.items()}

    # ===================== 내부원가 (LG BOM 기준) =====================
    # LG BOM(nx.lg_bom) 전개 + 우리 치수(nx.item) + 우리 공정(nx.routing 가공·용접·포장·체결).
    # 제작가능(가공공정 보유)=제작(소재단가×중량+가공비), 아니면 매입가. LME 없음. 조달 프로파일 무관(전부 우리제작 baseline).
    def _is_weld(self, node):
        """용접봉(RAC*)=공정종속 자재. BOM재료 아님·제작 아님 → 재료비는 내부원가 포함(공정종속), 가공/전개 없음."""
        return str(node).upper().startswith('RAC')

    def _weld_price(self, node, ymd):
        """용접봉 단가. LG코드(RAC30599301)에 단가 없으면 변형(-1)에서 가져옴."""
        for cand in (node, node + '-1'):
            p = self.pur_price(cand, ymd)
            if p: return round(p, 2)
        return 0.0

    def _weld_parts(self, item, ymd):
        """어셈블리 용접봉(RAC) 재료+가공 = nx.bom(레거시 내부용 diff0) RAC노드 합산(base코드별).
           용접ST→proc51 가공 + 소요량×단가 재료가 이미 레거시정합으로 계산됨 → LG 용접봉에 그대로 매핑."""
        d = self.naewon_nodes(item, ymd)
        out = {}
        for r in d['rows']:
            c = str(r['code'])
            if c.upper().startswith('RAC'):
                base = c.split('-')[0]
                o = out.setdefault(base, {'mat': 0.0, 'gag': 0.0})
                o['mat'] += float(r.get('mat', 0) or 0); o['gag'] += float(r.get('gag', 0) or 0)
        return {k: {'mat': round(v['mat'], 2), 'gag': round(v['gag'], 2)} for k, v in out.items()}

    def _makeable(self, node):
        """우리가 만들 수 있나 = 가공 공정(nx.routing proc<90 & 91/92/93 제외) 보유(work_qty>0). 용접봉 제외."""
        if self._is_weld(node): return False
        return any(wq>0 for (p,wq,uph,cg,pit) in self._procs(node))

    def _lg_rate(self, node, code, parent=''):
        info=self._load_item(node); db_item = parent if info['silver'] else ''
        for uph,work,pit in self._rate_proc(node, code):
            if pit==db_item: return uph
        return 0.0

    def naewon_lg(self, item, ymd):
        """내부원가(LG BOM). 제작가능이면 제작, 아니면 매입가. 노드방출+집계."""
        ymcut='20'+ymd[:4]; ym=ymcut
        self.cur.execute("SELECT parent_code, child_code, qty, ISNULL(supply_type,'') FROM nx.lg_bom WHERE model=? ORDER BY posnr", item)
        kids={}
        for p,c,q,sup in self.cur.fetchall():
            kids.setdefault(str(p).strip(),[]).append((str(c).strip(), float(q or 0), str(sup).strip()))
        rows=[]
        weld_parts=self._weld_parts(item, ymd); weld_used=set()   # 용접봉 재료+가공(레거시정합)
        def walk(node, cumq, cumea, lvl, parent, seen, sup=''):
            info=self._load_item(node)
            if (node!=item) and self._is_weld(node):
                # 용접봉 = 공정종속. 재료(소요량×단가) + 가공(용접ST×임율)을 레거시정합값(nx.bom RAC)으로 매핑.
                base=node.split('-')[0]
                wp = weld_parts.get(base) if base not in weld_used else None
                weld_used.add(base)
                mat = wp['mat'] if wp else 0.0
                gag = wp['gag'] if wp else 0.0
                rows.append({'level':lvl,'code':node,'qty':round(cumq,4),'makeable':False,'kind':'용접봉',
                    'won':self._weld_price(node, ymd),'mat':mat,'gag':gag,'ilban':0.0,'unban':0.0,'profit':0.0,
                    'diam':info['diam'],'thick':info['thick'],'metal':info['metal']})
                return
            makeable=self._makeable(node)
            childs=[(c,q,s) for (c,q,s) in kids.get(node,[]) if c not in seen]
            is_root=(node==item)
            # ★LG BOM 읽기규칙(사용자): Supplier·Assembly Pull=매입(leaf, 하위 미전개), Phantom=우리 제조(전개).
            # + 제작(치수)·자식없음도 leaf.
            stop=(not is_root) and (makeable or info['diam']>0 or sup in ('Supplier','Assembly Pull') or not childs)
            won=0.0
            if is_root:
                mat=0.0
            elif makeable and info['metal'] and info['diam']>0:
                won=round(self.std_metal_price(info['metal'],info['diam'],info['thick'],ymcut),2)   # 소재단가
                mat=round(won*info['wt']*cumq,2)
            else:
                won=round(self.pur_price(node,ymd,info['in_cust']) or 0,2)   # 매입단가
                mat=round(won*cumq,2)
            gag=round(self.proc_amt_nae(node,info,ym,parent)*cumea,2)
            r91=self._lg_rate(node,'91',parent); r92=self._lg_rate(node,'92',parent); r93=self._lg_rate(node,'93',parent)
            ilban=round(r91*(mat+gag),0) if r91 else 0.0
            unban=round(r92,0) if r92 else 0.0
            profit=round(r93*(gag+ilban),0) if r93 else 0.0
            rows.append({'level':lvl,'code':node,'qty':round(cumq,4),'makeable':makeable,'kind':('제작' if makeable else ('구조' if is_root else '매입')),
                'won':won,'mat':mat,'gag':gag,'ilban':ilban,'unban':unban,'profit':profit,
                'diam':info['diam'],'thick':info['thick'],'metal':info['metal']})
            if not stop:
                for c,q,s in childs:
                    cinfo=self._load_item(c); ea=q if cinfo['unit']=='EA' else 1.0
                    walk(c,cumq*q,cumea*ea,lvl+1,node,seen|{node},s)
        walk(item,1.0,1.0,0,'',set(),'')
        # 이름/규격 배치
        codes=list({r['code'] for r in rows}); meta={}
        for i in range(0,len(codes),900):
            ch=codes[i:i+900]; ph=",".join("?"*len(ch))
            self.cur.execute("SELECT i.item_code, ISNULL(i.item_name,''), ISNULL(i.item_spec,''), ISNULL(i.unit,'') FROM nx.item i JOIN STRING_SPLIT(?,',') s ON i.item_code=s.value", ",".join(ch))  # ★IN(N) 드라이버 오버헤드(520ms) 회피=STRING_SPLIT 단일파라미터(표시전용·원가무관)
            for r in self.cur.fetchall(): meta[r[0]]={'nm':r[1],'spec':r[2],'unit':r[3]}
        for r in rows:
            d=meta.get(r['code'],{}); r['name']=d.get('nm',''); r['spec']=d.get('spec',''); r['unit']=d.get('unit','')
        jae=round(sum(r['mat'] for r in rows),2); gg=round(sum(r['gag'] for r in rows),2)
        # overhead(일반/운반/이윤) = 레거시정합 산식(율91×(재료−LME+가공)·이윤율93×(가공+일반)·운반92) 롤업.
        # 재료·가공이 이미 diff0라 overhead도 동일 → overhead_nae(LG 노드기준)가 용접부 율을 못잡으므로 레거시정합값 사용.
        ob=self.overhead_nae(item, ymd)   # (ilban,unban,profit) — nx.bom 롤업(레거시 내부용 diff0)
        ilban,unban,profit=ob
        nae=round(jae+gg+ilban+unban+profit,2); lg=self.lg_cost(item,ymd)
        return {'rows':rows,'agg':{'jae':jae,'gagong':gg,'ilban':ilban,'unban':unban,'profit':profit,
                'naewon':nae,'lg':round(lg,2),'sonik':round(lg-nae,2)}}

if __name__=='__main__':
    sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
    sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\_harness')
    import cost_oracle as CO
    eng=NxCostEngine()
    for it in ['AJR75563503','AJR75563402','AJR75563503-F&T','AJR30077403','AJR75563503503']:
        try:
            o=CO.get_oracle(it,'260630'); ojae=o['sil']['jae']
            mjae=eng.material(it,'260630')
            d=mjae-ojae; ok='✓' if abs(d)<1 else f'✗ Δ{d:+.1f}'
            print(f"[{it}] nx재료={mjae:.1f}  오라클재료={ojae:.1f}  {ok}")
        except Exception as e: print(f"[{it}] 오류 {str(e)[:60]}")
    eng.close()
