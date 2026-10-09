'use client';

import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

const dismissalKey = 'ascentiq-install-dismissed';
const dismissalDays = 7;

export default function InstallApp() {
  const [prompt, setPrompt] = useState(null);
  const [installed, setInstalled] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [ios, setIos] = useState(false);
  const [secure, setSecure] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const installing = useRef(false);

  useEffect(() => {
    setSecure(window.isSecureContext);
    if (window.isSecureContext && 'serviceWorker' in navigator) {
      // The worker stores only the public offline shell, never personal responses.
      void navigator.serviceWorker.register('/sw.js').catch(() => {});
    }
    setIos(
      /iPad|iPhone|iPod/.test(navigator.userAgent) ||
        (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1),
    );
    const mode = window.matchMedia('(display-mode: standalone)');
    const update = () => setInstalled(mode.matches || navigator.standalone === true);
    const offer = (event) => {
      event.preventDefault();
      setPrompt(event);
    };
    const done = () => {
      setInstalled(true);
      setPrompt(null);
    };
    update();
    try {
      setDismissed(
        Number(localStorage.getItem(dismissalKey)) > Date.now() - dismissalDays * 86400000,
      );
    } catch {}
    window.addEventListener('beforeinstallprompt', offer);
    window.addEventListener('appinstalled', done);
    mode.addEventListener('change', update);
    return () => {
      window.removeEventListener('beforeinstallprompt', offer);
      window.removeEventListener('appinstalled', done);
      mode.removeEventListener('change', update);
    };
  }, []);

  function dismiss() {
    if (installing.current) return;
    setDismissed(true);
    try {
      localStorage.setItem(dismissalKey, String(Date.now()));
    } catch {}
  }

  async function install() {
    if (!prompt || installing.current) return;
    installing.current = true;
    setBusy(true);
    setError('');
    try {
      await prompt.prompt();
      const result = await prompt.userChoice;
      setPrompt(null);
      if (result.outcome === 'accepted') setInstalled(true);
      else {
        setDismissed(true);
        try {
          localStorage.setItem(dismissalKey, String(Date.now()));
        } catch {}
      }
    } catch {
      setError('Use o menu do navegador para instalar o app.');
      setPrompt(null);
    } finally {
      installing.current = false;
      setBusy(false);
    }
  }

  if (!secure || installed || dismissed || (!prompt && !ios && !error)) return null;
  return (
    <Card className="install-app" role="complementary" aria-label="Instalar AscentIQ">
      <div>
        <strong>Tenha o AscentIQ na tela inicial</strong>
        <p>
          {error ||
            (ios
              ? 'No menu Compartilhar, escolha “Adicionar à Tela de Início”.'
              : 'Abra seu painel como um app, direto pelo ícone.')}
        </p>
      </div>
      {prompt && (
        <Button disabled={busy} onClick={install}>
          {busy ? 'Abrindo instalação…' : 'Instalar app'}
        </Button>
      )}
      <Button
        variant="outline"
        disabled={busy}
        onClick={dismiss}
        aria-label="Lembrar da instalação mais tarde"
      >
        Agora não
      </Button>
    </Card>
  );
}
