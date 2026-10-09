import type { Metadata, Viewport } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'AscentIQ — Saúde e fitness pessoal',
  description: 'Seus registros de alimentação, treinos e recuperação em uma plataforma pessoal.',
  applicationName: 'AscentIQ',
  manifest: '/manifest.webmanifest',
  icons: { icon: '/icon.svg', apple: '/icon-180.png' },
  appleWebApp: { capable: true, statusBarStyle: 'black-translucent', title: 'AscentIQ' },
};

export const viewport: Viewport = { width: 'device-width', initialScale: 1, themeColor: '#0d1117' };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR" className="dark">
      <body>{children}</body>
    </html>
  );
}
