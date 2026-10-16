#!/usr/bin/env node
/*
 * webtest.js - Lance le fabricant de la page web (docs/mgs-vostfr.js) dans Node.
 *
 *   node webtest.js check disque.chd disque.bin [secteurs]   lecture CHD == BIN ?
 *   node webtest.js combine disque1.bin disque2.bin sortie.bin   CD Combiner (comme combine.py)
 *   node webtest.js build --fr1 a.chd --uk1 b.chd --fr2 c.chd --uk2 d.chd --out dossier [--carre --m9 --psg1 --l2r2 --fps] [--vf | --vo] [--life TEXTE] [--combine]
 *
 * Sert à vérifier que la page produit exactement les mêmes images que build.py.
 */
'use strict';
const fs = require('fs');
const path = require('path');
require(path.join(__dirname, '..', 'docs', 'patches.js'));
require(path.join(__dirname, '..', 'docs', 'mgs-vostfr.js'));
const M = globalThis.MGSVOSTFR;

async function openFile(p) {
  const fh = await fs.promises.open(p, 'r');
  const size = (await fh.stat()).size;
  return {
    name: path.basename(p), size,
    async read(off, len) {
      const b = Buffer.allocUnsafe(len);
      const { bytesRead } = await fh.read(b, 0, len, off);
      return new Uint8Array(b.buffer, b.byteOffset, bytesRead);
    }
  };
}

async function check(chd, bin, count) {
  const a = await M.openSource(await openFile(chd));
  const b = await M.openSource(await openFile(bin));
  const n = Math.min(count || a.nsectors, a.nsectors);
  const t = Date.now();
  for (let s = 0; s < n; s += 4096) {
    const k = Math.min(4096, n - s);
    const x = await a.readRaw(s, k, true), y = await b.readRaw(s, k, true);
    for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) throw new Error(`différence secteur ${s + Math.floor(i / 2352)} octet ${i % 2352}`);
  }
  const sec = (Date.now() - t) / 1000;
  console.log(`${n} secteurs identiques en ${sec.toFixed(1)} s (${(n * 2352 / 1048576 / sec).toFixed(1)} Mo/s)`);
}

async function build(args) {
  const get = k => { const i = args.indexOf('--' + k); return i >= 0 ? args[i + 1] : null; };
  const out = get('out');
  fs.mkdirSync(out, { recursive: true });
  const discs = {};
  for (const k of ['fr1', 'uk1', 'fr2', 'uk2']) {
    if (!get(k)) continue;
    const id = await M.identify(await openFile(get(k)));
    if (id.id !== k.toUpperCase()) throw new Error(`${get(k)} : ${id.id || id.exe}, attendu ${k.toUpperCase()}`);
    discs[id.id] = id.disc;
  }
  const opts = ['carre', 'm9', 'psg1', 'l2r2', 'fps'].filter(o => args.includes('--' + o));
  const mode = args.includes('--vf') ? 'fr' : args.includes('--vo') ? 'en' : 'vostfr';
  const t = Date.now();
  let last = '';
  await M.build(discs, opts, async name => {
    const fh = await fs.promises.open(path.join(out, name), 'w');
    return { write: b => fh.write(b), close: () => fh.close() };
  }, s => console.log(`[${((Date.now() - t) / 1000).toFixed(0)} s] ${s}`), (step) => {
    if (step !== last) { last = step; console.log(`[${((Date.now() - t) / 1000).toFixed(0)} s]   ${step}`); }
  }, { mode, life: get('life'), combine: args.includes('--combine'), openReader: name => openFile(path.join(out, name)) });
  console.log(`Terminé en ${((Date.now() - t) / 1000).toFixed(0)} s, mémoire max ~${(process.memoryUsage().rss / 1048576).toFixed(0)} Mo`);
}

async function combineCmd(a, b, outPath) {
  const t = Date.now();
  const d1 = new M.Disc(await M.openSource(await openFile(a))), d2 = new M.Disc(await M.openSource(await openFile(b)));
  const fh = await fs.promises.open(outPath, 'w');
  let last = '';
  await M.combine(d1, d2, { write: x => fh.write(x), close: () => fh.close() }, s => console.log(s), step => {
    if (step !== last) { last = step; console.log(`[${((Date.now() - t) / 1000).toFixed(0)} s]   ${step}`); }
  });
  await fh.close();
  console.log(`Terminé en ${((Date.now() - t) / 1000).toFixed(0)} s, mémoire max ~${(process.memoryUsage().rss / 1048576).toFixed(0)} Mo`);
}

(async () => {
  const [cmd, ...rest] = process.argv.slice(2);
  if (cmd === 'check') await check(rest[0], rest[1], rest[2] ? +rest[2] : 0);
  else if (cmd === 'combine') await combineCmd(rest[0], rest[1], rest[2]);
  else await build(rest);
})().catch(e => { console.error(e); process.exit(1); });
