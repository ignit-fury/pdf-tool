/** Audit the resolved browser runtime closure without third-party dependencies.
 * Missing evidence is a failure. This is a policy gate, not a legal opinion or
 * a malware scanner; a permissive wrapper never overrides bundled code notices.
 */
import { readFileSync, readdirSync, lstatSync, realpathSync, existsSync } from 'node:fs';
import { dirname, resolve, relative, basename, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const PERMISSIVE = new Set(['MIT', 'Apache-2.0', 'BSD-2-Clause', 'BSD-3-Clause', 'BSD-3-Clause-Clear',
  'ISC', '0BSD', 'Zlib', 'OFL-1.1', 'BSL-1.0', 'Unlicense', 'CC0-1.0']);
const COPYLEFT = /\b(?:A?GPL|LGPL)(?:-\d|\b)|affero|GNU\s+(?:(?:LESSER|LIBRARY)\s+)?GENERAL\s+PUBLIC\s+LICENSE/i;
const AGPL = /agpl|affero/i;
const NOTICE = /(?:licen[cs]e|copying|copyright|notice|third[-_ .]?party)/i;
const PERMISSIVE_NOTICE = /permission is hereby granted|permission to use, copy, modify, and\/or distribute|apache license|apache\.org\/licenses|redistribution and use in source and binary|SIL OPEN FONT LICENSE|zlib license|this software is provided ['"]as[- ]is['"]|public domain|CC0 1\.0 Universal|boost software license/i;

// Explicit reviewed exception for absent component-specific packaging notice.
// Version + exact artifact + SHA prevent a future wrapper/version from inheriting
// this evidence. This permits MIT, never copyleft or arbitrary unknown artifacts.
const REVIEWED_WASM = [{
  package: 'pdfjs-dist', version: '6.2.108', artifact: 'wasm/quickjs-eval.wasm', license: 'MIT',
  sha256: '7bcacc9f22cacf7e9b23866d2a6d1639693d40c7f144e41b7c69ed37ba9cbe8f',
  evidence: 'https://raw.githubusercontent.com/mozilla/pdf.js/v6.2.108/external/quickjs/README.md',
  reason: 'Upstream versioned build README identifies QuickJS and pdf.js.quickjs as MIT; published artifact lacks a dedicated notice.',
}];

function licenseResult(expression) {
  if (typeof expression !== 'string' || !expression.trim()) return 'UNKNOWN_LICENSE';
  if (AGPL.test(expression)) return 'FORBIDDEN_LICENSE';
  const tokens = expression.match(/\(|\)|[A-Za-z0-9.+-]+/g) ?? [];
  if (tokens.join('') !== expression.replace(/\s/g, '')) return 'UNKNOWN_LICENSE';
  let cursor = 0;
  let unknown = false;
  function atom() {
    const token = tokens[cursor++];
    if (token === '(') {
      const value = or();
      if (tokens[cursor++] !== ')') throw Error('syntax');
      return value;
    }
    if (!token || ['AND', 'OR', 'WITH', ')'].includes(token)) throw Error('syntax');
    if (PERMISSIVE.has(token)) return true;
    if (/^(?:GPL|LGPL)-\d\.\d(?:-only|-or-later|\+)?$/.test(token)) return false;
    unknown = true;
    return false;
  }
  function and() {
    let result = atom();
    while (tokens[cursor] === 'AND') { cursor++; const next = atom(); result = result && next; }
    return result;
  }
  function or() {
    let result = and();
    while (tokens[cursor] === 'OR') { cursor++; const next = and(); result = result || next; }
    return result;
  }
  try {
    const accepted = or();
    if (cursor !== tokens.length || unknown) return 'UNKNOWN_LICENSE';
    return accepted ? null : 'FORBIDDEN_LICENSE';
  } catch { return 'UNKNOWN_LICENSE'; }
}

function supports(values, actual) {
  if (!Array.isArray(values) || values.length === 0) return true;
  if (values.includes(`!${actual}`)) return false;
  const positive = values.filter(v => !v.startsWith('!'));
  return positive.length === 0 || positive.includes(actual) || positive.includes('any');
}

function filesBelow(root) {
  const files = [];
  function walk(directory, depth = 0) {
    if (depth > 32 || files.length > 20000) throw Error('scan limit');
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      if (entry.name === 'node_modules') continue; // Audited at its own lock entry.
      const file = resolve(directory, entry.name);
      if (entry.isSymbolicLink()) throw Error('unreviewed symlink');
      if (entry.isDirectory()) walk(file, depth + 1);
      else if (entry.isFile()) files.push(file);
      else throw Error('unsupported file');
    }
  }
  walk(root);
  return files;
}

/** Findings are deterministic fixed codes plus package/path evidence. */
export function auditClientClosure({ lockPath, modulesRoot }) {
  const findings = [];
  const add = (pkg, path, code, detail = '') => findings.push({ package: pkg, path, code, detail });
  let lock;
  try { lock = JSON.parse(readFileSync(lockPath, 'utf8')); }
  catch { add('(lock)', '', 'INVALID_LOCKFILE'); return findings; }
  if (![2, 3].includes(lock.lockfileVersion) || !lock.packages || !lock.packages['']) {
    add('(lock)', '', 'INVALID_LOCKFILE'); return findings;
  }
  const modules = resolve(modulesRoot);
  const entries = Object.entries(lock.packages).filter(([path, entry]) => path && entry.dev !== true);
  const runtime = new Set(entries.map(([path]) => path));
  const pathPattern = /^(?:node_modules\/(?:@[A-Za-z0-9_.-]+\/)?[A-Za-z0-9_.-]+)(?:\/node_modules\/(?:@[A-Za-z0-9_.-]+\/)?[A-Za-z0-9_.-]+)*$/;

  function dependencyPath(from, name) {
    if (!/^(?:@[A-Za-z0-9_.-]+\/)?[A-Za-z0-9_.-]+$/.test(name)) return null;
    let prefix = from;
    while (prefix) {
      const candidate = `${prefix}/node_modules/${name}`;
      if (lock.packages[candidate]) return candidate;
      prefix = prefix.includes('/node_modules/') ? prefix.slice(0, prefix.lastIndexOf('/node_modules/')) : '';
    }
    return lock.packages[`node_modules/${name}`] ? `node_modules/${name}` : null;
  }
  for (const [path, entry] of [['', lock.packages['']], ...entries]) {
    for (const name of Object.keys(entry.dependencies ?? {})) {
      const target = dependencyPath(path, name);
      if (!target || !runtime.has(target)) add(name, path, 'MISSING_RUNTIME_DEPENDENCY');
    }
    for (const name of Object.keys(entry.optionalDependencies ?? {})) {
      if (!dependencyPath(path, name)) add(name, path, 'MISSING_OPTIONAL_LOCK_ENTRY');
    }
  }

  for (const [lockPath, entry] of entries) {
    const name = lockPath.split('node_modules/').at(-1);
    if (!pathPattern.test(lockPath) || lockPath.split('/').some(p => p === '.' || p === '..')) {
      add(name, lockPath, 'INVALID_LOCK_PATH'); continue;
    }
    const directory = resolve(modules, lockPath.slice('node_modules/'.length));
    if (!directory.startsWith(`${modules}${sep}`)) { add(name, lockPath, 'INVALID_LOCK_PATH'); continue; }
    const packageFile = resolve(directory, 'package.json');
    if (!existsSync(packageFile)) {
      // Cross-platform optional binaries absent from this installation are not
      // shipped here. Applicable/missing optional entries still fail closed.
      if (entry.optional && (!supports(entry.os, process.platform) || !supports(entry.cpu, process.arch))) continue;
      add(name, lockPath, 'MISSING_METADATA'); continue;
    }
    let metadata;
    try {
      if (!realpathSync(directory).startsWith(`${realpathSync(modules)}${sep}`) || lstatSync(directory).isSymbolicLink()) throw Error('escape');
      metadata = JSON.parse(readFileSync(packageFile, 'utf8'));
    } catch { add(name, lockPath, 'MISSING_METADATA'); continue; }
    if (metadata.name !== name) add(name, lockPath, 'PACKAGE_NAME_DRIFT');
    if (metadata.version !== entry.version || typeof entry.version !== 'string') add(name, lockPath, 'VERSION_DRIFT');
    if (metadata.license !== entry.license) add(name, lockPath, 'LICENSE_DRIFT');
    for (const expression of new Set([entry.license, metadata.license])) {
      const violation = licenseResult(expression);
      if (violation) add(name, lockPath, violation, typeof expression === 'string' ? expression : 'missing');
    }
    if (typeof entry.resolved !== 'string' || !entry.resolved.startsWith('https://registry.npmjs.org/') ||
        typeof entry.integrity !== 'string' || !/^sha512-[A-Za-z0-9+/]+={0,2}$/.test(entry.integrity) || entry.link) {
      add(name, lockPath, 'UNREVIEWED_SOURCE');
    }
    let files;
    try { files = filesBelow(directory); }
    catch { add(name, lockPath, 'BUNDLE_SCAN_FAILED'); continue; }
    const notices = [];
    for (const file of files) {
      const isNotice = NOTICE.test(basename(file));
      const isSource = /\.(?:m?js|cjs|ts|c|h|cpp)$/i.test(file);
      if (!isNotice && !isSource) continue;
      if (lstatSync(file).size > 8 * 1024 * 1024) { add(name, lockPath, 'BUNDLE_SCAN_LIMIT'); continue; }
      const text = readFileSync(file, 'utf8');
      // Source headers (including SPDX) are independent bundled license evidence.
      const evidence = isNotice ? text : text.slice(0, 65536);
      if (COPYLEFT.test(evidence)) add(name, relative(directory, file), 'FORBIDDEN_BUNDLED_LICENSE');
      if (isNotice) {
        if (!PERMISSIVE_NOTICE.test(text)) add(name, relative(directory, file), 'UNKNOWN_BUNDLED_LICENSE');
        notices.push({ file, text });
      }
    }
    for (const file of files.filter(file => file.endsWith('.wasm'))) {
      const artifact = relative(directory, file).split(sep).join('/');
      const component = basename(file, '.wasm').replace(/(?:_bg|-eval)$/, '').toLowerCase();
      const specificNotice = notices.some(notice => basename(notice.file).toLowerCase().includes(component) &&
        PERMISSIVE_NOTICE.test(notice.text) && !COPYLEFT.test(notice.text));
      if (specificNotice) continue;
      const reviewed = REVIEWED_WASM.find(item => item.package === name && item.version === entry.version &&
        item.artifact === artifact && PERMISSIVE.has(item.license) && item.evidence && item.reason &&
        item.sha256 === createHash('sha256').update(readFileSync(file)).digest('hex'));
      if (!reviewed) add(name, artifact, 'WASM_PROVENANCE_MISSING');
    }
  }
  return findings;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const client = resolve(dirname(fileURLToPath(import.meta.url)), '../client');
  try {
    const findings = auditClientClosure({ lockPath: resolve(client, 'package-lock.json'), modulesRoot: resolve(client, 'node_modules') });
    for (const finding of findings) console.error(JSON.stringify(finding));
    if (findings.length) process.exitCode = 1;
    else console.log('client_license_gate: resolved installed runtime closure and bundled notices passed');
  } catch {
    console.error('client_license_gate: audit failed closed');
    process.exitCode = 1;
  }
}
