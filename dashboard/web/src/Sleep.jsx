import React, {useState} from 'react';
import {PagedList} from './ui';
import {sleepDays, sleepAverage, sleepDuration} from './sleepView';

const dayLabel = day => new Date(day+'T12:00:00Z').toLocaleDateString('pt-BR',{timeZone:'UTC'});
const before = (day, days) => { const value=new Date(day+'T12:00:00Z'); value.setUTCDate(value.getUTCDate()-days); return value.toISOString().slice(0,10); };
const number = value => value == null ? 'Sem dado' : Number(value).toLocaleString('pt-BR',{maximumFractionDigits:1});

export default function Sleep({data, Chart, Card, Panel}) {
  const records = data.sleep?.daily || [];
  const end = data.as_of;
  const earliest = records[0]?.date || end;
  const [from,setFrom] = useState(before(end,29)), [to,setTo] = useState(end);
  const invalid = !from || !to || from > to || from < '2000-01-01' || to > end;
  const rows = invalid ? [] : sleepDays(records,from,to);
  const duration = sleepAverage(rows,'duration_minutes'), score = sleepAverage(rows,'score');
  const recorded = rows.filter(row=>row.recorded).length;

  function period(days) {setFrom(days ? before(end,days-1) : earliest);setTo(end);}
  return <>

    <Panel title="Sleep" sub="Período histórico">
      <div className="report-actions">{[7,30,90].map(days=><button key={days} onClick={()=>period(days)}>{days} dias</button>)}<button onClick={()=>period(null)}>Todo o histórico</button></div>
      <div className="filters"><label>De<input type="date" min="2000-01-01" max={end} value={from} onChange={e=>{setFrom(e.target.value);}}/></label><label>Até<input type="date" min="2000-01-01" max={end} value={to} onChange={e=>{setTo(e.target.value);}}/></label></div>
      {invalid && <p className="error" role="alert">Escolha um período válido, de 2000 até hoje, com a data inicial anterior ou igual à final.</p>}
      <p className="small muted">As datas são as atribuídas pelo Garmin. “Sem registro” indica ausência de dados na base, não uma noite sem dormir. Campos ausentes não entram nas médias.</p>
    </Panel>
    {!invalid && <>
      <div className="metrics four"><Card label="Duração média" value={sleepDuration(duration.value)} note={`${duration.count} de ${rows.length} dias com duração`}/><Card label="Pontuação média" value={number(score.value)} unit="/100" note={`${score.count} dias com pontuação`}/><Card label="Dias com registros" value={recorded} note={`${rows.length} dias no período`}/><Card label="Dias sem registro" value={rows.length-recorded} note="Ausência de dados, não de sono"/></div>
      <div className="split"><Panel title="Duração do sono" sub="Horas decimais · 7,5 h = 7h30. Lacunas não são interpoladas."><Chart points key={from+to+'duration'} rows={rows} keys={[{key:'hours',label:'Duração / horas',color:'#58a6ff'}]} height={240} title="Duração diária do sono em horas"/></Panel><Panel title="Pontuação do Garmin" sub="Exibida somente quando fornecida pelo Garmin."><Chart points key={from+to+'score'} rows={rows} keys={[{key:'score',label:'Pontuação / 100',color:'#bc8cff'}]} height={240} title="Pontuação diária do sono"/></Panel></div>
      <Panel title="Registros por dia" sub="Do mais recente ao mais antigo. Duração e pontuação são medidas distintas; nenhuma confirma recuperação sozinha.">
        <PagedList items={[...rows].reverse()} resetKey={from+to} label="registros de sono">{page=><div className="table-scroll"><table><thead><tr><th>Data</th><th>Duração</th><th>Pontuação /100</th><th>Qualidade</th><th>FC repouso / bpm</th><th>Recarga Body Battery</th><th>Respiração / min</th><th>HRV média / ms</th><th>Estado HRV</th></tr></thead><tbody>{page.map(row=><tr key={row.date}><td><strong>{dayLabel(row.date)}</strong>{!row.recorded && <span className="small muted block">Sem registro</span>}</td><td>{sleepDuration(row.duration_minutes)}</td><td>{number(row.score)}</td><td>{row.quality || 'Sem dado'}</td><td>{number(row.resting_hr)}</td><td>{number(row.body_battery)}</td><td>{number(row.respiration)}</td><td>{number(row.hrv_ms)}</td><td>{row.hrv_status || 'Sem dado'}</td></tr>)}</tbody></table></div>}</PagedList>
      </Panel>
    </>}
  </>;
}
