/* ===== PNC ERP screens.prod.js — 생산 SCREEN (app.js 분할, 순수이동) ===== */

/* 생산재고입출고 (생산, dw_pr_stock_460) — 좌:파트재고(수불장 기준) 우:선택품목 입출고이력. 파트차원 추가, 전월이월 2502기준 */
SCREEN.prodinout=(c)=>{
  const API=API_BASE;
  let rows=[], mv={}, pn={}, curYm='', loading=false, msg='';   // rows=[part,mat,desc,spec,sgn,stock,bf]
  const pName=p=>pn[(''+p).trim()]||p;
  const fmtYmd=y=>{y=(''+(y||'')).trim();return (y.length>=6&&y!=='000000')?`${y.slice(0,2)}/${y.slice(2,4)}/${y.slice(4,6)}`:'00/00/00';};
  const ymToInput=y=>{y=(''+(y||'')).trim();return y.length>=4?`20${y.slice(0,2)}-${y.slice(2,4)}`:'';};
  const inYm=v=>(''+(v||'')).slice(2).replace('-','');
  let sel=null, curL=[], source='live';   // ★Phase5 데이터원(기본 라이브 무변경)
  const load=async(ym)=>{loading=true;msg='';sel=null;
    const st=c.querySelector('#lbody');if(st)st.innerHTML=spinRow(5);
    if(source==='nx'){loading=false;return nxDerivedView(c,`${API}/api/live/prodinout?ym=${encodeURIComponent(ym||'')}&source=nx`,{title:'생산입출고현황',onBack:()=>{source='live';load(ym);}});}
    try{const r=await fetch(`${API}/api/live/prodinout?ym=${encodeURIComponent(ym||'')}`);if(!r.ok)throw new Error('HTTP '+r.status);
      const j=await r.json();curYm=j.ym||ym||'';rows=j.stock||[];mv=j.moves||{};pn=j.partNames||{};}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';rows=[];mv={};pn={};}
    loading=false;
    const ymi=c.querySelector('#ym');if(ymi)ymi.value=ymToInput(curYm);
    const ps=[...new Set(rows.map(r=>r[0]))].sort((a,b)=>pName(a).localeCompare(pName(b),'ko'));
    const psel=c.querySelector('#part');if(psel){const v=psel.value;psel.innerHTML='<option value="">전체</option>'+ps.map(p=>`<option value="${esc(p)}">${esc(pName(p))}</option>`).join('');psel.value=v;}
    const sub=c.querySelector('#pio-sub');if(sub)sub.innerHTML=`파트별 생산재고 + 선택품목 입출고이력(누적재고) · 원본 <code>PR_T_STOCK_MAINT_MAT</code> 외 · 🔴 라이브 ${esc(ymToInput(curYm)||'-')}(이월기준 2502) · 0재고 숨김`;
    renderLeft();c.querySelector('#rbody').innerHTML='';c.querySelector('#rhead').innerHTML='<div class="s-item">← 좌측에서 품목을 클릭하세요</div>';};
  c.innerHTML=`
   <div class="page-title">🔁 생산입출고현황</div>
   <div class="page-sub" id="pio-sub">파트별 생산재고 + 선택품목 입출고이력(누적재고) · 원본 <code>PR_T_STOCK_MAINT_MAT</code> 외 · 🔴 라이브(이월기준 2502) · 0재고 숨김</div>
   <div class="toolbar">
     <label class="tl">조회월</label><input type="month" class="inp" id="ym" style="min-width:120px">
     <label class="tl">파트</label><select class="sel" id="part"><option value="">전체</option></select>
     <input class="inp" id="q" placeholder="자도번/품명">
     <select class="sel" id="gubun"><option value="all">전체</option><option value="plus">(+)재고</option><option value="minus">(-)재고</option></select>
     <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
     <button class="btn ghost" id="nxsrc" title="nx 단일원장 파생(대조용)">🔀 nx원장 파생</button>
     <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
   </div>
   <div style="display:flex;gap:10px;align-items:flex-start">
     <div style="flex:0 0 46%;min-width:0">
       <div class="summary-bar" id="lsum"></div>
       <div class="grid-wrap" style="max-height:520px;overflow:auto"><table class="tbl fit"><thead><tr><th>파트</th><th>자도번</th><th>품명</th><th>소분류</th><th class="num">재고</th></tr></thead><tbody id="lbody"></tbody></table></div>
       <div class="rowcount" id="lcnt"></div>
     </div>
     <div style="flex:1;min-width:0">
       <div class="summary-bar" id="rhead"><div class="s-item">← 좌측에서 품목을 클릭하세요</div></div>
       <div class="grid-wrap" style="max-height:548px;overflow:auto"><table class="tbl fit"><thead><tr><th class="center">일자</th><th class="num">전일재고</th><th class="num">입고</th><th class="num">재고조정</th><th class="num">출고</th><th class="num">재고수량</th><th>구분</th><th>사용이력</th></tr></thead><tbody id="rbody"></tbody></table></div>
     </div>
   </div>`;
  const renderRight=(part,mat)=>{
    const row=rows.find(r=>r[0]===part&&r[1]===mat)||[]; const bf=+row[6]||0;
    const lines=(mv[part+'||'+mat]||[]).slice().sort((a,b)=>(''+a[0]).localeCompare(''+b[0],'ko'));
    let bal=bf, html=`<tr><td class="center">00/00/00</td><td class="num">${won(bf)}</td><td class="num"></td><td class="num"></td><td class="num"></td><td class="num qty"><b>${won(bf)}</b></td><td>전월이월</td><td></td></tr>`;
    let si=0,se=0,so=0;
    lines.forEach(r=>{const prev=bal; const i=+r[1]||0,o=+r[2]||0,e=+r[3]||0; bal=prev+i-o+e; si+=i;so+=o;se+=e;
      html+=`<tr><td class="center">${fmtYmd(r[0])}</td><td class="num">${won(prev)}</td><td class="num">${i?won(i):''}</td><td class="num">${e?won(e):''}</td><td class="num">${o?won(o):''}</td><td class="num qty"><b>${won(bal)}</b></td><td>${esc(r[4])||''}</td><td class="cap" title="${esc(r[5]||'')}">${esc(r[5]||'')}</td></tr>`;});
    html+=`<tr class="grandtot"><td class="center">총계</td><td class="num">${won(bf)}</td><td class="num">${won(si)}</td><td class="num">${won(se)}</td><td class="num">${won(so)}</td><td class="num">${won(bal)}</td><td colspan="2"></td></tr>`;
    c.querySelector('#rbody').innerHTML=html;
    c.querySelector('#rhead').innerHTML=`<div class="s-item">${esc(pName(part))} · <b>${esc(mat)}</b></div><div class="s-item">${esc(row[2]||'')}</div><div class="s-item">현재고 <b>${won(bal)}</b></div>`;
    attachResizers(c);
  };
  const renderLeft=()=>{
    const q=c.querySelector('#q').value.trim().toLowerCase(), gb=c.querySelector('#gubun').value, pf=c.querySelector('#part').value;
    curL=rows.filter(r=>(!pf||r[0]===pf)&&(gb==='all'||(gb==='plus'?r[5]>0:r[5]<0))&&(!q||(''+r[1]).toLowerCase().includes(q)||(''+r[2]).toLowerCase().includes(q)))
      .sort((a,b)=>pName(a[0]).localeCompare(pName(b[0]),'ko')||(''+a[1]).localeCompare(''+b[1],'ko'));
    const tot=curL.reduce((a,b)=>a+(+b[5]||0),0);
    let lb=curL.map(r=>`<tr data-part="${esc(r[0])}" data-mat="${esc(r[1])}" class="${sel===r[0]+'||'+r[1]?'sel':''}"><td class="cap" title="${esc(pName(r[0]))}">${esc(pName(r[0]))}</td><td><b>${esc(r[1])}</b></td><td class="cap" title="${esc(r[2])}">${esc(r[2])}</td><td>${esc(r[4])}</td><td class="num qty">${won(r[5])}</td></tr>`).join('');
    if(curL.length)lb+=`<tr class="grandtot"><td colspan="4" class="right">총계 (${won(curL.length)} 품목)</td><td class="num">${won(tot)}</td></tr>`;
    c.querySelector('#lbody').innerHTML=curL.length?lb:`<tr><td colspan="5" class="empty">결과 없음</td></tr>`;
    c.querySelector('#lbody').querySelectorAll('tr[data-mat]').forEach(tr=>tr.onclick=()=>{sel=tr.dataset.part+'||'+tr.dataset.mat;c.querySelectorAll('#lbody tr').forEach(x=>x.classList.remove('sel'));tr.classList.add('sel');renderRight(tr.dataset.part,tr.dataset.mat);});
    c.querySelector('#lsum').innerHTML=`<div class="s-item">품목 <b>${won(curL.length)}</b></div><div class="s-item">재고 합계 <b>${won(tot)}</b></div>`;
    c.querySelector('#lcnt').textContent=`${curL.length}품목 (0재고 제외)`;
    attachResizers(c);
  };
  c.querySelector('#go').onclick=renderLeft;c.querySelector('#q').onkeyup=e=>{if(e.key==='Enter')renderLeft();};
  c.querySelector('#nxsrc').onclick=()=>{source='nx';load(curYm);};   // ★Phase5 nx 파생 보기
  c.querySelector('#gubun').onchange=renderLeft;c.querySelector('#part').onchange=renderLeft;
  c.querySelector('#ym').onchange=e=>load(inYm(e.target.value));
  c.querySelector('#reset').onclick=()=>{c.querySelector('#q').value='';c.querySelector('#gubun').value='all';c.querySelector('#part').value='';sel=null;renderLeft();c.querySelector('#rbody').innerHTML='';c.querySelector('#rhead').innerHTML='<div class="s-item">← 좌측에서 품목을 클릭하세요</div>';};
  c.querySelector('#xls').onclick=()=>downloadCSV('생산재고입출고.csv',['파트','자도번','품명','규격','소분류','재고'],curL.map(r=>[pName(r[0]),r[1],r[2],r[3],r[4],r[5]]));
  load('');
};

/* 생산재고조회 — 준비/가공/용접 토글 (+용접 집계/BOM풀기) */
SCREEN.prodstock=(c)=>{
  const API=API_BASE;
  let stage='GAGONG', wmode='agg', livePS=[], curYm='', loading=false, source='live';   // livePS=가공/용접 라이브 · ★Phase5 데이터원(기본 라이브)
  const ymToInput=y=>{y=(''+(y||'')).trim();return y.length>=4?`20${y.slice(0,2)}-${y.slice(2,4)}`:'';};
  const inYm=v=>(''+(v||'')).slice(2).replace('-','');
  const STAGES=[['GAGONG','가공'],['WELD','용접']];   // 준비(키팅) 탭 제거(중복·별도메뉴 폐지)
  const load=async(ym)=>{loading=true;
    const bd=c.querySelector('#body');if(bd)bd.innerHTML=spinRow(11);
    if(source==='nx'){loading=false;return nxDerivedView(c,`${API}/api/live/prodstock?ym=${encodeURIComponent(ym||'')}&source=nx`,{title:'생산재고조회',onBack:()=>{source='live';load(ym);}});}
    try{const r=await fetch(`${API}/api/live/prodstock?ym=${encodeURIComponent(ym||'')}`);if(!r.ok)throw new Error('HTTP '+r.status);
      const j=await r.json();livePS=j.rows||[];curYm=j.ym||ym||'';}
    catch(e){livePS=[];}
    loading=false;draw();};
  const draw=()=>{
    const isWeld=stage==='WELD', bomMode=isWeld&&wmode==='bom';
    const showLine=(stage==='READY')||(isWeld&&wmode==='agg');
    const hasMove = bomMode || stage==='GAGONG' || (isWeld&&wmode==='agg');   // 기초/입출/조정 표시
    let pool;
    const live=(stage==='GAGONG')||(isWeld&&!bomMode);   // 가공·용접집계=라이브 / 준비·BOM풀기=스냅샷
    if(bomMode) pool=DB.weldBom||[];
    else if(stage==='READY') pool=(DB.stock||[]).filter(r=>r.stage==='READY');
    else pool=livePS.filter(r=>r.stage===stage);
    const lines= showLine ? [...new Set(pool.map(r=>r.loc).filter(Boolean))].sort():[];
    const sub={READY:'키팅 준비재고(라인별) · 원본 PU_T_READY_STOCK · ⚠️스냅샷(라이브 예정)',
               GAGONG:`가공(P0001) 재공 · 원장 9-union · 🔴 라이브 ${esc(ymToInput(curYm)||'-')}`,
               WELD: bomMode?'용접 BOM풀기(하위품번 전개) · ⚠️스냅샷(SP, 라이브 예정)':`용접(가공제외) 재공 · 라인별 · 🔴 라이브 ${esc(ymToInput(curYm)||'-')}`}[stage];
    c.innerHTML=`
     <div class="page-title">🏭 생산재고조회</div><div class="page-sub">${sub}</div>
     <div class="toolbar">
       <div class="toggle-group">${STAGES.map(([k,v])=>`<button data-stage="${k}" class="${stage===k?'on':''}">${v}</button>`).join('')}</div>
       ${isWeld?`<div class="toggle-group" style="margin-left:6px"><button data-w="agg" class="${wmode==='agg'?'on':''}">집계</button><button data-w="bom" class="${wmode==='bom'?'on':''}">BOM풀기</button></div>`:''}
       ${live?`<label style="font-size:12px;color:var(--muted);font-weight:600;margin-left:4px">조회월</label><input type="month" class="inp" id="ym" value="${esc(ymToInput(curYm))}" style="min-width:120px">`:''}
       <input class="inp" id="q" placeholder="${bomMode?'ASSY/자재품번/품명':'품목코드/품명'}">
       ${!bomMode?`<select class="sel" id="type"><option value="">전체유형</option>${Object.entries(TYPE_NM).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select>`:''}
       ${showLine?`<select class="sel" id="line"><option value="">전체라인</option>${lines.map(l=>`<option value="${esc(l)}">${esc(lineName(l))}</option>`).join('')}</select>`:''}
       <select class="sel" id="gubun"><option value="all">전체</option><option value="plus">(+)재고</option><option value="minus">(-)재고</option></select>
       <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
       <button class="btn ghost" id="nxsrc" title="nx 단일원장 파생(대조용)">🔀 nx원장 파생</button>
       <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
     </div>
     <div class="summary-bar" id="sum"></div>
     <div class="grid-wrap" style="max-height:510px;overflow:auto"><table class="tbl fit"><thead id="th"></thead><tbody id="body"></tbody></table></div>
     <div class="rowcount" id="cnt"></div>
     <div class="summary-bar botsum" id="botsum" style="margin-top:6px;position:sticky;bottom:0"></div>`;
    c.querySelectorAll('[data-stage]').forEach(b=>b.onclick=()=>{stage=b.dataset.stage;wmode='agg';draw();});
    {const _nx=c.querySelector('#nxsrc');if(_nx)_nx.onclick=()=>{source='nx';load(curYm);};}   // ★Phase5 nx 파생 보기
    c.querySelectorAll('[data-w]').forEach(b=>b.onclick=()=>{wmode=b.dataset.w;draw();});
    let cur=[];
    const sumbar=rows=>{const qty=rows.reduce((a,b)=>a+(+b.qty||0),0),amt=rows.reduce((a,b)=>a+(+b.amt||0),0);
      const html=`<div class="s-item">건수 <b>${won(rows.length)}</b></div>
        <div class="s-item">재고수량 합계 <b>${won(qty)}</b></div>
        <div class="s-item ${amt<0?'neg':''}">재고금액 합계 <b>${wonI(amt)} 원</b></div>`;
      c.querySelector('#sum').innerHTML=html;
      const bs=c.querySelector('#botsum');if(bs)bs.innerHTML=`<div class="s-item" style="font-weight:700">📊 합계</div>${html}`;};
    function wire(apply){
      c.querySelector('#go').onclick=apply;c.querySelector('#q').onkeyup=e=>{if(e.key==='Enter')apply();};
      const ymi=c.querySelector('#ym');if(ymi)ymi.onchange=e=>load(inYm(e.target.value));   // 라이브 월변경=재조회
      if(c.querySelector('#type'))c.querySelector('#type').onchange=apply;
      if(c.querySelector('#line'))c.querySelector('#line').onchange=apply;
      c.querySelector('#gubun').onchange=apply;
      c.querySelector('#reset').onclick=()=>{c.querySelector('#q').value='';c.querySelector('#gubun').value='all';if(c.querySelector('#type'))c.querySelector('#type').value='';if(c.querySelector('#line'))c.querySelector('#line').value='';apply();};}
    const gbf=r=>{const gb=c.querySelector('#gubun').value;return gb==='all'||(gb==='plus'?r.qty>0:r.qty<0);};
    const T=(rs,k)=>rs.reduce((a,b)=>a+(+b[k]||0),0);
    // 영업(제품재고조회) 방식 총계행: 이동컬럼(기초/입고/출고/조정/현재고/금액) 정렬 합계
    const gtMove=(rows,lead)=>`<tr class="grandtot"><td colspan="${lead}" class="right">총계</td><td class="num">${won(T(rows,'basic'))}</td><td class="num">${won(T(rows,'inq'))}</td><td class="num">${won(T(rows,'outq'))}</td><td class="num">${won(T(rows,'adj'))}</td><td class="num">${won(T(rows,'qty'))}</td><td></td><td class="num">${wonI(T(rows,'amt'))}</td></tr>`;
    let render;
    if(bomMode){
      c.querySelector('#th').innerHTML=`<tr><th>ASSY 품번</th><th>자재품번</th><th>품명</th><th>거래처</th><th class="num">기초재고</th><th class="num">입고</th><th class="num">출고</th><th class="num">조정</th><th class="num">현재고</th><th class="num">단가</th><th class="num">금액</th></tr>`;
      render=rows=>{cur=rows;c.querySelector('#body').innerHTML=rows.length?rows.map(r=>`<tr><td>${esc(r.assy)||'-'}</td><td><b>${esc(r.mat)}</b></td><td>${esc(r.nm)}</td><td>${esc(r.cust)||'-'}</td><td class="num">${won(r.basic)}</td><td class="num">${won(r.inq)}</td><td class="num">${won(r.outq)}</td><td class="num">${won(r.adj)}</td><td class="num qty"><b>${won(r.qty)}</b></td><td class="num">${won(r.cost)}</td><td class="num"><b>${wonI(r.amt)}</b></td></tr>`).join('')+gtMove(rows,4):`<tr><td colspan="11" class="empty">결과 없음</td></tr>`;sumbar(rows);c.querySelector('#cnt').textContent=`${rows.length}건 / 대상 ${pool.length}건`;};
      wire(()=>{const q=c.querySelector('#q').value.trim().toLowerCase();render(pool.filter(r=>gbf(r)&&(!q||(r.mat||'').toLowerCase().includes(q)||(r.assy||'').toLowerCase().includes(q)||(r.nm||'').toLowerCase().includes(q))));});
      c.querySelector('#xls').onclick=()=>downloadCSV('생산재고_용접_BOM풀기.csv',['ASSY품번','자재품번','품명','거래처','기초재고','입고','출고','조정','현재고','단가','금액'],cur.map(r=>[r.assy,r.mat,r.nm,r.cust,r.basic,r.inq,r.outq,r.adj,r.qty,r.cost,Math.round(r.amt)]));
      render(pool);
      enableSort(c,['assy','mat','nm','cust','basic','inq','outq','adj','qty','cost','amt'],()=>cur,render);
    } else if(hasMove){
      c.querySelector('#th').innerHTML=`<tr><th>품목코드</th><th>품명</th><th>유형</th>${showLine?'<th class="center">라인</th>':''}<th class="num">기초재고</th><th class="num">입고</th><th class="num">출고</th><th class="num">조정</th><th class="num">현재고</th><th class="num">단가</th><th class="num">금액</th></tr>`;
      render=rows=>{cur=rows;c.querySelector('#body').innerHTML=rows.length?rows.map(r=>`<tr><td><b>${esc(r.cd)}</b></td><td>${esc(r.nm)}</td><td>${tbadge(r.type)}</td>${showLine?`<td class="center">${esc(lineName(r.loc))||'-'}</td>`:''}<td class="num">${won(r.basic)}</td><td class="num">${won(r.inq)}</td><td class="num">${won(r.outq)}</td><td class="num">${won(r.adj)}</td><td class="num qty"><b>${won(r.qty)}</b></td><td class="num">${won(r.cost)}</td><td class="num"><b>${wonI(r.amt)}</b></td></tr>`).join('')+gtMove(rows,showLine?4:3):`<tr><td colspan="11" class="empty">결과 없음</td></tr>`;sumbar(rows);c.querySelector('#cnt').textContent=`${rows.length}건 / 대상 ${pool.length}건`;};
      wire(()=>{const q=c.querySelector('#q').value.trim().toLowerCase(),t=c.querySelector('#type').value,ln=showLine?c.querySelector('#line').value:'';
        render(pool.filter(r=>gbf(r)&&(!t||r.type===t)&&(!ln||r.loc===ln)&&(!q||(r.cd||'').toLowerCase().includes(q)||(r.nm||'').toLowerCase().includes(q))));});
      c.querySelector('#xls').onclick=()=>downloadCSV('생산재고_'+stage+'.csv',['품목코드','품명','유형',...(showLine?['라인']:[]),'기초재고','입고','출고','조정','현재고','단가','금액'],cur.map(r=>[r.cd,r.nm,TYPE_NM[r.type]||r.type,...(showLine?[lineName(r.loc)]:[]),r.basic,r.inq,r.outq,r.adj,r.qty,r.cost,Math.round(r.amt)]));
      render(pool);
      enableSort(c,['cd','nm','type',...(showLine?['loc']:[]),'basic','inq','outq','adj','qty','cost','amt'],()=>cur,render);
    } else {
      c.querySelector('#th').innerHTML=`<tr><th>품목코드</th><th>품명</th><th>유형</th><th class="center">라인</th><th class="num">재고수량</th><th class="center">단위</th><th class="num">단가</th><th class="num">재고금액</th></tr>`;
      render=rows=>{cur=rows;c.querySelector('#body').innerHTML=rows.length?rows.map(r=>`<tr><td><b>${esc(r.cd)}</b></td><td>${esc(r.nm)}</td><td>${tbadge(r.type)}</td><td class="center">${esc(lineName(r.loc))||'-'}</td><td class="num qty">${won(r.qty)}</td><td class="center">${esc(r.uom)}</td><td class="num">${won(r.cost)}</td><td class="num"><b>${wonI(r.amt)}</b></td></tr>`).join('')+`<tr class="grandtot"><td colspan="4" class="right">총계</td><td class="num">${won(T(rows,'qty'))}</td><td></td><td></td><td class="num">${wonI(T(rows,'amt'))}</td></tr>`:`<tr><td colspan="8" class="empty">결과 없음</td></tr>`;sumbar(rows);c.querySelector('#cnt').textContent=`${rows.length}건 / 대상 ${pool.length}건`;};
      wire(()=>{const q=c.querySelector('#q').value.trim().toLowerCase(),t=c.querySelector('#type').value,ln=c.querySelector('#line').value;
        render(pool.filter(r=>gbf(r)&&(!t||r.type===t)&&(!ln||r.loc===ln)&&(!q||(r.cd||'').toLowerCase().includes(q)||(r.nm||'').toLowerCase().includes(q))));});
      c.querySelector('#xls').onclick=()=>downloadCSV('생산재고_준비.csv',['품목코드','품명','유형','라인','재고수량','단위','단가','재고금액'],cur.map(r=>[r.cd,r.nm,TYPE_NM[r.type]||r.type,lineName(r.loc),r.qty,r.uom,r.cost,Math.round(r.amt)]));
      render(pool);
      enableSort(c,['cd','nm','type','loc','qty','uom','cost','amt'],()=>cur,render);
    }
  };
  load('');
};

/* 용접 재고 — 집계 / BOM풀기 토글 */
SCREEN.stweld=(c)=>{
  let mode='agg';
  const pool=DB.stock.filter(r=>r.stage==='WELD'), bom=DB.weldBom||[];
  const lines=[...new Set(pool.map(r=>r.loc).filter(Boolean))].sort();
  const draw=()=>{
    c.innerHTML=`
     <div class="page-title">용접 재고</div>
     <div class="page-sub">용접(가공제외) 재공 · ${mode==='agg'?'ASSY 단위 집계':'BOM풀기(하위품번 전개) — ✔검증 07/15: 142,353 / ₩346.5M'}</div>
     <div class="toolbar">
       <div class="toggle-group"><button id="t-agg" class="${mode==='agg'?'on':''}">집계</button><button id="t-bom" class="${mode==='bom'?'on':''}">BOM풀기</button></div>
       <input class="inp" id="q" placeholder="${mode==='agg'?'품목코드/품명':'ASSY/자재품번/품명'}">
       ${mode==='agg'?`<select class="sel" id="line"><option value="">전체라인</option>${lines.map(l=>`<option value="${esc(l)}">${esc(lineName(l))}</option>`).join('')}</select>`:''}
       <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
       <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
     </div>
     <div class="summary-bar" id="sum"></div>
     <div class="grid-wrap" style="max-height:520px"><table class="tbl"><thead id="th"></thead><tbody id="body"></tbody></table></div>
     <div class="rowcount" id="cnt"></div>`;
    let cur=[];
    function sumbar(rows){const qty=rows.reduce((a,b)=>a+(+b.qty||0),0),amt=rows.reduce((a,b)=>a+(+b.amt||0),0);
      c.querySelector('#sum').innerHTML=`<div class="s-item">건수 <b>${won(rows.length)}</b></div>
        <div class="s-item">재고수량 합계 <b>${won(qty)}</b></div>
        <div class="s-item ${amt<0?'neg':''}">재고금액 합계 <b>${won(amt)} 원</b></div>`;}
    if(mode==='agg'){
      c.querySelector('#th').innerHTML=`<tr><th>품목코드</th><th>품명</th><th>유형</th><th class="center">라인</th><th class="num">재고수량</th><th class="center">단위</th><th class="num">단가</th><th class="num">재고금액</th></tr>`;
      const render=rows=>{cur=rows;
        c.querySelector('#body').innerHTML=rows.length?rows.map(r=>`<tr><td><b>${esc(r.cd)}</b></td><td>${esc(r.nm)}</td><td>${tbadge(r.type)}</td><td class="center">${esc(lineName(r.loc))||'-'}</td><td class="num qty">${won(r.qty)}</td><td class="center">${esc(r.uom)}</td><td class="num">${won(r.cost)}</td><td class="num"><b>${won(r.amt)}</b></td></tr>`).join(''):`<tr><td colspan="8" class="empty">결과 없음</td></tr>`;
        sumbar(rows);c.querySelector('#cnt').textContent=`${rows.length}건 / 대상 ${pool.length}건`;};
      const apply=()=>{const q=c.querySelector('#q').value.trim().toLowerCase(),ln=c.querySelector('#line').value;
        render(pool.filter(r=>(!ln||r.loc===ln)&&(!q||r.cd.toLowerCase().includes(q)||(r.nm||'').toLowerCase().includes(q))));};
      c.querySelector('#go').onclick=apply;c.querySelector('#q').onkeyup=e=>{if(e.key==='Enter')apply();};
      c.querySelector('#line').onchange=apply;
      c.querySelector('#reset').onclick=()=>{c.querySelector('#q').value='';c.querySelector('#line').value='';apply();};
      c.querySelector('#xls').onclick=()=>downloadCSV('용접재고_집계.csv',['품목코드','품명','유형','라인','재고수량','단위','단가','재고금액'],cur.map(r=>[r.cd,r.nm,TYPE_NM[r.type]||r.type,r.loc,r.qty,r.uom,r.cost,r.amt]));
      render(pool);
    } else {
      c.querySelector('#th').innerHTML=`<tr><th>ASSY 품번</th><th>자재품번</th><th>품명</th><th>거래처</th><th class="num">재고수량</th><th class="num">단가</th><th class="num">금액</th></tr>`;
      const render=rows=>{cur=rows;
        c.querySelector('#body').innerHTML=rows.length?rows.map(r=>`<tr><td>${esc(r.assy)||'-'}</td><td><b>${esc(r.mat)}</b></td><td>${esc(r.nm)}</td><td>${esc(r.cust)||'-'}</td><td class="num qty">${won(r.qty)}</td><td class="num">${won(r.cost)}</td><td class="num"><b>${won(r.amt)}</b></td></tr>`).join(''):`<tr><td colspan="7" class="empty">결과 없음</td></tr>`;
        sumbar(rows);c.querySelector('#cnt').textContent=`${rows.length}건 / 대상 ${bom.length}건`;};
      const apply=()=>{const q=c.querySelector('#q').value.trim().toLowerCase();
        render(bom.filter(r=>(!q||(r.mat||'').toLowerCase().includes(q)||(r.assy||'').toLowerCase().includes(q)||(r.nm||'').toLowerCase().includes(q))));};
      c.querySelector('#go').onclick=apply;c.querySelector('#q').onkeyup=e=>{if(e.key==='Enter')apply();};
      c.querySelector('#reset').onclick=()=>{c.querySelector('#q').value='';apply();};
      c.querySelector('#xls').onclick=()=>downloadCSV('용접재고_BOM풀기.csv',['ASSY품번','자재품번','품명','거래처','재고수량','단가','금액'],cur.map(r=>[r.assy,r.mat,r.nm,r.cust,r.qty,r.cost,r.amt]));
      render(bom);
    }
    c.querySelector('#t-agg').onclick=()=>{mode='agg';draw();};
    c.querySelector('#t-bom').onclick=()=>{mode='bom';draw();};
  };
  draw();
};

/* ===== 생산: 주문업로드 (w_pr_plan_010) — LG PU-SCS Purchase Order → nx.recv_dtl ===== */
SCREEN.orderupload=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const ymd=s=>(s&&(''+s).length===6)?`${(''+s).slice(0,2)}/${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:(s||'');
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  let F={from:iso(new Date(T.getFullYear(),T.getMonth(),1)),to:iso(T),nfrom:'',nto:'',done:'all',item:'',wo:'',cr:''};
  let data={rows:[],count:0,sum_qty:0,sum_amt:0}, loading=false, msg='', upcr='C', upfile=null;
  const load=async()=>{loading=true;draw();
    const qs=new URLSearchParams({from_ymd:F.from,to_ymd:F.to,need_from:F.nfrom,need_to:F.nto,done:F.done,item:F.item,wo:F.wo,cr:F.cr});
    try{const r=await fetch(`${API}/api/order/list?${qs}`);data=await r.json();msg='';}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';data={rows:[],count:0,sum_qty:0,sum_amt:0};}
    loading=false;draw();};
  const doUpload=async()=>{
    if(!upfile){alert('업로드할 엑셀 파일을 선택하세요.');return;}
    msg='업로드 중...';draw();
    const b64=await new Promise(res=>{const fr=new FileReader();fr.onload=()=>res(fr.result);fr.readAsDataURL(upfile);});
    try{const r=await fetch(`${API}/api/order/upload`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cr:upcr,b64})});
      const j=await r.json();
      if(j.ok){alert(`주문 UPLOAD 완료\n신규 ${nf(j.inserted)} · 갱신 ${nf(j.updated)} · 총 ${nf(j.total)}건 (구분 ${j.cr})`);upfile=null;load();return;}
      alert('업로드 실패: '+(j.detail||JSON.stringify(j)));}
    catch(e){alert('업로드 실패: '+e);}
    msg='';draw();};
  const draw=()=>{
    const canW=(typeof PERM!=='undefined')?PERM.canEdit('orderupload'):true;   // 수정권한 게이트(규칙#16)
    c.innerHTML=`
     <div class="page-title">📥 주문업로드 <span style="font-size:12px;color:var(--muted);font-weight:400">LG PU-SCS Purchase Order → 주문원장</span></div>
     <div class="page-sub">LG Open PO 엑셀(Material·PO No·Delivery Date·Order/Open Qty·P/S Order·Order Date·Unit Price)을 업로드합니다. 저장 <code>nx.recv_dtl</code> · 레거시 <code>SP_LGE_RECV_ORDER</code>/w_pr_plan_010 실검증(품번·단가·워크오더·납기·CR 0불일치)</div>
     <div class="toolbar">
       <label class="tl">주문기간</label><input class="inp" type="date" id="o-from" value="${F.from}"> ~ <input class="inp" type="date" id="o-to" value="${F.to}">
       <label class="tl">납기</label><input class="inp" type="date" id="o-nf" value="${F.nfrom}"> ~ <input class="inp" type="date" id="o-nt" value="${F.nto}">
       <label class="tl">납품</label><select class="inp" id="o-done"><option value="all"${F.done==='all'?' selected':''}>전체</option><option value="undone"${F.done==='undone'?' selected':''}>미완료</option><option value="done"${F.done==='done'?' selected':''}>완료</option></select>
     </div>
     <div class="toolbar" style="margin-top:2px">
       <label class="tl">품번</label><input class="inp" id="o-item" value="${esc(F.item)}" style="width:130px">
       <label class="tl">W/O</label><input class="inp" id="o-wo" value="${esc(F.wo)}" style="width:110px">
       <label class="tl">구분</label><select class="inp" id="o-cr"><option value=""${F.cr===''?' selected':''}>전체</option><option value="C"${F.cr==='C'?' selected':''}>C(SAC)</option><option value="R"${F.cr==='R'?' selected':''}>R(RAC)</option></select>
       <button class="btn" id="o-search">🔍 조회</button>
       <div class="spacer"></div>
       ${canW?`<label class="tl">업로드</label><select class="inp" id="o-upcr"><option value="C"${upcr==='C'?' selected':''}>C(SAC)</option><option value="R"${upcr==='R'?' selected':''}>R(RAC)</option></select>
       <input type="file" id="o-file" accept=".xls,.xlsx" style="width:200px">
       <button class="btn" id="o-upload" style="background:#1c47a0;color:#fff">📥 주문UPLOAD</button>`:`<span style="color:#c0392b;font-size:12px">🔒 업로드 권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span>`}
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="toolbar" style="margin-top:2px"><span class="rowcount">총 <b>${nf(data.count)}</b>건 · 수량 <b>${nf(data.sum_qty)}</b> · 금액 <b>${nf(data.sum_amt)}</b>원${data.count>=5000?' <span style="color:#c0392b">(상위 5,000건)</span>':''}</span></div>
     <div class="grid-wrap" style="max-height:calc(100vh - 330px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:12px"><thead><tr>
       <th>주문번호</th><th>주문일자</th><th>품번</th><th>품명</th><th class="num">주문수량</th><th class="num">잔량</th><th>납기</th><th>시각</th><th>WORK-ORDER</th><th class="num">주문단가</th><th class="num">금액</th><th>구분</th></tr></thead>
      <tbody>${loading?spinRow(12):((data.rows&&data.rows.length)?data.rows.map(r=>`<tr>
        <td>${esc(r.ORDER_NO)}</td><td class="center">${ymd(r.ORDER_YMD)}</td><td><b>${esc(r.ITEM_CODE)}</b></td>
        <td class="bcap" title="${esc(r.nm)}" style="max-width:200px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td>
        <td class="num">${nf(r.ORDER_QTY)}</td><td class="num">${nf(r.REMAIN_QTY)}</td><td class="center">${ymd(r.NEED_BY_YMD)}</td><td class="center">${esc(r.NEED_BY_HM)}</td>
        <td>${esc(r.WORK_ORDER)}</td><td class="num">${nf(r.ITEM_COST)}</td><td class="num">${nf(r.AMT)}</td><td class="center">${esc(r.CR_FLAG)}</td></tr>`).join(''):`<tr><td colspan="12" class="empty">조회 결과 없음 — 조건을 바꾸거나 엑셀을 업로드하세요.</td></tr>`)}</tbody></table></div>`;
    const g=id=>c.querySelector(id);
    g('#o-search').onclick=()=>{F.from=g('#o-from').value;F.to=g('#o-to').value;F.nfrom=g('#o-nf').value;F.nto=g('#o-nt').value;F.done=g('#o-done').value;F.item=g('#o-item').value;F.wo=g('#o-wo').value;F.cr=g('#o-cr').value;load();};
    if(canW){g('#o-upcr').onchange=e=>upcr=e.target.value;
      g('#o-file').onchange=e=>upfile=e.target.files[0]||null;
      g('#o-upload').onclick=doUpload;}
    ['#o-item','#o-wo'].forEach(id=>g(id).onkeyup=e=>{if(e.key==='Enter')g('#o-search').click();});
  };
  load();
};

/* ===== 생산: 생산계획업로드 (w_pr_plan_020) — LG Production Plan Status → nx.plan_dtl ===== */
SCREEN.planupload=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:s;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  let F={from:iso(T),to:iso(new Date(T.getTime()+30*864e5)),line:'',sched:'',wo:'',model:'',cr:''};
  let data={dates:[],rows:[],wo_count:0,sum_qty:0}, loading=false, msg='', upcr='C', upfile=null;
  const load=async()=>{loading=true;draw();
    const qs=new URLSearchParams({from_ymd:F.from,to_ymd:F.to,line:F.line,sched:F.sched,wo:F.wo,model:F.model,cr:F.cr});
    try{const r=await fetch(`${API}/api/plan/list?${qs}`);data=await r.json();msg='';}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';data={dates:[],rows:[],wo_count:0,sum_qty:0};}
    loading=false;draw();};
  const doUpload=async()=>{
    if(!upfile){alert('업로드할 엑셀 파일을 선택하세요.');return;}
    msg='업로드 중...';draw();
    const b64=await new Promise(res=>{const fr=new FileReader();fr.onload=()=>res(fr.result);fr.readAsDataURL(upfile);});
    try{const r=await fetch(`${API}/api/plan/upload`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cr:upcr,b64})});
      const j=await r.json();
      if(j.ok){alert(`생산계획 UPLOAD 완료\n신규 ${nf(j.inserted)} · 갱신 ${nf(j.updated)} · 총 ${nf(j.total)} (WO,일자) (구분 ${j.cr})`);upfile=null;load();return;}
      alert('업로드 실패: '+(j.detail||JSON.stringify(j)));}
    catch(e){alert('업로드 실패: '+e);}
    msg='';draw();};
  const draw=()=>{
    const dates=data.dates||[];
    const canW=(typeof PERM!=='undefined')?PERM.canEdit('planupload'):true;   // 수정권한 게이트(규칙#16)
    c.innerHTML=`
     <div class="page-title">📅 생산계획업로드 <span style="font-size:12px;color:var(--muted);font-weight:400">LG PU-SCS Production Plan Status → 생산계획</span></div>
     <div class="page-sub">LG 생산계획 엑셀(Line·P/S Order·Material·일자별 수량)을 업로드합니다. 일별 컬럼을 (제번,일자)로 전개. 저장 <code>nx.plan_dtl</code> · 레거시 w_pr_plan_020 실검증(WO총량 100% 일치)</div>
     <div class="toolbar">
       <label class="tl">계획기간</label><input class="inp" type="date" id="p-from" value="${F.from}"> ~ <input class="inp" type="date" id="p-to" value="${F.to}">
       <label class="tl">라인</label><input class="inp" id="p-line" value="${esc(F.line)}" style="width:70px">
       <label class="tl">그룹</label><input class="inp" id="p-sched" value="${esc(F.sched)}" style="width:60px">
       <label class="tl">W/O</label><input class="inp" id="p-wo" value="${esc(F.wo)}" style="width:100px">
       <label class="tl">모델</label><input class="inp" id="p-model" value="${esc(F.model)}" style="width:120px">
       <label class="tl">구분</label><select class="inp" id="p-cr"><option value=""${F.cr===''?' selected':''}>전체</option><option value="C"${F.cr==='C'?' selected':''}>C</option><option value="R"${F.cr==='R'?' selected':''}>R</option></select>
       <button class="btn" id="p-search">🔍 조회</button>
     </div>
     <div class="toolbar" style="margin-top:2px">
       <div class="spacer"></div>
       ${canW?`<label class="tl">업로드</label><select class="inp" id="p-upcr"><option value="C"${upcr==='C'?' selected':''}>C(SAC)</option><option value="R"${upcr==='R'?' selected':''}>R(RAC)</option></select>
       <input type="file" id="p-file" accept=".xls,.xlsx" style="width:200px">
       <button class="btn" id="p-upload" style="background:#1c47a0;color:#fff">📅 생산계획UPLOAD</button>
       <button class="btn" id="p-compose" style="background:#1c7c3a;color:#fff" title="ASSY→자도번 전개 + 조달프로파일 라우팅">🔗 협력사계획 편성</button>
       <button class="btn" id="p-compmat" style="background:#7a4ca0;color:#fff" title="레거시 STEP5→6→7 충실이식 정본 자재소요 + 조달 프로파일 오버레이 (수량100% 검증)">🧾 자재소요·조달 편성</button>`:`<span style="color:#c0392b;font-size:12px">🔒 업로드 권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span>`}
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="toolbar" style="margin-top:2px"><span class="rowcount">WO <b>${nf(data.wo_count)}</b> · 계획수량합 <b>${nf(data.sum_qty)}</b> · 일자 ${dates.length}개</span></div>
     <div class="grid-wrap" style="max-height:calc(100vh - 330px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:11px"><thead><tr>
       <th>라인</th><th>WORK-ORDER</th><th>모델</th><th>그룹</th><th class="num">Total</th><th class="num">잔량</th>${dates.map(d=>`<th class="num">${dcol(d)}</th>`).join('')}</tr></thead>
      <tbody>${loading?spinRow(6+dates.length):((data.rows&&data.rows.length)?data.rows.map(r=>`<tr>
        <td class="center">${esc(r.line)}</td><td><b>${esc(r.wo)}</b></td>
        <td class="bcap" title="${esc(r.model)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.model)}</td>
        <td class="center">${esc(r.sched)}</td><td class="num">${nf(r.total)}</td><td class="num">${nf(r.remain)}</td>
        ${dates.map(d=>{const v=(r.days&&r.days[d])||0;return `<td class="num"${v?'':' style="color:#dfe6ef"'}>${v?nf(v):'·'}</td>`;}).join('')}</tr>`).join(''):`<tr><td colspan="${6+dates.length}" class="empty">조회 결과 없음 — 조건을 바꾸거나 엑셀을 업로드하세요.</td></tr>`)}</tbody></table></div>`;
    const g=id=>c.querySelector(id);
    g('#p-search').onclick=()=>{F.from=g('#p-from').value;F.to=g('#p-to').value;F.line=g('#p-line').value;F.sched=g('#p-sched').value;F.wo=g('#p-wo').value;F.model=g('#p-model').value;F.cr=g('#p-cr').value;load();};
    if(canW){g('#p-upcr').onchange=e=>upcr=e.target.value;
      g('#p-file').onchange=e=>upfile=e.target.files[0]||null;
      g('#p-upload').onclick=doUpload;}
    const cp=g('#p-compose');if(cp)cp.onclick=async()=>{if(!confirm('업로드된 생산계획 전량을 협력사계획으로 편성합니다.\n(ASSY→자도번 전개 + 조달프로파일 라우팅)\n진행할까요?'))return;
      cp.disabled=true;cp.textContent='편성 중…';
      try{const r=await fetch(`${API}/api/plan/compose`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const jj=await r.json();
        if(jj.ok)alert(`협력사계획 편성 완료\n매핑 ${nf(jj.mapped)} / 미매핑 ${nf(jj.unmapped)}(계획선행분)\n자도번 계획라인 ${nf(jj.part_lines)}\n\n→ 파트별 생산계획 화면에서 확인`);
        else alert('편성 실패: '+(jj.detail||JSON.stringify(jj)));}
      catch(e){alert('편성 실패: '+e);}
      cp.disabled=false;cp.textContent='🔗 협력사계획 편성';};
    const cm=g('#p-compmat');if(cm)cm.onclick=async()=>{if(!confirm('업로드된 생산계획으로 정본 자재소요(레거시 STEP5→6→7)를 산출하고\n조달 프로파일을 오버레이해 조달 소요를 편성합니다.\n(수량 100% 검증본)\n진행할까요?'))return;
      cm.disabled=true;cm.textContent='편성 중…';
      try{const r=await fetch(`${API}/api/plan/compose_mat`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const jj=await r.json();
        if(jj.ok)alert(`자재소요·조달 편성 완료\n품목계획 ${nf(jj.item_lines)} · 자재소요 ${nf(jj.mat_lines)}(제번 ${nf(jj.mat_work_orders)}) · 조달소요 ${nf(jj.sourcing_lines)}\n\n→ 「자재소요·조달 조회」 화면에서 확인`);
        else alert('편성 실패: '+(jj.error||jj.detail||JSON.stringify(jj)));}
      catch(e){alert('편성 실패: '+e);}
      cm.disabled=false;cm.textContent='🧾 자재소요·조달 편성';};
    ['#p-wo','#p-model','#p-line'].forEach(id=>g(id).onkeyup=e=>{if(e.key==='Enter')g('#p-search').click();});
  };
  load();
};

SCREEN.partplan=(c)=>{
  // 파트별 생산계획 — 레거시 w_pr_input_410_new 재현. ★데이터/색상 정본 = 키팅과 동일 SP(GROUP BY gpc·wo·swo·assy·upper·item, 날짜피벗) → /api/kitting/grid 재사용(nx 직독). 값·색상 키팅과 자동일치.
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const f2=n=>Number(n||0).toLocaleString('ko-KR',{minimumFractionDigits:2,maximumFractionDigits:2});
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:(s||'');
  const iso=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const wlab=y=>{if(!y||y.length<6)return dcol(y);const dt=new Date(2000+ +y.slice(0,2),+y.slice(2,4)-1,+y.slice(4,6));const dow='일월화수목금토'[dt.getDay()];return `${y.slice(4,6)}${dow}`;};
  const isWkend=y=>{if(!y||y.length<6)return false;const dt=new Date(2000+ +y.slice(0,2),+y.slice(2,4)-1,+y.slice(4,6));return dt.getDay()===0||dt.getDay()===6;};
  // 당김,변경 = CHANGE_DAY + ',' + (LOT_QTY − LAST_LOT_QTY). 전차수 대비 일자·수량 변경(레거시 c_remarks3). 둘다 0이면 공백, 수량변경시 빨강.
  const pulltxt=r=>{const cd=(r.change_day||'').trim(),ld=+r.lot_diff||0;if(!cd&&!ld)return '';return `${cd}${cd&&ld?',':''}${ld?(ld>0?'+':'')+ld:(cd?'':'')}`;};
  const T=new Date();
  // ★색상 정본(레거시 c_color CASE = kitting finBg 이식): 90주황(출하완료)/70노랑(생산완료)/50·10녹(키팅완료)/else 백(미키팅)
  const finBg=f=>f==='6'?'#fac090':(f==='4'?'#ffff00':(f==='3'?'#669900':''));
  const finFg=f=>f==='3'?'#ffffff':'';
  const st={dates:[],rows:[],cnt:0,plan_sum:0,inwon:0,note:'',base:iso(T),gigan:2,wc:'',part:'',dono:'',jado:'',unfin:'전체',view:'전체',src:'nx',loading:false,msg:''};
  const load=async()=>{st.loading=true;render();
    const qs=new URLSearchParams({from_ymd:st.base,gigan:st.gigan,wc:st.wc,part:st.part,assy:st.dono,jado:st.jado,view:st.view,unfin:st.unfin,src:st.src,limit:8000});
    try{const r=await fetch(`${API}/api/plan/part410?${qs}`);const j=await r.json();st.dates=j.dates||[];st.rows=j.rows||[];st.cnt=j.cnt||0;st.plan_sum=j.plan_sum||0;st.inwon=j.inwon||0;st.note=j.note||'';st.msg='';}
    catch(e){st.msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';st.rows=[];st.dates=[];}
    st.loading=false;render();};
  const shiftDay=n=>{const d=new Date(st.base);d.setDate(d.getDate()+n);st.base=iso(d);load();};
  // 생산ST(행) = (생산계획 − 완료) × item_st(초) / 3600  [레거시 c_item_st]
  const rowST=r=>Math.max((+r.plan_qty||0)-(+r.finish||0),0)*(+r.item_st||0)/3600;
  const render=()=>{
    const d=st.dates;
    const wcM=new Map([['P1','용접'],['P2','가공']]);
    const PART_FIX=[['S5','01라인(용접)'],['S5-2','01라인(조립)'],['S1','02라인'],['S6','03라인'],['S4','04라인'],['S11','05라인'],['RAC','06라인'],['S10','자동은납 10'],['S13','서브/고주파'],['S12','설치'],['S8','서포터 08'],['S9','용접 09'],['S7','다관절 로봇 용접'],['-','-'],['Q1000','용접봉창고']];
    const partOpts='<option value=""'+(st.part?'':' selected')+'>전체</option>'+PART_FIX.map(([v,n])=>v==='-'?'<option disabled>─────────</option>':`<option value="${esc(v)}"${st.part===v?' selected':''}>${esc(n)}</option>`).join('');
    const seg=(name,val,opts)=>opts.map(v=>`<label style="font-weight:400;margin:0 5px 0 1px"><input type="radio" name="${name}" value="${v}" ${val===v?'checked':''}> ${v}</label>`).join('');
    // ── 구분(view): 집계=도번(item)단위 롤업 / 전체·제번=제번(WO)단위 상세 ──
    let disp=st.rows;
    if(st.view==='집계'){
      const agg=new Map();
      st.rows.forEach(r=>{const k=r.gpc+'|'+r.assy+'|'+r.upper+'|'+r.item;let g=agg.get(k);
        if(!g){g={gpcnm:r.gpcnm,gpc:r.gpc,assy:r.assy,upper:r.upper,item:r.item,nm:r.nm,line:r.line,inhm:r.inhm,part_ymd:r.part_ymd,plan_ymd:r.plan_ymd,item_st:r.item_st,change_day:r.change_day,lot_diff:0,wo:'(집계)',swo:'',plan_qty:0,finish:0,prior_plan:0,prior_cover:0,prior_fin:'0',days:{},dcov:{},dfin:{}};agg.set(k,g);}
        g.plan_qty+=+r.plan_qty||0;g.finish+=+r.finish||0;g.prior_plan+=+r.prior_plan||0;g.prior_cover+=+r.prior_cover||0;g.lot_diff+=+r.lot_diff||0;if(!g.change_day)g.change_day=r.change_day;
        if((r.part_ymd||'')<(g.part_ymd||'zz'))g.part_ymd=r.part_ymd;
        if(+r.prior_plan>0&&(g.prior_fin==='0'||finRank(r.prior_fin)<finRank(g.prior_fin)))g.prior_fin=r.prior_fin;
        d.forEach(x=>{if(r.days&&r.days[x]){g.days[x]=(g.days[x]||0)+r.days[x];g.dcov[x]=(g.dcov[x]||0)+((r.dcov&&r.dcov[x])||0);
          const cf=(r.dfin&&r.dfin[x])||'0';if(!g.dfin[x]||g.dfin[x]==='0'||finRank(cf)<finRank(g.dfin[x]))g.dfin[x]=cf;}});});
      disp=[...agg.values()];
    }
    // 정렬: PART일자+INPUT → 도번 → WO (레거시 sort)
    disp=disp.slice().sort((a,b)=>((a.part_ymd||'')+(a.inhm||'')).localeCompare((b.part_ymd||'')+(b.inhm||''))||(a.item||'').localeCompare(b.item||'')||(a.wo||'').localeCompare(b.wo||''));
    const NCOL=12;  // 고정컬럼(파트..당일이전계획)
    const numTd=(v,bg,strong,fg)=>`<td class="num"${bg?` style="background:${bg}${strong?';font-weight:700':''}${fg?';color:'+fg:''}"`:''}>${v}</td>`;
    const pcell=r=>r.prior_plan>0?`${nf(r.prior_cover)}/${nf(r.prior_plan)}`:'·';
    const rowHtml=(r,seq)=>{const pf=r.prior_fin||'0';
      return `<tr>
        <td class="center mut">${seq}</td><td>${esc(r.gpcnm||r.gpc)}</td>
        <td><b>${esc(r.assy)}</b></td><td>${esc(r.upper||'')}</td><td>${esc(r.item)}</td>
        <td class="bcap" title="${esc(r.nm||'')}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm||'')}</td>
        <td class="center">${esc(r.line||'')}</td><td class="center">${esc(dcol(r.part_ymd||''))}</td><td class="center">${esc(r.inhm||'')}</td>
        <td class="center" style="color:${(+r.lot_diff||0)?'#c0392b':'#b8791f'};font-weight:${(+r.lot_diff||0)?'700':'400'}">${esc(pulltxt(r))}</td>
        <td class="num">${f2(rowST(r))}</td><td class="num"><b>${nf(r.plan_qty)}</b></td>
        ${r.prior_plan>0?numTd(pcell(r),finBg(pf)||'#eef4fb',pf!=='0',finFg(pf)):numTd('·','',false)}
        ${d.map(x=>{const pl=(r.days&&r.days[x])||0,cv=(r.dcov&&r.dcov[x])||0,cf=(r.dfin&&r.dfin[x])||'0';return pl?numTd(`${nf(cv)}/${nf(pl)}`,finBg(cf)||'#eef4fb',cf!=='0',finFg(cf)):numTd('·','',false);}).join('')}</tr>`;};
    // footer: 당일이전·일자별 (완료/계획) + 생산ST행
    const fPrP=disp.reduce((s,r)=>s+(+r.prior_plan||0),0), fPrC=disp.reduce((s,r)=>s+(+r.prior_cover||0),0);
    const fPl=x=>disp.reduce((s,r)=>s+((r.days&&r.days[x])||0),0), fCv=x=>disp.reduce((s,r)=>s+((r.dcov&&r.dcov[x])||0),0);
    const fST=disp.reduce((s,r)=>s+rowST(r),0);
    const fSTd=x=>disp.reduce((s,r)=>s+Math.max(((r.days&&r.days[x])||0)-((r.dcov&&r.dcov[x])||0),0)*(+r.item_st||0)/3600,0);
    const fSTprior=disp.reduce((s,r)=>s+Math.max((+r.prior_plan||0)-(+r.prior_cover||0),0)*(+r.item_st||0)/3600,0);
    c.innerHTML=`
     <div class="page-title">🧩 파트별 생산계획 <span style="font-size:12px;color:var(--muted);font-weight:400">w_pr_input_410_new · nx 직독(키팅과 동일 SP·색상)</span></div>
     <div class="page-sub">사내 생산품(용접/가공) 파트별 일자계획. 당일이전계획=기준일 이전 계획 누적(완료/계획). 셀=완료/계획.
       <span style="background:#669900;color:#fff;padding:0 5px">녹=키팅완료</span> <span style="background:#ffff00;padding:0 5px">노랑=생산완료</span> <span style="background:#fac090;padding:0 5px">주황=출하완료</span> 백=미키팅</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <label class="tl">기준일자</label><button class="btn ghost" id="pp-prev" title="전일" style="padding:2px 6px">◀</button>
       <input class="inp" type="date" id="pp-base" value="${st.base}" style="width:138px">
       <button class="btn ghost" id="pp-next" title="익일" style="padding:2px 6px">▶</button>
       <label class="tl">적용일수</label><select class="inp" id="pp-gigan" style="width:62px">${[1,2,3,4,5,6,7,8,9,10].map(n=>`<option value="${n}"${st.gigan===n?' selected':''}>${n}일</option>`).join('')}</select>
       <label class="tl">자도번작업처</label><select class="inp" id="pp-wc" style="width:80px"><option value="">전체</option>${[...wcM].map(([v,n])=>`<option value="${esc(v)}"${st.wc===v?' selected':''}>${esc(n)}</option>`).join('')}</select>
       <label class="tl">파트</label><select class="inp" id="pp-part" style="width:130px">${partOpts}</select>
       <label class="tl">도번</label><input class="inp" id="pp-dono" value="${esc(st.dono)}" style="width:100px" placeholder="ASSY도번" autocomplete="off">
       <label class="tl">자도번</label><input class="inp" id="pp-jado" value="${esc(st.jado)}" style="width:100px" placeholder="도번(item)" autocomplete="off">
       <label class="tl">미생산</label>${seg('pp-uf',st.unfin,['전체','미생산'])}
       <label class="tl">구분</label>${seg('pp-vw',st.view,['전체','집계','제번'])}
       <label class="tl">소스</label><select class="inp" id="pp-src" style="width:110px"><option value="nx"${st.src==='nx'?' selected':''}>우리(nx)</option><option value="live"${st.src==='live'?' selected':''}>라이브 대사</option></select>
       <button class="btn" id="pp-go">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">${nf(disp.length)}건 · 계획합 <b>${nf(st.plan_sum)}</b> · 인원 ${nf(st.inwon)} · ${st.src==='live'?'🔴 라이브':'🟢 nx'} · 일자 ${d.length}개</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(st.msg)}</div>`:''}
     ${st.note?`<div class="page-sub" style="color:#b8860b">${esc(st.note)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr>
       <th>SEQ</th><th>파트</th><th>Assy도번</th><th>상위도번</th><th>도번</th><th>품명</th><th>Line No</th><th>PART일자</th><th>PART INPUT</th><th>당김</th><th class="num">생산ST</th><th class="num">생산계획</th><th class="num">당일이전계획</th>${d.map(x=>`<th class="num"${isWkend(x)?' style="color:#c0392b"':''}>${esc(wlab(x))}</th>`).join('')}</tr></thead>
      <tbody>${st.loading?spinRow(NCOL+d.length):(disp.length?disp.map((r,i)=>rowHtml(r,i+1)).join(''):`<tr><td colspan="${NCOL+d.length}" class="empty">조회 결과 없음 — 기준일자/작업처/파트/도번을 조정하세요</td></tr>`)}</tbody>
      ${disp.length?(()=>{const iw=st.inwon||0;return `<tfoot>
       <tr class="grandtot" style="position:sticky;bottom:44px;background:#eef2f7;font-weight:700;border-top:2px solid #b8c4d4">
        <td class="center" colspan="10">합계</td><td class="num">${f2(fST)}</td><td class="num">${nf(st.plan_sum)}</td>
        <td class="num">${fPrP>0?nf(fPrC)+'/'+nf(fPrP):'·'}</td>${d.map(x=>{const pl=fPl(x);return `<td class="num">${pl>0?nf(fCv(x))+'/'+nf(pl):'0/0'}</td>`;}).join('')}</tr>
       <tr class="grandtot" style="position:sticky;bottom:22px;background:#f4f7fc;color:#456;border-top:1px solid #d3ddea">
        <td class="center" colspan="10" style="font-weight:600">생산ST</td><td class="num">${f2(fST)}</td><td></td>
        <td class="num">${f2(fSTprior)}</td>${d.map(x=>`<td class="num">${f2(fSTd(x))}</td>`).join('')}</tr>
       <tr class="grandtot" style="position:sticky;bottom:0;background:#f4f7fc;color:#666;border-top:1px solid #d3ddea">
        <td class="center" colspan="10" style="font-weight:600">계상근무공수 (÷인원 ${nf(iw)})</td><td class="num">${iw?f2(fST/iw):'—'}</td><td></td>
        <td class="num"></td>${d.map((x,xi)=>`<td class="num">${iw?f2(((xi===0?fSTprior:0)+fSTd(x))/iw):'—'}</td>`).join('')}</tr>
       </tfoot>`;})():''}
      </table></div>`;
    const g=id=>c.querySelector(id);
    g('#pp-go').onclick=()=>{st.base=g('#pp-base').value;st.wc=g('#pp-wc').value;st.part=g('#pp-part').value;
      st.dono=g('#pp-dono').value.trim();st.jado=g('#pp-jado').value.trim();st.gigan=+g('#pp-gigan').value;st.src=g('#pp-src').value;
      const uf=c.querySelector('input[name=pp-uf]:checked');if(uf)st.unfin=uf.value;
      const vw=c.querySelector('input[name=pp-vw]:checked');if(vw)st.view=vw.value;
      load();};
    g('#pp-prev').onclick=()=>shiftDay(-1);g('#pp-next').onclick=()=>shiftDay(1);
    ['#pp-dono','#pp-jado'].forEach(id=>{const e=g(id);if(e)e.onkeyup=ev=>{if(ev.key==='Enter')g('#pp-go').click();};});
    if(typeof attachResizers==='function')attachResizers(c);
  };
  render();load();
};
// 색 우선순위(낮을수록 완료단계 높음): 출하6 < 생산4 < 키팅3 < 자재2 < 미키팅0
function finRank(f){return {'6':1,'4':2,'3':3,'2':4,'0':9}[f]||9;}

/* ===== 생산 ③: 생산실적현황 (w_pr_list_010) — 작업장별집계/도번별상세(실측확정) ===== */
SCREEN.prodresult=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const nf1=n=>Number(n||0).toLocaleString('ko-KR',{minimumFractionDigits:1,maximumFractionDigits:1});
  const ymd=s=>(s&&(''+s).length===6)?`${(''+s).slice(0,2)}/${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:s;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  let F={from:iso(new Date(T.getFullYear(),T.getMonth(),1)),to:iso(T),swork:'',line:'',item:'',tag:'',gubun:'1'};
  let works=[], lines=[], filtLoaded=false, acT=null;
  let data={mode:'1',rows:[],cnt:0,sum_lot:0,sum_qty:0,sum_st:0}, loading=false, msg='';
  const tagCell=g=>g==='양산'?'<span style="color:#1c47a0;font-weight:700">양산</span>':(g==='셀'?'<span style="color:#8a5a1a;font-weight:700">셀</span>':'');
  const acItem=(val)=>{clearTimeout(acT);const t=(val||'').trim();if(!t)return;acT=setTimeout(async()=>{try{const r=await fetch(`${API}/api/bom/search?q=${encodeURIComponent(t)}`);const rows=(await r.json()).rows||[];const dl=c.querySelector('#pr-itemdl');if(dl)dl.innerHTML=rows.slice(0,40).map(s=>`<option value="${esc(s.item)}">${esc((s.name||'').replace(/"/g,''))}</option>`).join('');}catch(e){}},180);};
  const loadFilters=async()=>{try{const r=await fetch(`${API}/api/prodresult/filters`);const j=await r.json();works=j.works||[];lines=j.lines||[];}catch(e){}filtLoaded=true;};
  const load=async()=>{loading=true;draw();
    const qs=new URLSearchParams({from_ymd:F.from,to_ymd:F.to,swork:F.swork,line:F.line,item:F.item,tag:F.tag,gubun:F.gubun});
    try{const r=await fetch(`${API}/api/prodresult/list?${qs}`);data=await r.json();msg='';}
    catch(e){msg='백엔드 연결 실패';data={mode:F.gubun,rows:[],cnt:0,sum_lot:0,sum_qty:0,sum_st:0};}
    loading=false;draw();};
  const draw=()=>{
    const detail=(data.mode==='2');
    const workOpts=`<option value="">전체</option>`+works.map(o=>`<option value="${esc(o.code)}"${F.swork===o.code?' selected':''}>${esc(o.code)} ${esc(o.name)}</option>`).join('');
    const lineOpts=`<option value="">전체</option>`+lines.map(l=>`<option value="${esc(l)}"${F.line===l?' selected':''}>${esc(l)}</option>`).join('');
    const head=detail
      ? `<tr><th style="text-align:left">도번</th><th style="text-align:left">품명</th><th class="center">생산일자</th><th class="center">라인</th><th class="num">생산수량</th><th class="num">필요ST</th><th class="center">구분</th></tr>`
      : `<tr><th style="text-align:left">작업장명</th><th class="center">생산일자</th><th class="num">LOT수량</th><th class="num">생산수량</th><th class="num">필요ST</th><th class="center">구분</th></tr>`;
    const ncol=detail?7:6;
    const body=loading?spinRow(ncol):(data.rows.length?data.rows.map(r=>detail
      ? `<tr><td style="text-align:left"><b>${esc(r.item)}</b></td><td style="text-align:left">${esc(r.inm)}</td><td class="center">${ymd(r.ymd)}</td><td class="center">${esc(r.line)}</td><td class="num"><b>${nf(r.qty)}</b></td><td class="num">${nf1(r.st)}</td><td class="center">${tagCell(r.gubun)}</td></tr>`
      : `<tr><td style="text-align:left">${esc((r.wc?r.wc+' ':'')+r.wcnm)||''}</td><td class="center">${ymd(r.ymd)}</td><td class="num">${nf(r.lot)}</td><td class="num"><b>${nf(r.qty)}</b></td><td class="num">${nf1(r.st)}</td><td class="center">${tagCell(r.gubun)}</td></tr>`
    ).join(''):`<tr><td colspan="${ncol}" class="empty">조회 결과 없음</td></tr>`);
    const foot=data.rows.length?(detail
      ? `<tfoot><tr class="grandtot"><td colspan="4" class="center">합계 ${nf(data.cnt)}건</td><td class="num">${nf(data.sum_qty)}</td><td class="num">${nf1(data.sum_st)}</td><td></td></tr></tfoot>`
      : `<tfoot><tr class="grandtot"><td colspan="2" class="center">합계 ${nf(data.cnt)}건</td><td class="num">${nf(data.sum_lot)}</td><td class="num">${nf(data.sum_qty)}</td><td class="num">${nf1(data.sum_st)}</td><td></td></tr></tfoot>`):'';
    c.innerHTML=`
     <div class="page-title">📊 생산실적현황 <span style="font-size:12px;color:var(--muted);font-weight:400">${detail?'도번별 상세':'작업장별 일별 집계'} · 레거시 w_pr_list_010</span></div>
     <div class="page-sub">필요ST=Σ(품목ST×생산수량)/60${detail?'':' · LOT수량=품목종수'}. 🔴 라이브 · 원본 <code>PR_T_PROD_DTL</code></div>
     <div class="toolbar">
       <label class="tl">생산기간</label><input class="inp" type="date" id="pr-from" value="${F.from}" style="width:130px"> ~ <input class="inp" type="date" id="pr-to" value="${F.to}" style="width:130px">
       <label class="tl">작업장</label><select class="inp" id="pr-sw" style="width:96px">${workOpts}</select>
       <label class="tl">라인</label><select class="inp" id="pr-line" style="width:74px">${lineOpts}</select>
       <label class="tl">양산/셀</label><select class="inp" id="pr-tag" style="width:70px"><option value=""${F.tag===''?' selected':''}>전체</option><option value="1"${F.tag==='1'?' selected':''}>양산</option><option value="2"${F.tag==='2'?' selected':''}>셀</option></select>
       <label class="tl">도번</label><input class="inp" id="pr-item" list="pr-itemdl" autocomplete="off" value="${esc(F.item)}" style="width:104px;text-transform:uppercase"><datalist id="pr-itemdl"></datalist>
       <label class="tl">조회종류</label><select class="inp" id="pr-gubun" style="width:132px"><option value="1"${F.gubun==='1'?' selected':''}>작업장별 집계</option><option value="2"${F.gubun==='2'?' selected':''}>도번별 상세</option></select>
       <button class="btn" id="pr-search">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">${nf(data.cnt)}건${detail?'':` · LOT <b>${nf(data.sum_lot)}</b>`} · 생산수량 <b>${nf(data.sum_qty)}</b> · 필요ST <b>${nf1(data.sum_st)}</b></span>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:12px"><thead>${head}</thead><tbody>${body}</tbody>${foot}</table></div>`;
    const g=id=>c.querySelector(id);
    g('#pr-search').onclick=()=>{F.from=g('#pr-from').value;F.to=g('#pr-to').value;F.swork=g('#pr-sw').value;F.line=g('#pr-line').value;F.item=g('#pr-item').value;F.tag=g('#pr-tag').value;F.gubun=g('#pr-gubun').value;load();};
    g('#pr-item').oninput=e=>acItem(e.target.value);
    g('#pr-item').onkeyup=e=>{if(e.key==='Enter')g('#pr-search').click();};
    ['#pr-sw','#pr-line','#pr-tag','#pr-gubun'].forEach(id=>g(id).onchange=()=>g('#pr-search').click());
  };
  (async()=>{await loadFilters();load();})();
};

/* ===== 생산 ④: 파트별 생산실적현황 (w_pr_list_090) — 집계/도번/바코드/가간판/스티커(실측확정) ===== */
SCREEN.partresult=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const nf1=n=>Number(n||0).toLocaleString('ko-KR',{minimumFractionDigits:1,maximumFractionDigits:1});
  const nf2=n=>Number(n||0).toLocaleString('ko-KR',{minimumFractionDigits:2,maximumFractionDigits:2});
  const ymd=s=>(s&&(''+s).length===6)?`${(''+s).slice(0,2)}/${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:s;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  // 레거시 w_pr_list_090 조회종류(list_gubun). 4(용접전표)는 제외.
  const GUBUNS=[['1','파트별 생산실적(집계)'],['2','파트별 생산실적(도번)'],['7','바코드실적처리'],['5','가간판'],['6','스티커']];
  let F={from:iso(new Date(T.getFullYear(),T.getMonth(),1)),to:iso(T),part:'',item:'',worker:'',gubun:'1'};
  let parts=[], acT=null;
  let data={mode:'1',rows:[],cnt:0,sum_qty:0,sum_st:0}, loading=false, msg='';
  const tagCell=g=>g==='양산'?'<span style="color:#1c47a0;font-weight:700">양산</span>':(g==='셀'?'<span style="color:#8a5a1a;font-weight:700">셀</span>':'');
  const pcell=r=>`<b>${esc(r.part)}</b>${r.partnm||r.pnm?' '+esc(r.partnm||r.pnm):''}`;
  // 모드별 컬럼정의 [header, align(l/c/n), render, footKey(qty/st1/st2)]
  const COLS={
    '1':[['파트','l',pcell],['생산일자','c',r=>ymd(r.ymd)],['생산수량','n',r=>`<b>${nf(r.qty)}</b>`,'qty'],['필요ST','n',r=>nf1(r.st),'st1'],['품목수','n',r=>nf(r.items)]],
    '2':[['파트','l',pcell],['도번','l',r=>`<b>${esc(r.item)}</b>`],['품명','l',r=>esc(r.inm)],['생산일자','c',r=>ymd(r.ymd)],['생산수량','n',r=>`<b>${nf(r.qty)}</b>`,'qty'],['필요ST','n',r=>nf1(r.st),'st1'],['구분','c',r=>tagCell(r.gubun)]],
    '7':[['파트코드','l',r=>esc(r.partnm||r.part)],['작업공정','l',r=>esc(((r.swork||'')+' '+(r.partnm||'')).trim())],['품번','l',r=>`<b>${esc(r.item)}</b>`],['수량','n',r=>`<b>${nf(r.qty)}</b>`,'qty'],['공정ST','n',r=>nf2(r.st),'st2'],['작업자','l',r=>esc(r.worker)],['설비','l',r=>esc(r.machnm||r.mach)],['작업시작시각','c',r=>esc(r.sta)],['작업완료시각','c',r=>esc(r.fin)],['바코드번호','c',r=>esc(r.barcode)],['전표번호','c',r=>esc(r.sheet)],['공정SEQ','c',r=>esc(r.proc_seq)],['최종처리자','l',r=>esc(r.u_user)],['최종처리일시','c',r=>esc(r.u_dt)]],
    '5':[['파트','l',pcell],['품번','l',r=>`<b>${esc(r.item)}</b>`],['양산/셀','c',r=>tagCell(r.gubun_tag)],['수량','n',r=>`<b>${nf(r.qty)}</b>`,'qty'],['공정ST','n',r=>nf2(r.st),'st2'],['설비','l',r=>esc(r.machnm||r.mach)],['작업자','l',r=>esc(r.worker)],['작업시작시각','c',r=>esc(r.sta)],['작업완료시각','c',r=>esc(r.fin)],['바코드번호','c',r=>esc(r.barcode)],['Update User','l',r=>esc(r.u_user)],['Update Datetime','c',r=>esc(r.u_dt)],['Update Ip','c',r=>esc(r.u_ip)],['Update Computer','c',r=>esc(r.u_comp)],['Update Window','c',r=>esc(r.u_win)]],
    '6':[['파트','l',pcell],['품번','l',r=>`<b>${esc(r.item)}</b>`],['수량','n',r=>`<b>${nf(r.qty)}</b>`,'qty'],['공정ST','n',r=>nf2(r.st),'st2'],['설비','l',r=>esc(r.machnm||r.mach)],['작업자','l',r=>esc(r.worker)],['작업완료시각','c',r=>esc(r.fin)],['바코드번호','c',r=>esc(r.barcode)],['Update User','l',r=>esc(r.u_user)],['Update Datetime','c',r=>esc(r.u_dt)],['Update Ip','c',r=>esc(r.u_ip)],['Update Computer','c',r=>esc(r.u_comp)],['Update Window','c',r=>esc(r.u_win)]]
  };
  const acItem=(val)=>{clearTimeout(acT);const t=(val||'').trim();if(!t)return;acT=setTimeout(async()=>{try{const r=await fetch(`${API}/api/bom/search?q=${encodeURIComponent(t)}`);const rows=(await r.json()).rows||[];const dl=c.querySelector('#pt-itemdl');if(dl)dl.innerHTML=rows.slice(0,40).map(s=>`<option value="${esc(s.item)}">${esc((s.name||'').replace(/"/g,''))}</option>`).join('');}catch(e){}},180);};
  const loadFilters=async()=>{try{const r=await fetch(`${API}/api/partresult/filters`);parts=(await r.json()).parts||[];}catch(e){}};
  const load=async()=>{loading=true;draw();
    const qs=new URLSearchParams({from_ymd:F.from,to_ymd:F.to,part:F.part,item:F.item,worker:F.worker,gubun:F.gubun});
    try{const r=await fetch(`${API}/api/partresult/list?${qs}`);data=await r.json();msg='';}
    catch(e){msg='백엔드 연결 실패';data={mode:F.gubun,rows:[],cnt:0,sum_qty:0,sum_st:0};}
    loading=false;draw();};
  const alnCls=a=>a==='n'?'num':(a==='c'?'center':'');
  const alnSty=a=>a==='l'?' style="text-align:left"':'';
  const footVal=k=>k==='qty'?nf(data.sum_qty):(k==='st1'?nf1(data.sum_st):(k==='st2'?nf2(data.sum_st):''));
  const draw=()=>{
    const m=data.mode||F.gubun, cols=COLS[m]||COLS['1'], wide=(m==='7'||m==='5'||m==='6');
    const stLbl=wide?'공정ST':'필요ST', stVal=wide?nf2(data.sum_st):nf1(data.sum_st);
    const partOpts=`<option value="">전체</option>`+parts.map(o=>`<option value="${esc(o.code)}"${F.part===o.code?' selected':''}>${esc(o.name)} (${esc(o.code)})</option>`).join('');
    const gubunOpts=GUBUNS.map(([v,l])=>`<option value="${v}"${F.gubun===v?' selected':''}>${v}:${l}</option>`).join('');
    const head=`<tr>${cols.map(cd=>`<th class="${alnCls(cd[1])}"${alnSty(cd[1])}${wide?' style="white-space:nowrap"':''}>${cd[0]}</th>`).join('')}</tr>`;
    const body=loading?spinRow(cols.length):(data.rows.length?data.rows.map(r=>`<tr>${cols.map(cd=>`<td class="${alnCls(cd[1])}"${alnSty(cd[1])}${wide?' style="white-space:nowrap"':''}>${cd[2](r)}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${cols.length}" class="empty">조회 결과 없음</td></tr>`);
    const foot=data.rows.length?`<tfoot><tr class="grandtot">${cols.map((cd,i)=>i===0?`<td class="center" style="white-space:nowrap">합계 ${nf(data.cnt)}건</td>`:(cd[3]?`<td class="num">${footVal(cd[3])}</td>`:`<td></td>`)).join('')}</tr></tfoot>`:'';
    const grid=`<table class="tbl${wide?'':' fit'}" style="font-size:12px"><thead>${head}</thead><tbody>${body}</tbody>${foot}</table>`;
    const desc={'1':'파트별 일별 집계','2':'파트·도번별 상세','7':'바코드실적처리(공정단위)','5':'가간판(가상설비 GP)','6':'스티커(실설비 00)'}[m]||'';
    const src=wide?'PR_T_PROD_DTL_STICKER + WELD_SHEET_DTL(공정ST)':'PROC(조립) ∪ STICKER(용접) ∪ CUTTING(가공)';
    c.innerHTML=`
     <div class="page-title">📈 파트별 생산실적현황 <span style="font-size:12px;color:var(--muted);font-weight:400">${desc} · 레거시 w_pr_list_090</span></div>
     <div class="page-sub">${wide?'공정ST'+(m==='7'?'=TOT_ST×수량':'=TOT_ST×수량/60')+' · 바코드단위 공정실적':'생산수량=Σ·필요ST=Σ(파트별 공정ST×수량)/60'+(m==='2'?'':'·품목수=품목종수')+' · 필요ST 합계=시간(Σ분/60)'}. 🔴 라이브 · 원본 <code>${src}</code></div>
     <div class="toolbar">
       <label class="tl">생산기간</label><input class="inp" type="date" id="pt-from" value="${F.from}" style="width:130px"> ~ <input class="inp" type="date" id="pt-to" value="${F.to}" style="width:130px">
       <label class="tl">도번</label><input class="inp" id="pt-item" list="pt-itemdl" autocomplete="off" value="${esc(F.item)}" style="width:110px;text-transform:uppercase"><datalist id="pt-itemdl"></datalist>
       <label class="tl">파트</label><select class="inp" id="pt-part" style="width:140px">${partOpts}</select>
       <label class="tl">작업자</label><input class="inp" id="pt-worker" value="${esc(F.worker)}" style="width:72px">
       <label class="tl">조회종류</label><select class="inp" id="pt-gubun" style="width:172px">${gubunOpts}</select>
       <button class="btn" id="pt-search">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">${nf(data.cnt)}건 · 생산수량 <b>${nf(data.sum_qty)}</b> · ${stLbl} <b>${stVal}</b></span>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      ${grid}</div>`;
    const g=id=>c.querySelector(id);
    g('#pt-search').onclick=()=>{F.from=g('#pt-from').value;F.to=g('#pt-to').value;F.part=g('#pt-part').value;F.item=g('#pt-item').value;F.worker=g('#pt-worker').value;F.gubun=g('#pt-gubun').value;load();};
    g('#pt-item').oninput=e=>acItem(e.target.value);
    ['#pt-item','#pt-worker'].forEach(id=>g(id).onkeyup=e=>{if(e.key==='Enter')g('#pt-search').click();});
    ['#pt-part','#pt-gubun'].forEach(id=>g(id).onchange=()=>g('#pt-search').click());
  };
  (async()=>{await loadFilters();load();})();
};

/* ===== 생산 ⑦: 생산파트재고조정 (w_pr_stock_470) — PR_T_STOCK_MAINT_MAT tag2 ===== */
/* ===== 생산 쓰기화면 공용 CRUD 패널 (nx 미러: 등록/수정/삭제) =====
   cfg: {listEp,saveEp,delEp,days,dateLabel,filters[],buildQS,cols[],form[],newRow,fromRow,toBody,sum} */

/* ===== 생산 ⑦: 생산파트재고조정 (w_pr_stock_470) — 라이브 조회 + nx.stock_maint 등록/수정/삭제 ===== */
SCREEN.partstockadj=(c)=>{
  wrShell(c,{sid:'partstockadj',
    title:`🛠️ 생산파트재고조정 <span style="font-size:12px;color:var(--muted);font-weight:400">자재개별재고조정(등록·수정·삭제)</span>`,
    sub:`파트재고 장부수정(조정, ±). 🔴 라이브=<code>PR_T_STOCK_MAINT_MAT</code> · ✏️ 신규편집=단일원장 <code>nx.stock_ledger</code>(PRD)`,
    default:'edit',
    live:(body)=>wrLiveLedger(body,'adj'),
    cfg:{
      listEp:'/api/stockmaint/list', saveEp:'/api/stockmaint/save', delEp:'/api/stockmaint/delete',
      dateLabel:'수정기간', filters:[{k:'tag',label:'구분',width:50},{k:'mat',label:'자재',width:120},{k:'wc',label:'작업처',width:60}],
      buildQS:F=>({from_ymd:F.from,to_ymd:F.to,tag:F.tag||'',mat:F.mat||'',wc:F.wc||''}),
      sum:d=>`조정수량합 <b>${_wnf(d.sum_qty)}</b>`,
      cols:[
        {h:'조정일자',cls:'center',fmt:r=>_wymd(r.MAINT_YMD)},
        {h:'구분',k:'tag_nm',cls:'center'},
        {h:'작업처',k:'work_code',cls:'center'},
        {h:'파트',k:'part_code',cls:'center'},
        {h:'자재',fmt:r=>`<b>${esc(r.mat_code)}</b>`},
        {h:'품명',k:'mat_nm',cap:1,title:'mat_nm'},
        {h:'도번',k:'item_code'},
        {h:'조정수량',cls:'num',fmt:r=>`<span style="color:${r.MAINT_QTY<0?'#c0392b':'#1c7c3a'}">${_wnf(r.MAINT_QTY)}</span>`},
        {h:'단가',cls:'num',fmt:r=>_wnf(r.MAINT_COST)},
        {h:'금액',cls:'num',fmt:r=>_wnf(r.MAINT_AMT)},
        {h:'비고',k:'remarks',cap:1,title:'remarks'},
        {h:'작업자',k:'usr'},
        {h:'작업일시',k:'INSERT_DATETIME',cls:'center'},
      ],
      form:[
        {k:'maint_ymd',label:'조정일자',type:'date',required:1,width:140},
        {k:'maint_tag',label:'구분',type:'select',opts:[{v:'2',t:'재고조정'},{v:'1',t:'불량'},{v:'4',t:'기타'}],width:100},
        {k:'work_code',label:'작업처',width:60},{k:'part_code',label:'파트',width:60},
        {k:'mat_code',label:'자재',required:1,search:1,width:160},{k:'item_code',label:'도번',search:1,width:140},
        {k:'maint_qty',label:'조정수량',type:'num',width:90},{k:'maint_cost',label:'단가',type:'num',width:90},
        {k:'prod_work_code',label:'생산작업장',width:70},{k:'remarks',label:'비고',width:200},
      ],
      newRow:F=>({id:null,maint_ymd:F.to,maint_tag:'2',work_code:'',part_code:'',mat_code:'',item_code:'',maint_qty:'',maint_cost:'',prod_work_code:'',remarks:''}),
      fromRow:r=>({id:r.ID,maint_ymd:_y6(r.MAINT_YMD),maint_tag:r.tag,work_code:r.work_code,part_code:r.part_code,mat_code:r.mat_code,item_code:r.item_code,maint_qty:r.MAINT_QTY,maint_cost:r.MAINT_COST,prod_work_code:r.prod_work_code,remarks:r.remarks}),
      toBody:f=>({id:f.id,maint_ymd:f.maint_ymd,maint_tag:f.maint_tag,work_code:f.work_code,part_code:f.part_code,mat_code:f.mat_code,item_code:f.item_code,maint_qty:f.maint_qty,maint_cost:f.maint_cost,prod_work_code:f.prod_work_code,remarks:f.remarks,user:'웹사용자'}),
    }
  });
};

/* ===== 생산 ⑧: 생산자재출고관리 (w_pr_stock_150) — PR_T_STOCK_MAINT_MAT 창고이동/출고 ===== */
SCREEN.partissue=(c)=>{
  wrShell(c,{sid:'partissue',
    title:`📤 생산자재출고관리 <span style="font-size:12px;color:var(--muted);font-weight:400">자재출고(창고간 이동, 등록·수정·삭제)</span>`,
    sub:`파트 창고간 이동(FROM파트→TO파트, net-0). 🔴 라이브=<code>PR_T_STOCK_MAINT_MAT</code> · ✏️ 신규편집=단일원장 <code>nx.stock_ledger</code>(MV)`,
    default:'edit',
    live:(body)=>wrLiveLedger(body,'issue'),
    cfg:{
      listEp:'/api/matissue/list', saveEp:'/api/matissue/save', delEp:'/api/matissue/delete',
      dateLabel:'출고기간', filters:[{k:'mat',label:'자재',width:120},{k:'frompart',label:'FROM파트',width:70},{k:'topart',label:'TO파트',width:70}],
      buildQS:F=>({from_ymd:F.from,to_ymd:F.to,mat:F.mat||'',frompart:F.frompart||'',topart:F.topart||''}),
      sum:d=>`출고수량합 <b>${_wnf(d.sum_qty)}</b>`,
      cols:[
        {h:'출고일자',cls:'center',fmt:r=>_wymd(r.ISSUE_YMD)},
        {h:'FROM파트',k:'frompart',cls:'center'},
        {h:'TO파트',k:'topart',cls:'center'},
        {h:'작업처',k:'work_code',cls:'center'},
        {h:'자재',fmt:r=>`<b>${esc(r.mat_code)}</b>`},
        {h:'품명',k:'mat_nm',cap:1,title:'mat_nm'},
        {h:'도번',k:'item_code'},
        {h:'출고수량',cls:'num',fmt:r=>`<b>${_wnf(r.ISSUE_QTY)}</b>`},
        {h:'비고',k:'remarks',cap:1,title:'remarks'},
        {h:'작업자',k:'usr'},
        {h:'작업일시',k:'INSERT_DATETIME',cls:'center'},
      ],
      form:[
        {k:'issue_ymd',label:'출고일자',type:'date',required:1,width:140},
        {k:'from_part_code',label:'FROM파트',width:70},{k:'part_code',label:'TO파트',width:70},{k:'work_code',label:'작업처',width:60},
        {k:'mat_code',label:'자재',required:1,search:1,width:160},{k:'item_code',label:'도번',search:1,width:140},
        {k:'issue_qty',label:'출고수량',type:'num',width:100},{k:'remarks',label:'비고',width:220},
      ],
      newRow:F=>({id:null,issue_ymd:F.to,from_part_code:'',part_code:'',work_code:'',mat_code:'',item_code:'',issue_qty:'',remarks:''}),
      fromRow:r=>({id:r.ID,issue_ymd:_y6(r.ISSUE_YMD),from_part_code:r.frompart,part_code:r.topart,work_code:r.work_code,mat_code:r.mat_code,item_code:r.item_code,issue_qty:r.ISSUE_QTY,remarks:r.remarks}),
      toBody:f=>({id:f.id,issue_ymd:f.issue_ymd,from_part_code:f.from_part_code,part_code:f.part_code,work_code:f.work_code,mat_code:f.mat_code,item_code:f.item_code,issue_qty:f.issue_qty,remarks:f.remarks,user:'웹사용자'}),
    }
  });
};

/* ===== 생산계획추가입력 CRUD (nx.prod_plan_input ← PR_T_PLAN_INPUT) — 수동 추가 생산계획 ===== */
SCREEN.planinput=(host)=>{
  const API=API_BASE;
  const iso=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const ymd6=d=>{ if(!d) return ''; const p=d.split('-'); return p[0].slice(2)+p[1]+p[2]; };  // yyyy-mm-dd → YYMMDD
  const shift=(d,n)=>{ const t=new Date(d+'T00:00:00'); t.setDate(t.getDate()+n); return iso(t); };
  const hmfmt=v=>{ const s=String(v||'').trim(); return /^\d{4}$/.test(s)?s.slice(0,2)+':'+s.slice(2):s; };  // HHMM→HH:MM
  // 엑셀 날짜 → YYMMDD(6). "2026-08-05","26/8/5","260805","20260805" 모두 흡수. 미인식시 원문 유지.
  const ymdNorm=v=>{ let s=String(v==null?'':v).replace(/[^\d]/g,''); if(s.length===8)s=s.slice(2); return /^\d{6}$/.test(s)?s:String(v==null?'':v).trim(); };
  const st={mx:{dates:[],rows:[],grandtot:{},total:0,cnt:0,note:''},q:'',line:'',base:iso(new Date()),
            prevDay:false,lines:[],form:null,bulk:null,sel:new Set(),msg:''};
  const F=[['plan_ymd','계획일자(YYMMDD)','req'],['line_no','라인','req'],['item_code','품번','req'],
    ['output_hm','산출시각(HHMM)','text'],['plan_qty','계획수량','num'],['work_order','제번','text'],
    ['work_code','공정(P1용접/P2가공)','text'],['prod_tag','생산구분(1양산/2셀)','text'],['remarks','비고','text']];
  // 라인 표기 = "코드 명칭"(레거시 dddw 형식). 명칭 없거나 코드=명칭이면 코드만.
  const lineLabel=l=>{ const c=String(l.code),n=String(l.nm||'').trim(); return (n&&n!==c)?`${c} ${n}`:c; };
  const lineNm=code=>{ const l=st.lines.find(x=>String(x.code)===String(code)); return l?lineLabel(l):(code||''); };
  // 라인 select 폭 = 표기 글자폭(UI규칙, 한글 폭 보정 1.7ch)
  const lineW=()=>{ const w=Math.max(6,...st.lines.map(l=>{const s=lineLabel(l);return [...s].reduce((a,ch)=>a+(ch.charCodeAt(0)>0x2000?1.7:1),0);})); return (w+3).toFixed(0)+'ch'; };
  const lineOpts=(sel,all)=>(all?`<option value=""${sel?'':' selected'}>전체</option>`:'')+
    st.lines.map(l=>`<option value="${esc(l.code)}"${String(sel)===String(l.code)?' selected':''}>${esc(lineLabel(l))}</option>`).join('');
  const loadLines=async()=>{ try{const r=await fetch(`${API}/api/planinput/lines`);const j=await r.json();st.lines=j.rows||[];}catch(e){st.lines=[];} };
  const load=async()=>{
    // 전일기준(prevDay): 시작일=OFF 기준일 / ON 전일(기준일−1). 기준일부터 forward 4주 매트릭스.
    const qs=new URLSearchParams({base:ymd6(st.base),prevday:st.prevDay?1:0,days:28,q:st.q,line:st.line});
    try{const r=await fetch(`${API}/api/planinput/matrix?${qs}`);const j=await r.json();
      st.mx=(j&&j.dates)?j:{dates:[],rows:[],grandtot:{},total:0,cnt:0,note:''};st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.mx={dates:[],rows:[],grandtot:{},total:0,cnt:0,note:''};}
    st.sel.clear();render();
  };
  // ── 수정 모달(기존 레코드 단건) ──
  const editHtml=(f)=>`<div class="wr-modal" style="position:fixed;inset:0;z-index:110;background:rgba(20,30,50,.38);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:24px 10px">
     <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.32);width:520px;max-width:96vw">
       <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c47a0;color:#fff;border-radius:10px 10px 0 0">
         <b>생산계획 수정</b><span id="pi-x" style="cursor:pointer;font-size:17px">✕</span></div>
       <div style="padding:12px 16px;max-height:calc(100vh - 170px);overflow:auto">
         <table style="border-collapse:collapse;width:100%"><tbody>${F.map(fd=>`<tr>
           <td style="padding:5px 8px 5px 0;white-space:nowrap;color:#33507d;font-weight:600;font-size:12px;text-align:right;width:120px">${fd[1]}${fd[2]==='req'?'<span style="color:#c0392b">*</span>':''}</td>
           <td style="padding:4px 0">${fd[0]==='line_no'
              ?`<select class="inp pf" data-k="line_no" style="width:${lineW()}">${lineOpts(f.line_no,false)}</select>`
              :`<input class="inp pf" data-k="${fd[0]}" value="${esc(f[fd[0]]||'')}" ${fd[2]==='num'?'type="number"':''} style="width:${fd[2]==='num'?100:200}px" autocomplete="off">`}</td></tr>`).join('')}</tbody></table>
       </div>
       <div style="padding:11px 16px;border-top:1px solid #e2e8f2;display:flex;justify-content:space-between;align-items:center">
         <span style="color:#c0392b;font-size:11px">* 계획일자(YYMMDD)·라인·품번·수량 필수. 시각은 HHMM.</span>
         <span><button class="btn" id="pi-save" style="background:#1b6ec2;color:#fff">💾 저장</button> <button class="btn" id="pi-cancel">닫기</button></span></div>
     </div></div>`;
  const render=()=>{
    const editing=st.form!==null, f=st.form||{}, bulking=st.bulk!==null;
    const ed=(typeof PERM!=='undefined')?PERM.canEdit('planinput'):true;
    const D=st.mx.dates||[], R=st.mx.rows||[], G=st.mx.grandtot||{};
    const wke=wd=>wd===5?'color:#1b6ec2':(wd===6?'color:#c0392b':'');  // 토 파랑 / 일 빨강
    const dhead=D.map(d=>`<th class="num" style="min-width:36px;${wke(d.wd)}" title="${esc(d.ymd)}">${esc(d.mmdd)}<br><span style="font-size:9px">${esc(d.dow)}</span></th>`).join('');
    host.innerHTML=`
     <div class="page-title">➕ 생산계획추가입력 <span style="font-size:12px;color:var(--muted);font-weight:400">일자별 계획 매트릭스 · nx.prod_plan_input(레거시 PR_T_PLAN_INPUT 이관본)</span></div>
     <div class="page-sub">레거시 <code>w_pr_plan_060 / dw_pr_plan_060_1</code> 재현. 좌측 고정컬럼 + <b>기준일 기준 최근 4주</b> 일자매트릭스(기준일=우측 끝 컬럼, 셀=계획수량, 하단 일자합계). 추가는 <b>엑셀 붙여넣기</b>. <span style="color:#c0392b">대체·출하수량은 원천 미보유(공란)</span>.</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <label class="tl">기준일자</label>
       <button class="btn" id="pi-prevd" title="전일" style="padding:1px 8px">◀</button>
       <input class="inp" type="date" id="pi-base" value="${st.base}">
       <button class="btn" id="pi-nextd" title="익일" style="padding:1px 8px">▶</button>
       <label class="tl" style="margin-left:6px"><input type="checkbox" id="pi-prev" ${st.prevDay?'checked':''}> 전일기준</label>
       <label class="tl">라인</label><select class="inp" id="pi-line" style="width:${lineW()}">${lineOpts(st.line,true)}</select>
       <label class="tl">검색</label><input class="inp" id="pi-q" value="${esc(st.q)}" placeholder="품번/제번" style="width:140px" autocomplete="off">
       <button class="btn" id="pi-search">🔍 조회</button>
       ${ed?`<button class="btn" id="pi-add" style="background:#1c7c3a;color:#fff">➕ 추가(엑셀붙여넣기)</button>
       <button class="btn" id="pi-del">🗑 선택삭제</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span>`}
       <div class="spacer"></div><span class="rowcount">${won(st.mx.cnt||0)}행 · 합계 ${won(st.mx.total||0)}</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')||st.msg.includes('오류')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     ${editing?editHtml(f):''}
     ${bulking?bulkHtml():''}
     <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr>
        <th style="width:24px"></th>
        <th>WORK-ORDER</th><th>작업처</th><th>양산/셀</th><th>라인</th><th>품번</th><th>품명</th><th>품목구분</th>
        <th class="num">생산수량</th><th class="num" title="원천 미보유(가정 공란)">대체수량</th><th class="num" title="원천 미보유(가정 공란)">출하수량</th><th class="num">시간</th>
        ${dhead}</tr></thead>
      <tbody>${R.length?R.map((r,i)=>{
        const cells=D.map(d=>{const c=r.cells[d.ymd];const q=c?c.qty:0;
          return `<td class="num" style="${wke(d.wd)}${q>0?';cursor:pointer;background:#eef5ff':''}" ${(q>0&&ed)?`data-edit="${c.recs[0].ppi_id}" title="클릭:수정"`:''}>${q>0?won(q):''}</td>`;}).join('');
        return `<tr>
        <td class="center">${ed?`<input type="checkbox" class="pi-chk" data-idx="${i}" ${st.sel.has(i)?'checked':''}>`:''}</td>
        <td>${esc(r.work_order)}</td><td>${esc(r.work_nm)}</td><td class="center">${esc(r.prod_nm)}</td>
        <td class="center" title="${esc(lineNm(r.line_no))}">${esc(lineNm(r.line_no))}</td><td><b>${esc(r.item_code)}</b></td>
        <td class="cap" title="${esc(r.nm)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td>
        <td>${esc(r.item_type)}</td>
        <td class="num"><b>${won(r.total||0)}</b></td><td class="num" style="color:#b8c2cf"></td><td class="num" style="color:#b8c2cf"></td>
        <td class="num">${esc(hmfmt(r.output_hm))}</td>
        ${cells}</tr>`;}).join(''):`<tr><td colspan="${12+D.length}" class="empty">조회 결과 없음${ed?' (➕추가로 등록)':''}</td></tr>`}</tbody>
      ${R.length?`<tfoot><tr style="position:sticky;bottom:0;background:#f0f4fa;font-weight:700">
        <td></td><td colspan="7" style="text-align:right">일자별 합계 ▶</td>
        <td class="num">${won(st.mx.total||0)}</td><td></td><td></td><td></td>
        ${D.map(d=>`<td class="num" style="${wke(d.wd)}">${G[d.ymd]?won(G[d.ymd]):''}</td>`).join('')}</tr></tfoot>`:''}
      </table></div>`;
    const g=id=>host.querySelector(id);
    g('#pi-prevd').onclick=()=>{st.base=shift(st.base,-1);load();};
    g('#pi-nextd').onclick=()=>{st.base=shift(st.base,1);load();};
    g('#pi-base').onchange=()=>{st.base=g('#pi-base').value||st.base;load();};
    g('#pi-prev').onchange=()=>{st.prevDay=g('#pi-prev').checked;load();};
    g('#pi-search').onclick=()=>{st.q=g('#pi-q').value;st.line=g('#pi-line').value;load();};
    g('#pi-line').onchange=()=>{st.line=g('#pi-line').value;load();};
    g('#pi-q').onkeyup=e=>{if(e.key==='Enter')g('#pi-search').click();};
    if(ed){
      g('#pi-add').onclick=async()=>{ if(!st.lines.length)await loadLines();   // 라인 드롭다운 보장(로드 실패/레이스 방어)
        st.bulk={plan_ymd:ymd6(st.base),line_no:st.line||(st.lines[0]&&st.lines[0].code)||'',output_hm:'2100',prod_tag:'1',work_code:'',rows:blankRows(10)};render();};
      g('#pi-del').onclick=()=>del();
      host.querySelectorAll('.pi-chk').forEach(ch=>ch.onclick=()=>{const i=+ch.dataset.idx;ch.checked?st.sel.add(i):st.sel.delete(i);});
      host.querySelectorAll('[data-edit]').forEach(td=>td.onclick=()=>editCell(+td.dataset.edit));
    }
    attachResizers(host);
    if(editing){
      g('#pi-cancel').onclick=g('#pi-x').onclick=()=>{st.form=null;render();};
      g('#pi-save').onclick=save;
      host.querySelectorAll('.pf').forEach(el=>{const h=()=>{st.form[el.dataset.k]=el.value;};el.oninput=h;el.onchange=h;});
    }
    if(bulking) wireBulk();
  };
  // ── 셀 클릭 수정(단건 레코드 프리필) ──
  const editCell=async(ppi_id)=>{
    try{const r=await fetch(`${API}/api/planinput/get?ppi_id=${ppi_id}`);const j=await r.json();
      if(j&&j.ppi_id){st.form=j;render();}else alert('행 조회 실패');}
    catch(e){alert('행 조회 오류: '+e);}
  };
  // ── 엑셀 붙여넣기 일괄추가 ──
  const blankRows=n=>Array.from({length:n},()=>({plan_ymd:'',item_code:'',plan_qty:'',work_order:'',remarks:''}));
  const bulkHtml=()=>{ const b=st.bulk;
    return `<div class="wr-modal" style="position:fixed;inset:0;z-index:120;background:rgba(20,30,50,.42);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:18px 10px">
     <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.34);width:1060px;max-width:94vw">
       <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c7c3a;color:#fff;border-radius:10px 10px 0 0">
         <b>➕ 생산계획 추가 — 엑셀 붙여넣기(날짜·품번·수량)</b><span id="pb-x" style="cursor:pointer;font-size:17px">✕</span></div>
       <div style="padding:12px 16px">
         <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:8px;font-size:12px">
           <label class="tl">기본 계획일자</label><input class="inp" id="pb-ymd" value="${esc(b.plan_ymd)}" placeholder="YYMMDD" style="width:8ch" autocomplete="off" title="행별 계획일자가 비면 이 값으로 채웁니다">
           <label class="tl">라인</label><select class="inp" id="pb-line" style="width:${lineW()}">${lineOpts(b.line_no,false)}</select>
           <label class="tl">산출시각</label><input class="inp" id="pb-hm" value="${esc(b.output_hm)}" placeholder="HHMM" style="width:5ch;min-width:0;flex:none" autocomplete="off">
           <label class="tl">생산구분</label><select class="inp" id="pb-tag" style="width:auto;min-width:0;flex:none" title="1양산/2셀"><option value="1" ${b.prod_tag==='1'?'selected':''}>1 양산</option><option value="2" ${b.prod_tag==='2'?'selected':''}>2 셀</option></select>
           <label class="tl">공정</label><input class="inp" id="pb-wc" value="${esc(b.work_code)}" placeholder="P1/P2" style="width:6ch;min-width:0;flex:none" autocomplete="off">
         </div>
         <div style="font-size:11px;color:#1c7c3a;margin-bottom:6px">💡 엑셀에서 <b>계획일자⇥품번⇥수량</b> (또는 품번만/품번⇥수량) 열을 복사해 아래 해당 칸에 <b>붙여넣기</b>하면 여러 행에 자동 분배됩니다. 계획일자 비면 상단 <b>기본 계획일자</b>로 채워집니다.</div>
         <div style="max-height:calc(100vh - 330px);overflow-y:auto;overflow-x:hidden;border:1px solid #d7dfea;border-radius:6px">
           <table class="tbl" style="font-size:11px;width:100%;table-layout:fixed"><thead><tr>
             <th style="width:30px">#</th><th style="width:82px">계획일자 <span style="color:#1c7c3a">(붙여넣기)</span></th><th>품번 <span style="color:#1c7c3a">(붙여넣기)</span></th><th class="num" style="width:84px">계획수량</th><th style="width:120px">제번</th><th>비고</th><th style="width:30px"></th></tr></thead>
           <tbody>${b.rows.map((r,i)=>`<tr>
             <td class="center" style="color:#8aa0bd">${i+1}</td>
             <td><input class="inp pb-ymd" data-i="${i}" value="${esc(r.plan_ymd)}" placeholder="YYMMDD" style="width:8ch" autocomplete="off"></td>
             <td><input class="inp pb-item" data-i="${i}" value="${esc(r.item_code)}" style="width:96%" autocomplete="off"></td>
             <td><input class="inp pb-qty" data-i="${i}" value="${esc(r.plan_qty)}" type="number" style="width:74px" autocomplete="off"></td>
             <td><input class="inp pb-wo" data-i="${i}" value="${esc(r.work_order)}" style="width:96%" autocomplete="off"></td>
             <td><input class="inp pb-rm" data-i="${i}" value="${esc(r.remarks)}" style="width:96%" autocomplete="off"></td>
             <td class="center"><span class="pb-rmrow" data-i="${i}" style="cursor:pointer;color:#c0392b" title="행삭제">✕</span></td></tr>`).join('')}</tbody></table>
         </div>
         <div style="margin-top:6px"><button class="btn" id="pb-addrow">＋ 행추가(5)</button>
           <span style="color:#8aa0bd;font-size:11px;margin-left:8px">품번·수량(>0)·계획일자 있는 행만 저장됩니다.</span></div>
       </div>
       <div style="padding:11px 16px;border-top:1px solid #e2e8f2;display:flex;justify-content:space-between;align-items:center">
         <span style="color:#c0392b;font-size:11px">* 라인·시각 공통 적용. 각 행 품번·수량 필수. 계획일자=행별 우선(비면 기본일자).</span>
         <span><button class="btn" id="pb-save" style="background:#1c7c3a;color:#fff">💾 일괄저장</button> <button class="btn" id="pb-cancel">닫기</button></span></div>
     </div></div>`;
  };
  // 다열 붙여넣기 자동분배: start행부터 fields 순서대로 셀 매핑(부족 행은 추가). 날짜=정규화·수량=숫자만.
  const applyPaste=(b,start,txt,fields)=>{
    const lines=txt.replace(/\r/g,'').split('\n');
    while(lines.length&&lines[lines.length-1]==='')lines.pop();  // 꼬리 빈줄 제거
    lines.forEach((ln,k)=>{
      const cells=ln.split('\t'), ri=start+k;
      while(b.rows.length<=ri)b.rows.push({plan_ymd:'',item_code:'',plan_qty:'',work_order:'',remarks:''});
      fields.forEach((f,ci)=>{
        if(ci>=cells.length)return;
        let v=(cells[ci]||'').trim(); if(v==='')return;
        if(f==='plan_ymd')v=ymdNorm(v); else if(f==='plan_qty')v=v.replace(/[^\d.\-]/g,'').trim();
        b.rows[ri][f]=v;
      });
    });
  };
  const wireBulk=()=>{ const g=id=>host.querySelector(id), b=st.bulk;
    g('#pb-x').onclick=g('#pb-cancel').onclick=()=>{st.bulk=null;render();};
    g('#pb-save').onclick=bulkSave;
    g('#pb-ymd').oninput=e=>b.plan_ymd=e.target.value;
    g('#pb-line').onchange=e=>b.line_no=e.target.value;
    g('#pb-hm').oninput=e=>b.output_hm=e.target.value;
    g('#pb-tag').oninput=e=>b.prod_tag=e.target.value;
    g('#pb-wc').oninput=e=>b.work_code=e.target.value;
    g('#pb-addrow').onclick=()=>{b.rows=b.rows.concat(blankRows(5));render();};
    // 계획일자 열: 단일=날짜, 다열=날짜⇥품번⇥수량⇥제번⇥비고
    host.querySelectorAll('.pb-ymd').forEach(el=>{
      el.oninput=e=>{b.rows[+e.target.dataset.i].plan_ymd=e.target.value;};
      el.onblur=e=>{const i=+e.target.dataset.i;b.rows[i].plan_ymd=ymdNorm(b.rows[i].plan_ymd);e.target.value=b.rows[i].plan_ymd;};
      el.onpaste=e=>{
        const txt=(e.clipboardData||window.clipboardData).getData('text');
        if(!/[\n\t]/.test(txt)){const i=+e.target.dataset.i;e.preventDefault();b.rows[i].plan_ymd=ymdNorm(txt);render();return;}
        e.preventDefault();
        applyPaste(b,+e.target.dataset.i,txt,['plan_ymd','item_code','plan_qty','work_order','remarks']);render();
      };
    });
    // 품번 열: 단일=품번, 다열=품번⇥수량⇥제번
    host.querySelectorAll('.pb-item').forEach(el=>{
      el.oninput=e=>{b.rows[+e.target.dataset.i].item_code=e.target.value;};
      el.onpaste=e=>{
        const txt=(e.clipboardData||window.clipboardData).getData('text');
        if(!/[\n\t]/.test(txt))return;               // 단일값이면 기본 붙여넣기
        e.preventDefault();
        applyPaste(b,+e.target.dataset.i,txt,['item_code','plan_qty','work_order']);render();
      };
    });
    host.querySelectorAll('.pb-qty').forEach(el=>el.oninput=e=>{b.rows[+e.target.dataset.i].plan_qty=e.target.value;});
    host.querySelectorAll('.pb-wo').forEach(el=>el.oninput=e=>{b.rows[+e.target.dataset.i].work_order=e.target.value;});
    host.querySelectorAll('.pb-rm').forEach(el=>el.oninput=e=>{b.rows[+e.target.dataset.i].remarks=e.target.value;});
    host.querySelectorAll('.pb-rmrow').forEach(el=>el.onclick=()=>{b.rows.splice(+el.dataset.i,1);if(!b.rows.length)b.rows=blankRows(3);render();});
  };
  const bulkSave=async()=>{ const b=st.bulk;
    if(!String(b.line_no||'').trim()){alert('라인을 선택하세요');return;}
    const hm=String(b.output_hm||'').trim(); if(hm&&!/^\d{4}$/.test(hm)){alert('산출시각은 HHMM(4자리)');return;}
    const base6=/^\d{6}$/.test(String(b.plan_ymd||'').trim())?String(b.plan_ymd).trim():'';   // 기본일자(선택)
    const eff=r=>{const d=ymdNorm(r.plan_ymd);return /^\d{6}$/.test(d)?d:base6;};                // 행별 우선, 없으면 기본
    const withItem=b.rows.filter(r=>String(r.item_code||'').trim()&&Number(r.plan_qty)>0);
    const valid=withItem.filter(r=>/^\d{6}$/.test(eff(r)));
    if(!valid.length){alert(withItem.length?'계획일자가 없습니다(행별 또는 기본 계획일자 입력)':'품번·수량(>0)이 있는 행이 없습니다');return;}
    const noDate=withItem.length-valid.length;
    if(noDate&&!confirm(`계획일자 없는 ${noDate}행은 제외됩니다. ${valid.length}행을 등록할까요? (라인 ${b.line_no})`))return;
    if(!noDate&&!confirm(`${valid.length}개 행을 일괄 등록할까요? (라인 ${b.line_no}${base6?` · 기본일자 ${base6}`:''})`))return;
    try{const r=await fetch(`${API}/api/planinput/bulk`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({plan_ymd:b.plan_ymd,line_no:b.line_no,output_hm:b.output_hm,prod_tag:b.prod_tag,work_code:b.work_code,rows:b.rows})});
      const j=await r.json();
      if(r.ok&&j.ok){st.msg=`✅ ${j.inserted}건 일괄등록${j.skipped?` (제외 ${j.skipped})`:''}`;st.bulk=null;
        const mx=valid.map(eff).sort().pop()||base6;   // 최신 등록일자를 기준일(우측 끝)로 → backward 창에 노출
        if(/^\d{6}$/.test(mx))st.base=`20${mx.slice(0,2)}-${mx.slice(2,4)}-${mx.slice(4,6)}`;
        st.line=b.line_no;await load();}
      else alert('일괄저장 실패: '+(j.detail||JSON.stringify(j)));}
    catch(e){alert('일괄저장 오류: '+e);}
  };
  const save=async()=>{
    const f=st.form;
    if(!/^\d{6}$/.test(String(f.plan_ymd||'').trim())){alert('계획일자는 YYMMDD(6자리 숫자)여야 합니다');return;}
    if(!String(f.line_no||'').trim()||!String(f.item_code||'').trim()){alert('라인·품번은 필수입니다');return;}
    if(!(Number(f.plan_qty)>0)){alert('계획수량은 0보다 커야 합니다');return;}
    const hm=String(f.output_hm||'').trim();
    if(hm&&!/^\d{4}$/.test(hm)){alert('산출시각은 HHMM(4자리)여야 합니다');return;}
    try{const r=await fetch(`${API}/api/planinput/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(f)});
      const j=await r.json();
      if(r.ok&&j.ok){st.msg=(j.mode==='insert'?'✅ 등록완료':'✅ 수정완료');st.form=null;await load();}
      else alert('저장 실패: '+(j.detail||JSON.stringify(j)));}
    catch(e){alert('저장 오류: '+e);}
  };
  const del=async()=>{
    const ids=[];st.sel.forEach(i=>{const row=st.mx.rows[i];if(row&&row.ppids)ids.push(...row.ppids);});
    if(!ids.length){alert('삭제할 행을 체크하세요');return;}
    if(!confirm(`선택 ${st.sel.size}행(${ids.length}건)을 삭제하시겠습니까?`))return;
    try{const r=await fetch(`${API}/api/planinput/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids})});
      const j=await r.json();st.msg='🗑 '+j.deleted+'건 삭제완료';st.sel.clear();await load();}
    catch(e){alert('삭제 오류: '+e);}
  };
  // 초기: 라인목록 로드 후 기준일 조회
  (async()=>{ await loadLines(); await load(); })();
};

/* ===== 준비실적처리(키팅) — 460_new 레이아웃. 라이브 자재소요+회수율+fin색상. 확인=nx flag-only(자재무차감) ===== */
SCREEN.kitting=(host)=>{
  // 준비실적처리(키팅) — 레거시 w_pr_input_460_new(≈dw_pr_input_410_t1_new2) 전 컬럼·2행·필터·버튼 재현. 라이브 PARTNER_ERP(RO).
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const f2=n=>Number(n||0).toLocaleString('ko-KR',{minimumFractionDigits:2,maximumFractionDigits:2});
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:(s||'');
  const iso=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const y2iso=y=>y&&y.length===6?`20${y.slice(0,2)}-${y.slice(2,4)}-${y.slice(4,6)}`:'';
  const wlab=y=>{if(!y||y.length<6)return dcol(y);const dt=new Date(2000+ +y.slice(0,2),+y.slice(2,4)-1,+y.slice(4,6));const dow='일월화수목금토'[dt.getDay()];return `${y.slice(4,6)}${dow}`;};   // 레거시 라벨: 일자+요일 (예 19월)
  const isWkend=y=>{if(!y||y.length<6)return false;const dt=new Date(2000+ +y.slice(0,2),+y.slice(2,4)-1,+y.slice(4,6));return dt.getDay()===0||dt.getDay()===6;};
  const T=new Date();
  const st={dates:[],rows:[],cnt:0,plan_sum:0,ready_sum:0,note:'',base:iso(T),gigan:2,wc:'',wh:'',part:'',pgroup:'',line:'',dono:'',jado:'',unfin:'전체',view:'전체',sel:new Set(),loading:false,msg:''};
  const load=async()=>{st.loading=true;render();
    const qs=new URLSearchParams({from_ymd:st.base,gigan:st.gigan,wc:st.wc,part:st.part,pgroup:st.pgroup,line:st.line,assy:st.dono,jado:st.jado,view:st.view,unfin:st.unfin,limit:6000});
    try{const r=await fetch(`${API}/api/kitting/grid?${qs}`);const j=await r.json();st.dates=j.dates||[];st.rows=j.rows||[];st.cnt=j.cnt||0;st.plan_sum=j.plan_sum||0;st.ready_sum=j.ready_sum||0;st.note=j.note||'';st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.rows=[];st.dates=[];}
    st.loading=false;st.sel.clear();render();};
  const shiftDay=n=>{const d=new Date(st.base);d.setDate(d.getDate()+n);st.base=iso(d);load();};
  const act=async(mode)=>{
    const rows=st.rows.filter((r,i)=>st.sel.has(i)).map(r=>({item_code:r.item,work_order:r.wo,gpc:r.gpc,plan_ymd:r.part_ymd,work_center:r.wc,qty:(mode==='cancel'?r.ready_qty:r.need_qty)})).filter(r=>r.qty>0);
    if(!rows.length){alert(mode==='cancel'?'취소할(준비수량>0) 행 선택':'준비필요(>0) 행 선택');return;}
    const knm=mode==='cancel'?'준비취소':'확인(준비등록)';
    if(!confirm(`${rows.length}건 ${knm}?\n(자재 무차감 · 준비재고+READY 마킹, 자재차감은 생산실적)`))return;
    try{const r=await fetch(`${API}/api/ready/register`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode,rows,user:(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹')})});
      const j=await r.json();if(j.ok){st.msg=`✅ ${knm} ${j.count}건 완료${j.skipped?` (제외 ${j.skipped})`:''}`;await load();}else alert(knm+' 실패');}
    catch(e){alert(knm+' 오류: '+e);}};
  // ★셀단위 확인/취소(우클릭) — flag-only(자재무차감). 확인=그 셀 잔량 준비등록, 취소=되돌림.
  const cellAct=async(mode,m)=>{
    const body={item:m.item,wo:m.wo,swo:m.swo,gpc:m.gpc,ymd:m.ymd,qty:+m.qty,assy:m.assy,user:(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹')};
    const url=mode==='confirm'?'/api/kitting/cell-confirm':'/api/kitting/cell-cancel';
    try{const r=await fetch(`${API}${url}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const j=await r.json();
      if(j.ok){st.msg=`✅ ${mode==='confirm'?'준비확인':'준비취소'} ${nf(j.qty||0)} (${esc(m.item)} · ${dcol(m.ymd)})`;await load();}
      else alert((mode==='confirm'?'확인':'취소')+' 불가: '+(j.detail||''));}
    catch(e){alert('셀 '+(mode==='confirm'?'확인':'취소')+' 오류: '+e);}};
  // fin 우선순위 6(출하완료,주황)>4(생산완료,노랑)>3(키팅완료,녹)>0(미키팅,백). ★레거시 c_color_new 정본색 이식.
  const finBg=f=>f==='6'?'#fac090':(f==='4'?'#ffff00':(f==='3'?'#669900':''));   // 주황=출하 / 노랑=생산 / 녹=키팅(gl_color_prod_ready)
  const finFg=f=>f==='3'?'#ffffff':'';   // 진한 녹 배경엔 흰 글자(가독)
  const NCOL=20;   // 고정컬럼수(체크 제외 헤더 수: SEQ..ASSY도번 = 20, +당일이전 포함) — colspan 계산용
  const render=()=>{
    const ed=(typeof PERM!=='undefined')?PERM.canEdit('kitting'):true;
    const d=st.dates;
    // ★파트·자도번작업처 드롭다운 = 고정 전체목록 항상 렌더(필터결과 rows에서 뽑지 않음 → 선택해도 목록 안 줄어듦).
    const wcM=new Map([['P1','용접'],['P2','가공']]);   // 자도번작업처 고정(PR_M_WORK)
    // 파트 고정 code↔name(PR_M_PROC_GAGONG 실측), 대표 지정순서. '-'=구분선. rows 무관.
    const PART_FIX=[['S5','01라인(용접)'],['S5-2','01라인(조립)'],['S1','02라인'],['S6','03라인'],['S4','04라인'],['S11','05라인'],['RAC','06라인'],['S10','자동은납 10'],['S13','서브/고주파'],['S12','설치'],['S8','서포터 08'],['S9','용접 09'],['S7','다관절 로봇 용접'],['-','-'],['Q1000','용접봉창고']];
    const partOpts='<option value=""'+(st.part?'':' selected')+'>전체</option>'+PART_FIX.map(([v,n])=>v==='-'?'<option disabled>─────────</option>':`<option value="${esc(v)}"${st.part===v?' selected':''}>${esc(n)}</option>`).join('');
    const seg=(name,val,opts)=>opts.map(v=>`<label style="font-weight:400;margin:0 5px 0 1px"><input type="radio" name="${name}" value="${v}" ${val===v?'checked':''}> ${v}</label>`).join('');
    // ── 본행/하위행 평탄화 (view: 전체=본행+제번 / 집계=본행 / 제번=제번행) ──
    const flat=[];let seq=0;
    st.rows.forEach((r,i)=>{
      if(st.view!=='제번'){seq++;flat.push({t:'m',r,i,seq});}
      if(st.view!=='집계'){(r.splits||[]).forEach(sp=>flat.push({t:'s',r,sp,i}));}
    });
    const numTd=(v,bg,strong,fg)=>`<td class="num"${bg?` style="background:${bg}${strong?';font-weight:700':''}${fg?';color:'+fg:''}"`:''}>${v}</td>`;
    // 우클릭 확인/취소 대상 셀(당일이전·일자) — data-*에 셀키(item·wo·gpc·ymd·잔량·assy·fin) 실어 컨텍스트메뉴에서 사용
    const ktCell=(v,bg,strong,fg,m)=>`<td class="num kt-cell" title="우클릭: 확인/취소" data-item="${esc(m.item)}" data-wo="${esc(m.wo)}" data-swo="${esc(m.swo)}" data-gpc="${esc(m.gpc)}" data-ymd="${esc(m.ymd)}" data-qty="${m.qty}" data-assy="${esc(m.assy)}" data-fin="${esc(m.fin)}"${(bg||fg)?` style="${bg?`background:${bg}${strong?';font-weight:700':''}`:''}${fg?';color:'+fg:''};cursor:context-menu"`:' style="cursor:context-menu"'}>${v}</td>`;
    const mainRow=(o)=>{const r=o.r,i=o.i;   // 셀별 색(당일이전=prior_fin, 일자=dfin), 전체행 배경 없음(레거시=셀별)
      const pfin=r.prior_fin||'0';
      const pcell=r.prior_plan>0?`${nf(r.prior_cover||0)}/${nf(r.prior_plan)}`:'·';
      return `<tr class="kt-main">
        <td class="center"><input type="checkbox" class="kt-chk" data-i="${i}" ${st.sel.has(i)?'checked':''}></td>
        <td class="center">${o.seq}</td><td>${esc(r.gpcnm||r.gpc)}</td><td><b>${esc(r.item)}</b></td>
        <td class="center">${esc(dcol(r.part_ymd||''))}</td><td class="center">${esc(r.inhm)}</td><td class="center">${esc(r.line)}</td>
        ${r.prior_plan>0?ktCell(pcell,finBg(pfin)||'#eef4fb',pfin!=='0',finFg(pfin),{item:r.item,wo:r.wo,swo:r.swo,gpc:r.gpc,ymd:r.part_ymd,qty:Math.max((r.prior_plan||0)-(r.prior_cover||0),0),assy:r.assy,fin:pfin}):numTd('·','',false)}
        ${d.map(x=>{const pl=(r.days&&r.days[x])||0,cv=(r.dcov&&r.dcov[x])||0,cf=(r.dfin&&r.dfin[x])||'0';return pl?ktCell(`${nf(cv)}/${nf(pl)}`,finBg(cf)||'#eef4fb',cf!=='0',finFg(cf),{item:r.item,wo:r.wo,swo:r.swo,gpc:r.gpc,ymd:x,qty:Math.max(pl-cv,0),assy:r.assy,fin:cf}):numTd('·','',false);}).join('')}
        ${numTd(nf(r.ready_stock))}${numTd(nf(r.finish))}<td class="num" style="color:#1c7c3a"><b>${nf(r.ready_qty)}</b></td>
        ${numTd(nf(r.prod_stock))}${numTd(nf(r.assy_stock))}${numTd(nf(r.sale))}${numTd(nf(r.use_qty))}
        <td>${esc(r.wo)}</td><td>${esc(r.swo)}</td><td class="num">${f2(r.rate)}</td><td class="num">${f2(r.item_st)}</td><td>${esc(r.assy)}</td></tr>`;};
    const subRow=(o)=>{const sp=o.sp,r=o.r;   // 하위행: 하늘색, 제번=파트(GAGONG_PROC_CODE) split (레거시 S11/S4/S5 코드유지)
      return `<tr class="kt-sub" style="background:#e3f0fb">
        <td class="center"></td><td class="center" style="color:#7a93b0">↳</td><td style="color:#456">${esc(sp.gpcnm||sp.gpc)}</td>
        <td style="color:#345"><span style="color:#2b6cb0">${esc(sp.gpc)}</span></td>
        <td class="center"></td><td class="center"></td><td class="center">${esc(r.line)}</td>
        ${numTd(sp.prior_plan>0?nf(sp.prior_plan):'·','',false)}
        ${d.map(x=>{const pl=(sp.days&&sp.days[x])||0;return numTd(pl?nf(pl):'·',pl?'#eef4fb':'',false);}).join('')}
        ${numTd('')}${numTd('')}${numTd('')}${numTd('')}${numTd('')}${numTd('')}${numTd('')}
        <td>${esc(r.wo)}</td><td>${esc(r.swo)}</td><td></td><td></td><td></td></tr>`;};
    host.innerHTML=`
     <div class="page-title">🧰 준비실적처리(키팅) <span style="font-size:12px;color:var(--muted);font-weight:400">w_pr_input_460_new · 라이브 PR_T_PLAN_PART_DTL(읽기전용)</span></div>
     <div class="page-sub">본행=도번×제번(Work Order) · <span style="background:#e3f0fb;padding:0 5px">하늘색 하위행=파트(GAGONG_PROC 예 S11/S4) split</span>. 셀=재고충당/계획. 당일이전=지평이전 백로그(단일누적). 회수율=PR_M_PROC_GAGONG.
       <span style="background:#669900;color:#fff;padding:0 5px">녹=키팅완료(준비충당)</span> <span style="background:#ffff00;padding:0 5px">노랑=생산완료(ASSY재고)</span> <span style="background:#fac090;padding:0 5px">주황=출하완료</span> 백=미키팅</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <button class="btn ghost" id="kt-bom">🖨 BOM출력</button>
       <button class="btn ghost" id="kt-move">🚚 생산이동표 강제발행</button>
       <button class="btn ghost" id="kt-short">⚠ 생산창고 재고과부족 확인</button>
       <div class="spacer" style="flex:0 0 8px"></div>
       <label class="tl">기준일자</label><button class="btn ghost" id="kt-prev" title="전일" style="padding:2px 6px">◀</button>
       <input class="inp" type="date" id="kt-base" value="${st.base}" style="width:138px">
       <button class="btn ghost" id="kt-next" title="익일" style="padding:2px 6px">▶</button>
       <label class="tl">기간</label><select class="inp" id="kt-gigan" style="width:62px">${[1,2,3,4,5,6,7,8].map(n=>`<option value="${n}"${st.gigan===n?' selected':''}>${n}일</option>`).join('')}</select>
       <label class="tl">자도번작업처</label><select class="inp" id="kt-wc" style="width:88px"><option value="">전체</option>${[...wcM].map(([v,n])=>`<option value="${esc(v)}"${st.wc===v?' selected':''}>${esc(n)}</option>`).join('')}</select>
       <label class="tl">파트</label><select class="inp" id="kt-part" style="width:130px">${partOpts}</select>
       <label class="tl">도번</label><input class="inp" id="kt-dono" value="${esc(st.dono)}" style="width:100px" placeholder="ASSY도번" autocomplete="off">
       <label class="tl">자도번</label><input class="inp" id="kt-jado" value="${esc(st.jado)}" style="width:100px" placeholder="도번(item)" autocomplete="off">
       <label class="tl">미생산</label>${seg('kt-uf',st.unfin,['전체','미생산','미키팅'])}
       <label class="tl">구분</label>${seg('kt-vw',st.view,['전체','집계','제번'])}
       <button class="btn" id="kt-go">🔍 조회</button>
       ${ed?`<button class="btn" id="kt-reg" style="background:#1c7c3a;color:#fff">✅ 확인(준비등록)</button><button class="btn ghost" id="kt-can">⏪ 준비취소</button>`:`<span style="color:#c0392b;font-size:12px">🔒 권한 없음</span>`}
       <div class="spacer"></div><span class="rowcount">본행 ${nf(st.cnt)}건 · 선택 ${st.sel.size} · 계획 ${nf(st.plan_sum)} · 준비 ${nf(st.ready_sum)}</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')||st.msg.includes('오류')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     ${st.note?`<div class="page-sub" style="color:#b8860b">${esc(st.note)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr><th style="width:22px"><input type="checkbox" id="kt-all"></th>
        <th>SEQ</th><th>파트</th><th>도번</th><th>PART일자</th><th>PART INPUT</th><th>Line No</th><th class="num">당일이전</th>${d.map(x=>`<th class="num"${isWkend(x)?' style="color:#c0392b"':''}>${esc(wlab(x))}</th>`).join('')}<th class="num">준비재고</th><th class="num">완료수량</th><th class="num">준비수량</th><th class="num">생산재고</th><th class="num">ASSY재고</th><th class="num">출하</th><th class="num">자재사용량</th><th>Work Order</th><th>Split Work Order</th><th class="num">회수율</th><th class="num">Item St(회수율반영)</th><th>ASSV도번</th></tr></thead>
      <tbody>${st.loading?spinRow(NCOL+d.length):(flat.length?flat.map(o=>o.t==='m'?mainRow(o):subRow(o)).join(''):`<tr><td colspan="${NCOL+d.length}" class="empty">조회 결과 없음 — 기준일자/작업처/파트/도번을 조정하세요</td></tr>`)}</tbody>
      ${flat.length?`<tfoot><tr class="grandtot" style="position:sticky;bottom:0;background:#eef2f7;font-weight:700;border-top:2px solid #b8c4d4">
        <td></td><td class="center">합계</td><td></td><td></td><td></td><td></td><td></td><td class="num">·</td>${d.map(x=>`<td class="num">${nf(st.rows.reduce((s,r)=>s+((r.days&&r.days[x])||0),0))}</td>`).join('')}
        <td class="num">${nf(st.rows.reduce((s,r)=>s+(r.ready_stock||0),0))}</td><td class="num">${nf(st.rows.reduce((s,r)=>s+(r.finish||0),0))}</td><td class="num">${nf(st.ready_sum)}</td>
        <td></td><td></td><td class="num">${nf(st.rows.reduce((s,r)=>s+(r.sale||0),0))}</td><td></td><td></td><td></td><td></td><td class="num">${f2(st.rows.reduce((s,r)=>s+(r.item_st||0),0))}</td><td></td></tr></tfoot>`:''}
      </table></div>`;
    const g=id=>host.querySelector(id);
    // ★필터는 상태만(자동 조회/재렌더 없음) → 여러 필터 연속 선택 가능. 실제 조회·렌더는 [조회] 버튼에서만.
    g('#kt-go').onclick=()=>{st.base=g('#kt-base').value;st.wc=g('#kt-wc').value;st.part=g('#kt-part').value;
      st.dono=g('#kt-dono').value.trim();st.jado=g('#kt-jado').value.trim();st.gigan=+g('#kt-gigan').value;
      const uf=host.querySelector('input[name=kt-uf]:checked');if(uf)st.unfin=uf.value;
      const vw=host.querySelector('input[name=kt-vw]:checked');if(vw)st.view=vw.value;
      load();};
    g('#kt-prev').onclick=()=>shiftDay(-1);g('#kt-next').onclick=()=>shiftDay(1);   // ◀▶만 즉시조회(예외)
    ['#kt-dono','#kt-jado'].forEach(id=>{const e=g(id);if(e)e.onkeyup=ev=>{if(ev.key==='Enter')g('#kt-go').click();};});
    g('#kt-bom').onclick=()=>alert('BOM출력: 선택 도번의 BOM 인쇄(레거시 전표 연동 예정).');
    g('#kt-move').onclick=()=>alert('생산이동표 강제발행: 선택분 생산창고 이동표 발행(레거시 연동 예정).');
    g('#kt-short').onclick=()=>alert('생산창고 재고과부족 확인: 준비재고 대비 소요 과부족 점검(레거시 연동 예정).');
    const ka=g('#kt-all');if(ka)ka.onclick=e=>{st.sel.clear();if(e.target.checked)st.rows.forEach((r,i)=>st.sel.add(i));render();};
    host.querySelectorAll('.kt-chk').forEach(ch=>ch.onclick=()=>{const i=+ch.dataset.i;ch.checked?st.sel.add(i):st.sel.delete(i);const a=g('#kt-all');if(a)a.checked=false;render();});
    if(ed){g('#kt-reg').onclick=()=>act('register');g('#kt-can').onclick=()=>act('cancel');}
    // ★셀 우클릭 컨텍스트 메뉴(확인/취소) — canEdit 게이트. 마감/출고(fin 6)·완료(fin 4)·잔량0 은 확인 비활성.
    if(ed){
      const gw=host.querySelector('.grid-wrap');
      if(gw)gw.oncontextmenu=(ev)=>{
        const td=ev.target.closest('.kt-cell'); if(!td)return;
        ev.preventDefault();
        const m={item:td.dataset.item,wo:td.dataset.wo,swo:td.dataset.swo,gpc:td.dataset.gpc,ymd:td.dataset.ymd,qty:+td.dataset.qty,assy:td.dataset.assy,fin:td.dataset.fin};
        const canC=m.qty>0 && m.fin!=='4' && m.fin!=='6';   // 확인: 잔량>0·미완료(생산/출하완료 아님)
        const canX=m.fin!=='6';                              // 취소: 출하완료 셀 불가
        const old=document.getElementById('kt-ctxmenu'); if(old)old.remove();
        const mn=document.createElement('div'); mn.id='kt-ctxmenu';
        mn.style.cssText=`position:fixed;left:${ev.clientX}px;top:${ev.clientY}px;z-index:99999;background:#fff;border:1px solid #b8c4d4;border-radius:6px;box-shadow:0 3px 10px rgba(0,0,0,.25);font-size:12px;min-width:150px;overflow:hidden`;
        mn.innerHTML=`<div style="padding:5px 12px;background:#f2f6fb;color:#456;border-bottom:1px solid #e3e9f0">${esc(m.item)} · ${esc(dcol(m.ymd))} · 잔량 ${nf(m.qty)}</div>`+
          `<div class="ktm" data-a="confirm" style="padding:7px 12px;cursor:${canC?'pointer':'not-allowed'};color:${canC?'#1c7c3a':'#c0c8d2'};font-weight:600">✅ 확인(준비등록)</div>`+
          `<div class="ktm" data-a="cancel" style="padding:7px 12px;cursor:${canX?'pointer':'not-allowed'};color:${canX?'#c0392b':'#c0c8d2'};border-top:1px solid #eee">⏪ 준비취소</div>`;
        document.body.appendChild(mn);
        mn.querySelectorAll('.ktm').forEach(el=>el.onclick=()=>{const a=el.dataset.a;
          if((a==='confirm'&&!canC)||(a==='cancel'&&!canX))return; mn.remove(); cellAct(a,m);});
        setTimeout(()=>document.addEventListener('click',()=>{const x=document.getElementById('kt-ctxmenu');if(x)x.remove();},{once:true}),0);
      };
    }
    attachResizers(host);
  };
  render();load();
};

/* ===== 생산전표출력관리 — 전표(J)/간판(G)/라벨(L) 조회·발행(nx.sheet_issue)·인쇄 ===== */
SCREEN.prodsheet=(host)=>{
  const API=API_BASE;
  const iso=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const T=new Date();
  const st={rows:[],cnt:0,from:iso(new Date(T.getTime()-7*864e5)),to:iso(new Date(T.getTime()+7*864e5)),line:'',item:'',sel:new Set(),loading:false,msg:''};
  const load=async()=>{st.loading=true;render();
    const qs=new URLSearchParams({from_ymd:st.from,to_ymd:st.to,line:st.line,item:st.item,limit:1000});
    try{const r=await fetch(`${API}/api/prodsheet/list?${qs}`);const j=await r.json();st.rows=j.rows||[];st.cnt=j.cnt||0;st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.rows=[];}
    st.loading=false;st.sel.clear();render();};
  const selRows=()=>st.rows.filter((r,i)=>st.sel.has(i));
  const issue=async(kind)=>{const rows=selRows();if(!rows.length){alert('발행할 행을 선택하세요');return;}
    const knm={J:'전표',G:'간판',L:'라벨'}[kind];
    if(!confirm(`${rows.length}건 ${knm} 발행(nx 채번)할까요?`))return;
    try{const r=await fetch(`${API}/api/prodsheet/issue`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,rows,user:(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹사용자')})});
      const j=await r.json();if(j.ok){st.msg=`✅ ${knm} ${j.issued}건 발행완료`;await load();}else alert('발행 실패: '+(j.detail||''));}
    catch(e){alert('발행 오류: '+e);}};
  const printOut=(kind)=>{const rows=selRows();if(!rows.length){alert('인쇄할 행을 선택하세요');return;}
    const knm={J:'전표',G:'간판',L:'라벨'}[kind];let html='';
    if(kind==='J')html=rows.map(r=>`<div class="sheet"><h2>생산전표 (작업지시서)</h2>
      <table><tr><th>계획일자</th><td>${esc(r.plan_ymd)}</td><th>라인</th><td>${esc(r.work_center)}</td></tr>
      <tr><th>도번</th><td><b>${esc(r.item_code)}</b></td><th>품명</th><td>${esc(r.nm)}</td></tr>
      <tr><th>워크오더</th><td>${esc(r.work_order)}</td><th>계획수량</th><td><b>${r.plan_qty}</b></td></tr>
      <tr><th>ASSY</th><td colspan="3">${esc(r.assy)}</td></tr></table></div>`).join('');
    else if(kind==='G')html=rows.map(r=>`<div class="kanban"><div class="kb-t">가 간 판</div>
      <div class="kb-item">${esc(r.item_code)}</div><div class="kb-nm">${esc(r.nm)}</div>
      <table><tr><th>라인</th><td>${esc(r.work_center)}</td><th>일자</th><td>${esc(r.plan_ymd)}</td></tr>
      <tr><th>수량</th><td class="big">${r.plan_qty}</td><th>W/O</th><td>${esc(r.work_order)}</td></tr></table></div>`).join('');
    else html=rows.map(r=>`<div class="label"><div class="lb-bc">*${esc(r.item_code)}*</div><div class="lb-item">${esc(r.item_code)}</div><div class="lb-nm">${esc(r.nm)}</div><div class="lb-q">수량 ${r.plan_qty} · ${esc(r.plan_ymd)}</div></div>`).join('');
    const w=window.open('','_blank');
    w.document.write(`<html><head><title>${knm} 인쇄</title><style>
      body{font-family:'맑은 고딕',sans-serif;margin:0;padding:10px}
      .sheet{border:2px solid #000;padding:14px;margin-bottom:14px;page-break-after:always}
      .sheet h2{text-align:center;margin:0 0 10px}.sheet table{width:100%;border-collapse:collapse}
      .sheet th,.sheet td{border:1px solid #333;padding:6px 10px;font-size:14px}.sheet th{background:#eee;width:90px}
      .kanban{border:3px solid #000;padding:12px;width:340px;margin-bottom:12px;page-break-after:always;display:inline-block;vertical-align:top}
      .kb-t{text-align:center;font-size:22px;font-weight:bold;letter-spacing:8px;border-bottom:2px solid #000;padding-bottom:6px}
      .kb-item{font-size:26px;font-weight:bold;text-align:center;margin:8px 0}.kb-nm{text-align:center;color:#333;margin-bottom:8px}
      .kanban table{width:100%;border-collapse:collapse}.kanban th,.kanban td{border:1px solid #333;padding:5px 8px}.kanban .big{font-size:24px;font-weight:bold}
      .label{border:1px solid #000;padding:8px;width:200px;margin:0 8px 8px 0;page-break-after:always;text-align:center;display:inline-block}
      .lb-bc{font-size:18px;letter-spacing:1px;font-weight:bold}.lb-item{font-size:16px;font-weight:bold}.lb-nm{font-size:11px;color:#333}.lb-q{font-size:12px}
      @media print{button{display:none}}
    </style></head><body><button onclick="window.print()" style="margin-bottom:10px;padding:6px 14px;cursor:pointer">🖨 인쇄</button>${html}</body></html>`);
    w.document.close();};
  const render=()=>{
    const ed=(typeof PERM!=='undefined')?PERM.canEdit('prodsheet'):true;
    host.innerHTML=`
     <div class="page-title">🖨️ 생산전표출력관리 <span style="font-size:12px;color:var(--muted);font-weight:400">전표·간판·라벨 조회/발행/인쇄</span></div>
     <div class="page-sub">도번별 생산계획(<code>nx.plan_part</code>) · 유형=jp_proc_method(<b>J전표/G간판</b>) · 발행=<code>nx.sheet_issue</code>(nx 신규원장 채번) · 인쇄=브라우저.</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <label class="tl">계획일자</label><input class="inp" type="date" id="ps-from" value="${st.from}"> ~ <input class="inp" type="date" id="ps-to" value="${st.to}">
       <label class="tl">라인</label><input class="inp" id="ps-line" value="${esc(st.line)}" style="width:70px">
       <label class="tl">도번</label><input class="inp" id="ps-item" value="${esc(st.item)}" style="width:120px">
       <button class="btn" id="ps-go">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">${won(st.cnt)}건 · 선택 ${st.sel.size}</span>
     </div>
     <div class="toolbar" style="margin-top:2px;gap:4px">
       <span class="tl">인쇄:</span><button class="btn" id="ps-pj">📄 전표</button><button class="btn" id="ps-pg">🏷 간판</button><button class="btn" id="ps-pl">🔖 라벨</button>
       ${ed?`<span style="width:12px"></span><span class="tl">발행:</span><button class="btn" id="ps-ij" style="background:#1c47a0;color:#fff">전표발행</button><button class="btn" id="ps-ig" style="background:#1c7c3a;color:#fff">간판발행</button><button class="btn" id="ps-il" style="background:#b8860b;color:#fff">라벨발행</button>`:`<span style="color:#c0392b;font-size:12px">🔒 발행권한 없음</span>`}
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')||st.msg.includes('오류')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 320px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr><th style="width:26px"><input type="checkbox" id="ps-all"></th>
        <th>계획일자</th><th>라인</th><th>도번</th><th>품명</th><th>워크오더</th><th class="num">계획수량</th><th>유형</th><th class="center">간판</th><th class="center">라벨</th></tr></thead>
      <tbody>${st.loading?spinRow(10):(st.rows.length?st.rows.map((r,i)=>`<tr>
        <td class="center"><input type="checkbox" class="ps-chk" data-i="${i}" ${st.sel.has(i)?'checked':''}></td>
        <td>${esc(r.plan_ymd)}</td><td>${esc(r.work_center)}</td><td><b>${esc(r.item_code)}</b></td>
        <td class="cap" title="${esc(r.nm)}" style="max-width:170px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td>
        <td>${esc(r.work_order)}</td><td class="num">${won(r.plan_qty)}</td>
        <td><span class="bdg ${r.method==='J'?'ok':(r.method==='G'?'':'off')}">${esc(r.method_nm)}</span></td>
        <td class="center">${r.gcnt?`<b style="color:#1c7c3a">${r.gcnt}</b>`:'-'}</td><td class="center">${r.lcnt?`<b style="color:#b8860b">${r.lcnt}</b>`:'-'}</td></tr>`).join(''):`<tr><td colspan="10" class="empty">조회 결과 없음</td></tr>`)}</tbody></table></div>`;
    const g=id=>host.querySelector(id);
    g('#ps-go').onclick=()=>{st.from=g('#ps-from').value;st.to=g('#ps-to').value;st.line=g('#ps-line').value;st.item=g('#ps-item').value;load();};
    g('#ps-all').onclick=e=>{st.sel.clear();if(e.target.checked)st.rows.forEach((r,i)=>st.sel.add(i));render();};
    host.querySelectorAll('.ps-chk').forEach(ch=>ch.onclick=()=>{const i=+ch.dataset.i;ch.checked?st.sel.add(i):st.sel.delete(i);g('#ps-all').checked=false;render();});
    g('#ps-pj').onclick=()=>printOut('J');g('#ps-pg').onclick=()=>printOut('G');g('#ps-pl').onclick=()=>printOut('L');
    if(ed){g('#ps-ij').onclick=()=>issue('J');g('#ps-ig').onclick=()=>issue('G');g('#ps-il').onclick=()=>issue('L');}
    attachResizers(host);
  };
  render();load();
};

/* ===== 공정별 바코드생산실적 (w_pr_input_520) — 스캔→자동채움→등록/취소(nx.proc_barcode) ===== */
SCREEN.procbarcode=(host)=>{
  const API=API_BASE;
  const st={ctx:{proc:'',worker:'',mach:''},rows:[],cnt:0,last:null};
  const load=async()=>{try{const r=await fetch(`${API}/api/procbc/list?limit=100`);const j=await r.json();st.rows=j.rows||[];st.cnt=j.cnt||0;}catch(e){}render();};
  const scan=async(bc)=>{bc=(bc||'').trim();if(!bc)return;
    if(!st.ctx.proc.trim()){alert('공정을 먼저 입력하세요');const pi=host.querySelector('#pb-proc');if(pi)pi.focus();return;}
    try{const lk=await(await fetch(`${API}/api/procbc/lookup?barcode=${encodeURIComponent(bc)}&proc_code=${encodeURIComponent(st.ctx.proc)}`)).json();
      if(!lk.found){st.last={err:lk.msg||'미발견',bc};render();refocus();return;}
      const sv=await(await fetch(`${API}/api/procbc/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({barcode:bc,proc_code:st.ctx.proc,item_code:lk.item_code,qty:lk.qty,sheet_no:lk.sheet_no,worker_code:st.ctx.worker,mach_code:st.ctx.mach,user:(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹사용자')})})).json();
      if(sv.ok)st.last={ok:1,action:sv.action,item:lk.item_code,nm:lk.item_name,qty:Math.abs(sv.qty),kind:lk.kind,bc};
      else st.last={err:(sv.errors||[]).join(' '),bc};
      await load();}
    catch(e){st.last={err:'오류: '+e,bc};render();}
    refocus();};
  const refocus=()=>setTimeout(()=>{const bi=host.querySelector('#pb-bc');if(bi){bi.value='';bi.focus();}},60);
  const render=()=>{
    const ed=(typeof PERM!=='undefined')?PERM.canEdit('procbarcode'):true;
    const L=st.last;
    host.innerHTML=`
     <div class="page-title">🔫 공정별 바코드생산실적 <span style="font-size:12px;color:var(--muted);font-weight:400">간판/라벨 스캔 → 실적 등록/취소 · nx.proc_barcode</span></div>
     <div class="page-sub">공정·작업자 설정 후 <b>간판(GP…)/라벨(QR) 바코드 스캔</b> → 품번·수량 자동채움 → 등록. 같은 바코드 재스캔=취소(토글). 발행=생산전표출력관리. <span style="color:#b8860b">※520 원본 소스 부재로 커밋 근사 — 원본 확보 후 대조</span>.</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:6px;background:#f4f7fc;border-radius:8px;padding:8px">
       <label class="tl">공정<span style="color:#c0392b">*</span></label><input class="inp" id="pb-proc" value="${esc(st.ctx.proc)}" placeholder="공정코드" style="width:100px">
       <label class="tl">작업자</label><input class="inp" id="pb-worker" value="${esc(st.ctx.worker)}" placeholder="작업자" style="width:100px">
       <label class="tl">작업테이블</label><input class="inp" id="pb-mach" value="${esc(st.ctx.mach)}" placeholder="설비" style="width:100px">
     </div>
     <div style="margin-top:10px;display:flex;gap:10px;align-items:center">
       <label class="tl" style="font-size:14px">🔫 바코드</label>
       <input class="inp" id="pb-bc" placeholder="간판(GP…) 또는 라벨 QR 스캔 후 Enter" style="width:340px;font-size:15px;padding:8px" ${ed?'':'disabled'} autofocus>
       ${ed?'':'<span style="color:#c0392b;font-size:12px">🔒 실적등록 권한 없음</span>'}
     </div>
     ${L?`<div style="margin-top:10px;padding:10px 14px;border-radius:8px;font-size:14px;${L.ok?'background:#e5f3e8;border:1px solid #a8d5b5':'background:#fdecec;border:1px solid #f3c9c9'}">
       ${L.ok?`<b style="color:${L.action==='취소'?'#c0392b':'#1c7c3a'}">${L.action==='취소'?'⏪ 취소':'✅ 등록'}</b> · ${L.kind} · <b>${esc(L.item)}</b> ${esc(L.nm)} · 수량 <b>${L.qty}</b>`:`<b style="color:#c0392b">✖ ${esc(L.err)}</b> (${esc(L.bc)})`}
     </div>`:''}
     <div class="page-sub" style="margin-top:12px;font-weight:600">최근 스캔 이력 <span style="color:var(--muted);font-weight:400">(${won(st.cnt)}건)</span></div>
     <div class="grid-wrap" style="max-height:calc(100vh - 420px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr>
        <th>일시</th><th>공정</th><th>바코드</th><th>도번</th><th>품명</th><th class="num">수량</th><th>작업자</th><th class="num">전표</th></tr></thead>
      <tbody>${st.rows.length?st.rows.map(r=>`<tr>
        <td class="mut">${esc(String(r.dt||'').slice(0,19).replace('T',' '))}</td><td>${esc(r.proc)}</td>
        <td>${esc(r.barcode)}</td><td><b>${esc(r.item_code)}</b></td>
        <td class="cap" title="${esc(r.nm)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td>
        <td class="num ${r.qty<0?'neg':''}">${won(r.qty)}</td><td>${esc(r.worker)}</td><td class="num">${esc(r.sheet_no)}</td></tr>`).join(''):`<tr><td colspan="8" class="empty">스캔 이력 없음</td></tr>`}</tbody></table></div>`;
    const g=id=>host.querySelector(id);
    g('#pb-proc').oninput=e=>{st.ctx.proc=e.target.value;};
    g('#pb-worker').oninput=e=>{st.ctx.worker=e.target.value;};
    g('#pb-mach').oninput=e=>{st.ctx.mach=e.target.value;};
    if(ed){const bi=g('#pb-bc');if(bi){bi.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();scan(bi.value);}};}}
    attachResizers(host);
  };
  render();load();
};

/* ===== 생산준비재고관리 — 준비(키팅) 재고 조회 (읽기전용) ===== */
SCREEN.readystock=(host)=>{
  const API=API_BASE;
  const st={rows:[],cnt:0,total:0,procs:[],q:'',proc:'',loading:false,msg:''};
  const load=async()=>{
    st.loading=true;render();
    const qs=new URLSearchParams({q:st.q,proc:st.proc,limit:1500});
    try{const r=await fetch(`${API}/api/readystock/list?${qs}`);const j=await r.json();
      st.rows=j.rows||[];st.cnt=j.cnt||0;st.total=j.total_qty||0;if(j.procs)st.procs=j.procs;st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.rows=[];}
    st.loading=false;render();
  };
  const render=()=>{
    host.innerHTML=`
     <div class="page-title">🧷 생산준비재고관리 <span style="font-size:12px;color:var(--muted);font-weight:400">준비(키팅) 재고 잔량 · 조회</span></div>
     <div class="page-sub">생산준비(키팅) 재고 잔량. 원천 <code>PU_T_READY_STOCK</code>. <b style="color:#b8860b">강제수정(자재복원)은 준비원장 설계 후 제공 예정 — 현재 조회만</b>.</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <label class="tl">공정</label><select class="inp" id="rs-proc" style="width:auto"><option value="">전체</option>${st.procs.map(o=>`<option value="${esc(o.code)}" ${st.proc===o.code?'selected':''}>${esc(o.nm)}</option>`).join('')}</select>
       <label class="tl">검색</label><input class="inp" id="rs-q" value="${esc(st.q)}" placeholder="품번/품명" style="width:170px">
       <button class="btn" id="rs-search">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">${won(st.cnt)}건 · 재고합 <b>${won(Math.round(st.total))}</b></span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:#c0392b;font-weight:600">${esc(st.msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr>
        <th>품번</th><th>품명</th><th>규격</th><th>공정</th><th>거래처</th><th class="num">준비재고</th><th class="center">최종수정</th></tr></thead>
      <tbody>${st.loading?spinRow(7):(st.rows.length?st.rows.map(r=>`<tr>
        <td><b>${esc(r.item_code)}</b></td>
        <td class="cap" title="${esc(r.nm)}" style="max-width:170px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td>
        <td class="cap" title="${esc(r.spec)}" style="max-width:120px;overflow:hidden;text-overflow:ellipsis">${esc(r.spec)}</td>
        <td>${esc(r.proc_nm)}</td><td class="cap" title="${esc(r.cust_nm)}" style="max-width:110px;overflow:hidden;text-overflow:ellipsis">${esc(r.cust_nm)}</td>
        <td class="num ${r.stock_qty<0?'neg':''}">${won(r.stock_qty)}</td>
        <td class="center mut">${esc((r.upd_dt||'').slice(0,10))}</td></tr>`).join(''):`<tr><td colspan="7" class="empty">조회 결과 없음</td></tr>`)}</tbody></table></div>`;
    const g=id=>host.querySelector(id);
    g('#rs-search').onclick=()=>{st.q=g('#rs-q').value;st.proc=g('#rs-proc').value;load();};
    g('#rs-q').onkeyup=e=>{if(e.key==='Enter')g('#rs-search').click();};
    g('#rs-proc').onchange=()=>{st.proc=g('#rs-proc').value;load();};
    attachResizers(host);
  };
  load();
};

/* ===== 생산: 생산계획현황 (라이브 SA_T_PLAN_DTL, 제번×일자 피벗) — 생산팀 요청 ===== */
SCREEN.prodplanstatus=(c)=>{
  const API=API_BASE;
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:(s||'');
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  let F={from:iso(new Date(T.getTime()-3*864e5)),to:iso(new Date(T.getTime()+14*864e5)),line:'',wo:'',model:'',cr:''};
  let data={dates:[],rows:[],wo_count:0,sum_qty:0}, loading=false, msg='';
  const load=async()=>{loading=true;draw();
    const qs=new URLSearchParams({from_ymd:F.from,to_ymd:F.to,line:F.line,wo:F.wo,model:F.model,cr:F.cr});
    try{const r=await fetch(`${API}/api/prodplan/status?${qs}`);data=await r.json();msg='';}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010';data={dates:[],rows:[],wo_count:0,sum_qty:0};}
    loading=false;draw();};
  const draw=()=>{
    const dates=data.dates||[];
    // 규칙17: 로드된 rows에서 라인·제번·모델 datalist (모델=값→이름 그대로)
    const psLine=new Set(),psWo=new Set(),psModel=new Set();
    (data.rows||[]).forEach(r=>{if(r.line)psLine.add(r.line);if(r.wo)psWo.add(r.wo);if(r.model)psModel.add(r.model);});
    const psLineOpts=[...psLine].map(v=>`<option value="${esc(v)}"></option>`).join('');
    const psWoOpts=[...psWo].map(v=>`<option value="${esc(v)}"></option>`).join('');
    const psModelOpts=[...psModel].map(v=>`<option value="${esc(v)}"></option>`).join('');
    c.innerHTML=`
     <div class="page-title">📋 생산계획현황 <span style="font-size:12px;color:var(--muted);font-weight:400">현행 LG 생산계획(제번×일자)</span></div>
     <div class="page-sub">현행 생산계획을 <b>제번(WO)×일자</b>로 조회(라이브·읽기전용). 원본 <code>SA_T_PLAN_DTL</code> · 업로드본(nx)은 생산계획업로드에서 대조 · C=확정/R=변경</div>
     <div class="toolbar">
       <label class="tl">계획기간</label><input class="inp" type="date" id="pp-from" value="${F.from}"> ~ <input class="inp" type="date" id="pp-to" value="${F.to}">
       <label class="tl">라인</label><input class="inp" id="pp-line" list="ppst-line" value="${esc(F.line)}" style="width:70px" placeholder="라인" autocomplete="off"><datalist id="ppst-line">${psLineOpts}</datalist>
       <label class="tl">제번</label><input class="inp" id="pp-wo" list="ppst-wo" value="${esc(F.wo)}" style="width:110px" placeholder="제번 입력" autocomplete="off"><datalist id="ppst-wo">${psWoOpts}</datalist>
       <label class="tl">모델</label><input class="inp" id="pp-model" list="ppst-model" value="${esc(F.model)}" style="width:120px" placeholder="모델명 입력" autocomplete="off"><datalist id="ppst-model">${psModelOpts}</datalist>
       <label class="tl">구분</label><select class="inp" id="pp-cr"><option value="">전체</option><option value="C"${F.cr==='C'?' selected':''}>확정(C)</option><option value="R"${F.cr==='R'?' selected':''}>변경(R)</option></select>
       <button class="btn" id="pp-search">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">제번 ${won(data.wo_count)} · 계획합 <b>${won(data.sum_qty)}</b> · 일자 ${dates.length}</span>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:11px"><thead><tr>
        <th>라인</th><th>제번</th><th>모델</th><th class="center">구분</th><th class="center">치공구</th><th class="num">계</th>${dates.map(d=>`<th class="num">${dcol(d)}</th>`).join('')}</tr></thead>
      <tbody>${loading?spinRow(6+dates.length):((data.rows&&data.rows.length)?data.rows.map(r=>`<tr>
        <td class="center">${esc(r.line)}</td><td><b>${esc(r.wo)}</b></td>
        <td class="bcap" title="${esc(r.model)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.model)}</td>
        <td class="center">${r.cr==='R'?'<span class="bdg" style="background:#f4d3d3;color:#a33">변경</span>':(r.cr==='C'?'<span class="bdg ok">확정</span>':esc(r.cr))}</td>
        <td class="center">${esc(r.tool)}</td><td class="num"><b>${won(r.total)}</b></td>
        ${dates.map(d=>`<td class="num">${r.days[d]?won(r.days[d]):''}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${6+dates.length}" class="empty">조회 결과 없음 (기간/조건 조정)</td></tr>`)}</tbody></table></div>`;
    const g=id=>c.querySelector(id);
    g('#pp-search').onclick=()=>{F.from=g('#pp-from').value;F.to=g('#pp-to').value;F.line=g('#pp-line').value;F.wo=g('#pp-wo').value;F.model=g('#pp-model').value;F.cr=g('#pp-cr').value;load();};
    ['#pp-line','#pp-wo','#pp-model'].forEach(id=>g(id).onkeyup=e=>{if(e.key==='Enter')g('#pp-search').click();});
  };
  load();
};

/* ===== 일반업무: 공수등록(근무/지원) — HR_M_WORK_INFO(라이브)↔nx.hr_work_info ===== */
SCREEN.gongsu=(c)=>{
  wrShell(c,{sid:'gongsu',
    title:`⏱️ 공수등록 <span style="font-size:12px;color:var(--muted);font-weight:400">근무/지원 공수(등록·수정·삭제)</span>`,
    sub:`부서·작업자별 근무/지원 공수. 🔴 라이브=<code>HR_M_WORK_INFO</code> · ✏️ 신규편집=<code>nx.hr_work_info</code> · 근태 0정상/1연차/2반차/3조퇴(소스 w_pr_worktime)`,
    default:'live',
    live:(body)=>qcRead(body,{
      listEp:'/api/gongsu/list', dateLabel:'근무일', days:7,
      filters:[{k:'gubun',label:'구분',width:60},{k:'dept',label:'부서',width:60},{k:'user',label:'작업자',width:90}],
      buildQS:F=>({from_ymd:F.from,to_ymd:F.to,gubun:F.gubun||'',dept:F.dept||'',user:F.user||'',src:'legacy'}),
      sum:d=>`공수합 <b>${_wnf(d.sum_hr)}</b>h`,
      cols:[
        {h:'구분',cls:'center',fmt:r=>r.gubun==='지원'?'<span class="bdg" style="background:#e7f0ff;color:#1c47a0">지원</span>':'<span class="bdg ok">근무</span>'},
        {h:'근무일',cls:'center',fmt:r=>_wymd(r.work_ymd)},
        {h:'부서',fmt:r=>esc(r.dept_nm||r.dept_code)},
        {h:'작업자',k:'user_id'},
        {h:'라인',k:'line',cls:'center'},
        {h:'시작',k:'start_time',cls:'center'},{h:'종료',k:'end_time',cls:'center'},
        {h:'근무h',cls:'num',fmt:r=>_wnf(r.work_hr)},
        {h:'지원라인',k:'support_line',cls:'center'},
        {h:'지원h',cls:'num',fmt:r=>r.support_hr?_wnf(r.support_hr):''},
        {h:'근태',cls:'center',fmt:r=>r.hr_check_nm==='정상'?'':`<span style="color:#c0392b">${esc(r.hr_check_nm)}</span>`},
        {h:'비고',k:'remarks',cap:1,title:'remarks'},
      ]}),
    cfg:{
      listEp:'/api/gongsu/list', saveEp:'/api/gongsu/save', delEp:'/api/gongsu/delete', days:14,
      dateLabel:'근무일', filters:[{k:'gubun',label:'구분',width:60},{k:'dept',label:'부서',width:60},{k:'user',label:'작업자',width:90}],
      buildQS:F=>({from_ymd:F.from,to_ymd:F.to,gubun:F.gubun||'',dept:F.dept||'',user:F.user||'',src:'nx'}),
      sum:d=>`공수합 <b>${_wnf(d.sum_hr)}</b>h`,
      cols:[
        {h:'구분',cls:'center',k:'gubun'},
        {h:'근무일',cls:'center',fmt:r=>_wymd(r.work_ymd)},
        {h:'부서',k:'dept_code',cls:'center'},
        {h:'작업자',k:'user_id'},
        {h:'라인',k:'line',cls:'center'},
        {h:'시작',k:'start_time',cls:'center'},{h:'종료',k:'end_time',cls:'center'},
        {h:'근무h',cls:'num',fmt:r=>_wnf(r.work_hr)},
        {h:'지원h',cls:'num',fmt:r=>r.support_hr?_wnf(r.support_hr):''},
        {h:'근태',cls:'center',k:'hr_check_nm'},
        {h:'비고',k:'remarks',cap:1,title:'remarks'},
      ],
      form:[
        {k:'gubun',label:'구분',type:'select',opts:[{v:'근무',t:'근무'},{v:'지원',t:'지원'}],width:80},
        {k:'work_ymd',label:'근무일',type:'date',required:1,width:140},
        {k:'dept_code',label:'부서',width:70},{k:'user_id',label:'작업자',required:1,width:100},
        {k:'line',label:'라인',width:70},{k:'start_time',label:'시작',width:60},{k:'end_time',label:'종료',width:60},
        {k:'work_hr',label:'근무시간',type:'num',width:80},
        {k:'support_line',label:'지원라인',width:70},{k:'support_hr',label:'지원시간',type:'num',width:80},
        {k:'hr_check',label:'근태',type:'select',opts:[{v:'0',t:'정상'},{v:'1',t:'연차'},{v:'2',t:'반차'},{v:'3',t:'조퇴'}],width:90},
        {k:'remarks',label:'비고',width:200},
      ],
      newRow:F=>({id:null,gubun:'근무',work_ymd:F.to,dept_code:'',user_id:'',line:'',start_time:'0800',end_time:'1700',work_hr:8,support_line:'',support_hr:'',hr_check:'0',remarks:''}),
      fromRow:r=>({id:r.ID,gubun:r.gubun,work_ymd:_y6(r.work_ymd),dept_code:r.dept_code,user_id:r.user_id,line:r.line,start_time:r.start_time,end_time:r.end_time,work_hr:r.work_hr,support_line:r.support_line,support_hr:r.support_hr,hr_check:r.hr_check,remarks:r.remarks}),
      toBody:f=>({id:f.id,gubun:f.gubun,work_ymd:f.work_ymd,dept_code:f.dept_code,user_id:f.user_id,line:f.line,start_time:f.start_time,end_time:f.end_time,work_hr:f.work_hr,support_line:f.support_line,support_hr:f.support_hr,hr_check:f.hr_check,remarks:f.remarks,uuser:'웹사용자'}),
    }
  });
};

/* ===== 일반업무: 일일체크리스트 (DAY_CHECK_LIST 라이브 조회, 과거이력 안내) ===== */
SCREEN.daycheck=(c)=>{
  const API=API_BASE;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  let F={from:nowMS(),to:nowCD(),dept:''}, data={rows:[],cnt:0,note:''}, loading=false, msg='';
  const load=async()=>{loading=true;draw();
    const qs=new URLSearchParams({from_ymd:F.from,to_ymd:F.to,dept:F.dept});
    try{const r=await fetch(`${API}/api/daycheck/list?${qs}`);data=await r.json();msg='';}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010';data={rows:[],cnt:0};}
    loading=false;draw();};
  const draw=()=>{
    c.innerHTML=`
     <div class="page-title">📋 일일체크리스트 <span style="font-size:12px;color:var(--muted);font-weight:400">부서간 일일 이슈/체크</span></div>
     <div class="page-sub">부서간 일일 이슈·체크 공유(라이브·읽기전용). 원본 <code>DAY_CHECK_LIST</code>.</div>
     ${data.note?`<div class="page-sub" style="color:#b8860b">ℹ ${esc(data.note)} (최신 ${esc(_wymd(data.max_ymd))})</div>`:''}
     <div class="toolbar">
       <label class="tl">일자</label><input class="inp" type="date" id="dc-from" value="${F.from}"> ~ <input class="inp" type="date" id="dc-to" value="${F.to}">
       <label class="tl">부서</label><input class="inp" id="dc-dept" value="${esc(F.dept)}" style="width:120px">
       <button class="btn" id="dc-search">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">${won(data.cnt)}건</span>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 320px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:11px"><thead><tr><th>일자</th><th>부서</th><th>요청자</th><th>이슈항목</th><th>이슈내용</th><th>내용/조치</th><th class="center">결과</th><th>결과자</th><th class="center">중요</th></tr></thead>
      <tbody>${loading?spinRow(9):((data.rows&&data.rows.length)?data.rows.map(r=>`<tr>
        <td class="center">${esc(_wymd(r.ymd))}</td><td>${esc(r.dept)}</td><td>${esc(r.req)}</td>
        <td>${esc(r.item)}</td><td class="bcap" title="${esc(r.note)}" style="max-width:200px;overflow:hidden;text-overflow:ellipsis">${esc(r.note)}</td>
        <td class="bcap" title="${esc(r.contents)}" style="max-width:200px;overflow:hidden;text-overflow:ellipsis">${esc(r.contents)}</td>
        <td class="center">${esc(r.result)}</td><td>${esc(r.rmember)}</td><td class="center">${r.imp?'⭐':''}</td></tr>`).join(''):`<tr><td colspan="9" class="empty">조회 결과 없음</td></tr>`)}</tbody></table></div>`;
    const g=id=>c.querySelector(id);
    g('#dc-search').onclick=()=>{F.from=g('#dc-from').value;F.to=g('#dc-to').value;F.dept=g('#dc-dept').value;load();};
    g('#dc-dept').onkeyup=e=>{if(e.key==='Enter')g('#dc-search').click();};
  };
  load();
};

/* ===== 생산 ⑨: 공정별 생산실적등록 (w_pr_input_260) — PR_T_PROD_DTL 실적 이력 ===== */
SCREEN.procresult=(c)=>{
  const wrLiveProc=(body)=>{
    const API=API_BASE;
    const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
    const T=new Date();
    let F={from:iso(new Date(T.getFullYear(),T.getMonth(),1)),to:iso(T),swork:'',line:'',item:''};
    let data={rows:[],cnt:0,sum_qty:0}, loading=false, msg='';
    const load=async()=>{loading=true;draw();
      const qs=new URLSearchParams({from_ymd:F.from,to_ymd:F.to,swork:F.swork,line:F.line,item:F.item});
      try{const r=await fetch(`${API}/api/procresult/dtl?${qs}`);data=await r.json();msg='';}
      catch(e){msg='백엔드 연결 실패';data={rows:[],cnt:0,sum_qty:0};}
      loading=false;draw();};
    const draw=()=>{
      body.innerHTML=`
       <div class="toolbar">
         <label class="tl">생산기간</label><input class="inp" type="date" id="pc-from" value="${F.from}"> ~ <input class="inp" type="date" id="pc-to" value="${F.to}">
         <label class="tl">공정</label><input class="inp" id="pc-sw" value="${esc(F.swork)}" style="width:70px">
         <label class="tl">라인</label><input class="inp" id="pc-line" value="${esc(F.line)}" style="width:60px">
         <label class="tl">품번</label><input class="inp" id="pc-item" value="${esc(F.item)}" style="width:120px">
         <button class="btn" id="pc-search">🔍 조회</button>
         <div class="spacer"></div><span class="rowcount">${_wnf(data.cnt)}건 · 생산수량합 <b>${_wnf(data.sum_qty)}</b></span>
       </div>
       ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
       <div class="grid-wrap" style="max-height:calc(100vh - 340px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
        <table class="tbl" style="font-size:11px"><thead><tr><th>생산일자</th><th>시각</th><th>WORK-ORDER</th><th>도번</th><th>품명</th><th>파트</th><th>공정</th><th>라인</th><th class="num">생산수량</th><th>작업자</th></tr></thead>
        <tbody>${loading?spinRow(10):((data.rows&&data.rows.length)?data.rows.map(r=>`<tr>
          <td class="center">${_wymd(r.PROD_YMD)}</td><td class="center">${_whms(r.PROD_HMS)}</td><td>${esc(r.wo)}</td><td><b>${esc(r.item)}</b></td>
          <td class="bcap" title="${esc(r.nm)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td>
          <td class="center">${esc(r.part)}</td><td class="center">${esc(r.sw)}</td><td class="center">${esc(r.line)}</td>
          <td class="num"><b>${_wnf(r.PROD_QTY)}</b></td><td>${esc(r.usr)}</td></tr>`).join(''):`<tr><td colspan="10" class="empty">조회 결과 없음</td></tr>`)}</tbody></table></div>`;
      const g=id=>body.querySelector(id);
      g('#pc-search').onclick=()=>{F.from=g('#pc-from').value;F.to=g('#pc-to').value;F.swork=g('#pc-sw').value;F.line=g('#pc-line').value;F.item=g('#pc-item').value;load();};
      ['#pc-sw','#pc-line','#pc-item'].forEach(id=>g(id).onkeyup=e=>{if(e.key==='Enter')g('#pc-search').click();});
    };
    load();
  };
  wrShell(c,{sid:'procresult',
    title:`✅ 공정별 생산실적등록 <span style="font-size:12px;color:var(--muted);font-weight:400">공정별 생산실적(등록·수정·삭제)</span>`,
    sub:`공정별 생산실적(제번·품목·공정·수량). 🔴 라이브=<code>PR_T_PROD_DTL</code> · ✏️ 신규편집=<code>nx.proc_result</code>`,
    default:'edit',
    live:wrLiveProc,
    cfg:{
      listEp:'/api/procreg/list', saveEp:'/api/procreg/save', delEp:'/api/procreg/delete', days:3,
      dateLabel:'생산기간', filters:[{k:'swork',label:'공정',width:60},{k:'line',label:'라인',width:50},{k:'item',label:'품번',width:120},{k:'wo',label:'WO',width:100}],
      buildQS:F=>({from_ymd:F.from,to_ymd:F.to,swork:F.swork||'',line:F.line||'',item:F.item||'',wo:F.wo||''}),
      sum:d=>`생산수량합 <b>${_wnf(d.sum_qty)}</b>`,
      cols:[
        {h:'생산일자',cls:'center',fmt:r=>_wymd(r.PROD_YMD)},
        {h:'시각',cls:'center',fmt:r=>_whms(r.PROD_HMS)},
        {h:'WORK-ORDER',k:'wo'},
        {h:'도번',fmt:r=>`<b>${esc(r.item)}</b>`},
        {h:'품명',k:'nm',cap:1,title:'nm'},
        {h:'파트',k:'part',cls:'center'},
        {h:'공정',k:'sw',cls:'center'},
        {h:'라인',k:'line',cls:'center'},
        {h:'생산수량',cls:'num',fmt:r=>`<b>${_wnf(r.PROD_QTY)}</b>`},
        {h:'완료',cls:'center',fmt:r=>r.fin==='5'?'✔':''},
        {h:'작업자',k:'usr'},
      ],
      form:[
        {k:'prod_ymd',label:'생산일자',type:'date',required:1,width:140},
        {k:'work_order',label:'WO',width:110},{k:'split_work_order',label:'분할WO',width:110},
        {k:'item_code',label:'도번',required:1,search:1,width:150},
        {k:'part_code',label:'파트',width:60},{k:'s_work_code',label:'공정',type:'num',width:70},{k:'line_no',label:'라인',width:60},
        {k:'prod_qty',label:'생산수량',type:'num',width:90},{k:'work_code',label:'작업처',width:60},
        {k:'finish_flag',label:'완료',type:'select',opts:[{v:'0',t:'진행'},{v:'5',t:'완료'}],width:90},
      ],
      newRow:F=>({id:null,prod_ymd:F.to,work_order:'',split_work_order:'',item_code:'',part_code:'',s_work_code:'',line_no:'',prod_qty:'',work_code:'',finish_flag:'0'}),
      fromRow:r=>({id:r.ID,prod_ymd:_y6(r.PROD_YMD),prod_hms:r.PROD_HMS,work_order:r.wo,split_work_order:r.swo,item_code:r.item,part_code:r.part,s_work_code:r.sw,line_no:r.line,prod_qty:r.PROD_QTY,work_code:r.work_code,finish_flag:r.fin||'0'}),
      toBody:f=>({id:f.id,prod_ymd:f.prod_ymd,prod_hms:f.prod_hms||'',work_order:f.work_order,split_work_order:f.split_work_order,item_code:f.item_code,part_code:f.part_code,s_work_code:f.s_work_code,line_no:f.line_no,prod_qty:f.prod_qty,work_code:f.work_code,finish_flag:f.finish_flag,user:'웹사용자'}),
    }
  });
};
