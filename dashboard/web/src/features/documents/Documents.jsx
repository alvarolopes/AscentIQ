'use client';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Card } from '@/components/ui/card';
import { useCallback, useEffect, useRef, useState } from 'react';
import { PagedList } from '@/components/shared/ui';
import {
  array,
  dayLabel,
  ErrorNotice,
  PageHeading,
  personalApi,
  StatusNotice,
  today,
} from '@/lib/personalApi';

export default function Documents({ onStateChange, initialDay = '' }) {
  const [documents, setDocuments] = useState([]),
    [file, setFile] = useState(null),
    [label, setLabel] = useState(''),
    [date, setDate] = useState(initialDay),
    [draft, setDraft] = useState(null),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(''),
    [message, setMessage] = useState(''),
    [consent, setConsent] = useState({});
  const [reviewPage, setReviewPage] = useState(1),
    [reviewSize, setReviewSize] = useState(10);
  const operation = useRef(false),
    fileInput = useRef(null);
  const [initialUpload, setInitialUpload] = useState(JSON.stringify({ label, date }));
  useEffect(() => {
    if (!initialDay) {
      const next = today();
      setInitialUpload(JSON.stringify({ label: '', date: next }));
      setDate(next);
    }
  }, [initialDay]);
  const dirty = Boolean(file || draft) || JSON.stringify({ label, date }) !== initialUpload;
  useEffect(() => {
    onStateChange?.({ busy: busy || loading, dirty });
  }, [busy, loading, dirty, onStateChange]);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const value = await personalApi('documents');
      setDocuments(array(value.documents));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [load]);
  async function run(action, notice, reload = true) {
    if (operation.current) return;
    operation.current = true;
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await action();
      if (reload) await load();
      if (notice) setMessage(notice);
    } catch (e) {
      setError(e.message);
    } finally {
      operation.current = false;
      setBusy(false);
    }
  }
  async function upload(event) {
    event.preventDefault();
    if (!file) return;
    await run(async () => {
      if (file.size > 12 * 1024 * 1024) throw new Error('Escolha um documento de até 12 MB.');
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = '';
      for (let i = 0; i < bytes.length; i += 16384)
        binary += String.fromCharCode(...bytes.subarray(i, i + 16384));
      await personalApi('documents', {
        filename: file.name,
        content: btoa(binary),
        label: label.trim() || file.name,
        date,
      });
      setFile(null);
      if (fileInput.current) fileInput.current.value = '';
      setLabel('');
      setInitialUpload(JSON.stringify({ label: '', date }));
    }, 'Documento privado salvo. Resultados só serão incorporados após revisão.');
  }
  function replaceReview(next) {
    if (draft && !window.confirm('Descartar a revisão ainda não confirmada para abrir outra?'))
      return false;
    setDraft(next);
    setReviewPage(1);
    setError('');
    setMessage('');
    return true;
  }
  function closeReview() {
    if (!window.confirm('Descartar a revisão ainda não confirmada?')) return;
    setDraft(null);
    setReviewPage(1);
  }
  function edit(index, key, value) {
    setDraft((v) => ({
      ...v,
      observations: v.observations.map((row, i) => (i === index ? { ...row, [key]: value } : row)),
    }));
  }
  function removeObservation(index) {
    const observations = draft.observations.filter((_, i) => i !== index);
    setDraft({ ...draft, observations });
    setReviewPage((page) =>
      Math.min(page, Math.max(1, Math.ceil(observations.length / reviewSize))),
    );
  }
  function addObservation() {
    const observations = [
      ...draft.observations,
      { name: '', value: '', unit: '', date, page: null },
    ];
    setDraft({ ...draft, observations });
    setReviewPage(Math.ceil(observations.length / reviewSize));
  }
  async function saveReview(event) {
    event.preventDefault();
    await run(async () => {
      const missing = draft.observations.findIndex((row) => !String(row.name || '').trim());
      if (missing >= 0) {
        setReviewPage(Math.floor(missing / reviewSize) + 1);
        throw new Error(
          'Preencha o indicador do resultado ' + (missing + 1) + ' antes de confirmar.',
        );
      }
      await personalApi('documents/' + encodeURIComponent(draft.document_id) + '/review', {
        observations: draft.observations,
      });
      setDraft(null);
      setReviewPage(1);
    }, 'Observações revisadas e incorporadas.');
  }
  async function extract(document) {
    if (
      draft &&
      !window.confirm('Descartar a revisão ainda não confirmada para extrair este documento?')
    )
      return;
    await run(async () => {
      const result = await personalApi(
        'documents/' + encodeURIComponent(document.id) + '/extract',
        { use_ai: true },
      );
      setDraft({
        document_id: document.id,
        observations: array(result.draft?.observations).map((row) => ({ ...row })),
        notes: result.draft?.notes,
      });
      setReviewPage(1);
      setConsent((v) => ({ ...v, [document.id]: false }));
    }, 'Extração preparada. Confira os valores antes de confirmar.');
  }
  async function removeDocument(document) {
    if (
      draft?.document_id === document.id &&
      !window.confirm('Remover este documento e descartar sua revisão ainda não confirmada?')
    )
      return;
    await run(async () => {
      await personalApi('documents/' + encodeURIComponent(document.id) + '/remove', {});
      if (draft?.document_id === document.id) {
        setDraft(null);
        setReviewPage(1);
      }
    }, 'Documento removido.');
  }
  const observations = array(draft?.observations),
    reviewPages = Math.max(1, Math.ceil(observations.length / reviewSize)),
    reviewCurrent = Math.min(reviewPage, reviewPages);
  const reviewItems = observations
    .map((row, index) => ({ row, index }))
    .slice((reviewCurrent - 1) * reviewSize, reviewCurrent * reviewSize);
  return (
    <>
      <PageHeading kicker="DOCUMENTOS / RESULTADOS" title="Documentos privados">
        Consulte o original e revise os resultados antes de incorporá-los.
      </PageHeading>
      <ErrorNotice error={error} />
      <StatusNotice message={message} />
      <fieldset className="food-fieldset" disabled={busy || loading}>
        <Card className="panel gap-0">
          <h2>Adicionar documento</h2>
          <form className="personal-form" onSubmit={upload}>
            <div className="form-grid">
              <Label className="items-stretch">
                Documento (até 12 MB)
                <Input
                  ref={fileInput}
                  type="file"
                  accept=".pdf,.txt,.png,.jpg,.jpeg,.webp"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                />
              </Label>
              <Label className="items-stretch">
                Identificação
                <Input
                  value={label}
                  maxLength="300"
                  onChange={(e) => setLabel(e.target.value)}
                  placeholder="Ex.: avaliação, exame, orientação"
                />
              </Label>
              <Label className="items-stretch">
                Data de referência
                <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
              </Label>
            </div>
            <Button variant="default" className="primary" disabled={!file}>
              {busy ? 'Processando…' : 'Salvar documento'}
            </Button>
          </form>
        </Card>
        {draft && (
          <Card className="panel gap-0">
            <div className="panel-heading">
              <div>
                <h2>Revisar resultados extraídos</h2>
                <p>
                  {draft.notes || 'Compare os itens com o documento original antes de incorporar.'}
                </p>
              </div>
              <Button variant="outline" onClick={closeReview}>
                Fechar revisão
              </Button>
            </div>
            <form onSubmit={saveReview}>
              <PagedList
                items={reviewItems}
                label="Resultados em revisão"
                pagination={{
                  total: observations.length,
                  pages: reviewPages,
                  page: reviewCurrent,
                  page_size: reviewSize,
                }}
                onPageChange={setReviewPage}
                onPageSizeChange={(size) => {
                  setReviewSize(size);
                  setReviewPage(1);
                }}
              >
                {(items) => (
                  <div
                    className="table-scroll"
                    tabIndex={0}
                    role="region"
                    aria-label="Registros em tabela"
                  >
                    <table>
                      <thead>
                        <tr>
                          <th>Indicador</th>
                          <th>Valor</th>
                          <th>Unidade</th>
                          <th>Data</th>
                          <th>Página</th>
                          <th>Excluir</th>
                        </tr>
                      </thead>
                      <tbody>
                        {items.map(({ row, index }) => (
                          <tr key={index}>
                            <td>
                              <Input
                                aria-label={'Indicador ' + (index + 1)}
                                value={row.name || ''}
                                required
                                onChange={(e) => edit(index, 'name', e.target.value)}
                              />
                            </td>
                            <td>
                              <Input
                                aria-label={'Valor ' + (index + 1)}
                                value={row.value ?? ''}
                                onChange={(e) => edit(index, 'value', e.target.value)}
                              />
                            </td>
                            <td>
                              <Input
                                aria-label={'Unidade ' + (index + 1)}
                                value={row.unit || ''}
                                onChange={(e) => edit(index, 'unit', e.target.value)}
                              />
                            </td>
                            <td>
                              <Input
                                aria-label={'Data ' + (index + 1)}
                                type="date"
                                value={row.date || ''}
                                onChange={(e) => edit(index, 'date', e.target.value)}
                              />
                            </td>
                            <td>
                              <Input
                                aria-label={'Página ' + (index + 1)}
                                type="number"
                                min="1"
                                value={row.page ?? ''}
                                onChange={(e) =>
                                  edit(
                                    index,
                                    'page',
                                    e.target.value ? Number(e.target.value) : null,
                                  )
                                }
                              />
                            </td>
                            <td>
                              <Button
                                variant="outline"
                                type="button"
                                onClick={() => removeObservation(index)}
                              >
                                Remover
                              </Button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </PagedList>
              <div className="report-actions">
                <Button variant="outline" type="button" onClick={addObservation}>
                  Adicionar resultado
                </Button>
                <Button variant="default" className="primary" disabled={!observations.length}>
                  Confirmar resultados revisados
                </Button>
              </div>
            </form>
          </Card>
        )}
        <Card className="panel gap-0">
          <div className="panel-heading">
            <h2>Arquivo privado</h2>
            <Button variant="outline" onClick={() => run(load, undefined, false)}>
              Atualizar documentos
            </Button>
          </div>
          {loading && (
            <p className="muted" role="status">
              Consultando documentos…
            </p>
          )}
          {documents.length ? (
            <PagedList items={documents} label="Documentos">
              {(items) =>
                items.map((document) => (
                  <article className="document-card" key={document.id}>
                    <div className="proposal-heading">
                      <h3>{document.label || document.filename}</h3>
                      <span className="tag">
                        {document.reviewed
                          ? 'Revisado'
                          : document.status === 'extracted'
                            ? 'Extração pendente de revisão'
                            : 'Documento original'}
                      </span>
                    </div>
                    <p className="small muted">
                      {dayLabel(document.date)} · {document.filename}
                    </p>
                    <div className="report-actions">
                      <a
                        className="button"
                        href={'/api/documents/' + encodeURIComponent(document.id) + '/file'}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Abrir original
                      </a>
                      <Button
                        variant="outline"
                        onClick={() =>
                          replaceReview({
                            document_id: document.id,
                            observations: array(document.observations).map((row) => ({ ...row })),
                            notes:
                              'Digite ou revise os resultados consultando o documento original.',
                          })
                        }
                      >
                        Registrar resultados manualmente
                      </Button>
                      <Button variant="outline" onClick={() => removeDocument(document)}>
                        Remover documento
                      </Button>
                    </div>
                    <details className="method">
                      <summary>Extrair resultados com IA</summary>
                      <p>A resposta da IA permanece pendente até sua revisão.</p>
                      <Label htmlFor={'document-consent-' + document.id} className="checkbox-label">
                        <Checkbox
                          id={'document-consent-' + document.id}
                          checked={Boolean(consent[document.id])}
                          onCheckedChange={(checked) =>
                            setConsent((v) => ({ ...v, [document.id]: checked === true }))
                          }
                        />
                        Enviar este documento para extração com IA
                      </Label>
                      <Button
                        variant="outline"
                        disabled={!consent[document.id]}
                        onClick={() => extract(document)}
                      >
                        Extrair e revisar
                      </Button>
                    </details>
                    {array(document.observations).length > 0 && (
                      <details className="method">
                        <summary>Resultados revisados</summary>
                        <PagedList
                          items={array(document.observations)}
                          resetKey={document.id}
                          label={'Resultados de ' + (document.label || document.filename)}
                        >
                          {(rows) => (
                            <div
                              className="table-scroll"
                              tabIndex={0}
                              role="region"
                              aria-label="Registros em tabela"
                            >
                              <table>
                                <thead>
                                  <tr>
                                    <th>Indicador</th>
                                    <th>Resultado</th>
                                    <th>Referência</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {rows.map((row, index) => (
                                    <tr key={index}>
                                      <td>{row.name}</td>
                                      <td>
                                        {row.value} {row.unit}
                                      </td>
                                      <td>
                                        {dayLabel(row.date)}
                                        {row.page ? ' · pág. ' + row.page : ''}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </PagedList>
                      </details>
                    )}
                  </article>
                ))
              }
            </PagedList>
          ) : (
            !loading && <p className="empty">Nenhum documento adicional registrado.</p>
          )}
        </Card>
      </fieldset>
    </>
  );
}
