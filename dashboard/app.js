// KStore Habitat: this client contains no operational fixtures.
const API = location.pathname.startsWith('/dashboard') ? location.origin : 'http://192.168.0.87:8788';
const names = ['Overview', 'Pipelines', 'Traffic', 'Queues', 'Storage', 'Models', 'Audit'];
const state = {
  screen: new URLSearchParams(location.search).get('screen') || 'Overview',
  snapshot: null, events: null, jobs: null, reviews: null,
  errors: {}, lastFetch: {}, query: '', selected: null, before: null, eventsBusy: false,
  loading: true, logOpen: false, logSource: 'concierge', logs: null,
  logQuery: '', logAt: '', logFollow: true, logError: '',
  chat: [], chatBusy: false, chatDraft: '', explanation: '', analyzedFailure: '', citations: [],
  domPatches: [],
};
if (!names.includes(state.screen)) state.screen = 'Overview';
const root = document.querySelector('#app');
const e = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const when = value => value ? new Date(value).toLocaleString() : 'No observation';
const count = value => typeof value === 'number' ? value.toLocaleString() : '—';
const duration = value => typeof value === 'number' ? (value >= 3600 ? `${(value/3600).toFixed(1)} h` : value >= 60 ? `${(value/60).toFixed(1)} min` : `${value.toFixed(0)} s`) : '—';
const status = source => source?.state === 'ok' ? `<span class="badge good">OBSERVED</span>` : source?.state === 'unavailable' ? `<span class="badge warn">PROBE FAILED</span>` : `<span class="badge">CONNECTING</span>`;
const source = name => state.snapshot?.sources?.[name];
const section = (eyebrow, inner, extra='') => `<section class="panel live-panel ${extra}"><div class="section-top"><span class="eyebrow">${eyebrow}</span></div>${inner}</section>`;
const error = key => state.errors[key] ? `<div class="source-error">${e(key)} request failed at ${when(state.lastFetch[key])}: ${e(state.errors[key])}</div>` : '';
const sourceError = data => data?.state === 'unavailable' ? `<p class="source-error">Probe failed at ${when(data.observed_at)} · ${e(data.error_class)}</p>` : '';
const empty = (message) => `<p class="empty-state">${e(message)}</p>`;
function sourceCard(name, label, value, detail) {
  const s = source(name);
  return `<div class="source-card"><div class="source-head"><strong>${e(label)}</strong>${status(s)}</div>${s?.state === 'ok' ? `<div class="source-value">${e(value(s.data))}</div><p>${e(detail(s.data))}</p>` : sourceError(s)}</div>`;
}
function overview() {
  const pg = source('postgres'); const q = pg?.data?.queue; const activity = pg?.data?.activity;
  return `<div class="live-grid">${section('CAPTURE / POSTGRESQL', pg?.state === 'ok' ? `<div class="live-number">${count(activity.event_count)}</div><p>Committed activity events</p><div class="detail-pair"><span>Latest committed event</span><strong>${when(activity.latest_event_at)}</strong></div>` : sourceError(pg) || empty('Connecting to PostgreSQL observation.'))}${section('EMBEDDING QUEUE', q ? `<div class="live-number">${count(q.counts.pending)}</div><p>Pending durable jobs</p><div class="detail-pair"><span>Processing</span><strong>${count(q.counts.processing)}</strong></div><div class="detail-pair"><span>Oldest incomplete</span><strong>${duration(q.oldest_incomplete_age_seconds)}</strong></div>${q.latest_error ? `<div class="source-error">Latest error: ${e(q.latest_error.class)} · ${when(q.latest_error.updated_at)}</div>` : ''}` : sourceError(pg) || empty('Connecting to queue observation.'))}${section('SYSTEM SOURCES', `<div class="source-grid">${sourceCard('postgres','PostgreSQL',d=>`${count(d.activity.event_count)} events`,d=>`Observed ${when(source('postgres').observed_at)}`)}${sourceCard('qdrant','Qdrant',d=>`${count(d.points)} points`,d=>`Collection: ${d.collection}`)}${sourceCard('ollama','Ollama',d=>d.loaded ? 'Configured embedder loaded' : 'Configured embedder not loaded',d=>d.configured_embedding_model)}${sourceCard('worker','Embedding worker',d=>d.state,d=>d.unit)}</div>`, 'span-two')}${section('RECENT CAPTURED ACTIVITY', state.events ? (state.events.items.length ? `<div class="compact-list">${state.events.items.slice(0,8).map(row=>`<button data-event="${e(row.sha256)}"><span>${e(row.kind)}</span><small>${when(row.created_at)} · ${e(row.stream_id)} / ${row.sequence}</small></button>`).join('')}</div>` : empty('No captured activity events were returned.')) : error('events') || empty('Connecting to activity events.'), 'span-two')}</div>`;
}
function pipelines() {
  const snap = state.snapshot;
  return `${section('OBSERVED HOST', snap ? `<div class="host-title">${e(snap.host)}</div><p>These sources were probed by the concierge at ${when(snap.generated_at)}. This view does not infer other hosts or network paths.</p><div class="source-grid">${sourceCard('postgres','PostgreSQL',d=>`${count(d.activity.event_count)} events`,d=>'Durable activity and jobs')}${sourceCard('qdrant','Qdrant',d=>`${count(d.points)} points`,d=>d.collection)}${sourceCard('ollama','Ollama',d=>d.loaded ? 'Loaded' : 'Not loaded',d=>d.configured_embedding_model)}${sourceCard('worker','Embedding worker',d=>d.state,d=>d.unit)}</div>` : error('snapshot') || empty('Connecting to source observations.'))}`;
}
function traffic() {
  const rows = (state.events?.items || []).filter(row => `${row.kind} ${row.stream_id} ${row.turn_id || ''} ${row.sha256}`.toLowerCase().includes(state.query.toLowerCase()));
  const chosen = rows.find(row => row.sha256 === state.selected) || rows[0];
  return `<div class="traffic-layout"><section class="panel traffic-main"><div class="section-top"><span class="eyebrow">CAPTURED ACTIVITY EVENTS</span>${state.events ? `<span class="muted">Read ${when(state.events.observed_at)}</span>` : ''}</div><div class="search-wrap"><span>⌕</span><input id="event-query" aria-label="Filter captured events" value="${e(state.query)}" placeholder="Filter recorded kind, stream, turn, or hash"></div>${error('events')}${state.events ? (rows.length ? `<div class="table-scroll"><table><thead><tr><th>COMMITTED</th><th>KIND</th><th>STREAM / SEQUENCE</th><th>TURN</th><th>BYTES</th></tr></thead><tbody>${rows.map(row=>`<tr data-event="${e(row.sha256)}" class="${chosen?.sha256 === row.sha256 ? 'selected' : ''}"><td>${when(row.created_at)}</td><td class="op">${e(row.kind)}</td><td class="mono">${e(row.stream_id)} / ${row.sequence}</td><td class="mono">${e(row.turn_id || '')}</td><td class="mono">${count(row.bytes)}</td></tr>`).join('')}</tbody></table></div>` : empty('No recorded events match the current filter.')) : empty('Connecting to activity events.')}${state.events?.next_cursor ? `<button class="ghost" id="events-older" ${state.eventsBusy?'disabled':''}>${state.eventsBusy?'Loading recorded events…':'Load older recorded events'}</button>` : ''}<div class="table-foot">Raw payloads and private reasoning are not exposed by this read API.</div></section><aside class="panel inspector"><span class="eyebrow">EVENT METADATA</span>${chosen ? `<h2>${e(chosen.kind)}</h2><div class="detail-pair"><span>Committed</span><strong>${when(chosen.created_at)}</strong></div><div class="detail-pair"><span>Stream</span><strong>${e(chosen.stream_id)}</strong></div><div class="detail-pair"><span>Sequence</span><strong>${chosen.sequence}</strong></div><div class="detail-pair"><span>Turn</span><strong>${e(chosen.turn_id || '')}</strong></div><div class="detail-pair"><span>Bytes</span><strong>${count(chosen.bytes)}</strong></div><div class="detail-pair"><span>Private blocks filtered</span><strong>${chosen.filtered ? 'Yes' : 'No'}</strong></div><div class="hash">SHA256 ${e(chosen.sha256)}</div>` : empty('Select a recorded event.')}</aside></div>`;
}
function queues() {
  const pg = source('postgres'); const q = pg?.data?.queue;
  return `${section('DURABLE JOB STATE', q ? `<div class="metric-strip">${['pending','processing','complete'].map(kind=>`<div><span>${kind.toUpperCase()}</span><strong>${count(q.counts[kind])}</strong></div>`).join('')}<div><span>OLDEST INCOMPLETE</span><strong>${duration(q.oldest_incomplete_age_seconds)}</strong></div></div>${q.latest_error ? `<div class="source-error">Latest recorded error: ${e(q.latest_error.class)} at ${when(q.latest_error.updated_at)}</div>` : ''}` : sourceError(pg) || empty('Connecting to queue observation.'))}${section('OLDEST INCOMPLETE JOBS', state.jobs ? (state.jobs.items.length ? `<div class="job-list">${state.jobs.items.map(job=>`<div><span class="mono">${e(job.entity_uuid)}</span><span class="badge ${job.state==='processing'?'warn':''}">${e(job.state)}</span><small>Attempts ${job.attempts} · Enqueued ${when(job.created_at)}${job.error_class ? ` · ${e(job.error_class)}` : ''}</small></div>`).join('')}</div>` : empty('No incomplete jobs were returned.')) : error('jobs') || empty('Connecting to durable jobs.'))}`;
}
function storage() {
  return `<div class="source-grid full-width">${sourceCard('postgres','PostgreSQL',d=>`${count(d.activity.event_count)} captured events`,d=>`Latest event ${when(d.activity.latest_event_at)}`)}${sourceCard('qdrant','Qdrant',d=>`${count(d.points)} indexed points`,d=>`Collection ${d.collection}`)}</div>`;
}
function models() {
  const o = source('ollama'); const w = source('worker');
  return `<div class="source-grid full-width">${sourceCard('ollama','Configured embedding model',d=>d.configured_embedding_model,d=>d.loaded ? 'Observed in Ollama /api/ps' : 'Absent from Ollama /api/ps')}${sourceCard('worker','Embedding worker',d=>d.state,d=>`Observed unit ${d.unit}`)}</div>${section('MODEL OBSERVATION', o?.state === 'ok' ? `<p>Ollama answered the model residency probe at ${when(o.observed_at)}. Residency is not a claim that an inference request succeeded.</p>` : sourceError(o) || empty('Connecting to model observation.'))}`;
}
function audit() {
  const latest = source('postgres')?.data?.latest_review;
  return `${section('LATEST PERSISTED REVIEW', latest ? `<div class="audit-banner"><strong>${e(latest.status)}</strong><span>${when(latest.created_at)}</span></div><div class="hash">Review ID ${e(latest.id)}</div>` : source('postgres')?.state === 'ok' ? empty('No persisted review was returned.') : sourceError(source('postgres')) || empty('Connecting to review observation.'))}${section('RECENT REVIEWS', state.reviews ? (state.reviews.items.length ? `<div class="job-list">${state.reviews.items.map(r=>`<div><span class="mono">${e(r.id)}</span><span class="badge">${e(r.status)}</span><small>${when(r.created_at)} · ${e(r.stream_id)}${r.coverage ? ` · sequences ${e(r.coverage.first_sequence)}–${e(r.coverage.last_sequence)}` : ''}</small></div>`).join('')}</div>` : empty('No persisted reviews were returned.')) : error('reviews') || empty('Connecting to persisted reviews.'))}`;
}
const screens = {Overview: overview, Pipelines: pipelines, Traffic: traffic, Queues: queues, Storage: storage, Models: models, Audit: audit};
const logSources = [
  ['concierge', 'Concierge'], ['qdrant', 'Qdrant'], ['worker', 'Embedding worker'],
  ['gpu_recovery', 'GPU recovery'], ['ollama', 'Ollama'],
];
const initialLogSource = new URLSearchParams(location.search).get('logs');
if (logSources.some(([id]) => id === initialLogSource)) {
  state.logSource = initialLogSource;
  state.logOpen = true;
}
function diagnosticPanel() {
  const entries = state.logs?.items || [];
  return `<section class="diagnostic-panel ${state.logOpen ? 'expanded' : ''}" aria-label="Diagnostics and assistant">
    <div class="diagnostic-bar"><button id="toggle-diagnostics" aria-expanded="${state.logOpen}">▤ Diagnostics ${state.logOpen ? '⌄' : '⌃'}</button><span>${state.logs ? `${e(state.logs.unit)} · ${entries.length} recorded lines · ${when(state.logs.observed_at)}` : 'Select a log source'}</span>${state.logError ? `<strong>${e(state.logError)}</strong>` : ''}</div>
    ${state.logOpen ? `<div class="diagnostic-body"><div class="log-side"><div class="log-tabs" role="tablist">${logSources.map(([id,label])=>`<button role="tab" aria-selected="${state.logSource===id}" data-log-source="${id}" class="${state.logSource===id?'active':''}">${label}</button>`).join('')}</div><div class="log-tools"><input id="log-search" aria-label="Search log lines" value="${e(state.logQuery)}" placeholder="Search recorded lines"><label>Seek time <input id="log-seek" type="datetime-local" value="${e(state.logAt)}"></label><button id="log-follow" class="ghost">${state.logFollow ? 'Following' : 'Follow new'}</button><button id="log-refresh" class="ghost">Refresh</button></div>${state.explanation ? `<div class="log-explanation"><strong>Likely sequence · GLM inference</strong><p>${e(state.explanation)}</p></div>` : ''}<div class="log-list" id="log-list">${state.logError ? `<div class="source-error">${e(state.logError)}</div>` : ''}${entries.length ? entries.map((entry,index)=>`<div class="log-entry ${entry.highlight?'important':''}" data-log-id="${e(entry.id)}"><span class="log-index">${index+1}</span><time>${when(entry.at)}</time><span class="log-message">${e(entry.message)}</span>${entry.truncated?'<small>Entry clipped at 4,000 characters</small>':''}</div>`).join('') : empty('No recorded lines in this interval.')}</div>${state.logs?.gap ? `<div class="source-error">More entries exist beyond this page. Refresh from the current cursor to continue.</div>` : ''}</div><div class="assistant-side"><div class="assistant-title"><span class="eyebrow">GLM-5.3-FLASH / DASHBOARD ASSISTANT</span><span>DOM read + write</span></div><div class="chat-messages">${state.chat.map(item=>`<div class="chat-message ${item.role}"><b>${item.role==='user'?'You':'GLM'}</b><p>${e(item.text)}</p></div>`).join('')}${state.chatBusy ? `<div class="chat-message assistant">Working with current dashboard DOM and selected logs…</div>` : ''}</div><form id="assistant-form"><textarea id="assistant-input" aria-label="Ask the dashboard assistant" placeholder="Ask about the selected logs, or direct the assistant to navigate and change this dashboard">${e(state.chatDraft)}</textarea><button class="ghost" ${state.chatBusy?'disabled':''}>Send</button></form></div></div>` : ''}
  </section>`;
}
async function loadLogs({at=null, cursor=null}={}) {
  const params = new URLSearchParams({source:state.logSource,limit:'100'});
  if (at) params.set('at',at);
  if (cursor) params.set('cursor',cursor);
  if (state.logQuery) params.set('q',state.logQuery);
  try {
    const response = await fetch(`${API}/observability/logs?${params}`, {cache:'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const page = await response.json();
    state.logs = cursor && state.logs ? {...page,items:[...state.logs.items,...page.items].slice(-200)} : page;
    state.logError = '';
  } catch (err) {state.logError = err.name === 'TypeError' ? 'Log request failed' : err.message;}
  render();
}
function executeDomActions(actions, record=true) {
  for (const action of actions) {
    if (!action || typeof action.selector !== 'string') continue;
    let node;
    try {node = root.querySelector(action.selector);} catch {continue;}
    if (!node) continue;
    const value = String(action.value ?? '');
    const operation = action.op || action.type;
    if (record && operation !== 'click') state.domPatches.push({...action,op:operation});
    if (operation === 'click') node.click();
    else if (operation === 'set_value' && 'value' in node) {node.value=value;if(record){node.dispatchEvent(new Event('input',{bubbles:true}));node.dispatchEvent(new Event('change',{bubbles:true}));}}
    else if (operation === 'set_text') node.textContent=value;
    else if (operation === 'set_html') node.innerHTML=value;
    else if (operation === 'append_html') node.insertAdjacentHTML('beforeend',value);
    else if (operation === 'add_class') node.classList.add(value);
    else if (operation === 'remove_class') node.classList.remove(value);
    else if (operation === 'remove') node.remove();
  }
}
async function askAssistant(message,{diagnostic=false}={}) {
  if (state.chatBusy) return;
  state.chatBusy=true;
  if (!diagnostic) state.chat.push({role:'user',text:message});
  render();
  try {
    const recorded=state.logs?.items || [];
    const relevant=new Set();
    if(diagnostic){for(let i=0;i<recorded.length;i++)if(recorded[i].highlight)for(let j=Math.max(0,i-2);j<=i;j++)relevant.add(j);}
    const logEntries=diagnostic ? (relevant.size ? [...relevant].sort((a,b)=>a-b).slice(-12).map(i=>recorded[i]) : recorded.slice(-12)) : recorded;
    const currentDom=diagnostic ? root.querySelector('.page-intro').outerHTML : root.innerHTML;
    const response=await fetch(`${API}/observability/assistant`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,dom:currentDom,log_source:state.logSource,log_entries:logEntries})});
    if (!response.ok) throw new Error(`Assistant HTTP ${response.status}`);
    const answer=await response.json();
    if (diagnostic) state.explanation=answer.reply;
    else state.chat.push({role:'assistant',text:answer.reply});
    state.chatBusy=false;
    render();
    if (Array.isArray(answer.citations)) state.citations=answer.citations.filter(id=>typeof id==='string' && state.logs?.items.some(entry=>entry.id===id));
    for (const item of root.querySelectorAll('[data-log-id]')) if (state.citations.includes(item.dataset.logId)) item.classList.add('cited');
    executeDomActions(answer.actions || []);
  } catch(err) {
    state.chatBusy=false;
    const message=err.message || 'Assistant request failed';
    if (diagnostic) state.explanation=`Analysis failed: ${message}`;
    else state.chat.push({role:'assistant',text:message});
    render();
  }
}
async function inspectFailedProbe() {
  const failed=Object.entries(state.snapshot?.sources || {}).find(([,value])=>value.state==='unavailable');
  if (!failed) {state.analyzedFailure='';return;}
  const [sourceName, observation]=failed;
  const key=`${sourceName}:${observation.error_class}`;
  if (state.analyzedFailure===key) return;
  state.analyzedFailure=key;
  state.logOpen=true;
  state.logSource=sourceName==='postgres'?'concierge':sourceName;
  if (!logSources.some(([id])=>id===state.logSource)) state.logSource='concierge';
  state.logFollow=false;
  await loadLogs({at:observation.observed_at});
  if (state.logs?.items?.length) await askAssistant(`A ${sourceName} probe failed with ${observation.error_class} at ${observation.observed_at}. In up to four short sentences, give the most likely sequence using only these recorded log entries, cite their exact cursor IDs, and distinguish inference from observation. If the fragment cannot establish a cause, say so.`,{diagnostic:true});
}
function render() {
  root.innerHTML = `<div class="shell"><aside class="sidebar"><div class="brand"><div class="brand-mark"><span></span><span></span><span></span></div><div><strong>KSTORE</strong><small>HABITAT / CONTROL</small></div></div><nav aria-label="Primary">${names.map(name=>`<button data-screen="${name}" class="${state.screen===name?'active':''}"><span class="nav-icon">${({Overview:'◫',Pipelines:'⌁',Traffic:'⇄',Queues:'≋',Storage:'▤',Models:'⬡',Audit:'◇'})[name]}</span>${name}</button>`).join('')}</nav><div class="side-bottom"><div class="side-rail"><i class="dot ${source('postgres')?.state==='ok'?'mint':'amber'}"></i><div><strong>${source('postgres')?.state==='ok'?'PostgreSQL observed':'Source observation pending'}</strong><small>${state.snapshot ? when(state.snapshot.generated_at) : ''}</small></div></div></div></aside><main class="main"><header class="topbar"><div class="breadcrumbs">KSTORE <span>/</span> HABITAT <span>/</span> <strong>${state.screen.toUpperCase()}</strong></div><div class="top-actions"><span class="live-chip"><i class="dot ${state.errors.snapshot?'amber':'mint'}"></i>${state.snapshot ? `OBSERVED ${when(state.snapshot.generated_at)}` : 'CONNECTING'}</span></div></header><div class="content"><div class="page-intro"><div><div class="eyebrow intro-overline">KSTORE OBSERVABILITY</div><h1>${state.screen==='Traffic'?'Captured activity':state.screen==='Queues'?'Durable queue':state.screen==='Pipelines'?'Observed host':state.screen==='Audit'?'Review history':state.screen==='Models'?'Model and worker':state.screen==='Storage'?'Storage sources':'Habitat overview'}</h1></div><button class="ghost" id="refresh">Refresh observations</button></div>${error('snapshot')}${screens[state.screen]()}</div><footer>KStore Habitat · read-only observations from ${e(API)}</footer></main></div>${diagnosticPanel()}`;
  root.querySelectorAll('[data-screen]').forEach(button=>button.onclick=()=>{state.screen=button.dataset.screen;history.replaceState(null,'',`?screen=${encodeURIComponent(state.screen)}`);render();});
  root.querySelectorAll('[data-event]').forEach(button=>button.onclick=()=>{state.selected=button.dataset.event;state.screen='Traffic';render();});
  root.querySelector('#refresh').onclick=refresh;
  root.querySelector('#toggle-diagnostics').onclick=()=>{state.logOpen=!state.logOpen;render();if(state.logOpen&&!state.logs)loadLogs();};
  root.querySelectorAll('[data-log-source]').forEach(button=>button.onclick=()=>{state.logSource=button.dataset.logSource;state.logs=null;state.logAt='';state.explanation='';state.logFollow=true;render();loadLogs();});
  const logSearch=root.querySelector('#log-search');
  if(logSearch) {logSearch.oninput=ev=>{state.logQuery=ev.target.value;};logSearch.onchange=ev=>{state.logs=null;loadLogs({at:state.logAt ? new Date(state.logAt).toISOString() : null});};}
  const logSeek=root.querySelector('#log-seek');
  if(logSeek) {logSeek.oninput=ev=>{state.logAt=ev.target.value;};logSeek.onchange=ev=>{state.logFollow=false;state.logs=null;loadLogs({at:state.logAt ? new Date(state.logAt).toISOString() : null});};}
  const logFollow=root.querySelector('#log-follow');
  if(logFollow) logFollow.onclick=()=>{state.logFollow=true;state.logAt='';state.logs=null;loadLogs();};
  const logRefresh=root.querySelector('#log-refresh');
  if(logRefresh) logRefresh.onclick=()=>loadLogs({at:state.logAt ? new Date(state.logAt).toISOString() : null});
  const assistantForm=root.querySelector('#assistant-form');
  if(assistantForm) assistantForm.onsubmit=ev=>{ev.preventDefault();const input=root.querySelector('#assistant-input');const message=input.value.trim();if(message){state.chatDraft='';askAssistant(message);}};
  const assistantInput=root.querySelector('#assistant-input');
  if(assistantInput) assistantInput.oninput=ev=>{state.chatDraft=ev.target.value;};
  const query=root.querySelector('#event-query');
  if(query) query.oninput=ev=>{const pos=ev.target.selectionStart;state.query=ev.target.value;render();const next=root.querySelector('#event-query');next.focus();next.setSelectionRange(pos,pos);};
  const older=root.querySelector('#events-older');
  if(older) older.onclick=loadOlderEvents;
  if(state.domPatches.length) executeDomActions(state.domPatches,false);
  for (const item of root.querySelectorAll('[data-log-id]')) if (state.citations.includes(item.dataset.logId)) item.classList.add('cited');
}
async function fetchJSON(key,path){
  state.lastFetch[key]=new Date().toISOString();
  try {const response=await fetch(API+path,{cache:'no-store'});if(!response.ok)throw new Error(`HTTP ${response.status}`);state[key]=await response.json();delete state.errors[key];}
  catch(err){state[key]=null;state.errors[key]=err.name==='TypeError'?'Network request failed':err.message;}
}
async function loadOlderEvents(){
  if(state.eventsBusy || !state.events?.next_cursor) return;
  state.eventsBusy=true;
  const cursor=state.events.next_cursor;
  render();
  try {
    const response=await fetch(`${API}/observability/events?limit=80&before=${encodeURIComponent(cursor)}`,{cache:'no-store'});
    if(!response.ok) throw new Error(`HTTP ${response.status}`);
    const page=await response.json();
    state.events={...page,items:[...state.events.items,...page.items]};
    delete state.errors.events;
  } catch(err) {state.errors.events=err.message || 'Older event request failed';}
  state.eventsBusy=false;
  render();
}
async function refresh(){await Promise.all([fetchJSON('snapshot','/observability/snapshot'),fetchJSON('events','/observability/events?limit=80'),fetchJSON('jobs','/observability/jobs?limit=50'),fetchJSON('reviews','/observability/reviews?limit=30')]);state.loading=false;render();await inspectFailedProbe();}
render();refresh();if(state.logOpen)loadLogs();setInterval(refresh,15000);setInterval(()=>{if(state.logOpen&&state.logFollow&&state.logs?.next_cursor)loadLogs({cursor:state.logs.next_cursor});},5000);
