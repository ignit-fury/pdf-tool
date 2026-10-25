import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

async function fixture(run) {
  const root = mkdtempSync(join(tmpdir(), 'client-license-'));
  const lock = { lockfileVersion: 3, packages: { '': { dependencies: { wrapper: '1.0.0' } } } };
  function pkg(path, { license = 'MIT', version = '1.0.0', installedLicense = license, installedVersion = version,
    notices = {}, ...extra } = {}) {
    const name = path.split('node_modules/').at(-1);
    lock.packages[path] = { version, license, resolved: `https://registry.npmjs.org/${name}/-/${name.split('/').at(-1)}-${version}.tgz`,
      integrity: `sha512-${Buffer.alloc(64).toString('base64')}`, ...extra };
    const dir = join(root, path);
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, 'package.json'), JSON.stringify({ name, version: installedVersion, license: installedLicense }));
    writeFileSync(join(dir, 'LICENSE'), 'Permission is hereby granted, free of charge, to any person obtaining a copy. MIT License');
    for (const [file, text] of Object.entries(notices)) {
      mkdirSync(join(dir, file, '..'), { recursive: true });
      writeFileSync(join(dir, file), text);
    }
  }
  const audit = async () => {
    writeFileSync(join(root, 'package-lock.json'), JSON.stringify(lock));
    const { auditClientClosure } = await import('./client_license_gate.mjs');
    return auditClientClosure({ lockPath: join(root, 'package-lock.json'), modulesRoot: join(root, 'node_modules') });
  };
  try { await run({ root, lock, pkg, audit }); } finally { rmSync(root, { recursive: true, force: true }); }
}

test('resolved permissive runtime closure passes, development GPL is excluded', async () => fixture(async ({ pkg, audit }) => {
  pkg('node_modules/wrapper');
  pkg('node_modules/wrapper/node_modules/transitive', { license: '(MIT AND Zlib)' });
  pkg('node_modules/dev-tool', { license: 'GPL-3.0-only', dev: true });
  assert.deepEqual(await audit(), []);
}));

test('transitive AGPL hidden below MIT wrapper fails', async () => fixture(async ({ pkg, audit }) => {
  pkg('node_modules/wrapper');
  pkg('node_modules/wrapper/node_modules/decoder', { license: 'AGPL-3.0-only' });
  assert.ok((await audit()).some(f => f.code === 'FORBIDDEN_LICENSE' && f.package === 'decoder'));
}));

test('MIT wrapper cannot hide bundled LGPL WASM notice', async () => fixture(async ({ pkg, audit }) => {
  pkg('node_modules/wrapper', { notices: { 'codec.wasm': Buffer.from('\0asm'),
    'LICENSE_HEIF': 'GNU LESSER GENERAL PUBLIC LICENSE Version 3' } });
  assert.ok((await audit()).some(f => f.code === 'FORBIDDEN_BUNDLED_LICENSE'));
}));

test('unknown or absent installed license refuses', async () => fixture(async ({ pkg, audit }) => {
  pkg('node_modules/wrapper', { license: 'LicenseRef-Trust-Me' });
  assert.ok((await audit()).some(f => f.code === 'UNKNOWN_LICENSE'));
}));

test('installed version and license drift refuse', async () => fixture(async ({ pkg, audit }) => {
  pkg('node_modules/wrapper', { installedVersion: '2.0.0', installedLicense: 'BSD-3-Clause' });
  const found = await audit();
  assert.ok(found.some(f => f.code === 'VERSION_DRIFT'));
  assert.ok(found.some(f => f.code === 'LICENSE_DRIFT'));
}));

test('missing package metadata refuses', async () => fixture(async ({ pkg, root, audit }) => {
  pkg('node_modules/wrapper');
  rmSync(join(root, 'node_modules/wrapper/package.json'));
  assert.ok((await audit()).some(f => f.code === 'MISSING_METADATA'));
}));

test('OR permits an explicit permissive choice; AND and any AGPL refuse', async () => fixture(async ({ pkg, audit }) => {
  pkg('node_modules/wrapper', { license: '(MIT OR Apache-2.0)' });
  assert.deepEqual(await audit(), []);
  pkg('node_modules/wrapper', { license: '(MIT OR GPL-2.0-only)' });
  assert.deepEqual(await audit(), []);
  pkg('node_modules/wrapper', { license: '(MIT AND GPL-2.0-only)' });
  assert.ok((await audit()).some(f => f.code === 'FORBIDDEN_LICENSE'));
  pkg('node_modules/wrapper', { license: '(MIT OR AGPL-3.0-only)' });
  assert.ok((await audit()).some(f => f.code === 'FORBIDDEN_LICENSE'));
}));

test('WASM needs artifact-specific provenance, not wrapper MIT', async () => fixture(async ({ pkg, audit }) => {
  pkg('node_modules/wrapper', { notices: { 'hidden-codec.wasm': Buffer.from('\0asm') } });
  assert.ok((await audit()).some(f => f.code === 'WASM_PROVENANCE_MISSING'));
}));

test('installed optional runtime entries are audited', async () => fixture(async ({ pkg, audit }) => {
  pkg('node_modules/wrapper');
  pkg('node_modules/optional-decoder', { license: 'LGPL-3.0-only', optional: true });
  assert.ok((await audit()).some(f => f.code === 'FORBIDDEN_LICENSE'));
}));

test('unsupported SPDX syntax and nonregistry source require review', async () => fixture(async ({ pkg, audit }) => {
  pkg('node_modules/wrapper', { license: 'MIT WITH mysterious-exception', resolved: 'git+https://example.invalid/codec' });
  const found = await audit();
  assert.ok(found.some(f => f.code === 'UNKNOWN_LICENSE'));
  assert.ok(found.some(f => f.code === 'UNREVIEWED_SOURCE'));
}));

test('lock path traversal refuses without reading external packages', async () => fixture(async ({ pkg, lock, audit }) => {
  pkg('node_modules/wrapper');
  lock.packages['node_modules/../../outside'] = { version: '1', license: 'MIT' };
  assert.ok((await audit()).some(f => f.code === 'INVALID_LOCK_PATH'));
}));

test('bundled source license header is independently audited', async () => fixture(async ({ pkg, audit }) => {
  pkg('node_modules/wrapper', { notices: { 'vendor/hidden.js': '/* SPDX-License-Identifier: GPL-3.0-only */\nexport default 1;' } });
  assert.ok((await audit()).some(f => f.code === 'FORBIDDEN_BUNDLED_LICENSE'));
}));
