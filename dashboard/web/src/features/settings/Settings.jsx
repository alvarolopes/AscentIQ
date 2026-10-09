'use client';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { NativeSelect } from '@/components/ui/native-select';
import { Card } from '@/components/ui/card';
import { useCallback, useEffect, useRef, useState } from 'react';
import { PagedList } from '@/components/shared/ui';
import { newId } from '@/lib/ids';
import {
  array,
  dayLabel,
  ErrorNotice,
  format,
  notifyIntegrationChange,
  optionalNumber,
  PageHeading,
  personalApi,
  StatusNotice,
  today,
} from '@/lib/personalApi';

const stateLabel = {
  available: 'Disponível',
  configured: 'Configurada',
  connected: 'Conectada',
  completed: 'Atualizada',
  partial: 'Parcial',
  failed: 'Falhou',
  unconfigured: 'Não configurada',
  disconnected: 'Desconectada',
  unknown: 'Não verificada',
};
export default function Settings({ onJob, busy: jobBusy = false, onStateChange, initialDay = '' }) {
  const [value, setValue] = useState(null),
    [file, setFile] = useState(null),
    [fileFormat, setFileFormat] = useState('csv'),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(''),
    [message, setMessage] = useState(''),
    [result, setResult] = useState(null),
    [credentials, setCredentials] = useState({});
  const [manual, setManual] = useState({
    date: initialDay,
    type: 'running',
    name: '',
    duration_minutes: '',
    distance_km: '',
    avg_hr: '',
  });
  const manualId = useRef(null);
  const [attachments, setAttachments] = useState({
    include_documents: false,
    include_food_images: false,
    include_imports: false,
  });
  const operation = useRef(false),
    fileInput = useRef(null);
  const [initialManual, setInitialManual] = useState(JSON.stringify(manual));
  useEffect(() => {
    if (initialDay) return;
    const date = today();
    setInitialManual(
      JSON.stringify({
        date,
        type: 'running',
        name: '',
        duration_minutes: '',
        distance_km: '',
        avg_hr: '',
      }),
    );
    setManual((current) => ({ ...current, date: current.date || date }));
  }, [initialDay]);
  const dirty =
    Boolean(file) ||
    Object.values(credentials).some((fields) =>
      Object.values(fields || {}).some((value) => String(value).length > 0),
    ) ||
    JSON.stringify(manual) !== initialManual;
  useEffect(() => {
    onStateChange?.({ busy: busy || loading, dirty });
  }, [busy, loading, dirty, onStateChange]);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await personalApi('integrations');
      setValue(data);
      return data;
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [load]);
  const providers = array(value?.providers),
    importView = value?.imports || {};
  const imports = array(importView.imports),
    pending = array(importView.reconciliation).filter(
      (row) => !row.status || row.status === 'ambiguous',
    );
  const sourceRecords = [
    ...array(importView.records),
    ...array(importView.source_records),
    ...array(importView.legacy_candidates),
  ];
  const sourceRecord = (id) =>
    sourceRecords.find((record) => record.id === id) || { id, name: 'Registro da fonte' };
  async function run(action, notice, reload = true) {
    if (operation.current) return;
    operation.current = true;
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await action();
      if (reload) await load();
      notifyIntegrationChange();
      if (notice) setMessage(notice);
    } catch (e) {
      setError(e.message);
    } finally {
      operation.current = false;
      setBusy(false);
    }
  }
  async function importFile(event) {
    event.preventDefault();
    if (!file) return;
    await run(async () => {
      if (file.size > 12 * 1024 * 1024) throw new Error('Escolha um arquivo de até 12 MB.');
      let content;
      if (fileFormat === 'fit') {
        const bytes = new Uint8Array(await file.arrayBuffer());
        let binary = '';
        for (let i = 0; i < bytes.length; i += 16384)
          binary += String.fromCharCode(...bytes.subarray(i, i + 16384));
        content = btoa(binary);
      } else content = await file.text();
      setResult(await personalApi('import', { format: fileFormat, filename: file.name, content }));
      setFile(null);
      if (fileInput.current) fileInput.current.value = '';
    }, 'Arquivo processado. Confira o resultado e as correspondências.');
  }
  async function saveManual(event) {
    event.preventDefault();
    await run(async () => {
      await personalApi('import', {
        format: 'manual',
        filename: 'manual',
        content: JSON.stringify({
          id: manualId.current ?? (manualId.current = newId()),
          date: manual.date,
          type: manual.type,
          name: manual.name,
          duration_seconds:
            optionalNumber(manual.duration_minutes) == null
              ? null
              : Number(manual.duration_minutes) * 60,
          distance_km: optionalNumber(manual.distance_km),
          avg_hr: optionalNumber(manual.avg_hr),
        }),
      });
      const next = { ...manual, name: '', duration_minutes: '', distance_km: '', avg_hr: '' };
      setInitialManual(JSON.stringify(next));
      setManual(next);
      manualId.current = null;
    }, 'Atividade manual registrada.');
  }
  async function reconcile(row, action) {
    await run(
      () =>
        personalApi('import/reconcile', {
          record_id: row.record_id,
          action,
          other_id: row.other_id || null,
        }),
      'Correspondência revisada.',
    );
  }
  function activityLabel(id) {
    const row = sourceRecord(id);
    return (
      <>
        <strong>{row.name || row.title || 'Atividade'}</strong>
        <p>
          {dayLabel(row.date)} · {row.type || row.kind || 'Modalidade não informada'}
          {row.duration_seconds != null
            ? ' · ' + format(row.duration_seconds / 60, 0) + ' min'
            : ''}
        </p>
      </>
    );
  }
  const receipt = result?.import || {};
  return (
    <>
      <PageHeading kicker="FONTES / PORTABILIDADE" title="Dados e fontes">
        Conexões, importação e exportação dos seus registros.
      </PageHeading>
      <ErrorNotice error={error} />
      <StatusNotice message={message} />
      <fieldset className="food-fieldset" disabled={busy || loading}>
        <Card className="panel gap-0">
          <div className="panel-heading">
            <div>
              <h2>Plataformas e fontes</h2>
              <p>Configuração e última coleta são estados diferentes.</p>
            </div>
            <Button variant="outline" onClick={() => run(load, undefined, false)}>
              Consultar status
            </Button>
          </div>
          {loading && (
            <p className="muted" role="status">
              Consultando integrações…
            </p>
          )}
          <PagedList items={providers} label="Fontes">
            {(items) => (
              <div className="integration-grid">
                {items.map((provider) => (
                  <article className="integration-card" key={provider.id}>
                    <div className="proposal-heading">
                      <h3>{provider.name || provider.id}</h3>
                      <span className={'tag ' + (provider.status || 'unknown')}>
                        {provider.status
                          ? stateLabel[provider.status] || provider.status
                          : provider.enabled === false
                            ? 'Desativada'
                            : provider.configured
                              ? 'Configurada'
                              : 'Não configurada'}
                      </span>
                    </div>
                    <p>
                      {provider.description ||
                        (provider.id === 'hevy'
                          ? 'Musculação, exercícios e séries.'
                          : provider.id === 'ai'
                            ? provider.local
                              ? 'Ollama local · ' +
                                provider.model +
                                '. Sem cobrança de API e sem envio à nuvem.'
                              : 'OpenAI: estimativas sob demanda, com cobrança da API.'
                            : 'Atividades e sinais disponíveis na plataforma.')}
                    </p>
                    <dl>
                      <div>
                        <dt>Último registro na base</dt>
                        <dd>
                          {dayLabel(
                            provider.last_success ||
                              value?.freshness?.[provider.id] ||
                              (provider.id === 'garmin' ? value?.freshness?.activities : null),
                          )}
                        </dd>
                      </div>
                    </dl>
                    {provider.error && <p className="notice">{provider.error}</p>}
                    <details className="method">
                      <summary>
                        {provider.configured ? 'Alterar conexão' : 'Configurar conexão'}
                      </summary>
                      <form
                        className="personal-form"
                        onSubmit={(event) => {
                          event.preventDefault();
                          run(async () => {
                            await personalApi('integrations/' + encodeURIComponent(provider.id), {
                              credentials: credentials[provider.id] || {},
                              enabled: true,
                            });
                            setCredentials((v) => ({ ...v, [provider.id]: {} }));
                          }, 'Conexão salva. Atualize a fonte para verificar a coleta.');
                        }}
                      >
                        {array(provider.fields).map((field) => {
                          const key = typeof field === 'string' ? field : field.name || field.key;
                          const selected =
                            credentials.ai?.provider || provider.provider || 'openai';
                          if (
                            provider.id === 'ai' &&
                            ((selected === 'ollama' && ['api_key', 'model'].includes(key)) ||
                              (selected === 'openai' && key === 'local_model'))
                          )
                            return null;
                          if (provider.id === 'ai' && key === 'provider')
                            return (
                              <Label className="items-stretch" key={key}>
                                Provedor de IA
                                <NativeSelect
                                  className="w-full min-w-0"
                                  value={selected}
                                  onChange={(e) =>
                                    setCredentials((v) => ({
                                      ...v,
                                      ai: { ...v.ai, provider: e.target.value },
                                    }))
                                  }
                                >
                                  <option value="ollama">
                                    Ollama local · sem cobrança por chamada
                                  </option>
                                  <option value="openai">OpenAI · API paga</option>
                                </NativeSelect>
                              </Label>
                            );
                          const sensitive = /password|api_key|token/.test(key);
                          return (
                            <Label className="items-stretch" key={key}>
                              {{
                                email: 'E-mail Garmin',
                                password: 'Senha Garmin',
                                api_key:
                                  provider.id === 'ai' ? 'Chave API da IA' : 'Chave API Hevy',
                                model: 'Modelo OpenAI (opcional)',
                                local_model: 'Modelo local instalado no Ollama',
                              }[key] ||
                                field.label ||
                                key}
                              <Input
                                type={sensitive ? 'password' : key === 'email' ? 'email' : 'text'}
                                placeholder={
                                  key === 'local_model' ? provider.model || 'qwen3.5:4b' : undefined
                                }
                                value={credentials[provider.id]?.[key] || ''}
                                required={!['model', 'local_model'].includes(key)}
                                autoComplete="off"
                                onChange={(e) =>
                                  setCredentials((v) => ({
                                    ...v,
                                    [provider.id]: { ...v[provider.id], [key]: e.target.value },
                                  }))
                                }
                              />
                            </Label>
                          );
                        })}
                        <Button variant="default" className="primary">
                          Salvar conexão
                        </Button>
                      </form>
                    </details>
                    {provider.configured && (
                      <Button
                        variant="outline"
                        className="text-button"
                        onClick={() =>
                          run(
                            () =>
                              personalApi(
                                'integrations/' + encodeURIComponent(provider.id) + '/disconnect',
                                {},
                              ),
                            'Novas coletas desativadas. O histórico foi preservado.',
                          )
                        }
                      >
                        Desconectar coleta
                      </Button>
                    )}
                  </article>
                ))}
              </div>
            )}
          </PagedList>
          <Button
            variant="default"
            className="primary"
            disabled={jobBusy}
            onClick={() => run(() => onJob('sync'), undefined, false)}
          >
            {jobBusy ? 'Atualização em execução…' : 'Atualizar Garmin e Hevy'}
          </Button>
          <p className="small muted">
            Credenciais são enviadas ao servidor privado e não fazem parte da exportação. Conectar
            uma fonte não garante que todos os sinais estejam disponíveis.
          </p>
        </Card>
        <Card className="panel gap-0">
          <div className="panel-heading">
            <div>
              <h2>Importar histórico ou percurso</h2>
              <p>
                CSV e FIT descrevem atividades. GPX importa um percurso de referência. Arquivos de
                até 12 MB.
              </p>
            </div>
          </div>
          <form className="personal-form" onSubmit={importFile}>
            <div className="form-grid">
              <Label className="items-stretch">
                Formato
                <NativeSelect
                  className="w-full min-w-0"
                  value={fileFormat}
                  onChange={(e) => {
                    setFileFormat(e.target.value);
                    setFile(null);
                  }}
                >
                  <option value="csv">CSV · exportação de atividades</option>
                  <option value="gpx">GPX · percurso de referência</option>
                  <option value="fit">FIT · registro do dispositivo</option>
                </NativeSelect>
              </Label>
              <Label className="items-stretch">
                Arquivo
                <Input
                  ref={fileInput}
                  key={fileFormat}
                  type="file"
                  accept={'.' + fileFormat}
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                />
              </Label>
            </div>
            <Button variant="default" className="primary" disabled={!file}>
              {busy ? 'Importando…' : 'Importar arquivo'}
            </Button>
          </form>
          {value?.csv_template && (
            <details className="method">
              <summary>Ver formato do CSV</summary>
              <p>Use este cabeçalho e dados em unidades consistentes.</p>
              <pre className="context-preview">
                {typeof value.csv_template === 'string'
                  ? value.csv_template
                  : JSON.stringify(value.csv_template, null, 2)}
              </pre>
            </details>
          )}
          {result && (
            <div className="import-result">
              <h3>{result.repeated ? 'Arquivo já importado' : 'Importação processada'}</h3>
              <div className="context-grid">
                <div>
                  <span>Atividades do arquivo</span>
                  <b>{receipt.activity_count ?? 0}</b>
                </div>
                <div>
                  <span>Percursos do arquivo</span>
                  <b>{receipt.route_count ?? 0}</b>
                </div>
              </div>
              <p>
                Repetir o arquivo preserva os registros existentes. Confira abaixo se há
                correspondências ambíguas.
              </p>
              <PagedList
                items={array(result.warnings)}
                resetKey={receipt.id || ''}
                label="Avisos da importação"
              >
                {(items) =>
                  items.map((text, index) => (
                    <p className="notice" key={index}>
                      {text}
                    </p>
                  ))
                }
              </PagedList>
            </div>
          )}
        </Card>
        <Card className="panel gap-0">
          <h2>Registrar atividade manual</h2>
          <form className="personal-form" onSubmit={saveManual}>
            <div className="form-grid">
              <Label className="items-stretch">
                Data
                <Input
                  type="date"
                  required
                  value={manual.date}
                  onChange={(e) => setManual((v) => ({ ...v, date: e.target.value }))}
                />
              </Label>
              <Label className="items-stretch">
                Modalidade
                <NativeSelect
                  className="w-full min-w-0"
                  value={manual.type}
                  onChange={(e) => setManual((v) => ({ ...v, type: e.target.value }))}
                >
                  {[
                    ['running', 'Corrida'],
                    ['walking', 'Caminhada'],
                    ['strength', 'Musculação'],
                    ['cycling', 'Ciclismo'],
                    ['swimming', 'Natação'],
                    ['hiking', 'Montanhismo'],
                    ['other', 'Outra'],
                  ].map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </NativeSelect>
              </Label>
              <Label className="wide items-stretch">
                Nome
                <Input
                  required
                  maxLength="500"
                  value={manual.name}
                  onChange={(e) => setManual((v) => ({ ...v, name: e.target.value }))}
                />
              </Label>
              {[
                ['duration_minutes', 'Duração (minutos)'],
                ['distance_km', 'Distância (km)'],
                ['avg_hr', 'FC média (bpm)'],
              ].map(([key, label]) => (
                <Label className="items-stretch" key={key}>
                  {label}
                  <Input
                    type="number"
                    min="0"
                    max={key === 'avg_hr' ? 250 : 100000}
                    step="0.1"
                    value={manual[key]}
                    onChange={(e) => setManual((v) => ({ ...v, [key]: e.target.value }))}
                  />
                </Label>
              ))}
            </div>
            <Button variant="default" className="primary">
              Salvar atividade manual
            </Button>
          </form>
        </Card>
        {pending.length > 0 && (
          <Card className="panel gap-0">
            <h2>Correspondências para revisar</h2>
            <p className="small muted">
              Confira modalidade, horário e duração antes de decidir se são a mesma sessão.
            </p>
            <PagedList items={pending} label="Correspondências">
              {(items) =>
                items.map((row) => (
                  <div className="record-row" key={row.record_id + '-' + row.other_id}>
                    <div>
                      <div>{activityLabel(row.record_id)}</div>
                      <span className="small muted">Possível correspondência com:</span>
                      <div>{activityLabel(row.other_id)}</div>
                      <p className="small muted">{row.reason}</p>
                    </div>
                    <div className="report-actions">
                      <Button variant="outline" onClick={() => reconcile(row, 'merge')}>
                        Vincular sessões
                      </Button>
                      <Button variant="outline" onClick={() => reconcile(row, 'keep')}>
                        Manter separadas
                      </Button>
                    </div>
                  </div>
                ))
              }
            </PagedList>
          </Card>
        )}
        {array(importView.links).length > 0 && (
          <details className="panel">
            <summary className="section-summary">Sessões vinculadas</summary>
            <PagedList items={array(importView.links)} label="Vínculos de sessões">
              {(items) =>
                items.map((row) => (
                  <div className="record-row" key={row.record_id + '-' + row.other_id}>
                    <div>
                      {activityLabel(row.record_id)}
                      <p className="small muted">
                        Vinculada a {sourceRecord(row.other_id).name || 'registro de outra fonte'}
                      </p>
                    </div>
                    <Button variant="outline" onClick={() => reconcile(row, 'unlink')}>
                      Desfazer vínculo
                    </Button>
                  </div>
                ))
              }
            </PagedList>
          </details>
        )}
        {imports.length > 0 && (
          <Card className="panel gap-0">
            <h2>Importações anteriores</h2>
            <PagedList items={imports.slice().reverse()} label="Importações">
              {(items) =>
                items.map((row) => (
                  <div className="record-row" key={row.id}>
                    <div>
                      <strong>{row.filename || row.format}</strong>
                      <p>
                        {dayLabel(row.imported_at)} · {row.status || 'Processada'}
                      </p>
                    </div>
                    <span className="small muted">
                      {row.activity_count || 0} atividades · {row.route_count || 0} percursos
                    </span>
                  </div>
                ))
              }
            </PagedList>
          </Card>
        )}
        <Card className="panel gap-0">
          <div className="panel-heading">
            <div>
              <h2>Exportar sua memória pessoal</h2>
              <p>Baixe seus registros em formato estruturado.</p>
            </div>
          </div>
          <div className="report-actions">
            <a className="button" href="/api/export" download>
              Baixar exportação completa (JSON)
            </a>
          </div>
          <div className="export-selection">
            {[
              ['include_documents', 'Documentos privados'],
              ['include_food_images', 'Fotos das refeições'],
              ['include_imports', 'Arquivos de importação'],
            ].map(([key, label]) => (
              <Label key={key} htmlFor={'settings-export-' + key} className="checkbox-label">
                <Checkbox
                  id={'settings-export-' + key}
                  checked={attachments[key]}
                  onCheckedChange={(checked) =>
                    setAttachments((v) => ({ ...v, [key]: checked === true }))
                  }
                />
                {label}
              </Label>
            ))}
          </div>
          <a
            className="button"
            href={
              '/api/export/archive?' +
              new URLSearchParams(
                Object.fromEntries(
                  Object.entries(attachments).map(([key, value]) => [key, String(value)]),
                ),
              ).toString()
            }
            download
          >
            Baixar contexto e anexos selecionados (ZIP)
          </a>
          <p className="small muted">
            O arquivo contém dados pessoais de saúde. Guarde-o em um local privado. Remover um
            registro ativo preserva as revisões privadas e backups anteriores. A exportação exclui
            credenciais, sessões e chaves de recuperação.
          </p>
        </Card>
      </fieldset>
    </>
  );
}
