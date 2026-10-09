import fs from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const forbidden = ['styled-components', '@emotion/react', '@emotion/styled'];
const pkg = JSON.parse(await fs.readFile(path.join(root, 'package.json'), 'utf8'));
const lock = JSON.parse(await fs.readFile(path.join(root, 'package-lock.json'), 'utf8'));
for (const name of [...forbidden, 'styled-jsx']) {
  if (pkg.dependencies?.[name] || pkg.devDependencies?.[name]) throw new Error(`Dependência direta proibida: ${name}`);
}
for (const name of forbidden) {
  if (Object.keys(lock.packages).some(key => key.endsWith(`node_modules/${name}`))) throw new Error(`Dependência proibida: ${name}`);
}
async function scan(directory) {
  for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
    const file = path.join(directory, entry.name);
    if (entry.isDirectory()) await scan(file);
    else if (/\.[jt]sx?$/.test(file)) {
      const code = await fs.readFile(file, 'utf8');
      if (/from\s+['"](?:styled-components|@emotion\/|styled-jsx)/.test(code) || /<style\s+jsx\b/.test(code) || /@ts-nocheck/.test(code)) throw new Error(`Estilo/supressão proibida: ${file}`);
    }
  }
}
await scan(path.join(root, 'src'));
console.log('Tailwind/shadcn: nenhum styled-components ou CSS-in-JS direto.');
