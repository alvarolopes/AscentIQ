import React, {useCallback, useEffect, useRef, useState} from 'react';
import {array,dayLabel,ErrorNotice,PageHeading,personalApi,StatusNotice,today} from './personalApi';
import {PagedList} from './ui';

const newId = () => crypto.randomUUID();

export default function Assistant({compact=false, day:initialDay=today()}) {
  const [day,setDay] = useState(initialDay), [period,setPeriod] = useState('day'), [days,setDays] = useState(14);
  const [start,setStart] = useState(initialDay), [end,setEnd] = useState(initialDay), [includeMedical,setIncludeMedical] = useState(false);
  const [question,setQuestion] = useState(''), [manual,setManual] = useState(''), [manualFingerprint,setManualFingerprint] = useState(null);
  const [context,setContext] = useState(null), [loading,setLoading] = useState(true), [busy,setBusy] = useState(false);
  const [conversationLoading,setConversationLoading] = useState(true);
  const [error,setError] = useState(''), [message,setMessage] = useState(''), [conversation,setConversation] = useState(newId);
  const [records,setRecords] = useState([]), [pagination,setPagination] = useState({page:1,page_size:10,pages:1,total:0});
  const [past,setPast] = useState([]), [pastPagination,setPastPagination] = useState({page:1,page_size:10,pages:1,total:0});
  const [showPast,setShowPast] = useState(false), [refresh,setRefresh] = useState(0);
  const sequence = useRef(0), historySequence = useRef(0), references = useRef([]), sending = useRef(false);
  useEffect(()=>{setDay(initialDay);},[initialDay]);
  const scope = useCallback(()=>({day,period,days,include_medical:includeMedical,...(period==='custom'?{start,end}:{})}),[day,period,days,includeMedical,start,end]);
  const fetchContext = useCallback(()=>personalApi('assistant/context?'+new URLSearchParams(scope())),[scope]);

  useEffect(()=>{
    const version=++sequence.current;
    setLoading(true);setContext(null);setError('');
    fetchContext().then(value=>{if(version===sequence.current)setContext(value);})
      .catch(e=>{if(version===sequence.current)setError(e.message);})
      .finally(()=>{if(version===sequence.current)setLoading(false);});
    return()=>{sequence.current++;};
  },[fetchContext,refresh]);

  const loadConversation = useCallback(async(page=1,pageSize=10)=>{
    const version=++historySequence.current;
    const response=await personalApi('assistant/history?'+new URLSearchParams({conversation_id:conversation,page,page_size:pageSize}));
    if(version!==historySequence.current)return;
    const rows=array(response.history);
    setRecords(rows);setPagination(response.pagination);
    if(response.pagination.page===1)references.current=rows.slice(0,3).reverse().map(row=>row.id);
  },[conversation]);
  useEffect(()=>{let active=true;references.current=[];setRecords([]);setConversationLoading(true);loadConversation().catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setConversationLoading(false);});return()=>{active=false;historySequence.current++;};},[loadConversation]);

  async function loadPast(page=1,pageSize=10) {
    try {const response=await personalApi(`assistant/history?page=${page}&page_size=${pageSize}`);setPast(array(response.history));setPastPagination(response.pagination);}
    catch(e){setError(e.message);}
  }
  async function send(imported=false) {
    if(sending.current)return;
    sending.current=true;setBusy(true);setError('');setMessage('');
    const text=question.trim();
    const requestScope=scope(), requestConversation=conversation, contextVersion=sequence.current;
    try {
      // Imported answers retain the fingerprint of the context actually reviewed.
      const fresh=await personalApi('assistant/context?'+new URLSearchParams(requestScope));
      if(contextVersion===sequence.current)setContext(fresh);
      const previous=await personalApi('assistant/history?'+new URLSearchParams({conversation_id:requestConversation,page:1,page_size:10}));
      references.current=array(previous.history).slice(0,3).reverse().map(row=>row.id);
      const fingerprint=imported?(manualFingerprint || context?.fingerprint):fresh.fingerprint;
      const value=await personalApi('assistant',{...requestScope,question:text,conversation_id:requestConversation,
        message_ids:references.current,fingerprint,...(imported?{manual_response:manual.trim()}:{})});
      references.current=[...references.current,value.id].slice(-3);
      setQuestion('');setManual('');setManualFingerprint(null);
      setMessage(value.withheld_medical_turns?'Respostas anteriores com dados médicos não foram reenviadas sem a autorização atual.':value.cached?'Resposta recuperada para esta conversa.':'Resposta salva. Seu plano e seus registros permanecem sob seu controle.');
      await loadConversation(1,pagination.page_size);
      if(showPast)await loadPast(1,pastPagination.page_size);
    } catch(e) {
      setError(e.message);
      if(e.status===409)setRefresh(v=>v+1);
    } finally {sending.current=false;setBusy(false);}
  }
  const prompt=(question?'PERGUNTA: '+question+'\n\n':'')+(context?.prompt || '');
  async function copy() {
    try {await navigator.clipboard.writeText(prompt);setManualFingerprint(context.fingerprint);setMessage('Pergunta e contexto copiados.');}
    catch{setError('Selecione o texto do contexto e copie manualmente.');}
  }
  function beginConversation() {references.current=[];setConversationLoading(true);setConversation(newId());setMessage('Nova conversa iniciada. Seu rascunho foi mantido.');}
  const chosen=context?.context?.period;
  const selected=context?.context?.selection;
  const turn = row => <article className="assistant-message" key={row.id}>
    <div className="assistant-meta"><span>{dayLabel(row.date || row.created_at)}</span><span>{row.source==='imported'?'Resposta importada':row.model}</span></div>
    <h3>{row.question}</h3><div className="daily-report">{row.text || 'Resposta indisponível.'}</div>
  </article>;
  return <div className={'assistant-content'+(compact?' compact':'')}>
    {!compact&&<PageHeading kicker="ASSISTENTE" title="Converse com seu contexto.">Consulte seus registros e continue a conversa sem alterar automaticamente seu plano.</PageHeading>}
    <ErrorNotice error={error}/><StatusNotice message={message}/>
    <div className="filters assistant-scope">
      <label>Contexto<select value={period} disabled={busy} onChange={e=>setPeriod(e.target.value)}>
        <option value="day">Dia</option><option value="month">Mês</option><option value="goals">Objetivos</option><option value="days">Últimos dias</option><option value="custom">Período definido</option>
      </select></label>
      {period==='custom'?<><label>De<input type="date" value={start} disabled={busy} onChange={e=>setStart(e.target.value)}/></label><label>Até<input type="date" value={end} disabled={busy} onChange={e=>setEnd(e.target.value)}/></label></>:<label>{period==='month'?'Mês de referência':'Data'}<input type="date" value={day} disabled={busy} onChange={e=>setDay(e.target.value)}/></label>}
      {period==='days'&&<label>Período<select value={days} disabled={busy} onChange={e=>setDays(Number(e.target.value))}><option value="7">7 dias</option><option value="14">14 dias</option><option value="30">30 dias</option></select></label>}
    </div>
    {loading?<p className="small muted" role="status">Reunindo os registros…</p>:chosen&&<p className="small muted">{dayLabel(chosen.from)} a {dayLabel(chosen.to)} · Os dados são atualizados antes de cada pergunta.</p>}
    <label className="question-label">Sua pergunta<textarea rows={compact?3:4} maxLength="5000" value={question} disabled={busy} onChange={e=>setQuestion(e.target.value)} placeholder="Ex.: como minha alimentação deste mês se relaciona com meu objetivo?"/></label>
    <div className="report-actions"><button className="primary" disabled={busy || loading || conversationLoading || !context || question.trim().length<3 || context.configured===false} onClick={()=>send()}>{busy?'Preparando resposta…':conversationLoading?'Reunindo a conversa…':'Perguntar à IA'}</button><button disabled={busy} onClick={beginConversation}>Nova conversa</button></div>
    {context?.configured===false&&<p className="notice">Configure a IA em Dados e fontes ou copie o contexto e importe uma resposta.</p>}
    <details className="method"><summary>Contexto e opções</summary>
      <p className="small muted">Seu perfil, objetivos, plano, alimentação, treinos, carga, sono e check-ins entram quando disponíveis. A conversa considera trechos de até três respostas recentes. Força inclui nomes dos exercícios e totais, sem todas as séries. Dados médicos e documentos só entram com a autorização abaixo.</p>
      <label className="checkbox-label"><input type="checkbox" disabled={busy} checked={includeMedical} onChange={e=>setIncludeMedical(e.target.checked)}/>Incluir referências médicas e documentos registrados</label>
      {selected&&<p className="small muted">Resumos cobrem todo o período. Detalhes selecionados: {selected.meal_details_included}/{selected.meal_detail_count} refeições, {selected.activities_included}/{selected.activity_count} atividades, {selected.strength_included}/{selected.strength_count} sessões de força, {selected.goals_included}/{selected.goal_count} objetivos e {selected.plans_included}/{selected.plan_count} planos. {selected.primary_goal_always_included&&'O objetivo principal foi preservado. '}{!selected.all_daily_totals_included&&'As séries diárias foram resumidas para caber no modelo; os totais do período foram preservados. '}Para um detalhe antigo, selecione sua data.</p>}
      <div className="report-actions"><button disabled={busy || loading} onClick={()=>setRefresh(v=>v+1)}>Atualizar contexto</button><button disabled={!context || busy} onClick={copy}>Copiar contexto</button></div>
      <details className="method"><summary>Ver dados enviados</summary><textarea className="daily-textarea" readOnly aria-label="Contexto do assistente" rows="8" value={prompt}/></details>
      <details className="method"><summary>Importar resposta de outra IA</summary><p className="small muted">Use a pergunta e o contexto copiados. Se os dados mudarem, uma nova revisão será necessária.</p><textarea aria-label="Resposta de outra IA" rows="4" maxLength="30000" value={manual} disabled={busy} onChange={e=>{setManual(e.target.value);if(!manualFingerprint)setManualFingerprint(context?.fingerprint);}}/><button disabled={busy || loading || conversationLoading || !context || question.trim().length<3 || manual.trim().length<20} onClick={()=>send(true)}>Salvar resposta importada</button></details>
    </details>
    <section className="assistant-conversation" aria-label="Conversa atual" aria-live="polite">
      <h2>Conversa atual</h2><PagedList items={records} pagination={pagination} onPageChange={page=>loadConversation(page,pagination.page_size).catch(e=>setError(e.message))} onPageSizeChange={size=>loadConversation(1,size).catch(e=>setError(e.message))} label="respostas" empty="Sua primeira pergunta inicia a conversa.">{rows=>rows.map(turn)}</PagedList>
    </section>
    <details className="method" onToggle={e=>{setShowPast(e.currentTarget.open);if(e.currentTarget.open)loadPast();}}><summary>Conversas anteriores</summary>
      <PagedList items={past} pagination={pastPagination} onPageChange={page=>loadPast(page,pastPagination.page_size)} onPageSizeChange={size=>loadPast(1,size)} label="respostas anteriores" empty="Nenhuma conversa anterior.">{rows=>rows.map(row=><div key={row.id}>{turn(row)}<button disabled={busy} onClick={()=>{setQuestion(existing=>existing || row.question || '');if(row.conversation_id && row.conversation_id!==conversation){setConversationLoading(true);setConversation(row.conversation_id);}setMessage('Conversa selecionada. Seu rascunho foi mantido; o contexto será atualizado antes da próxima pergunta.');}}>Continuar esta conversa</button></div>)}</PagedList>
    </details>
  </div>;
}
