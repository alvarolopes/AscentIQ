import { cpSync, existsSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { join } from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const standalone = join(root, '.next/standalone');
if (!existsSync(join(standalone, 'server.js'))) throw new Error('Execute npm run build primeiro.');
cpSync(join(root, 'public'), join(standalone, 'public'), {recursive: true});
cpSync(join(root, '.next/static'), join(standalone, '.next/static'), {recursive: true});
process.env.HOSTNAME = process.env.HOSTNAME || '127.0.0.1';
await import(pathToFileURL(join(standalone, 'server.js')).href);
