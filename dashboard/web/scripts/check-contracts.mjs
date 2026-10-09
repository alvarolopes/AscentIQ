import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const committed = join(root, 'src/lib/api/generated/openapi.d.ts');
const temp = mkdtempSync(join(tmpdir(), 'ascentiq-openapi-'));
try {
  const output = join(temp, 'openapi.d.ts');
  execFileSync(process.execPath,
               [join(root, 'node_modules/openapi-typescript/bin/cli.js'), '../openapi.json', '-o', output],
               { cwd: root, stdio: 'inherit' });
  if (readFileSync(join(temp, 'openapi.d.ts'), 'utf8') !== readFileSync(committed, 'utf8')) {
    console.error('src/lib/api/generated/openapi.d.ts is stale; run npm run contracts');
    process.exit(1);
  }
  console.log('src/lib/api/generated/openapi.d.ts is current');
} finally {
  rmSync(temp, { recursive: true, force: true });
}
