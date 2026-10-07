import React, {useEffect, useState} from 'react';

export default function InstallApp() {
  const [prompt, setPrompt] = useState(null);
  const [installed, setInstalled] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [error, setError] = useState('');
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  useEffect(() => {
    const mode = window.matchMedia('(display-mode: standalone)');
    const update = () => setInstalled(mode.matches || navigator.standalone === true);
    const offer = event => { event.preventDefault(); setPrompt(event); };
    const done = () => { setInstalled(true); setPrompt(null); };
    update();
    try { setDismissed(Number(localStorage.getItem('ascentiq-install-dismissed')) > Date.now() - 7*86400000); } catch {}
    window.addEventListener('beforeinstallprompt', offer);
    window.addEventListener('appinstalled', done);
    mode.addEventListener('change', update);
    return () => { window.removeEventListener('beforeinstallprompt', offer); window.removeEventListener('appinstalled', done); mode.removeEventListener('change', update); };
  }, []);
  function dismiss() {
    setDismissed(true);
    try { localStorage.setItem('ascentiq-install-dismissed', String(Date.now())); } catch {}
  }
  async function install() {
    if (!prompt) return;
    try {
      await prompt.prompt();
      const result = await prompt.userChoice;
      setPrompt(null);
      if (result.outcome === 'accepted') setInstalled(true); else dismiss();
    } catch { setError('Use o menu do navegador para instalar o app.'); setPrompt(null); }
  }
  if (installed || dismissed || (!prompt && !ios && !error)) return null;
  if (!window.isSecureContext) return null;
  return <aside className="install-app" aria-label="Instalar AscentIQ">
    <div><strong>Tenha o AscentIQ na tela inicial</strong><p>{error || (ios ? 'No menu Compartilhar, escolha “Adicionar à Tela de Início”.' : 'Abra seu painel como um app, direto pelo ícone.')}</p></div>
    {prompt && <button className="primary" onClick={install}>Instalar app</button>}
    <button onClick={dismiss} aria-label="Lembrar da instalação mais tarde">Agora não</button>
  </aside>;
}
