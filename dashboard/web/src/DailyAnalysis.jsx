import React, { useEffect, useRef, useState } from 'react';
import SleepContext from './SleepContext';

const labels = {running:'Corrida', strength:'Força', cycling:'Bike', swimming:'Natação', other:'Outros'};
async function request(day, body) {
  const response = await fetch(`/api/daily-analysis/${day}`, {
    credentials:'same-origin', cache:'no-store',
    ...(body ? {method:'POST', headers:{'Content-Type':'application/json','X-AscentIQ-Request':'1'}, body:JSON.stringify(body)} : {})
  });
  const result = await response.json().catch(()=>({}));
  if (!response.ok) throw new Error(result.detail && typeof result.detail === 'string' ? result.detail : 'Não foi possível consultar a análise. Verifique o acesso e tente novamente.');
  return result;
}
export default function DailyAnalysis({data}) {
  const dates = [...new Set([...data.activities,...data.strength].map(r=>r.date).filter(Boolean))].sort().reverse();
  const [day,setDay] = useState(dates[0] || new Date().toLocaleDateString('en-CA'));
  const [result,setResult] = useState(null), [loading,setLoading] = useState(false), [busy,setBusy] = useState(false);
  const [error,setError] = useState(''), [manual,setManual] = useState(''), [copied,setCopied] = useState(false);
  const sequence = useRef(0);
  async function load() {
    const version = ++sequence.current;
    setLoading(true); setResult(null); setError(''); setManual(''); setCopied(false);
    if (!day) {setLoading(false); return;}
    try { const value = await request(day); if (version === sequence.current) setResult(value); }
    catch(e) {if(version === sequence.current)setError(e.message);}
    finally {if(version === sequence.current)setLoading(false);}
  }
  useEffect(()=>{load(); return ()=>{sequence.current++;};},[day]);
  async function generate(imported = false) {
    setBusy(true); setError('');
    const version = sequence.current;
    try {
      const report = await request(day,{fingerprint:result.fingerprint,...(imported ? {text:manual} : {})});
      if(version === sequence.current) {setResult(previous=>({...previous,report,stale:false}));setManual('');}
    } catch(e) {if(version === sequence.current)setError(e.message);}
    finally {setBusy(false);}
  }
  async function copy() {
    try {await navigator.clipboard.writeText(result.prompt);setCopied(true);}
    catch {setError('Não foi possível copiar automaticamente. Selecione o texto do prompt abaixo e copie.');}
  }
  return <>
    <div className="page-title"><div className="eyebrow">TREINOS / EFEITOS / RECUPERAÇÃO</div><h1>O que o treino do dia estimula?</h1><p>Corrida, força e outras atividades em uma análise conjunta, com contexto da carga recente.</p></div>
    <section className="panel">
      <div className="panel-heading"><div><h2>Análise diária por IA</h2><p>Escolha a data para reunir os registros e preparar o prompt.</p></div></div>
      <div className="filters"><label>Dia do treino<input type="date" value={day} disabled={busy} onChange={e=>setDay(e.target.value)}/></label><button disabled={busy || loading || !day} onClick={load}>Consultar novamente</button></div>
      {error && <div className="error" role="alert">{error}</div>}
      {loading && <p role="status">Reunindo os treinos…</p>}
      {result && <>
        <p><strong>{result.context.session_count} sessões</strong> · {result.context.activities.map(a=>labels[a.kind] || a.type || 'Outros').concat(result.context.strength.map(()=>'Força')).join(' · ') || 'Sem treinos registrados'}</p>
        <div className="daily-sessions">{result.context.activities.map((a,i)=><div className="notice" key={'a'+i}><strong>{a.name || labels[a.kind] || 'Atividade'}</strong><p>{a.elapsed_time || 'Duração indisponível'}{a.distance_km != null ? ` · ${a.distance_km} km` : ''}{a.avg_hr != null ? ` · FC média ${a.avg_hr} bpm` : ''}</p></div>)}{result.context.strength.map((s,i)=><div className="notice" key={'s'+i}><strong>{s.title}</strong><p>{s.working_sets ?? 'Sem dado de'} séries de trabalho · {s.volume_kg ?? 'Sem dado de'} kg de volume</p><p>{s.exercises.map(e=>e.name).filter(Boolean).join(' · ') || 'Detalhes de exercícios indisponíveis'}</p></div>)}</div>
        {!result.context.session_count && <div className="empty">Não há registros nessa data. Escolha outro dia ou atualize seus treinos.</div>}
        <SleepContext sleep={result.context.sleep}/>
        <p className="small muted">Ao gerar, os registros de treino, sono e carga exibidos no prompt são enviados à OpenAI. O período termina no dia selecionado; referências anteriores de sono aparecem com suas datas. Exames e medidas corporais não fazem parte deste envio.</p>
        {!result.configured && <div className="notice">Geração automática ainda não configurada. Você já pode copiar o prompt, pedir a análise no ChatGPT ou em outra IA e importar a resposta abaixo.</div>}
        <div className="report-actions"><button className="primary" disabled={busy || !result.configured || !result.context.session_count} onClick={()=>generate()}>{busy?'Salvando análise…':'Gerar análise com IA'}</button><button disabled={busy || !result.context.session_count} onClick={copy}>{copied?'Prompt copiado':'Copiar prompt'}</button></div>
        <details className="method"><summary>Ver prompt e dados enviados</summary><textarea className="daily-textarea" aria-label="Prompt da análise" readOnly value={result.prompt} rows={14}/></details>
        <details className="method"><summary>Importar resposta de uma IA</summary><p className="small muted">Cole a resposta produzida com o prompt desta data. Ela ficará identificada como resposta importada.</p><textarea className="daily-textarea" aria-label="Resposta da IA" rows={10} value={manual} disabled={busy} onChange={e=>setManual(e.target.value)} placeholder="Cole o relatório aqui…"/><button disabled={busy || manual.trim().length<20 || manual.length>30000 || !result.context.session_count} onClick={()=>generate(true)}>Salvar e exibir relatório</button></details>
      </>}
    </section>
    {result?.report && <section className="panel"><div className="panel-heading"><div><h2>Relatório do dia · {new Date(day+'T12:00:00').toLocaleDateString('pt-BR')}</h2><p>{result.report.model} · {new Date(result.report.generated_at).toLocaleString('pt-BR')}</p></div></div>{result.stale && <div className="notice">Os dados mudaram desde esta análise. Gere um novo relatório ou importe uma nova resposta com o prompt atualizado.</div>}<article className="daily-report">{result.report.text}</article><p className="small muted">Interpretação por IA: efeitos prováveis, não ganhos medidos nem avaliação médica.</p></section>}
  </>;
}
