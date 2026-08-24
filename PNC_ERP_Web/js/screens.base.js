/* ===== PNC ERP screens.base.js — 기준정보 SCREEN (app.js 분할, 순수이동) ===== */
SCREEN.items=(c)=>itemLiveView(c,false);

/* 대시보드 */
SCREEN.dash=(c)=>{
  const d=DB.dashboard;
  const kpi=(l,v,s,ic)=>`<div class="kpi"><div class="k-ic">${ic}</div><div class="k-lbl">${l}</div>
    <div class="k-val">${won(v)}</div><div class="k-sub">${s}</div></div>`;
  const bars=(arr)=>{const max=Math.max(...arr.map(x=>x.cnt));
    return arr.map(x=>`<div class="bar-row"><div class="lbl">${esc(x.name||'(기타)')}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.max(3,x.cnt/max*100)}%"></div></div>
      <div class="cnt">${won(x.cnt)}</div></div>`).join('');};
  c.innerHTML=`<div class="page-title">🏠 대시보드 <span class="muted" style="font-size:12px;font-weight:400">차세대 스키마 실데이터</span></div>
   <div class="page-sub">현행 ERP 데이터를 차세대 스키마로 이관·검증한 실측 현황입니다.</div>
   <div class="kpis">
     ${kpi('품목 마스터',d.items_total,'RAW·SUB·CON·S_ASSY·PROD','📦')}
     ${kpi('거래처',d.partners_total,'매입·매출·가공외주','🤝')}
     ${kpi('BOM 리비전',d.bom_revisions,`구성 ${won(d.bom_comps)}행`,'🧬')}
     ${kpi('단가 이력',d.price_records,'시계열','💰')}
     ${kpi('생산경로',d.routes,'경로별 손익','🛤️')}</div>
   <div class="charts">
     <div class="panel"><div class="panel-h">📦 품목 유형별 분포</div><div class="panel-b">${bars(d.items_by_type.map(x=>({name:TYPE_NM[x.type]||x.type,cnt:x.cnt})))}</div></div>
     <div class="panel"><div class="panel-h">🤝 거래처 업무분류별 분포</div><div class="panel-b">${bars(d.partners_by_class)}</div></div></div>
   <div class="panel"><div class="panel-h">🔗 역할 분포 (N:M — 매입·매출 동시)</div><div class="panel-b">${bars(d.partners_by_role)}
     <div class="recon">✔ 상단 메뉴에서 모듈을 고르면 좌측에 하위메뉴가 나타납니다. 자재 조회부터 하나씩 추가하며 기존 ERP와 값을 대조하십시오.</div></div></div>`;
};

/* 거래처 조회 */
SCREEN.partners=(c)=>{
  const classes=[...new Set(DB.partners.map(p=>p.class).filter(Boolean))];
  c.innerHTML=`<div class="page-title">🤝 거래처 조회</div>
   <div class="page-sub">전체 ${DB.partners.length}건 · 역할 N:M (매입·매출·가공외주)</div>
   <div class="toolbar"><label>검색</label><input class="inp" id="p-q" placeholder="거래처코드 / 상호 / 대표자">
     <label>업무분류</label><select class="sel" id="p-cls"><option value="">전체</option>${classes.map(x=>`<option>${esc(x)}</option>`).join('')}</select>
     <button class="btn" id="p-go">검색</button><button class="btn ghost" id="p-reset">초기화</button></div>
   <div class="grid-wrap"><table class="tbl"><thead><tr>
     <th>코드</th><th>상호</th><th>대표자</th><th>사업자번호</th><th>업무분류</th><th>역할</th><th class="center">사용</th>
   </tr></thead><tbody id="p-body"></tbody></table></div><div class="rowcount" id="p-cnt"></div>`;
  const roleBadges=s=>(s||'').split(', ').filter(Boolean).map(r=>{const v=r.startsWith('VENDOR');
    const nm=r.replace('CUSTOMER','매출처').replace('VENDOR','매입처').replace('(OUTSOURCE)','·외주').replace('(NORMAL)','');
    return `<span class="bdg role ${v?'v':''}">${nm}</span>`;}).join('');
  const body=c.querySelector('#p-body');
  const render=rows=>{body.innerHTML=rows.length?rows.map(r=>`<tr>
    <td><b>${esc(r.cd)}</b></td><td>${esc(r.nm)}</td><td>${esc(r.owner)||'-'}</td>
    <td>${esc(r.biz)||'-'}</td><td>${esc(r.class)||'-'}</td><td>${roleBadges(r.roles)}</td>
    <td class="center"><span class="bdg ${r.useyn==='Y'?'ok':'off'}">${r.useyn==='Y'?'사용':'중지'}</span></td></tr>`).join('')
    :`<tr><td colspan="7" class="empty">결과 없음</td></tr>`;
    c.querySelector('#p-cnt').textContent=`${rows.length}건 표시`;};
  const apply=()=>{const q=c.querySelector('#p-q').value.trim().toLowerCase(),cl=c.querySelector('#p-cls').value;
    render(DB.partners.filter(r=>(!cl||r.class===cl)&&(!q||r.cd.toLowerCase().includes(q)||(r.nm||'').toLowerCase().includes(q)||(r.owner||'').toLowerCase().includes(q))));};
  c.querySelector('#p-go').onclick=apply;c.querySelector('#p-q').onkeyup=e=>{if(e.key==='Enter')apply();};
  c.querySelector('#p-cls').onchange=apply;c.querySelector('#p-reset').onclick=()=>{c.querySelector('#p-q').value='';c.querySelector('#p-cls').value='';apply();};
  render(DB.partners);
};

/* BOM 조회 */
/* 협력사 > 거래명세서 발행 (레거시 w_pr_outside_420) — 협력사가 요청수량에 납품수량 입력·완성분 체크 → 송장발행 → 거래명세표(SET바코드) 인쇄.
   날짜 기본 월1일~당일. 여러 도번을 하나의 SET바코드로 묶음. 바코드=순수JS Code39(외부라이브러리 없음). */

/* 기준정보 관리 > LG BOM 조회 (nx.lg_bom, LG 원본 BOM Explosion) — 모델(완제품) 검색 → 전 레벨 트리 전개. 읽기전용. */
SCREEN.lgbomview=(c)=>{
  const API=API_BASE;
  const won=v=>(v==null||v==='')?'':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:4});
  const WK={DMZ:"DMZ(SAC)",DGZ:"DGZ(RAC)"};
  let st={q:"",werks:"",models:[],sel:null,modelnm:"",tree:[],msortKey:"",msortDir:1,loading:false,tloading:false,uploading:false,upmsg:""};
  const doUpload=async(f)=>{if(!f)return;
    if(!/\.(xlsx|xls)$/i.test(f.name||"")){st.upmsg="❌ 엑셀 파일(.xlsx/.xls)만 업로드할 수 있습니다";draw();return;}
    st.uploading=true;st.upmsg="";draw();
    try{const fd=new FormData();fd.append("file",f);
      const r=await fetch(`${API}/api/lgbom/upload`,{method:"POST",body:fd});
      let j={};try{j=await r.json();}catch(e){}
      if(r.ok&&j.ok){st.upmsg=`✅ 업로드 완료 — ${won(j.rows)}행 · 모델 ${(j.models||[]).length}개 적재 (${(j.models||[]).join(", ").slice(0,70)})`;st.q=(j.models||[])[0]||st.q;st.uploading=false;await search();return;}
      else{st.upmsg="❌ 업로드 실패: "+(j.detail||("HTTP "+r.status));}
    }catch(e){st.upmsg="❌ 업로드 오류: "+e.message;}
    st.uploading=false;draw();};
  const search=async()=>{st.loading=true;st.sel=null;st.tree=[];draw();
    try{const r=await fetch(`${API}/api/lgbom/search?q=${encodeURIComponent(st.q)}&werks=${st.werks}`);
      const j=await r.json();st.models=j.rows||[];}catch(e){st.models=[];}
    st.loading=false;draw();};
  const openTree=async(m)=>{st.sel=m;st.tree=[];st.tloading=true;draw();
    try{const r=await fetch(`${API}/api/lgbom/tree?model=${encodeURIComponent(m.model)}&werks=${encodeURIComponent(m.werks)}`);
      const j=await r.json();st.modelnm=j.modelnm||"";st.tree=buildTree(j.rows||[],m.model);}catch(e){st.tree=[];}
    st.tloading=false;draw();};
  // parent_code→child_code 로 트리 조립 후 DFS 평탄화(depth 포함)
  const buildTree=(rows,model)=>{
    const byParent={};rows.forEach(r=>{(byParent[r.parent_code]=byParent[r.parent_code]||[]).push(r);});
    const out=[],seen=new Set();
    const walk=(pc,depth)=>{const kids=byParent[pc]||[];
      kids.sort((a,b)=>String(a.posnr||"").localeCompare(String(b.posnr||""),"ko",{numeric:true}));
      kids.forEach(k=>{const key=k.id;if(seen.has(key))return;seen.add(key);
        out.push({...k,depth});walk(k.child_code,depth+1);});};
    walk(model,0);
    // 트리에 안 걸린 나머지(부모 미연결)는 stufe순 부록
    rows.forEach(r=>{if(!seen.has(r.id)){seen.add(r.id);out.push({...r,depth:(r.stufe||1)-1,orphan:true});}});
    return out;};
  const draw=()=>{
    if(st.msortKey){const k=st.msortKey,d=st.msortDir||1;st.models.sort((a,b)=>{const x=a[k],y=b[k],nx=parseFloat(x),ny=parseFloat(y);if(x!=null&&y!=null&&!isNaN(nx)&&!isNaN(ny))return(nx-ny)*d;return String(x==null?"":x).localeCompare(String(y==null?"":y),"ko")*d;});}
    const totq=st.tree.reduce((a,r)=>a+(+r.qty||0),0);
    c.innerHTML=`
     <div class="page-title">LG BOM 관리 <span style="font-size:12px;color:var(--muted);font-weight:400">조회 + 엑셀 업로드(신규 BOM 등록 전 사전적재)</span></div>
     <div class="toolbar">
       <label class="tl">모델/품번</label><input class="inp" id="lb-q" value="${esc(st.q)}" placeholder="모델/품번 검색" style="width:220px">
       <label class="tl" style="margin-left:8px">공장</label><select class="inp" id="lb-wk"><option value="">전체</option><option value="DMZ" ${st.werks==="DMZ"?"selected":""}>DMZ(SAC)</option><option value="DGZ" ${st.werks==="DGZ"?"selected":""}>DGZ(RAC)</option></select>
       <button class="btn" id="lb-go">🔍 조회</button>
       <div class="spacer"></div>
       <span id="lb-drop" title="엑셀 파일을 여기로 끌어다 놓거나 클릭하세요" style="border:2px dashed #1c7c3a;border-radius:8px;padding:14px 30px;min-width:560px;text-align:center;background:#eaf7ef;color:#1c7c3a;font-size:13px;font-weight:600;white-space:nowrap;cursor:pointer">엑셀을 여기로 <b>드래그&드롭</b></span>
       <input type="file" id="lb-file" accept=".xlsx,.xls" style="display:none">
       <button class="btn" id="lb-upload" style="background:#1c7c3a;color:#fff"${st.uploading?' disabled':''}>${st.uploading?'업로드중…':'⬆ LG BOM 업로드'}</button>
       <button class="btn xls" id="lb-xls">⬇ 엑셀</button>
     </div>
     ${st.upmsg?`<div class="page-sub" style="color:${st.upmsg.startsWith('✅')?'#1c7c3a':'#c0392b'};font-weight:600">${esc(st.upmsg)}</div>`:''}
     <div style="display:flex;gap:10px;align-items:flex-start">
      <div class="panel" style="flex:0 0 380px;min-width:0"><div class="panel-h">모델 ${st.loading?"(조회중…)":`(${st.models.length})`}</div><div class="panel-b" style="padding:0">
       <div class="grid-wrap" style="max-height:560px;overflow:auto"><table class="tbl" style="white-space:nowrap"><thead><tr>
         <th data-key="model">모델</th><th class="center" data-key="werks">공장</th><th class="num" data-key="child_cnt">구성수</th></tr></thead>
       <tbody>${st.models.map(m=>`<tr class="rowsel ${st.sel&&st.sel.model===m.model&&st.sel.werks===m.werks?'on':''}" data-m="${esc(m.model)}" data-w="${esc(m.werks)}" style="cursor:pointer">
         <td><b>${esc(m.model)}</b>${m.modelnm?`<div class="cap" style="font-size:11px;color:var(--muted);max-width:230px;overflow:hidden;text-overflow:ellipsis" title="${esc(m.modelnm)}">${esc(m.modelnm)}</div>`:""}</td>
         <td class="center">${WK[m.werks]||m.werks}</td><td class="num">${m.child_cnt}</td></tr>`).join("")||`<tr><td colspan="3" style="padding:16px;color:var(--muted)">${st.loading?"":"조회 결과 없음 — 상위품번으로 검색"}</td></tr>`}
       </tbody></table></div></div></div>
      <div class="panel" style="flex:1;min-width:0"><div class="panel-h">BOM 전개 ${st.sel?`— ${esc(st.sel.model)} ${st.modelnm?"("+esc(st.modelnm)+")":""}`:""} ${st.tloading?"(전개중…)":st.tree.length?`(${st.tree.length}행)`:""}</div><div class="panel-b" style="padding:0">
       ${st.sel?`<div class="grid-wrap" style="max-height:560px;overflow:auto"><table class="tbl" style="white-space:nowrap"><thead><tr>
         <th class="center">Lv</th><th>자재코드</th><th>품명</th><th>규격</th><th class="num">수량</th><th class="center">단위</th><th class="center">공급</th><th class="center">최하위</th><th class="center">상태</th><th class="center">유효기간</th></tr></thead>
       <tbody>${st.tree.map(r=>{const ind=(r.depth||0);const lf=r.lowest_flg==='Y';return `<tr${r.orphan?' style="opacity:.6"':''}>
         <td class="center">${(r.stufe!=null?r.stufe:ind+1)}</td>
         <td style="padding-left:${8+ind*16}px">${ind>0?'<span style="color:#b7c9e6">└ </span>':''}<b>${esc(r.child_code)}</b></td>
         <td class="cap" style="max-width:190px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.child_desc||r.nx_desc||"")}">${esc(r.child_desc||r.nx_desc||"")}</td>
         <td class="cap" style="max-width:220px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.child_spec||"")}">${esc(r.child_spec||"")}</td>
         <td class="num">${won(r.qty)}</td><td class="center">${esc(r.unit||"")}</td><td class="center">${esc(r.supply_type||"")}</td>
         <td class="center">${lf?'<span style="color:#1f7a3d;font-weight:700">Y</span>':''}</td>
         <td class="center cap" style="max-width:110px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.mmsta||"")}">${esc(r.mmsta||"")}</td>
         <td class="center" style="font-size:11px;color:var(--muted)">${esc(r.valid_from||"")}~${esc(r.valid_to||"")}</td></tr>`;}).join("")||`<tr><td colspan="10" style="padding:16px;color:var(--muted)">${st.tloading?"":"구성 없음"}</td></tr>`}
       <tr class="grandtot"><td colspan="4" class="center">구성 ${st.tree.length}행</td><td class="num">${won(totq)}</td><td colspan="5"></td></tr>
       </tbody></table></div>`:'<div style="padding:24px;color:var(--muted);text-align:center">← 좌측 모델을 선택하면 BOM 트리가 전개됩니다</div>'}
       </div></div>
     </div>`;
    const g=id=>c.querySelector(id);
    const q=g("#lb-q");q.oninput=x=>st.q=x.target.value;q.onkeydown=x=>{if(x.key==="Enter")search();};
    g("#lb-wk").onchange=x=>st.werks=x.target.value;g("#lb-go").onclick=search;
    const fe=g("#lb-file"),ub=g("#lb-upload"),dz=g("#lb-drop");
    if(ub&&fe){ub.onclick=()=>fe.click();fe.onchange=()=>{doUpload(fe.files&&fe.files[0]);fe.value="";};}
    {const xb=g("#lb-xls");if(xb)xb.onclick=()=>{
      if(st.sel&&st.tree.length){
        const hd=['Lv','자재코드','품명','규격','수량','단위','공급','최하위','상태','유효시작','유효종료'];
        const out=st.tree.map(r=>[(r.stufe!=null?r.stufe:(r.depth||0)+1),r.child_code,(r.child_desc||r.nx_desc||''),(r.child_spec||''),(r.qty==null?'':r.qty),(r.unit||''),(r.supply_type||''),(r.lowest_flg==='Y'?'Y':''),(r.mmsta||''),(r.valid_from||''),(r.valid_to||'')]);
        downloadCSV(`LGBOM_${st.sel.model}.csv`,hd,out);
      }else if(st.models.length){
        const hd=['모델','품명','공장','구성수'];
        const out=st.models.map(m=>[m.model,(m.modelnm||''),(WK[m.werks]||m.werks),m.child_cnt]);
        downloadCSV('LGBOM_모델목록.csv',hd,out);
      }else alert('내보낼 데이터가 없습니다 — 먼저 조회하세요.');
    };}
    if(dz&&fe){dz.onclick=()=>fe.click();
      dz.ondragover=e=>{e.preventDefault();dz.style.background="#e3f0ff";dz.style.borderColor="#1c7c3a";dz.style.color="#1c7c3a";};
      dz.ondragleave=()=>{dz.style.background="#f4f9fe";dz.style.borderColor="#8fb4d6";dz.style.color="#5a7597";};
      dz.ondrop=e=>{e.preventDefault();dz.style.background="#f4f9fe";dz.style.borderColor="#8fb4d6";dz.style.color="#5a7597";const f=e.dataTransfer.files&&e.dataTransfer.files[0];if(f)doUpload(f);};}
    c.querySelectorAll("tr.rowsel").forEach(tr=>tr.onclick=()=>{const m=st.models.find(v=>v.model===tr.dataset.m&&v.werks===tr.dataset.w);if(m)openTree(m);});
    c.querySelectorAll("thead th").forEach(th=>{addResizer(th);const k=th.dataset.key;if(k){th.style.cursor="pointer";th.title="더블클릭 정렬·경계드래그 너비조절";th.ondblclick=()=>{st.msortDir=(st.msortKey===k&&st.msortDir===1)?-1:1;st.msortKey=k;draw();};}});
  };
  draw();
};

SCREEN.bom=(c)=>{
  const b=DB.bomExample;
  c.innerHTML=`<div class="page-title">🧬 BOM 조회</div>
   <div class="page-sub">3축 분리(자재/공정/조달) · 리비전 이력 · 재귀 무제한 depth</div>
   <div class="panel"><div class="panel-h">완제품 <span class="bdg PROD">완제품</span></div><div class="panel-b">
     <dl class="kv"><dt>품목코드</dt><dd>${esc(b.parent)}</dd><dt>품명</dt><dd>${esc(b.parent_nm)}</dd></dl></div></div>
   <div class="split">
     <div class="panel"><div class="panel-h">📌 BOM 리비전 (이력)</div><div class="panel-b" style="padding:0">
       <table class="tbl"><thead><tr><th class="center">Rev</th><th>유효시작</th><th>유효종료</th><th class="center">상태</th></tr></thead>
       <tbody>${b.revisions.map(r=>`<tr><td class="center"><b>${r.rev}</b></td><td>${esc(r.vf)||'-'}</td>
         <td>${esc(r.vt)||'-'}</td><td class="center"><span class="bdg ${r.status==='ACTIVE'?'ok':'off'}">${r.status}</span></td></tr>`).join('')}</tbody></table></div></div>
     <div class="panel"><div class="panel-h">ℹ️ 설계 포인트</div><div class="panel-b">
       <dl class="kv"><dt>구성 수</dt><dd>${b.comps.length} 건</dd>
         <dt>사급 구성</dt><dd>${b.comps.filter(x=>x.sagub==='Y').length} 건</dd>
         <dt>이력</dt><dd>리비전 ${b.revisions.length}개 — 스냅샷 대체</dd></dl>
       <div class="recon">같은 BOM이라도 <b>생산경로(Route)</b>에 따라 손익이 분리됩니다.</div></div></div></div>
   <div class="panel"><div class="panel-h">🧩 BOM 구성 (최신 리비전)</div><div class="panel-b" style="padding:0">
     <div class="grid-wrap" style="max-height:460px"><table class="tbl"><thead><tr>
       <th class="center">순번</th><th>자재코드</th><th>자재명</th><th>유형</th><th class="num">소요량</th><th class="center">단위</th><th class="center">사급</th>
     </tr></thead><tbody>${b.comps.map(x=>`<tr><td class="center">${x.seq}</td><td><b>${esc(x.cd)}</b></td>
       <td>${esc(x.nm)}</td><td>${tbadge(x.type)}</td><td class="num qty">${won(x.qty)}</td>
       <td class="center">${esc(x.uom)}</td><td class="center">${x.sagub==='Y'?'<span class="bdg sagub">사급</span>':'-'}</td></tr>`).join('')}
     </tbody></table></div></div></div>`;
};

/* 개발 > 원가엔진 검증(라이브) — 레거시 SP(실원가용) vs nx 원가엔진 성분별 대조.
   nx_cost_engine(검증완료: 재료90%·가공100%·실원가≤5%100%·손익 end-to-end)를 app.py /api/cost/compare로 라이브 호출. */

/* 기준정보 > 품목 BOM 조회 — 품목BOM관리와 동일 UI, 읽기전용(편집/저장/복사 비노출) */
SCREEN.bomview=(c)=>SCREEN.unifybom(c,true);

/* ===== 도면/문서 관리 — 탭 통합(설계도면 / 품목시방). 조회+관리 = 권한 분기 ===== */
SCREEN.docmgr=(c)=>{
  const TABS=[['dwg','📐 설계도면'],['itemspec','📎 품목시방']];
  let tab='dwg';
  c.innerHTML=`<div id="dm-tabs" style="display:flex;gap:4px;padding:6px 0 0;border-bottom:2px solid #dce3ee;margin-bottom:10px"></div><div id="dm-body"></div>`;
  const tb=c.querySelector('#dm-tabs'), body=c.querySelector('#dm-body');
  const draw=()=>{
    tb.innerHTML=TABS.map(t=>`<button class="btn ${tab===t[0]?'':'ghost'}" data-tab="${t[0]}" style="border-radius:8px 8px 0 0;${tab===t[0]?'background:#1c47a0;color:#fff':''}">${t[1]}</button>`).join('');
    tb.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{if(tab!==b.dataset.tab){tab=b.dataset.tab;draw();}});
    if(tab==='dwg')SCREEN.drawingdoc(body); else SCREEN.itemspec(body);
  };
  draw();
};

/* ===== 설계도면조회 (w_pr_master_200) — 도면 조회·다운로드·업로드. nx.doc+레거시blob ===== */
SCREEN.drawingdoc=(host)=>{
  const API=API_BASE;
  const st={rows:[],cnt:0,item:'',loading:false,msg:'',file:null};
  const fmt=b=>b>=1048576?(b/1048576).toFixed(1)+'MB':(b>0?(b/1024).toFixed(0)+'KB':'-');
  const load=async()=>{
    st.loading=true;render();   // ★빈 품번=전체 최근 파일 조회(브라우즈)
    try{const r=await fetch(`${API}/api/doc/list?item_code=${encodeURIComponent(st.item.trim())}`);const j=await r.json();st.rows=j.rows||[];st.cnt=j.cnt||0;st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.rows=[];}
    st.loading=false;render();
  };
  const upload=async()=>{
    if(!st.item.trim()){alert('품번을 먼저 입력/조회하세요');return;}
    if(!st.file){alert('업로드할 파일을 선택하세요');return;}
    const fd=new FormData();fd.append('file',st.file);fd.append('doc_kind','GENERAL_DWG');fd.append('item_code',st.item.trim());
    fd.append('user',(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹사용자'));
    st.msg='업로드 중...';render();
    try{const r=await fetch(`${API}/api/doc/upload`,{method:'POST',body:fd});const j=await r.json();
      if(j.ok){st.msg=`✅ 일반도면 업로드 완료 (${fmt(j.size)})`;st.file=null;await load();}else{st.msg='';alert('업로드 실패: '+(j.detail||JSON.stringify(j)));}}
    catch(e){st.msg='';alert('업로드 오류: '+e);}
  };
  const dl=(r)=>{const base=`${API}/api/doc/download?src=${encodeURIComponent(r.src)}&key=${encodeURIComponent(r.key)}`;
    window.open(base+'&disp=inline','_blank');   // 열기(브라우저 뷰)
    const a=document.createElement('a');a.href=base+'&disp=attach';a.download=r.filename||'';document.body.appendChild(a);a.click();setTimeout(()=>a.remove(),1500);};  // 다운로드 동시
  const del=async(r)=>{if(!confirm(r.filename+' 를 삭제할까요?'))return;
    try{const rr=await fetch(`${API}/api/doc/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({doc_id:+r.key})});const j=await rr.json();
      if(j.ok){st.msg='🗑 삭제완료';await load();}else alert('삭제 불가:\n'+(j.errors||[]).join('\n'));}
    catch(e){alert('삭제 오류: '+e);}
  };
  const render=()=>{
    const ed=(typeof PERM!=='undefined')?PERM.canEdit('drawingdoc'):true;
    host.innerHTML=`
     <div class="page-title">📐 설계도면조회 <span style="font-size:12px;color:var(--muted);font-weight:400">도면 파일 조회·다운로드·업로드 · w_pr_master_200</span></div>
     <div class="page-sub">품번별 도면. <b>일반도면=개발(업로드·삭제 가능)</b> · <b>시방도면=품질(시방변경관리에서 업로드/삭제)</b>. 신규 저장=NAS(현재 <code>F:\\NEW_ERP_FILES</code>), 기존은 레거시 blob 다운로드.</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <label class="tl">품번·파일명</label><input class="inp" id="dd-item" value="${esc(st.item)}" placeholder="품번/파일명 검색 (빈칸=전체 최근)" style="width:230px">
       <button class="btn" id="dd-go">🔍 조회</button>
       ${ed?`<div class="spacer"></div><label class="tl">일반도면 업로드</label><input type="file" id="dd-file" style="width:210px"><button class="btn" id="dd-up" style="background:#1c47a0;color:#fff">⬆ 업로드</button>`:`<div class="spacer"></div><span style="color:#c0392b;font-size:12px">🔒 업로드 권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span>`}
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')||st.msg.includes('오류')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     <div class="toolbar" style="margin-top:2px"><span class="rowcount">${won(st.cnt)}건${st.item.trim()?'':' — 품번을 조회하세요'}</span></div>
     <div class="grid-wrap" style="max-height:calc(100vh - 320px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr>
        <th>구분</th><th>파일명</th><th>시방관리번호</th><th>수정자</th><th>파일일시</th><th class="num">크기</th><th class="center">다운로드</th>${ed?'<th class="center">삭제</th>':''}</tr></thead>
      <tbody>${st.loading?spinRow(ed?8:7):(st.rows.length?st.rows.map((r,i)=>`<tr>
        <td><span class="bdg ${r.kind==='GENERAL_DWG'?'ok':'off'}">${esc(r.kind_nm)}</span></td>
        <td class="cap" title="${esc(r.filename)}" style="max-width:260px;overflow:hidden;text-overflow:ellipsis"><b>${esc(r.filename)}</b></td>
        <td>${esc(r.spec_no||r.rev||'')}</td><td>${esc(r.user)}</td><td class="mut">${esc(String(r.dt||'').slice(0,19).replace('T',' '))}</td>
        <td class="num">${fmt(r.size)}</td>
        <td class="center"><button class="btn dd-dl" data-i="${i}" style="padding:1px 8px">⬇</button></td>
        ${ed?`<td class="center">${r.editable?`<button class="btn dd-del" data-i="${i}" style="padding:1px 6px;color:#c0392b">🗑</button>`:'<span class="mut" style="font-size:10px" title="시방도면은 시방변경관리에서 삭제">시방</span>'}</td>`:''}</tr>`).join(''):`<tr><td colspan="${ed?8:7}" class="empty">${st.item.trim()?'검색 결과 없음':'🔍 조회를 누르면 최근 파일이 표시됩니다 (품번·파일명으로 검색)'}</td></tr>`)}</tbody></table></div>`;
    const g=id=>host.querySelector(id);
    g('#dd-go').onclick=()=>{st.item=g('#dd-item').value;load();};
    g('#dd-item').onkeyup=e=>{if(e.key==='Enter')g('#dd-go').click();};
    if(ed){
      const fe=g('#dd-file');if(fe)fe.onchange=e=>{st.file=e.target.files[0]||null;};
      const ub=g('#dd-up');if(ub)ub.onclick=upload;
    }
    host.querySelectorAll('.dd-dl').forEach(b=>b.onclick=()=>dl(st.rows[+b.dataset.i]));
    host.querySelectorAll('.dd-del').forEach(b=>b.onclick=()=>del(st.rows[+b.dataset.i]));
    attachResizers(host);
  };
  load();   // ★열자마자 최근 도면(일반+시방) 자동조회
};

/* ===== 품목시방관리 (w_pr_master_210) — 시방PPT(PR_M_SIBANG)+품목첨부14종(PR_M_ITEM_BLOB)+nx.doc ===== */
SCREEN.itemspec=(host)=>{
  const API=API_BASE;
  const st={rows:[],cnt:0,item:'',loading:false,msg:'',file:null};
  const fmt=b=>b>=1048576?(b/1048576).toFixed(1)+'MB':(b>0?(b/1024).toFixed(0)+'KB':'-');
  const load=async()=>{   // ★빈 품번=전건 브라우즈(레거시 동일)
    st.loading=true;render();
    try{const r=await fetch(`${API}/api/itemspec/list?item_code=${encodeURIComponent(st.item.trim())}`);const j=await r.json();st.rows=j.rows||[];st.cnt=j.cnt||0;st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.rows=[];}
    st.loading=false;render();
  };
  const upload=async()=>{
    if(!st.item.trim()){alert('품번을 먼저 입력/조회하세요');return;}
    if(!st.file){alert('업로드할 파일을 선택하세요');return;}
    const fd=new FormData();fd.append('file',st.file);fd.append('doc_kind','ITEM_ATTACH');fd.append('item_code',st.item.trim());
    fd.append('user',(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹사용자'));
    st.msg='업로드 중...';render();
    try{const r=await fetch(`${API}/api/doc/upload`,{method:'POST',body:fd});const j=await r.json();
      if(j.ok){st.msg=`✅ 첨부 업로드 완료 (${fmt(j.size)})`;st.file=null;await load();}else{st.msg='';alert('업로드 실패: '+(j.detail||JSON.stringify(j)));}}
    catch(e){st.msg='';alert('업로드 오류: '+e);}
  };
  const dl=(r)=>{const base=`${API}/api/doc/download?src=${encodeURIComponent(r.src)}&key=${encodeURIComponent(r.key)}`;
    window.open(base+'&disp=inline','_blank');
    const a=document.createElement('a');a.href=base+'&disp=attach';a.download=r.filename||'';document.body.appendChild(a);a.click();setTimeout(()=>a.remove(),1500);};
  const del=async(r)=>{if(!confirm(r.filename+' 를 삭제할까요?'))return;
    try{const rr=await fetch(`${API}/api/doc/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({doc_id:+r.key})});const j=await rr.json();
      if(j.ok){st.msg='🗑 삭제완료';await load();}else alert('삭제 불가:\n'+(j.errors||[]).join('\n'));}
    catch(e){alert('삭제 오류: '+e);}
  };
  const render=()=>{
    const ed=(typeof PERM!=='undefined')?PERM.canEdit('itemspec'):true;
    host.innerHTML=`
     <div class="page-title">📎 품목시방관리 <span style="font-size:12px;color:var(--muted);font-weight:400">품목 시방(PPT)·첨부문서 · w_pr_master_210</span></div>
     <div class="page-sub">품번별 첨부문서. <b>시방(PPT)</b>=DRAWING.PR_M_SIBANG · <b>품목첨부 14종</b>(Q-map·QC공정도·XRF·작업표준서·검사성적서·도면 등, PR010) · 신규=nx.doc(<code>F:\\NEW_ERP_FILES</code>). 기존은 레거시 blob 다운로드.</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <label class="tl">품목번호</label><input class="inp" id="is-item" value="${esc(st.item)}" placeholder="품번" style="width:200px">
       <button class="btn" id="is-go">🔍 조회</button>
       ${ed?`<div class="spacer"></div><label class="tl">첨부 업로드</label><input type="file" id="is-file" style="width:210px"><button class="btn" id="is-up" style="background:#1c47a0;color:#fff">⬆ 업로드</button>`:`<div class="spacer"></div><span style="color:#c0392b;font-size:12px">🔒 업로드 권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span>`}
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')||st.msg.includes('오류')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     <div class="toolbar" style="margin-top:2px"><span class="rowcount">${won(st.cnt)}건${st.item.trim()?'':' — 품번을 조회하세요'}</span></div>
     <div class="grid-wrap" style="max-height:calc(100vh - 320px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr>
        <th>첨부유형</th><th>파일명</th><th>수정자</th><th>파일일시</th><th class="num">크기</th><th class="center">다운로드</th>${ed?'<th class="center">삭제</th>':''}</tr></thead>
      <tbody>${st.loading?spinRow(ed?7:6):(st.rows.length?st.rows.map((r,i)=>`<tr>
        <td><span class="bdg ${r.editable?'ok':'off'}">${esc(r.atype_nm)}</span></td>
        <td class="cap" title="${esc(r.filename)}" style="max-width:280px;overflow:hidden;text-overflow:ellipsis"><b>${esc(r.filename)}</b></td>
        <td>${esc(r.user)}</td><td class="mut">${esc(String(r.dt||'').slice(0,19).replace('T',' '))}</td>
        <td class="num">${fmt(r.size)}</td>
        <td class="center"><button class="btn is-dl" data-i="${i}" style="padding:1px 8px">⬇</button></td>
        ${ed?`<td class="center">${r.editable?`<button class="btn is-del" data-i="${i}" style="padding:1px 6px;color:#c0392b">🗑</button>`:'<span class="mut" style="font-size:10px" title="레거시 첨부는 레거시에서 관리">레거시</span>'}</td>`:''}</tr>`).join(''):`<tr><td colspan="${ed?7:6}" class="empty">${st.item.trim()?'첨부 없음':'품목번호를 조회하세요'}</td></tr>`)}</tbody></table></div>`;
    const g=id=>host.querySelector(id);
    g('#is-go').onclick=()=>{st.item=g('#is-item').value;load();};
    g('#is-item').onkeyup=e=>{if(e.key==='Enter')g('#is-go').click();};
    if(ed){
      const fe=g('#is-file');if(fe)fe.onchange=e=>{st.file=e.target.files[0]||null;};
      const ub=g('#is-up');if(ub)ub.onclick=upload;
    }
    host.querySelectorAll('.is-dl').forEach(b=>b.onclick=()=>dl(st.rows[+b.dataset.i]));
    host.querySelectorAll('.is-del').forEach(b=>b.onclick=()=>del(st.rows[+b.dataset.i]));
    attachResizers(host);
  };
  load();   // ★열자마자 전체 시방 자동조회
};

/* ===== 기준정보: 기준 마스터 관리 (부서·라인·조립공정·단품공정 + 달력3종, 라이브 조회) — 생산팀 요청 ===== */
SCREEN.basemaster=(c)=>{
  const API=API_BASE;
  const TABS=[{k:'partner',t:'거래처 마스터'},{k:'dept',t:'부서 마스터'},{k:'line',t:'라인 마스터'},{k:'assem',t:'조립공정 마스터'},{k:'proc',t:'단품공정 마스터'},
              {k:'partmaster',t:'파트 마스터'},{k:'cal_line',t:'라인별달력',cal:1},{k:'cal_part',t:'공장운영 달력관리',cal:1}];
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  let kind='partner', q='', data={headers:[],rows:[],cnt:0,title:'',table:''}, loading=false, msg='';
  let cal={ent:'',from:iso(new Date(T.getTime()-30*864e5)),to:iso(new Date(T.getTime()+30*864e5))};
  let sortIdx=-1, sortDir=1;
  const isCal=()=>!!(TABS.find(t=>t.k===kind)||{}).cal;
  const numCol=h=>/정렬|ST|UPH|리드|시각/.test(h);
  const load=async()=>{
    if(kind==='partner'||kind==='partmaster'||MST_CFG[kind]||kind==='cal_line'||kind==='cal_work'||kind==='cal_part'){draw();return;}
    loading=true;draw();
    try{
      if(isCal()){const qs=new URLSearchParams({kind,ent:cal.ent,from_ymd:cal.from,to_ymd:cal.to});
        const r=await fetch(`${API}/api/basemaster/cal?${qs}`);data=await r.json();}
      else{const r=await fetch(`${API}/api/basemaster/list?kind=${kind}&q=${encodeURIComponent(q)}`);data=await r.json();}
      msg='';}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010';data={headers:[],rows:[],cnt:0};}
    loading=false;draw();};
  const wsBadge=w=>w==='근무'?'<span class="bdg ok">근무</span>':(w==='휴무'?'<span class="bdg" style="background:#f4d3d3;color:#a33">휴무</span>':`<span class="bdg" style="background:#eee;color:#777">기타</span>`);
  const draw=()=>{
    if(kind==='partmaster'){   // 파트 마스터(PR_M_PROC_GAGONG)를 탭으로 편입 — SCREEN.partmaster 재사용
      c.innerHTML=`<div class="toolbar" style="gap:4px;flex-wrap:wrap;margin-bottom:4px">${TABS.map(t=>`<button class="btn ${kind===t.k?'':'ghost'}" data-k="${t.k}" style="${kind===t.k?'background:#1c47a0;color:#fff':''}">${t.t}</button>`).join('')}</div><div id="bm-pm"></div>`;
      c.querySelectorAll('[data-k]').forEach(b=>b.onclick=()=>{kind=b.dataset.k;q='';cal.ent='';sortIdx=-1;load();});
      SCREEN.partmaster(c.querySelector('#bm-pm'));
      return;
    }
    if(kind==='partner'||MST_CFG[kind]){
      const isP=kind==='partner', cfg=MST_CFG[kind];
      const nm=isP?'거래처':cfg.title, org=isP?'nx.cust':(cfg.org||('nx.'+kind));
      c.innerHTML=`<div class="page-title">🗂️ 기준 마스터 관리 <span style="font-size:12px;color:var(--muted);font-weight:400">${esc(nm)} 유지관리(nx${isP?'·위하고정합':''})</span></div>
       <div class="page-sub">${esc(nm)} <b>등록·수정·삭제</b> · 원장 <code>${esc(org)}</code>(레거시 이관) · 코드→이름 · 권한게이트(PERM)</div>
       <div class="toolbar" style="gap:4px;flex-wrap:wrap">${TABS.map(t=>`<button class="btn ${kind===t.k?'':'ghost'}" data-k="${t.k}" style="${kind===t.k?'background:#1c47a0;color:#fff':''}">${t.t}</button>`).join('')}</div>
       <div id="bm-crud"></div>`;
      c.querySelectorAll('[data-k]').forEach(b=>b.onclick=()=>{kind=b.dataset.k;q='';cal.ent='';sortIdx=-1;load();});
      const host=c.querySelector('#bm-crud');
      if(isP) custMaint(host); else mstCrud(host, cfg);
      return;
    }
    if(kind==='cal_line'){
      c.innerHTML=`<div class="page-title">🗂️ 기준 마스터 관리 <span style="font-size:12px;color:var(--muted);font-weight:400">라인별달력 (LG 라인스케줄)</span></div>
       <div class="page-sub">LG 라인스케줄 엑셀 업로드 → 라인×날짜 가동/잔업 매트릭스 · <b>생산계획 가동캘린더</b>(휴무·잔업 기준) · 드래그&드롭/파일선택 · 기준일 입력</div>
       <div class="toolbar" style="gap:4px;flex-wrap:wrap">${TABS.map(t=>`<button class="btn ${kind===t.k?'':'ghost'}" data-k="${t.k}" style="${kind===t.k?'background:#1c47a0;color:#fff':''}">${t.t}</button>`).join('')}</div>
       <div id="bm-lc"></div>`;
      c.querySelectorAll('[data-k]').forEach(b=>b.onclick=()=>{kind=b.dataset.k;q='';cal.ent='';sortIdx=-1;load();});
      lineCalView(c.querySelector('#bm-lc'));
      return;
    }
    if(kind==='cal_work'||kind==='cal_part'){
      const nm=kind==='cal_work'?'근무 달력관리':'공장운영 달력관리';
      const sub=kind==='cal_work'?'근무팀 가동/휴무 캘린더':'파트별 가동/휴무 캘린더 (공통=근무달력) · PART→파트';
      c.innerHTML=`<div class="page-title">🗂️ 기준 마스터 관리 <span style="font-size:12px;color:var(--muted);font-weight:400">${nm}</span></div>
       <div class="page-sub">${sub} · WORK_STATS(정상/잔업/일요일/휴무) · <b>기본 조회, ✎수정</b> · 권한게이트(PERM)</div>
       <div class="toolbar" style="gap:4px;flex-wrap:wrap">${TABS.map(t=>`<button class="btn ${kind===t.k?'':'ghost'}" data-k="${t.k}" style="${kind===t.k?'background:#1c47a0;color:#fff':''}">${t.t}</button>`).join('')}</div>
       <div id="bm-wc"></div>`;
      c.querySelectorAll('[data-k]').forEach(b=>b.onclick=()=>{kind=b.dataset.k;q='';cal.ent='';sortIdx=-1;load();});
      wcalView(c.querySelector('#bm-wc'), kind==='cal_work'?'work':'part');
      return;
    }
    const cal_=isCal();
    c.innerHTML=`
     <div class="page-title">🗂️ 기준 마스터 관리 <span style="font-size:12px;color:var(--muted);font-weight:400">생산 기준 마스터 조회</span></div>
     <div class="page-sub">거래처·부서·라인·조립/단품공정 + 달력(근무/라인/파트) <b>조회</b>(nx). 원본 <code>${esc(data.table||'')}</code> · 거래처구분=코드마스터 PR011 · 조립/단품 공정 원가편집은 개발›원가/BOM기준정보 · 달력 근무구분 소스=<code>w_pr_plan_020</code>(1·2·5·6=근무, 4=휴무)</div>
     <div class="toolbar" style="gap:4px;flex-wrap:wrap">${TABS.map(t=>`<button class="btn ${kind===t.k?'':'ghost'}" data-k="${t.k}" style="${kind===t.k?'background:#1c47a0;color:#fff':''}">${t.t}</button>`).join('')}</div>
     ${cal_?`<div class="toolbar" style="margin-top:2px">
        <label class="tl">${esc(data.entlbl||'대상')}</label><select class="inp" id="bm-ent" style="min-width:120px"><option value="">전체</option>${(data.ents||[]).map(e=>`<option value="${esc(e)}"${cal.ent===e?' selected':''}>${esc(e)}</option>`).join('')}</select>
        <label class="tl">기간</label><input class="inp" type="date" id="bm-from" value="${cal.from}"> ~ <input class="inp" type="date" id="bm-to" value="${cal.to}">
        <button class="btn" id="bm-cgo">🔍 조회</button>
        <div class="spacer"></div><span class="rowcount">${won(data.cnt)}건 · 근무일 <b>${won(data.work_days)}</b></span>
      </div>`:`<div class="toolbar" style="margin-top:2px">
        <div class="spacer"></div><input class="inp" id="bm-q" value="${esc(q)}" placeholder="코드/명 검색" style="width:160px"><button class="btn" id="bm-go">🔍</button>
        <span class="rowcount" style="margin-left:8px">${won(data.cnt)}건</span></div>`}
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      ${cal_?`<table class="tbl fit" style="font-size:12px"><thead><tr><th>${esc(data.entlbl||'대상')}</th><th class="center">일자</th><th class="center">요일</th><th class="center">근무구분</th><th class="center">코드</th><th>비고</th></tr></thead>
       <tbody>${loading?spinRow(6):((data.rows&&data.rows.length)?data.rows.map(r=>`<tr>
         <td><b>${esc(r.ent)}</b></td><td class="center">${esc(_wymd(r.ymd))}</td><td class="center">${esc(r.weekday)}</td>
         <td class="center">${wsBadge(r.ws_nm)}</td><td class="center" style="color:#8aa0bd">${esc(r.ws)}</td><td>${esc(r.remarks)}</td></tr>`).join(''):`<tr><td colspan="6" class="empty">데이터 없음 (대상/기간을 조정하세요)</td></tr>`)}</tbody></table>`
      :`<table class="tbl fit" style="font-size:12px"><thead><tr>${(data.headers||[]).map(h=>`<th class="${numCol(h)?'num':''}">${esc(h)}</th>`).join('')}</tr></thead>
       <tbody>${loading?spinRow((data.headers||[]).length||5):((data.rows&&data.rows.length)?data.rows.map(row=>`<tr>${row.map((v,i)=>{const h=data.headers[i];return `<td class="${numCol(h)?'num':''}" ${i===1?`title="${esc(v)}" style="max-width:220px;overflow:hidden;text-overflow:ellipsis"`:''}>${i===0?`<b>${esc(v)}</b>`:esc(v)}</td>`;}).join('')}</tr>`).join(''):`<tr><td colspan="${(data.headers||[]).length||5}" class="empty">데이터 없음</td></tr>`)}</tbody></table>`}
     </div>`;
    c.querySelectorAll('[data-k]').forEach(b=>b.onclick=()=>{kind=b.dataset.k;q='';cal.ent='';load();});
    const g=id=>c.querySelector(id);
    if(cal_){
      g('#bm-cgo').onclick=()=>{cal.ent=g('#bm-ent').value;cal.from=g('#bm-from').value;cal.to=g('#bm-to').value;load();};
      g('#bm-ent').onchange=()=>{cal.ent=g('#bm-ent').value;load();};
    }else{
      g('#bm-go').onclick=()=>{q=g('#bm-q').value;load();};
      g('#bm-q').onkeyup=e=>{if(e.key==='Enter'){q=e.target.value;load();}};
    }
    attachResizers(c);   // 헤더 드래그 컬럼폭 조절(UI규칙 #7)
  };
  load();
};

/* ===== 파트 마스터 (w_pr_master_280) — PR_M_PROC_GAGONG 라이브 CRUD. 생산효율=키팅 회수율 ===== */
SCREEN.partmaster=(c)=>{
  const API=API_BASE;
  const st={rows:[],cnt:0,q:'',loading:false,msg:'',edit:null,sel:'',workers:[],wload:false,wmode:'view',wdraft:null};
  const GUBUN=[['W','자재창고'],['P','생산파트'],['V','생산창고'],['Q','가공파트']];
  const loadWorkers=async(part)=>{st.sel=part;st.wload=true;st.workers=[];st.wmode='view';st.wdraft=null;draw();   // 파트별 작업자(레거시 w_pr_master_350 하단)
    try{const r=await fetch(`${API}/api/partmaster/workers?part=${encodeURIComponent(part)}`);st.workers=(await r.json()).rows||[];}
    catch(e){st.workers=[];}st.wload=false;draw();};
  const load=async()=>{st.loading=true;draw();
    try{const r=await fetch(`${API}/api/partmaster/list?${new URLSearchParams({q:st.q})}`);const j=await r.json();st.rows=j.rows||[];st.cnt=j.cnt||0;st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.rows=[];}
    st.loading=false;draw();};
  const save=async()=>{const row=st.edit;if(!row.code||!(''+row.code).trim()){alert('파트코드 필수');return;}
    if(!row.nm||!(''+row.nm).trim()){alert('파트명 필수');return;}
    try{const r=await fetch(`${API}/api/partmaster/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({row,user:(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹')})});
      const j=await r.json();if(j.ok){st.edit=null;st.msg=`✅ 저장(${j.mode==='insert'?'신규':'수정'}) 완료`;await load();}else alert('저장 실패: '+(j.detail||''));}
    catch(e){alert('저장 오류: '+e);}};
  const del=async(code)=>{if(!confirm(`파트 [${code}] 삭제할까요?`))return;
    try{const r=await fetch(`${API}/api/partmaster/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code})});
      const j=await r.json();if(j.ok){st.msg='🗑 삭제 완료';await load();}else alert('삭제 실패: '+(j.detail||''));}
    catch(e){alert('삭제 오류: '+e);}};
  // 파트별 작업자 리스트 통째 편집 (레거시 w_pr_master_350 하단그리드)
  const wEnter=(addBlank)=>{st.wdraft=st.workers.map(w=>({worker:w.worker,real:w.real}));if(addBlank)st.wdraft.push({worker:'',real:true});st.wmode='edit';draw();};
  const wCancel=()=>{st.wmode='view';st.wdraft=null;draw();};
  const wAddRow=()=>{st.wdraft.push({worker:'',real:true});draw();};
  const wRemoveRow=(i)=>{st.wdraft.splice(i,1);draw();};
  const wToggleReal=(i)=>{st.wdraft[i].real=!st.wdraft[i].real;draw();};
  const wSaveAll=async()=>{
    const rows=st.wdraft.map(w=>({worker:(''+(w.worker||'')).trim(),real:!!w.real}));
    if(rows.some(r=>!r.worker)){alert('빈 작업자명이 있습니다');return;}
    const names=rows.map(r=>r.worker);if(new Set(names).size!==names.length){alert('중복 작업자명이 있습니다');return;}
    try{const r=await fetch(`${API}/api/partmaster/worker_save_all`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({part:st.sel,rows,user:(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹')})});
      const j=await r.json();if(j.ok){st.wmode='view';st.wdraft=null;st.msg=`✅ 작업자 저장(추가 ${j.ins}·수정 ${j.upd}·삭제 ${j.del})`;await loadWorkers(st.sel);}else alert('저장 실패: '+(j.detail||''));}
    catch(e){alert('저장 오류: '+e);}};
  const draw=()=>{
    const ed=(typeof PERM!=='undefined')?PERM.canEdit('partmaster'):true;
    c.innerHTML=`
     <div class="page-title">🔧 파트 마스터 <span style="font-size:12px;color:var(--muted);font-weight:400">PR_M_PROC_GAGONG · 생산효율(=키팅 회수율)</span></div>
     <div class="page-sub">파트별 <b>생산효율(회수율)</b>·연동창고·정렬키 관리. 원가·계획·키팅이 공유하는 마스터(nx 편집). <span style="color:#b8860b">노란=생산효율≠100</span></div>
     <div class="toolbar">
       <label class="tl">파트/파트명</label><input class="inp" id="pm-q" value="${esc(st.q)}" placeholder="파트코드/파트명" autocomplete="off" style="width:160px">
       <button class="btn" id="pm-go">🔍 조회</button>
       ${ed?`<button class="btn" id="pm-new" style="background:#1c7c3a;color:#fff">➕ 신규</button>`:`<span style="color:#c0392b;font-size:12px">🔒 조회권한</span>`}
       <div class="spacer"></div><span class="rowcount">${won(st.cnt)}건</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')||st.msg.includes('오류')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     <div style="display:flex;gap:10px;align-items:flex-start">
      <div class="grid-wrap" style="flex:1 1 0;min-width:0;max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
       <table class="tbl fit" style="font-size:12px"><thead><tr>
        <th>작업처</th><th>구분</th><th>파트</th><th>연동창고</th><th class="num">정렬</th><th class="num">생산효율</th><th>파트그룹</th><th class="num">RACK</th><th>최종작업자</th><th>최종시각</th>${ed?'<th class="pmact">수정</th>':''}</tr></thead>
       <tbody>${st.loading?spinRow(11):(st.rows.length?st.rows.map(r=>`<tr class="pm-row${st.sel===r.code?' pm-sel':''}" data-sel="${esc(r.code)}" style="cursor:pointer">
        <td>${esc(r.wcnm||r.wc)}</td><td class="center">${esc(r.gubunnm)}</td><td><b>${esc(r.code)}</b>${r.nm?' <span style="color:#5a6b82">'+esc(r.nm)+'</span>':''}</td>
        <td>${esc(r.whnm||r.wh)}</td><td class="num">${r.sortkey}</td>
        <td class="num" style="${r.rate!=100?'background:#fff8d6;font-weight:700':''}">${r.rate}</td>
        <td class="center">${esc(r.grp)}</td><td class="num">${r.rack}</td>
        <td>${esc(r.uid)}</td><td style="color:#8aa0bd;font-size:11px">${esc(r.udt)}</td>
        ${ed?`<td class="center pmact" style="white-space:nowrap"><button class="btn ghost" data-e="${esc(r.code)}" style="padding:1px 7px">✎</button> <button class="btn ghost" data-d="${esc(r.code)}" style="padding:1px 7px;color:#c0392b">🗑</button></td>`:''}</tr>`).join(''):`<tr><td colspan="11" class="empty">조회 결과 없음</td></tr>`)}</tbody></table></div>
      <div style="flex:1.15 1 0;min-width:420px">
       <div style="display:flex;align-items:center;gap:6px;padding:4px 2px">
        <div style="font-weight:700;font-size:13px;color:#33507d">👷 파트별 작업자 ${st.sel?`— <b style="color:#1c47a0">${esc(st.sel)}</b> <span style="color:#8aa0bd;font-weight:400">${st.wload?'…':(st.wmode==='edit'?st.wdraft.length:st.workers.length)+'명'}</span>`:'<span style="color:#8aa0bd;font-weight:400">— 좌측 파트 클릭</span>'}</div>
        <div style="flex:1"></div>
        ${ed&&st.sel?(st.wmode==='edit'
          ?`<button class="btn" id="pm-waddrow" style="background:#1c7c3a;color:#fff;padding:2px 9px;font-size:12px">➕ 작업자</button>
            <button class="btn" id="pm-wsaveall" style="background:#1c47a0;color:#fff;padding:2px 9px;font-size:12px">💾 저장</button>
            <button class="btn ghost" id="pm-wcancel" style="padding:2px 9px;font-size:12px">취소</button>`
          :`<button class="btn" id="pm-wnew" style="background:#1c7c3a;color:#fff;padding:2px 9px;font-size:12px">➕ 작업자</button>
            <button class="btn" id="pm-wedit" style="padding:2px 9px;font-size:12px">✎ 수정</button>`):''}
       </div>
       <div class="grid-wrap" style="max-height:calc(100vh - 330px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
        ${st.wmode==='edit'
        ?`<table class="tbl fit" style="font-size:12px"><thead><tr><th style="text-align:left">작업자명</th><th class="center" style="width:74px">실작업자</th><th style="width:40px"></th></tr></thead>
          <tbody>${st.wdraft.length?st.wdraft.map((w,i)=>`<tr>
            <td style="text-align:left"><input class="inp pm-wname" data-i="${i}" value="${esc(w.worker)}" maxlength="30" autocomplete="off" placeholder="작업자명" style="width:100%;box-sizing:border-box;font-size:12px;padding:2px 5px"></td>
            <td class="center"><span class="pm-wreal" data-i="${i}" title="클릭하여 실작업자 토글" style="cursor:pointer;font-weight:700;font-size:15px;color:${w.real?'#1c7c3a':'#c8d0dc'}">${w.real?'✔':'—'}</span></td>
            <td class="center"><button class="btn ghost pm-wrm" data-i="${i}" style="padding:1px 6px;color:#c0392b">🗑</button></td></tr>`).join(''):`<tr><td colspan="3" class="empty">작업자 없음 — ➕ 작업자로 추가</td></tr>`}</tbody></table>`
        :`<table class="tbl fit" style="font-size:12px"><thead><tr><th style="text-align:left">작업자</th><th class="center">실작업자</th><th>등록자</th><th>등록시각</th><th>수정자</th><th>수정시각</th></tr></thead>
          <tbody>${st.wload?spinRow(6):(st.workers.length?st.workers.map(w=>`<tr><td style="text-align:left"><b>${esc(w.worker)}</b></td><td class="center">${w.real?'<span style="color:#1c7c3a;font-weight:700">✔</span>':'<span style="color:#c8d0dc">—</span>'}</td><td>${esc(w.ins_user)}</td><td style="font-size:11px;color:#8aa0bd">${esc(w.ins_dt)}</td><td>${esc(w.upd_user)}</td><td style="font-size:11px;color:#8aa0bd">${esc(w.upd_dt)}</td></tr>`).join(''):`<tr><td colspan="6" class="empty">${st.sel?'등록된 작업자 없음':'좌측에서 파트를 선택하세요'}</td></tr>`)}</tbody></table>`}</div>
      </div>
     </div>
     <style>.pm-row:hover{background:#f2f7ff}.pm-row.pm-sel{background:#e7effe!important;outline:2px solid #9cc0f0;outline-offset:-2px}
      .pmact{position:sticky;right:0;background:#fff;box-shadow:-5px 0 6px -4px rgba(10,25,55,.18)}
      thead .pmact{background:#eef2f8;z-index:2}
      .pm-row:hover .pmact{background:#f2f7ff}.pm-row.pm-sel .pmact{background:#e7effe}</style>
     ${st.edit?editModal():''}`;
    const g=id=>c.querySelector(id);
    g('#pm-go').onclick=()=>{st.q=g('#pm-q').value;load();};
    g('#pm-q').onkeyup=e=>{if(e.key==='Enter'){st.q=e.target.value;load();}};
    c.querySelectorAll('.pm-row[data-sel]').forEach(el=>el.onclick=()=>loadWorkers(el.dataset.sel));   // 파트 클릭 → 작업자 로드
    if(ed){
      const nb=g('#pm-new');if(nb)nb.onclick=()=>{st.edit={code:'',nm:'',gubun:'P',wc:'',wh:'Z99990',sortkey:0,rate:100,grp:'',ip:'',rack:0,_new:true};draw();};
      c.querySelectorAll('[data-e]').forEach(b=>b.onclick=(e)=>{e.stopPropagation();const row=st.rows.find(x=>x.code===b.dataset.e);st.edit={...row,_new:false};draw();});
      c.querySelectorAll('[data-d]').forEach(b=>b.onclick=(e)=>{e.stopPropagation();del(b.dataset.d);});
      // 작업자 리스트 편집 버튼
      const wnb=g('#pm-wnew');if(wnb)wnb.onclick=()=>wEnter(true);      // 신규 작업자 → 편집모드+빈행
      const web=g('#pm-wedit');if(web)web.onclick=()=>wEnter(false);    // 수정 → 리스트 통째 편집모드
      const war=g('#pm-waddrow');if(war)war.onclick=wAddRow;
      const wsa=g('#pm-wsaveall');if(wsa)wsa.onclick=wSaveAll;
      const wca=g('#pm-wcancel');if(wca)wca.onclick=wCancel;
      c.querySelectorAll('.pm-wname').forEach(inp=>inp.oninput=()=>{st.wdraft[+inp.dataset.i].worker=inp.value;});  // 재렌더 없이 동기화(포커스 유지)
      c.querySelectorAll('.pm-wreal').forEach(el=>el.onclick=()=>wToggleReal(+el.dataset.i));   // 실작업자 클릭 토글
      c.querySelectorAll('.pm-wrm').forEach(b=>b.onclick=()=>wRemoveRow(+b.dataset.i));
      wireModal();
    }
    attachResizers(c);
  };
  const editModal=()=>{const r=st.edit;
    const f=(lbl,key,attrs='')=>`<label class="tl" style="display:block;margin:6px 0 2px">${lbl}</label><input class="inp" id="pm-f-${key}" value="${esc(r[key]!=null?r[key]:'')}" ${attrs} style="width:100%;box-sizing:border-box">`;
    return `<div style="position:fixed;inset:0;background:rgba(20,40,80,.4);display:flex;align-items:center;justify-content:center;z-index:900">
     <div style="background:#fff;border-radius:12px;padding:20px;width:420px;max-height:90vh;overflow:auto;box-shadow:0 20px 60px rgba(10,25,55,.4)">
       <div style="font-weight:700;font-size:16px;margin-bottom:10px">${r._new?'➕ 파트 신규':'✎ 파트 수정'}</div>
       <label class="tl" style="display:block;margin:6px 0 2px">파트코드 *</label><input class="inp" id="pm-f-code" value="${esc(r.code)}" ${r._new?'':'readonly'} style="width:100%;box-sizing:border-box;${r._new?'':'background:#eef'}">
       ${f('파트명 *','nm')}
       <label class="tl" style="display:block;margin:6px 0 2px">구분</label><select class="inp" id="pm-f-gubun" style="width:100%">${GUBUN.map(([v,n])=>`<option value="${v}"${r.gubun===v?' selected':''}>${n}</option>`).join('')}</select>
       <label class="tl" style="display:block;margin:6px 0 2px">작업처</label><select class="inp" id="pm-f-wc" style="width:100%"><option value="">-</option><option value="P1"${r.wc==='P1'?' selected':''}>용접 (P1)</option><option value="P2"${r.wc==='P2'?' selected':''}>가공 (P2)</option></select>
       ${f('연동창고(코드)','wh')}${f('정렬키','sortkey','type="number"')}
       ${f('★생산효율(회수율 %)','rate','type="number" step="0.1"')}
       ${f('파트그룹','grp')}${f('자동창고IP','ip')}${f('RACK개수','rack','type="number"')}
       <div style="margin-top:14px;text-align:right"><button class="btn ghost" id="pm-cancel">취소</button> <button class="btn" id="pm-save" style="background:#1c47a0;color:#fff">💾 저장</button></div>
     </div></div>`;};
  const wireModal=()=>{if(!st.edit)return;const g=id=>c.querySelector(id);
    ['code','nm','gubun','wc','wh','sortkey','rate','grp','ip','rack'].forEach(k=>{const el=g('#pm-f-'+k);if(el)el.oninput=()=>{st.edit[k]=el.value;};});
    g('#pm-cancel').onclick=()=>{st.edit=null;draw();};
    g('#pm-save').onclick=save;};
  load();
};

/* ===== 기준정보: 생산정보등록 (레거시 w_pr_master_090 우측 3패널 재구현) =====
   품번 검색 → ① 조립(공정수) ② 단품(공정수)=외경별 표준ST 매트릭스 ③ 하단 탭5(LOB·양산준비·지그·수율·생산공정순서).
   조회=라이브 PARTNER_ERP ∪ nx(nx우선), 편집/저장=PARTNER_ERP_TEST3.nx 만. 상세 스펙: _legacy_analysis/ITEM_MASTER_090_ANALYSIS.md */
SCREEN.prodinfo=(c)=>{
  const API=API_BASE;
  const OD_DISPLAY=['4.76','5.00'];                       // 원천 부재 → 표시만/공란
  const OD_MAP={'6.35':'st_635','7.94':'st_794','9.52':'st_952','12.70':'st_127','15.88':'st_1588','19.05':'st_1905','22.20':'st_22','25.40':'st_254','28.00':'st_28'};
  const num=(v,d=3)=>(v==null||v==='')?'':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:d});
  const ed=()=>(typeof PERM!=='undefined')?PERM.canEdit('prodinfo'):true;
  const uname=()=>(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹');
  const st={q:'',results:[],dlrows:[],item:'',data:null,loading:false,msg:'',
            assyall:false,singleEdit:false,tab:'proc',opts:null};

  const post=async(url,body)=>{const r=await fetch(API+url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});return r.json();};
  const flash=(m)=>{st.msg=m;draw();setTimeout(()=>{st.msg='';const el=c.querySelector('#pi-msg');if(el)el.textContent='';},4000);};

  const search=async()=>{st.loading=true;draw();
    try{const r=await fetch(`${API}/api/prodinfo/search?q=${encodeURIComponent(st.q)}`);const j=await r.json();st.results=j.rows||[];}
    catch(e){st.results=[];st.msg='검색 실패';}
    st.loading=false;draw();};
  const loadOpts=async()=>{if(st.opts)return;try{const r=await fetch(`${API}/api/prodinfo/opts`);st.opts=await r.json();}catch(e){st.opts={works:[],parts:[],singles:[],machs:[],jp_methods:{}};}};
  const loadItem=async(it)=>{st.item=it;st.data=null;st.loading=true;draw();
    await loadOpts();
    try{const r=await fetch(`${API}/api/prodinfo/get?item=${encodeURIComponent(it)}&assyall=${st.assyall?1:0}`);
      if(!r.ok){st.msg='로드 실패';st.loading=false;draw();return;}
      st.data=await r.json();st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';}
    st.loading=false;draw();};

  // ---------- 상단 검색 + 헤더 + 패널 셸 ----------
  const draw=()=>{
    const d=st.data, h=d&&d.head;
    c.innerHTML=`
     <style>
      /* UI규칙: 컬럼폭=글자크기(내용폭) · 셀 패딩 축소 · 빈공간 최소화 (SCREEN.prodinfo 한정) */
      #pi-assy .tbl,#pi-single .tbl,#pi-tabs .tbl{width:auto;min-width:0;max-width:100%}
      #pi-assy .tbl th,#pi-assy .tbl td,#pi-single .tbl th,#pi-single .tbl td,#pi-tabs .tbl th,#pi-tabs .tbl td{padding:2px 6px}
      #pi-assy .tbl input.inp,#pi-single .tbl input.inp,#pi-tabs .tbl input.inp{height:24px}
     </style>
     <div class="page-title">⚙️ 생산정보등록 <span style="font-size:12px;color:var(--muted);font-weight:400">품번별 조립·단품 공정 + 생산공정순서 · 레거시 w_pr_master_090</span></div>
     <div class="page-sub">품번 검색 → ① 조립(공정수) ② 하단탭(LOB·양산준비·지그·수율·생산공정순서). 조회·편집/저장=<code>nx</code>(TEST3) · ${ed()?'<span style="color:#1c7c3a">편집권한</span>':'<span style="color:#c0392b">조회권한(읽기)</span>'}</div>
     <div class="toolbar">
       <label class="tl">품번</label><input class="inp" id="pi-q" list="pi-dl" value="${esc(st.q)}" placeholder="품번/품명 타이핑(자동완성)" style="width:230px" autocomplete="off">
       <datalist id="pi-dl">${(st.dlrows||[]).map(r=>`<option value="${esc(r.item)}">${esc(r.item)} · ${esc(r.name)}</option>`).join('')}</datalist>
       <button class="btn" id="pi-go">🔍 검색</button>
       ${st.results.length?`<select class="inp" id="pi-pick" style="min-width:280px"><option value="">— 검색결과 ${st.results.length}건 —</option>${st.results.map(r=>`<option value="${esc(r.item)}"${r.item===st.item?' selected':''}>${esc(r.item)} · ${esc(r.name)}</option>`).join('')}</select>`:''}
       <div class="spacer"></div>
       ${h?`<span class="rowcount">회수율 <b>${num(h.prod_rate,1)}%</b></span>`:''}
     </div>
     ${st.msg?`<div class="page-sub" id="pi-msg" style="color:${/실패|오류|중복|필수/.test(st.msg)?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:'<div id="pi-msg"></div>'}
     ${!h?`<div class="empty" style="padding:30px">${st.loading?'<span class="lspin"></span> 로딩 중…':'품번을 검색하여 선택하세요.'}</div>`:`
      <div class="panel" style="margin-bottom:8px"><div class="panel-b" style="padding:8px 12px;display:flex;gap:18px;flex-wrap:wrap;font-size:13px">
        <span><b style="font-size:15px">${esc(h.item)}</b></span><span>${esc(h.name)}</span>
        <span style="color:var(--muted)">${esc(h.spec||'')}</span>
        <span>외경 <b>${num(h.diam,2)}</b> · 두께 <b>${num(h.thick,2)}</b> · 길이 <b>${num(h.length,1)}</b></span>
        <span>회수율 <b>${num(h.prod_rate,1)}%</b></span></div></div>
      <div style="display:flex;gap:10px;align-items:flex-start">
        <div style="flex:0 1 auto;min-width:300px;max-width:560px" id="pi-assy"></div>
        <div style="flex:1 1 0;min-width:440px;display:flex;flex-direction:column;gap:10px">
          <div id="pi-tabs"></div>
        </div>
      </div>`}`;
    const g=id=>c.querySelector(id);
    g('#pi-go').onclick=()=>{st.q=g('#pi-q').value;search();};
    g('#pi-q').onkeyup=e=>{if(e.key==='Enter'){st.q=e.target.value;search();}};
    // 오토컴플리트: 타이핑 중 서버검색→datalist DOM만 갱신(포커스 유지). datalist 정확선택/엔터 시 loadItem.
    const qEl=g('#pi-q');
    if(qEl){let dlt;qEl.oninput=()=>{const v=qEl.value.trim();st.q=v;
      if(v&&st.dlrows&&st.dlrows.some(r=>r.item===v)&&v!==st.item){loadItem(v);return;}
      clearTimeout(dlt);dlt=setTimeout(async()=>{
        if(!v){st.dlrows=[];const dl=c.querySelector('#pi-dl');if(dl)dl.innerHTML='';return;}
        try{const r=await fetch(`${API}/api/prodinfo/search?q=${encodeURIComponent(v)}`);const j=await r.json();
          st.dlrows=j.rows||[];const dl=c.querySelector('#pi-dl');
          if(dl)dl.innerHTML=st.dlrows.map(rr=>`<option value="${esc(rr.item)}">${esc(rr.item)} · ${esc(rr.name)}</option>`).join('');
        }catch(e){/* 무시(디바운스 다음 입력) */}
      },250);};}
    const pk=g('#pi-pick');if(pk)pk.onchange=()=>{if(pk.value)loadItem(pk.value);};
    if(h){renderAssy();renderTabs();attachResizers(c);}   // ② 단품(공정수) 패널 제거 → ③ 하단탭 상단 배치
  };

  // ---------- 패널① 조립(공정수) ----------
  const renderAssy=()=>{
    const host=c.querySelector('#pi-assy');if(!host)return;
    const rows=st.data.assy;const canEd=ed();
    // 소계: 용접(1)/검사(2,21)/조립(3,31) — 레거시는 1/21/31만 합산(버그). 여기선 전 구분 정합 집계.
    const grp=g=>g==='1'?'weld':(g==='2'||g==='21')?'check':(g==='3'||g==='31')?'assy':'etc';
    let subQty={weld:0,check:0,assy:0,etc:0},subSt={weld:0,check:0,assy:0,etc:0};
    rows.forEach(r=>{const q=+r.work_qty||0,s=q*(+r.work_st||0);const k=grp(r.proc_gubun);subQty[k]+=q;subSt[k]+=s;});
    const totQty=subQty.weld+subQty.check+subQty.assy+subQty.etc, totSt=subSt.weld+subSt.check+subSt.assy+subSt.etc;
    host.innerHTML=`<div class="panel"><div class="panel-h">① 조립(공정수)
       <span style="float:right;font-weight:400;font-size:11px">
        <label style="cursor:pointer"><input type="checkbox" id="pi-assyall" ${st.assyall?'checked':''}> 전체공정(${won(st.data.assy_master_cnt)})</label>
        ${canEd?'<button class="btn" id="pi-assy-save" style="padding:1px 8px;margin-left:6px;background:#1c47a0;color:#fff">💾 저장</button>':''}</span></div>
     <div class="panel-b" style="padding:0"><div class="grid-wrap" style="max-height:300px;overflow:auto">
      <table class="tbl" style="font-size:12px;white-space:nowrap"><thead><tr>
        <th>공정명</th><th class="num">공정수</th><th class="num">표준ST</th><th class="num">ST</th><th class="center">구분</th></tr></thead>
      <tbody>${rows.length?rows.map((r,i)=>`<tr>
        <td>${esc(r.work_desc)}${r.nx_flag?' <span class="bdg ok" style="font-size:9px">nx</span>':''}</td>
        <td class="num">${canEd?`<input class="inp pi-aq" data-i="${i}" type="number" value="${r.work_qty==null?'':r.work_qty}" style="width:44px;min-width:0;text-align:right;padding:1px 3px">`:won(r.work_qty)}</td>
        <td class="num">${num(r.work_st,2)}</td><td class="num pi-ast" data-i="${i}">${num((+r.work_qty||0)*(+r.work_st||0),3)}</td>
        <td class="center">${esc(r.proc_gubun_nm)}</td></tr>`).join(''):`<tr><td colspan="5" class="empty">조립공정 없음</td></tr>`}
      </tbody><tfoot>
        <tr class="grandtot"><td class="center">용접</td><td class="num">${won(subQty.weld)}</td><td></td><td class="num">${num(subSt.weld,3)}</td><td></td></tr>
        <tr class="grandtot"><td class="center">검사</td><td class="num">${won(subQty.check)}</td><td></td><td class="num">${num(subSt.check,3)}</td><td></td></tr>
        <tr class="grandtot"><td class="center">조립</td><td class="num">${won(subQty.assy)}</td><td></td><td class="num">${num(subSt.assy,3)}</td><td></td></tr>
        ${subQty.etc?`<tr class="grandtot"><td class="center">기타</td><td class="num">${won(subQty.etc)}</td><td></td><td class="num">${num(subSt.etc,3)}</td><td></td></tr>`:''}
        <tr class="grandtot" style="font-weight:800"><td class="center">총계</td><td class="num">${won(totQty)}</td><td></td><td class="num">${num(totSt,3)}</td><td></td></tr>
      </tfoot></table></div></div></div>`;
    const ck=host.querySelector('#pi-assyall');if(ck)ck.onchange=()=>{st.assyall=ck.checked;loadItem(st.item);};
    host.querySelectorAll('.pi-aq').forEach(inp=>inp.oninput=()=>{const i=+inp.dataset.i;st.data.assy[i].work_qty=inp.value;
      const cell=host.querySelector(`.pi-ast[data-i="${i}"]`);if(cell)cell.textContent=num((+inp.value||0)*(+st.data.assy[i].work_st||0),3);});
    const sv=host.querySelector('#pi-assy-save');if(sv)sv.onclick=async()=>{
      const payload={item:st.item,user:uname(),rows:st.data.assy.map(r=>({a_work_code:r.a_work_code,work_qty:r.work_qty}))};
      const j=await post('/api/prodinfo/assy/save',payload);if(j.ok){flash(`✅ 조립 저장(${j.saved}건)`);loadItem(st.item);}else flash('저장 실패: '+(j.detail||''));};
    host.querySelectorAll('thead th').forEach(addResizer);
  };

  // ---------- 패널② 단품(공정수) = 외경별 표준ST 매트릭스 ----------
  const renderSingle=()=>{
    const host=c.querySelector('#pi-single');if(!host)return;
    const rows=st.data.single;const canEd=ed();const em=st.singleEdit&&canEd;
    const odReal=(st.data.od_cols||Object.keys(OD_MAP).map(k=>k));  // ['6.35',...]
    const wname=wc=>{const w=(st.opts&&st.opts.works||[]).find(x=>x.code===wc);return w?w.name:wc;};
    host.innerHTML=`<div class="panel"><div class="panel-h">② 단품(공정수) · 외경별 표준ST
       <span style="float:right;font-weight:400;font-size:11px;color:var(--muted)">전사 공유 마스터(PR_M_WORK_SINGLE) · ∅4.76/5.00 원천부재(공란)
        ${canEd?`<button class="btn" id="pi-sg-edit" style="padding:1px 8px;margin-left:6px;${em?'background:#b8860b;color:#fff':''}">${em?'✎ 편집중':'✎ 편집'}</button>${em?'<button class="btn" id="pi-sg-save" style="padding:1px 8px;margin-left:4px;background:#1c47a0;color:#fff">💾 저장</button>':''}`:''}</span></div>
     <div class="panel-b" style="padding:0"><div class="grid-wrap" style="max-height:300px;overflow:auto">
      <table class="tbl" style="font-size:11px;white-space:nowrap"><thead><tr>
        <th>작업처</th><th>공정명</th><th class="num">임율</th>
        ${OD_DISPLAY.map(o=>`<th class="num" style="color:#b0b8c4" title="원천 부재(미저장)">∅${o}</th>`).join('')}
        ${odReal.map(o=>`<th class="num">∅${o}</th>`).join('')}</tr></thead>
      <tbody>${rows.length?rows.map((r,i)=>`<tr>
        <td>${esc(wname(r.work_code))}${r.nx_flag?' <span class="bdg ok" style="font-size:9px">nx</span>':''}</td>
        <td>${esc(r.work_desc)}</td><td class="num">${won(r.hour_pay)}</td>
        ${OD_DISPLAY.map(()=>`<td class="num" style="color:#c8ccd2">·</td>`).join('')}
        ${odReal.map(o=>{const k=OD_MAP[o];const v=r[k];
          return `<td class="num">${em?`<input class="inp pi-sgv" data-i="${i}" data-k="${k}" type="number" step="0.001" value="${v==null?'':v}" style="width:44px;min-width:0;text-align:right;padding:1px 2px">`:num(v,3)}</td>`;}).join('')}
        </tr>`).join(''):`<tr><td colspan="${3+OD_DISPLAY.length+odReal.length}" class="empty">단품공정 없음</td></tr>`}
      </tbody></table></div></div></div>`;
    const eb=host.querySelector('#pi-sg-edit');if(eb)eb.onclick=()=>{st.singleEdit=!st.singleEdit;renderSingle();};
    host.querySelectorAll('.pi-sgv').forEach(inp=>inp.oninput=()=>{st.data.single[+inp.dataset.i][inp.dataset.k]=inp.value===''?null:inp.value;});
    const sv=host.querySelector('#pi-sg-save');if(sv)sv.onclick=async()=>{
      // 변경(=nx편집)행만 전송: 편집모드에서 손댄 값 반영 위해 전체 전송은 과함 → nx_flag 또는 값보유 행 전송
      const payload={user:uname(),rows:st.data.single.map(r=>{const o={s_work_code:r.s_work_code,work_desc:r.work_desc,work_code:r.work_code,gagong_proc_code:r.gagong_proc_code,hour_pay:r.hour_pay,cutting_flag:r.cutting_flag,sub_weld_flag:r.sub_weld_flag,sort_seq:r.sort_seq};odReal.forEach(o2=>{const k=OD_MAP[o2];o[k]=r[k];});return o;})};
      const j=await post('/api/prodinfo/single/save',payload);if(j.ok){flash(`✅ 단품 마스터 저장(${j.saved}건)`);st.singleEdit=false;loadItem(st.item);}else flash('저장 실패: '+(j.detail||''));};
    host.querySelectorAll('thead th').forEach(addResizer);
  };

  // ---------- 하단 탭 ----------
  const TABS=[['lob','LOB분석'],['yangsan','양산준비'],['jig','지그정보'],['yield','수율(공정수)'],['proc','생산공정순서']];
  const renderTabs=()=>{
    const host=c.querySelector('#pi-tabs');if(!host)return;
    host.innerHTML=`<div style="display:flex;gap:3px;border-bottom:2px solid #dce3ee">${TABS.map(t=>`<button class="btn ${st.tab===t[0]?'':'ghost'}" data-t="${t[0]}" style="border-radius:8px 8px 0 0;${st.tab===t[0]?'background:#1c47a0;color:#fff':''}">${t[1]}</button>`).join('')}</div><div id="pi-tabbody" style="padding-top:8px"></div>`;
    host.querySelectorAll('[data-t]').forEach(b=>b.onclick=()=>{st.tab=b.dataset.t;renderTabs();});
    const body=host.querySelector('#pi-tabbody');
    if(st.tab==='proc')renderProc(body);
    else if(st.tab==='lob')renderLob(body);
    else if(st.tab==='yangsan')renderYangsan(body);
    else if(st.tab==='jig')renderJig(body);
    else if(st.tab==='yield')renderYield(body);
  };

  // ---------- 탭: 생산공정순서 (★핵심 편집) ----------
  const renderProc=(body)=>{
    const canEd=ed();const rows=st.data.proc;const O=st.opts||{works:[],parts:[],singles:[],machs:[],jp_methods:{}};
    const opt=(list,val,disp)=>`<option value="">-</option>`+list.map(o=>`<option value="${esc(''+o.code)}"${(''+o.code)===(''+val)?' selected':''}>${esc(disp(o))}</option>`).join('');
    const partsFor=wc=>O.parts.filter(p=>!wc||!p.work_code||p.work_code===wc);
    const singlesFor=wc=>O.singles.filter(s=>!wc||!s.work_code||s.work_code===wc);
    const machsFor=wc=>O.machs.filter(m=>!wc||!m.work_code||m.work_code===wc);
    const cols=['','공정SEQ','작업처','파트','가공공정','가공설비','공정횟수','준비(초)','설비CT','인원','TT(초)','ST(초)','LT(Hr)','전표'];
    const totSt=rows.reduce((a,r)=>a+(+r.tot_st||0),0);
    body.innerHTML=`<div class="toolbar" style="margin:0 0 6px">
       <span style="font-size:12px;color:var(--muted)">라우팅 원천: <b>${st.data.proc_src==='nx'?'nx.prodinfo_proc(편집본)':'라이브 PR_M_ITEM_PROC_GAGONG'}</b> · 저장=nx</span>
       <div class="spacer"></div>
       ${canEd?`<button class="btn" id="pi-proc-add" style="background:#1c7c3a;color:#fff">➕ 행추가</button><button class="btn" id="pi-proc-save" style="background:#1c47a0;color:#fff">💾 저장</button>`:'<span style="color:#c0392b;font-size:12px">🔒 읽기전용</span>'}</div>
     <div class="grid-wrap" style="max-height:360px;overflow:auto"><table class="tbl" style="font-size:11px;white-space:nowrap"><thead><tr>${cols.map(h=>`<th class="${/SEQ|횟수|초|CT|인원|Hr/.test(h)?'num':'center'}">${h}</th>`).join('')}</tr></thead>
      <tbody>${rows.length?rows.map((r,i)=>{const wc=r.work_code;
        const cell=(k,w=44,step='0.001')=>canEd?`<input class="inp pi-pc" data-i="${i}" data-k="${k}" type="number" step="${step}" value="${r[k]==null?'':r[k]}" style="width:${w}px;min-width:0;text-align:right;padding:1px 3px">`:num(r[k],3);
        return `<tr>
        <td class="center">${canEd?`<button class="btn ghost pi-pdel" data-i="${i}" style="padding:0 5px;color:#c0392b">🗑</button>`:''}</td>
        <td class="num">${canEd?`<input class="inp pi-pc" data-i="${i}" data-k="proc_seq" type="number" value="${r.proc_seq}" style="width:44px;min-width:0;text-align:right;padding:1px 3px">`:r.proc_seq}</td>
        <td>${canEd?`<select class="inp pi-pwc" data-i="${i}" style="min-width:64px">${opt(O.works,wc,o=>o.code+' '+o.name)}</select>`:esc((wc?wc+' ':'')+r.work_desc)}</td>
        <td>${canEd?`<select class="inp pi-pc" data-i="${i}" data-k="gagong_proc_code" style="min-width:0;font-size:10px">${opt(partsFor(wc),r.gagong_proc_code,o=>o.name)}</select>`:esc(r.part_desc)}</td>
        <td>${canEd?`<select class="inp pi-pc" data-i="${i}" data-k="s_work_code" style="min-width:0;font-size:10px">${opt(singlesFor(wc),r.s_work_code,o=>o.name)}</select>`:esc(r.s_work_desc)}</td>
        <td>${canEd?`<select class="inp pi-pc" data-i="${i}" data-k="mach_code" style="min-width:0;font-size:10px">${opt(machsFor(wc),r.mach_code,o=>o.name)}</select>`:esc(r.mach_desc)}</td>
        <td class="num">${cell('work_qty',40,'0.1')}</td>
        <td class="num">${cell('ready_st',44)}</td><td class="num">${cell('mach_ct',44)}</td>
        <td class="num">${canEd?`<input class="inp pi-pc" data-i="${i}" data-k="inwon" type="number" value="${r.inwon==null?'':r.inwon}" style="width:36px;min-width:0;text-align:right;padding:1px 3px">`:r.inwon}</td>
        <td class="num">${cell('human_st',44)}</td><td class="num" style="background:#f3f8ff">${cell('tot_st',48)}</td>
        <td class="num">${cell('lt_hr',44)}</td>
        <td>${canEd?`<select class="inp pi-pc" data-i="${i}" data-k="jp_proc_method" style="min-width:80px">${Object.entries(O.jp_methods||{}).map(([k,v])=>`<option value="${k}"${r.jp_proc_method===k?' selected':''}>${esc(v)}</option>`).join('')}</select>`:esc((O.jp_methods||{})[r.jp_proc_method]||r.jp_proc_method)}</td>
        </tr>`;}).join(''):`<tr><td colspan="14" class="empty">생산공정순서 없음${canEd?' — [➕ 행추가]로 등록':''}</td></tr>`}
      </tbody><tfoot><tr class="grandtot"><td colspan="11" class="center">공정 ${rows.length}행 · ST(초) 합계</td><td class="num" style="font-weight:800">${num(totSt,3)}</td><td colspan="2"></td></tr></tfoot></table></div>`;
    if(!canEd){body.querySelectorAll('thead th').forEach(addResizer);return;}
    // 텍스트/숫자 셀: state만 갱신(재렌더X → 포커스 유지)
    body.querySelectorAll('.pi-pc').forEach(el=>el.oninput=el.onchange=()=>{const i=+el.dataset.i,k=el.dataset.k;
      let v=el.value; if(el.type==='number')v=(v===''?null:v); st.data.proc[i][k]=v;
      if(k==='tot_st'){const t=st.data.proc.reduce((a,r)=>a+(+r.tot_st||0),0);const tf=body.querySelector('tfoot .num');if(tf)tf.textContent=num(t,3);}});
    // 작업처 변경 → 캐스케이드(파트/공정/설비 재필터). 유효성 잃은 값 초기화 후 재렌더.
    body.querySelectorAll('.pi-pwc').forEach(el=>el.onchange=()=>{const i=+el.dataset.i;const wc=el.value;const r=st.data.proc[i];
      r.work_code=wc;
      if(wc){ if(!partsFor(wc).some(p=>p.code===r.gagong_proc_code))r.gagong_proc_code='';
        if(!singlesFor(wc).some(s=>(''+s.code)===(''+r.s_work_code)))r.s_work_code=0;
        if(!machsFor(wc).some(m=>m.code===r.mach_code))r.mach_code=''; }
      renderProc(body);});
    body.querySelectorAll('.pi-pdel').forEach(el=>el.onclick=()=>{st.data.proc.splice(+el.dataset.i,1);renderProc(body);});
    const ab=body.querySelector('#pi-proc-add');if(ab)ab.onclick=()=>{const mx=st.data.proc.reduce((a,r)=>Math.max(a,+r.proc_seq||0),0);
      st.data.proc.push({proc_seq:mx+1,work_code:'P2',gagong_proc_code:'',s_work_code:0,mach_code:'',work_qty:1,std_size:'',gagong_proc_seq:1,ready_st:0,mach_ct:0,inwon:0,human_st:0,tot_st:0,jp_proc_method:'J',lt_hr:0,work_desc:'',part_desc:'',s_work_desc:'',mach_desc:''});renderProc(body);};
    const sb=body.querySelector('#pi-proc-save');if(sb)sb.onclick=async()=>{
      const j=await post('/api/prodinfo/proc/save',{item:st.item,user:uname(),rows:st.data.proc});
      if(j.ok){flash(`✅ 생산공정순서 저장(${j.saved}행)`);loadItem(st.item);}else flash('저장 실패: '+(j.detail||''));};
    body.querySelectorAll('thead th').forEach(addResizer);
  };

  // ---------- 탭: LOB분석 = 용접(P1)/가공(P2) 좌우 2패널 + PR_M_ITEM_ST 인원/CAPA(편집→nx) ----------
  //  레거시 LOB 전용 dw 미발견(ITEM_MASTER_090_ANALYSIS §5) → 라우팅(생산공정순서) 스테이션 데이터를
  //  작업처(P1용접/P2가공)로 좌우 분리해 재구성. 시간=ST(초). LOB=ΣST÷(최대ST×NET공정)×100(표준 라인밸런싱).
  const renderLob=(body)=>{
    const canEd=ed();const rows=st.data.item_st;const proc=st.data.proc||[];
    const lobPanel=(title,list)=>{
      const sumSt=list.reduce((a,r)=>a+(+r.tot_st||0),0);
      const sumInw=list.reduce((a,r)=>a+(+r.inwon||0),0);
      const ts=list.map(r=>+r.tot_st||0).filter(x=>x>0);
      const net=ts.length,mn=net?Math.min(...ts):0,mx=net?Math.max(...ts):0,av=net?sumSt/net:0;
      const lob=(mx&&net)?sumSt/(mx*net)*100:0;
      return `<div class="panel" style="flex:0 1 auto;min-width:300px"><div class="panel-h">${title}</div>
       <div class="panel-b" style="padding:0"><div class="grid-wrap" style="max-height:260px;overflow:auto">
        <table class="tbl" style="font-size:11px;white-space:nowrap"><thead><tr>
          <th>공정명</th><th>호기</th><th class="num">인원</th><th class="num">CT</th><th>표준치수</th><th class="num">소요</th></tr></thead>
        <tbody>${list.length?list.map(r=>`<tr>
          <td>${esc(r.s_work_desc||r.part_desc||r.work_desc||'')}</td>
          <td>${esc(r.mach_desc||'')}</td>
          <td class="num">${won(r.inwon)}</td>
          <td class="num">${num(r.mach_ct,3)}</td>
          <td>${esc(r.std_size||'')}</td>
          <td class="num">${num(r.work_qty,1)}</td></tr>`).join(''):`<tr><td colspan="6" class="empty">공정 없음</td></tr>`}
        </tbody><tfoot>
          <tr class="grandtot"><td class="center">계</td><td></td><td class="num">${won(sumInw)}</td><td class="num">${num(sumSt,3)}</td><td colspan="2"></td></tr>
          <tr class="grandtot"><td class="center">이네트공정</td><td colspan="5" style="text-align:left;font-weight:600">${net}공정 · 최소 ${num(mn,3)} · 최대 ${num(mx,3)} · 평균 ${num(av,3)} · <b>LOB ${num(lob,1)}%</b></td></tr>
        </tfoot></table></div></div></div>`;};
    const weld=proc.filter(r=>(r.work_code||'').toUpperCase().startsWith('P1'));
    const gagong=proc.filter(r=>(r.work_code||'').toUpperCase().startsWith('P2'));
    body.innerHTML=`<div class="page-sub" style="margin:0 0 6px">LOB분석 · 작업처별 <b>«용접»(P1) / «가공»(P2)</b> 공정균형 · 시간=ST(초) · <span style="color:#b8860b">전용 dw 미발견(§5)→라우팅 재구성</span></div>
     <div style="display:flex;gap:10px;align-items:flex-start;flex-wrap:wrap;margin-bottom:10px">
       ${lobPanel('«용접공정» (작업처 P1)',weld)}
       ${lobPanel('«가공공정» (작업처 P2)',gagong)}
     </div>
     <div class="panel"><div class="panel-h" style="font-size:12px">생산구분별 투입인원·생산능력(CAPA) · PR_M_ITEM_ST → nx.prodinfo_item_st · 능력산정
       <span style="float:right;font-weight:400">${canEd?`<button class="btn" id="pi-lob-add" style="padding:1px 8px;background:#1c7c3a;color:#fff">➕ 행추가</button> <button class="btn" id="pi-lob-save" style="padding:1px 8px;background:#1c47a0;color:#fff">💾 저장</button>`:''}</span></div>
     <div class="panel-b" style="padding:0"><div class="grid-wrap" style="max-height:240px;overflow:auto"><table class="tbl" style="font-size:12px"><thead><tr>
       <th></th><th>생산구분</th><th class="num">투입인원</th><th class="num">CAPA</th><th class="center">원천</th></tr></thead>
      <tbody>${rows.length?rows.map((r,i)=>`<tr>
        <td class="center">${canEd?`<button class="btn ghost pi-lobdel" data-i="${i}" style="padding:0 5px;color:#c0392b">🗑</button>`:''}</td>
        <td>${canEd?`<input class="inp pi-lobc" data-i="${i}" data-k="prod_gubun" value="${esc(r.prod_gubun)}" maxlength="2" style="width:44px;min-width:0;padding:1px 4px">`:esc(r.prod_gubun)}</td>
        <td class="num">${canEd?`<input class="inp pi-lobc" data-i="${i}" data-k="member_qty" type="number" value="${r.member_qty}" style="width:60px;min-width:0;text-align:right;padding:1px 4px">`:won(r.member_qty)}</td>
        <td class="num">${canEd?`<input class="inp pi-lobc" data-i="${i}" data-k="capa_qty" type="number" value="${r.capa_qty}" style="width:72px;min-width:0;text-align:right;padding:1px 4px">`:won(r.capa_qty)}</td>
        <td class="center">${r.src==='nx'?'<span class="bdg ok" style="font-size:9px">nx</span>':'<span class="bdg off" style="font-size:9px">라이브</span>'}</td></tr>`).join(''):`<tr><td colspan="5" class="empty">인원/CAPA 없음</td></tr>`}
      </tbody></table></div></div></div>`;
    if(!canEd)return;
    body.querySelectorAll('.pi-lobc').forEach(el=>el.oninput=()=>{st.data.item_st[+el.dataset.i][el.dataset.k]=el.value;});
    body.querySelectorAll('.pi-lobdel').forEach(el=>el.onclick=()=>{st.data.item_st.splice(+el.dataset.i,1);renderLob(body);});
    const ab=body.querySelector('#pi-lob-add');if(ab)ab.onclick=()=>{st.data.item_st.push({prod_gubun:'',member_qty:0,capa_qty:0,src:'nx'});renderLob(body);};
    const sb=body.querySelector('#pi-lob-save');if(sb)sb.onclick=async()=>{
      const j=await post('/api/prodinfo/itemst/save',{item:st.item,user:uname(),rows:st.data.item_st});
      if(j.ok){flash(`✅ LOB 저장(${j.saved}건)`);loadItem(st.item);}else flash('저장 실패: '+(j.detail||''));};
  };

  // ---------- 탭: 양산준비 = 14종 문서 파일첨부(nx.prodinfo_yangsan, 편집=업로드/삭제) ----------
  const renderYangsan=(body)=>{
    const canEd=ed();const list=st.data.yangsan||[];
    body.innerHTML=`<div class="page-sub" style="margin:0 0 6px">양산준비 문서 14종 · 행별 <b>파일보기·추가</b>(첨부는 서버 보관 nx.prodinfo_yangsan) · 편집=nx</div>
     <input type="file" id="pi-ys-file" style="display:none">
     <div class="grid-wrap" style="max-height:360px;overflow:auto"><table class="tbl" style="font-size:12px;white-space:nowrap"><thead><tr>
       <th class="num">#</th><th>문서구분</th><th>첨부파일</th><th class="center">작업자</th><th class="center">수정일시</th>${canEd?'<th class="center">추가</th>':''}</tr></thead>
      <tbody>${list.map((d,i)=>{const f=(d.files&&d.files[0])||null;
        return `<tr>
        <td class="num">${i+1}</td>
        <td>${esc(d.doc_nm)}</td>
        <td>${f?`<a href="#" class="pi-ys-view" data-yid="${f.yid}">${esc(f.filename)}</a>${d.files.length>1?` <span class="mut">외 ${d.files.length-1}</span>`:''}${canEd?` <button class="btn ghost pi-ys-del" data-yid="${f.yid}" style="padding:0 5px;color:#c0392b">🗑</button>`:''}`:'<span class="mut">-</span>'}</td>
        <td class="center">${esc(f?f.user:'')}</td>
        <td class="center">${esc(f?f.dt:'')}</td>
        ${canEd?`<td class="center"><button class="btn pi-ys-add" data-dt="${esc(d.doc_type)}" style="padding:1px 8px;background:#1c7c3a;color:#fff">＋</button></td>`:''}
        </tr>`;}).join('')}
      </tbody></table></div>`;
    body.querySelectorAll('.pi-ys-view').forEach(a=>a.onclick=e=>{e.preventDefault();
      window.open(`${API}/api/prodinfo/yangsan/download?yid=${a.dataset.yid}&disp=inline`,'_blank');});
    if(!canEd)return;
    const fileEl=body.querySelector('#pi-ys-file');
    body.querySelectorAll('.pi-ys-add').forEach(b=>b.onclick=()=>{fileEl.dataset.dt=b.dataset.dt;fileEl.value='';fileEl.click();});
    fileEl.onchange=async()=>{const f=fileEl.files&&fileEl.files[0];if(!f)return;
      const fd=new FormData();fd.append('file',f);fd.append('item',st.item);fd.append('doc_type',fileEl.dataset.dt);fd.append('user',uname());
      try{const r=await fetch(`${API}/api/prodinfo/yangsan/upload`,{method:'POST',body:fd});const j=await r.json();
        if(j.ok){flash(`✅ 첨부 업로드(${Math.round((j.size||0)/1024)}KB)`);loadItem(st.item);}else flash('업로드 실패: '+(j.detail||''));}
      catch(e){flash('업로드 실패(연결)');}};
    body.querySelectorAll('.pi-ys-del').forEach(b=>b.onclick=async()=>{if(!confirm('첨부를 삭제할까요?'))return;
      const j=await post('/api/prodinfo/yangsan/delete',{yid:+b.dataset.yid});
      if(j.ok){flash('🗑 첨부 삭제');loadItem(st.item);}else flash('삭제 실패: '+(j.detail||''));});};

  // ---------- 탭: 지그정보 = CRUD(nx.prodinfo_jig) + 레거시 단건 참조 ----------
  const renderJig=(body)=>{
    const canEd=ed();const rows=st.data.jig||[];const lg=st.data.jig_legacy||{};
    body.innerHTML=`<div class="page-sub" style="margin:0 0 6px">지그정보 · 편집=nx.prodinfo_jig · <span style="color:var(--muted)">레거시참조: 지그코드 <b>${esc(lg.jig_code||'-')}</b> · 적치 ${esc(lg.jig_area||'-')} · 수량 ${won(lg.zig_qty)}</span>
       <span style="float:right">${canEd?`<button class="btn" id="pi-jig-add" style="padding:1px 8px;background:#1c7c3a;color:#fff">➕ 행추가</button> <button class="btn" id="pi-jig-save" style="padding:1px 8px;background:#1c47a0;color:#fff">💾 저장</button>`:''}</span></div>
     <div class="grid-wrap" style="max-height:300px;overflow:auto"><table class="tbl" style="font-size:12px;white-space:nowrap"><thead><tr>
       <th></th><th>지그구분</th><th class="num">수량</th><th>보관위치(RACK)</th><th class="center">제작일</th></tr></thead>
      <tbody>${rows.length?rows.map((r,i)=>`<tr>
        <td class="center">${canEd?`<button class="btn ghost pi-jigdel" data-i="${i}" style="padding:0 5px;color:#c0392b">🗑</button>`:''}</td>
        <td>${canEd?`<input class="inp pi-jigc" data-i="${i}" data-k="jig_gubun" value="${esc(r.jig_gubun||'')}" style="width:140px;padding:1px 4px">`:esc(r.jig_gubun||'')}</td>
        <td class="num">${canEd?`<input class="inp pi-jigc" data-i="${i}" data-k="jig_qty" type="number" value="${r.jig_qty==null?'':r.jig_qty}" style="width:64px;min-width:0;text-align:right;padding:1px 4px">`:won(r.jig_qty)}</td>
        <td>${canEd?`<input class="inp pi-jigc" data-i="${i}" data-k="rack_loc" value="${esc(r.rack_loc||'')}" style="width:140px;padding:1px 4px">`:esc(r.rack_loc||'')}</td>
        <td class="center">${canEd?`<input class="inp pi-jigc" data-i="${i}" data-k="make_ymd" value="${esc(r.make_ymd||'')}" placeholder="YYYYMMDD" maxlength="8" style="width:100px;min-width:0;text-align:center;padding:1px 4px">`:esc(r.make_ymd||'')}</td>
        </tr>`).join(''):`<tr><td colspan="5" class="empty">지그 없음${canEd?' — [➕ 행추가]로 등록':''}</td></tr>`}
      </tbody></table></div>`;
    if(!canEd)return;
    body.querySelectorAll('.pi-jigc').forEach(el=>el.oninput=()=>{st.data.jig[+el.dataset.i][el.dataset.k]=el.value;});
    body.querySelectorAll('.pi-jigdel').forEach(el=>el.onclick=()=>{st.data.jig.splice(+el.dataset.i,1);renderJig(body);});
    const ab=body.querySelector('#pi-jig-add');if(ab)ab.onclick=()=>{(st.data.jig=st.data.jig||[]).push({jig_gubun:'',jig_qty:0,rack_loc:'',make_ymd:'',src:'nx'});renderJig(body);};
    const sb=body.querySelector('#pi-jig-save');if(sb)sb.onclick=async()=>{
      const j=await post('/api/prodinfo/jig/save',{item:st.item,user:uname(),rows:st.data.jig||[]});
      if(j.ok){flash(`✅ 지그 저장(${j.saved}건)`);loadItem(st.item);}else flash('저장 실패: '+(j.detail||''));};};

  // ---------- 탭: 수율(공정수) = CRUD(nx.prodinfo_yield) + 합계 footer ----------
  //  §5-4: 저장실체=회수율 3계층(PR_M_ITEM.PROD_RATE 등)이나 전용 dw 미발견 → nx 편집그리드로 재구성.
  const renderYield=(body)=>{
    const canEd=ed();const h=st.data.head;const rows=st.data.yield||[];
    const totQ=rows.reduce((a,r)=>a+(+r.proc_qty||0),0),totSt=rows.reduce((a,r)=>a+(+r.st||0),0);
    body.innerHTML=`<div class="page-sub" style="margin:0 0 6px">수율(공정수) · 편집=nx.prodinfo_yield · 품목회수율 <b>${num(h.prod_rate,1)}%</b>(PR_M_ITEM.PROD_RATE §5-4) · 소요=표준÷(회수율/100)
       <span style="float:right">${canEd?`<button class="btn" id="pi-yld-add" style="padding:1px 8px;background:#1c7c3a;color:#fff">➕ 행추가</button> <button class="btn" id="pi-yld-save" style="padding:1px 8px;background:#1c47a0;color:#fff">💾 저장</button>`:''}</span></div>
     <div class="grid-wrap" style="max-height:300px;overflow:auto"><table class="tbl" style="font-size:12px;white-space:nowrap"><thead><tr>
       <th></th><th>수율공정</th><th class="num">공정수</th><th class="num">표준ST</th><th class="num">ST</th></tr></thead>
      <tbody>${rows.length?rows.map((r,i)=>`<tr>
        <td class="center">${canEd?`<button class="btn ghost pi-ylddel" data-i="${i}" style="padding:0 5px;color:#c0392b">🗑</button>`:''}</td>
        <td>${canEd?`<input class="inp pi-yldc" data-i="${i}" data-k="yield_proc" value="${esc(r.yield_proc||'')}" style="width:170px;padding:1px 4px">`:esc(r.yield_proc||'')}</td>
        <td class="num">${canEd?`<input class="inp pi-yldc" data-i="${i}" data-k="proc_qty" type="number" step="0.1" value="${r.proc_qty==null?'':r.proc_qty}" style="width:64px;min-width:0;text-align:right;padding:1px 4px">`:num(r.proc_qty,1)}</td>
        <td class="num">${canEd?`<input class="inp pi-yldc" data-i="${i}" data-k="std_st" type="number" step="0.001" value="${r.std_st==null?'':r.std_st}" style="width:72px;min-width:0;text-align:right;padding:1px 4px">`:num(r.std_st,3)}</td>
        <td class="num">${canEd?`<input class="inp pi-yldc" data-i="${i}" data-k="st" type="number" step="0.001" value="${r.st==null?'':r.st}" style="width:72px;min-width:0;text-align:right;padding:1px 4px">`:num(r.st,3)}</td>
        </tr>`).join(''):`<tr><td colspan="5" class="empty">수율공정 없음${canEd?' — [➕ 행추가]로 등록':''}</td></tr>`}
      </tbody><tfoot><tr class="grandtot"><td colspan="2" class="center">합계</td><td class="num">${num(totQ,1)}</td><td></td><td class="num">${num(totSt,3)}</td></tr></tfoot></table></div>`;
    if(!canEd)return;
    body.querySelectorAll('.pi-yldc').forEach(el=>el.oninput=()=>{st.data.yield[+el.dataset.i][el.dataset.k]=el.value;
      if(el.dataset.k==='proc_qty'||el.dataset.k==='st'){const tq=st.data.yield.reduce((a,r)=>a+(+r.proc_qty||0),0),ts=st.data.yield.reduce((a,r)=>a+(+r.st||0),0);
        const tf=body.querySelectorAll('tfoot .num');if(tf[0])tf[0].textContent=num(tq,1);if(tf[1])tf[1].textContent=num(ts,3);}});
    body.querySelectorAll('.pi-ylddel').forEach(el=>el.onclick=()=>{st.data.yield.splice(+el.dataset.i,1);renderYield(body);});
    const ab=body.querySelector('#pi-yld-add');if(ab)ab.onclick=()=>{(st.data.yield=st.data.yield||[]).push({yield_proc:'',proc_qty:0,std_st:0,st:0});renderYield(body);};
    const sb=body.querySelector('#pi-yld-save');if(sb)sb.onclick=async()=>{
      const j=await post('/api/prodinfo/yield/save',{item:st.item,user:uname(),rows:st.data.yield||[]});
      if(j.ok){flash(`✅ 수율 저장(${j.saved}건)`);loadItem(st.item);}else flash('저장 실패: '+(j.detail||''));};};

  draw();
};
