import React from 'react';
import {array,dayLabel} from './personalApi';

const statusLabel = {pending:'Aguardando decisão',accepted:'Aceita',rejected:'Rejeitada',stale:'Dados alterados',active:'Ativo',provisional:'Provisório',superseded:'Substituído',paused:'Pausado',completed:'Concluído',archived:'Arquivado'};
export default function Timeline({state={},day,compact=false}) {
  const events = [
    ...array(state.decisions).map(row=>({...row,kind:'decision',date:row.day || row.date || row.created_at,label:'Decisão registrada',detail:row.reason || row.decision})),
    ...array(state.plans).map(row=>({...row,kind:'plan',date:row.effective_from || row.created_at,label:`Plano · versão ${row.version || 1}`,detail:row.reason || (row.target_kcal != null ? `${row.target_kcal} kcal por dia` : 'Plano registrado')})),
    ...array(state.checkins).map(row=>({...row,kind:'checkin',label:'Check-in pessoal',detail:row.notes || 'Percepção e contexto registrados'})),
    ...array(state.measurements).map(row=>({...row,kind:'measurement',label:'Medida corporal',detail:row.weight_kg != null ? `${row.weight_kg} kg · ${row.method || 'método não informado'}` : row.method || 'Medidas registradas'})),
  ].filter(row=>row.date && (!day || row.date.slice(0,10)<=day)).sort((a,b)=>String(b.date).localeCompare(String(a.date))).slice(0,compact?8:20);
  return <section className="panel"><div className="panel-heading"><div><h2>História e decisões</h2><p>Referências datadas para entender como seu contexto evoluiu.</p></div></div>{events.length ? <ol className="personal-timeline">{events.map((row,index)=><li key={`${row.kind}-${row.id || index}`}><span className={'timeline-dot '+row.kind}/><div><span className="eyebrow">{dayLabel(row.date)}</span><strong>{row.label}</strong><p>{row.detail}</p>{row.status && <span className={'tag '+row.status}>{statusLabel[row.status] || row.status}</span>}</div></li>)}</ol> : <p className="empty">Seus registros e decisões aparecerão aqui.</p>}</section>;
}
