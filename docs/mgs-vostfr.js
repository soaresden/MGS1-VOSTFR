/*
 * mgs-vostfr.js - Fabrique les images VOSTFR de Metal Gear Solid (PS1) dans le navigateur.
 *
 * Portage fidèle des scripts Python de tools/ (chd2bin, psxiso, cdsector, vox, radio,
 * voxalign, vox_vostfr, demo_vostfr, isorebuild) : à options égales, l'image produite est
 * identique octet pour octet à celle de build.py. Les options (Carré, M9, PSG1, L2/R2,
 * visée) sont des différences d'octets exportées par tools/webpatches.py (docs/patches.js).
 *
 * Tout se passe en mémoire, sur la machine : aucun fichier n'est envoyé nulle part.
 * Fonctionne aussi dans Node (tools/webtest.js) pour les tests.
 */
(function (G) {
  'use strict';

  var SECTOR = 2352;
  var SYNC = [0, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 0];

  function u16(b, o) { return b[o] | b[o + 1] << 8; }
  function u24(b, o) { return b[o] | b[o + 1] << 8 | b[o + 2] << 16; }
  function u32(b, o) { return (b[o] | b[o + 1] << 8 | b[o + 2] << 16 | b[o + 3] << 24) >>> 0; }
  function u32be(b, o) { return (b[o] << 24 | b[o + 1] << 16 | b[o + 2] << 8 | b[o + 3]) >>> 0; }
  function w32(b, o, v) { b[o] = v; b[o + 1] = v >>> 8; b[o + 2] = v >>> 16; b[o + 3] = v >>> 24; }
  function w32be(b, o, v) { b[o] = v >>> 24; b[o + 1] = v >>> 16; b[o + 2] = v >>> 8; b[o + 3] = v; }
  function ascii(b, a, e) { var s = ''; for (var i = a; i < e; i++) s += String.fromCharCode(b[i]); return s; }
  function concat(parts, total) {
    if (total === undefined) { total = 0; parts.forEach(function (p) { total += p.length; }); }
    var out = new Uint8Array(total), o = 0;
    parts.forEach(function (p) { out.set(p, o); o += p.length; });
    return out;
  }
  function pyRound(x) {  // round() de Python : arrondi au pair
    var f = Math.floor(x), d = x - f;
    if (d > 0.5) return f + 1;
    if (d < 0.5) return f;
    return f % 2 === 0 ? f : f + 1;
  }

  // ------------------------------------------------------------------ CRC32 / empreinte
  var CRC = (function () {
    var t = new Uint32Array(256);
    for (var i = 0; i < 256; i++) { var c = i; for (var k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[i] = c; }
    return t;
  })();
  function crc32(b) {
    var c = 0xFFFFFFFF;
    for (var i = 0; i < b.length; i++) c = CRC[(c ^ b[i]) & 255] ^ (c >>> 8);
    return (c ^ 0xFFFFFFFF) >>> 0;
  }
  function digest(b, a, e) {  // empreinte 64 bits (remplace le MD5 de voxalign : égalité seulement)
    var h1 = 0x811C9DC5, h2 = 0x01000193 ^ (e - a);
    for (var i = a; i < e; i++) {
      h1 = Math.imul(h1 ^ b[i], 0x01000193);
      h2 = Math.imul(h2 ^ b[i], 0x5BD1E995) ^ (h2 >>> 15);
    }
    return (h1 >>> 0).toString(16) + ':' + (h2 >>> 0).toString(16) + ':' + (e - a);
  }

  // ------------------------------------------------------------------ EDC / ECC (cdsector.py)
  var F_LUT = new Uint8Array(256), B_LUT = new Uint8Array(256), EDC_LUT = new Uint32Array(256);
  (function () {
    for (var i = 0; i < 256; i++) {
      var j = ((i << 1) ^ (i & 0x80 ? 0x11D : 0)) & 0xFF;
      F_LUT[i] = j; B_LUT[i ^ j] = i;
      var e = i;
      for (var k = 0; k < 8; k++) e = (e >>> 1) ^ (e & 1 ? 0xD8018001 : 0);
      EDC_LUT[i] = e >>> 0;
    }
  })();
  function eccIndex(majorCount, minorCount, majorMult, minorInc) {
    var size = majorCount * minorCount, idx = new Int32Array(majorCount * minorCount);
    for (var major = 0; major < majorCount; major++) {
      var index = (major >> 1) * majorMult + (major & 1);
      for (var minor = 0; minor < minorCount; minor++) {
        idx[major * minorCount + minor] = index;
        index += minorInc;
        if (index >= size) index -= size;
      }
    }
    return idx;
  }
  var P_IDX = eccIndex(86, 24, 2, 86), Q_IDX = eccIndex(52, 43, 86, 88);
  function eccBlock(s, o, idx, majorCount, minorCount, dest) {
    var base = o + 0xC;
    for (var major = 0; major < majorCount; major++) {
      var a = 0, b = 0, k = major * minorCount;
      for (var minor = 0; minor < minorCount; minor++) {
        var t = s[base + idx[k + minor]];
        a ^= t; b ^= t; a = F_LUT[a];
      }
      a = B_LUT[F_LUT[a] ^ b];
      s[o + dest + major] = a;
      s[o + dest + major + majorCount] = a ^ b;
    }
  }
  function fixEcc(s, o) {  // ECC P/Q (adresse à zéro en Mode 2)
    var mode2 = s[o + 15] === 2, a0 = s[o + 12], a1 = s[o + 13], a2 = s[o + 14], a3 = s[o + 15];
    if (mode2) { s[o + 12] = 0; s[o + 13] = 0; s[o + 14] = 0; s[o + 15] = 0; }
    eccBlock(s, o, P_IDX, 86, 24, 0x81C);
    eccBlock(s, o, Q_IDX, 52, 43, 0x8C8);
    s[o + 12] = a0; s[o + 13] = a1; s[o + 14] = a2; s[o + 15] = a3;
  }
  function fixForm1(s, o) {  // EDC + ECC d'un secteur Mode 2 Form 1
    var e = 0;
    for (var k = o + 0x10, end = o + 0x818; k < end; k++) e = EDC_LUT[(e ^ s[k]) & 0xFF] ^ (e >>> 8);
    w32(s, o + 0x818, e >>> 0);
    fixEcc(s, o);
  }
  function bcd(x) { return ((x / 10) | 0) << 4 | x % 10; }
  function setMsf(s, o, lba) {
    var x = lba + 150;
    s[o + 12] = bcd((x / 4500) | 0); s[o + 13] = bcd(((x / 75) | 0) % 60); s[o + 14] = bcd(x % 75);
  }

  // ------------------------------------------------------------------ LZMA brut (LZMA1, sans marqueur de fin)
  var LZ = {
    lit: new Uint16Array(0x300 << 4), isMatch: new Uint16Array(192), isRep: new Uint16Array(12),
    g0: new Uint16Array(12), g1: new Uint16Array(12), g2: new Uint16Array(12), rep0Long: new Uint16Array(192),
    posSlot: new Uint16Array(256), posDec: new Uint16Array(115), align: new Uint16Array(16),
    len: [new Uint16Array(2), new Uint16Array(128), new Uint16Array(128), new Uint16Array(256)],
    rep: [new Uint16Array(2), new Uint16Array(128), new Uint16Array(128), new Uint16Array(256)]
  };
  // Décodeur généré (tous les bits « dépliés », variables locales) : voir l'historique git.
  function lzmaDecode(src, ip, out, outSize, lc, lp, pb) {
    var L = LZ, k;
    if ((0x300 << (lc + lp)) > L.lit.length) L.lit = new Uint16Array(0x300 << (lc + lp));
    var lit = L.lit, isMatch = L.isMatch, isRep = L.isRep, g0 = L.g0, g1 = L.g1, g2 = L.g2, rep0Long = L.rep0Long;
    var posSlot = L.posSlot, posDec = L.posDec, align = L.align;
    var Lc = L.len[0], Ll = L.len[1], Lm = L.len[2], Lh = L.len[3], Rc = L.rep[0], Rl = L.rep[1], Rm = L.rep[2], Rh = L.rep[3];
    lit.fill(1024); isMatch.fill(1024); isRep.fill(1024); g0.fill(1024); g1.fill(1024); g2.fill(1024);
    rep0Long.fill(1024); posSlot.fill(1024); posDec.fill(1024); align.fill(1024);
    for (k = 0; k < 4; k++) { L.len[k].fill(1024); L.rep[k].fill(1024); }
    var range = 0xFFFFFFFF, code = 0, v = 0, bound = 0, b = 0, m = 0, t = 0;
    ip++;  // premier octet du codeur : 0
    for (k = 0; k < 4; k++) code = code * 256 + src[ip++];
    var pbMask = (1 << pb) - 1, lpMask = (1 << lp) - 1, sh = 8 - lc;
    var state = 0, rep0 = 0, rep1 = 0, rep2 = 0, rep3 = 0, pos = 0, ps = 0, len = 0, sym = 0, base = 0;
    while (pos < outSize) {
      ps = pos & pbMask;
      v = isMatch[(state << 4) + ps]; bound = (range >>> 11) * v; if (code < bound) { range = bound; isMatch[(state << 4) + ps] = v + ((2048 - v) >>> 5); b = 0; } else { range -= bound; code -= bound; isMatch[(state << 4) + ps] = v - (v >>> 5); b = 1; } if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; }
      if (b === 0) {
        base = 0x300 * (((pos & lpMask) << lc) + ((pos > 0 ? out[pos - 1] : 0) >>> sh));
        sym = 1;
        if (state >= 7) {
          var mb = out[pos - rep0 - 1], mbit = 0;
          do {
            mbit = (mb >>> 7) & 1; mb <<= 1;
            v = lit[base + ((1 + mbit) << 8) + sym]; bound = (range >>> 11) * v; if (code < bound) { range = bound; lit[base + ((1 + mbit) << 8) + sym] = v + ((2048 - v) >>> 5); b = 0; } else { range -= bound; code -= bound; lit[base + ((1 + mbit) << 8) + sym] = v - (v >>> 5); b = 1; } if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; }
            sym = (sym << 1) | b;
            if (mbit !== b) break;
          } while (sym < 0x100);
        }
        while (sym < 0x100) { v = lit[base + sym]; bound = (range >>> 11) * v; if (code < bound) { range = bound; lit[base + sym] = v + ((2048 - v) >>> 5); b = 0; } else { range -= bound; code -= bound; lit[base + sym] = v - (v >>> 5); b = 1; } if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; } sym = (sym << 1) | b; }
        out[pos++] = sym & 0xFF;
        state = state < 4 ? 0 : (state < 10 ? state - 3 : state - 6);
        continue;
      }
      v = isRep[state]; bound = (range >>> 11) * v; if (code < bound) { range = bound; isRep[state] = v + ((2048 - v) >>> 5); b = 0; } else { range -= bound; code -= bound; isRep[state] = v - (v >>> 5); b = 1; } if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; }
      if (b) {
        v = g0[state]; bound = (range >>> 11) * v; if (code < bound) { range = bound; g0[state] = v + ((2048 - v) >>> 5); b = 0; } else { range -= bound; code -= bound; g0[state] = v - (v >>> 5); b = 1; } if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; }
        if (b === 0) {
          v = rep0Long[(state << 4) + ps]; bound = (range >>> 11) * v; if (code < bound) { range = bound; rep0Long[(state << 4) + ps] = v + ((2048 - v) >>> 5); b = 0; } else { range -= bound; code -= bound; rep0Long[(state << 4) + ps] = v - (v >>> 5); b = 1; } if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; }
          if (b === 0) {
            state = state < 7 ? 9 : 11;
            out[pos] = out[pos - rep0 - 1]; pos++;
            continue;
          }
        } else {
          var dist;
          v = g1[state]; bound = (range >>> 11) * v; if (code < bound) { range = bound; g1[state] = v + ((2048 - v) >>> 5); b = 0; } else { range -= bound; code -= bound; g1[state] = v - (v >>> 5); b = 1; } if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; }
          if (b === 0) dist = rep1;
          else {
            v = g2[state]; bound = (range >>> 11) * v; if (code < bound) { range = bound; g2[state] = v + ((2048 - v) >>> 5); b = 0; } else { range -= bound; code -= bound; g2[state] = v - (v >>> 5); b = 1; } if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; }
            if (b === 0) dist = rep2;
            else { dist = rep3; rep3 = rep2; }
            rep2 = rep1;
          }
          rep1 = rep0; rep0 = dist;
        }
        v = Rc[0]; bound = (range >>> 11) * v; if (code < bound) { range = bound; Rc[0] = v + ((2048 - v) >>> 5); b = 0; } else { range -= bound; code -= bound; Rc[0] = v - (v >>> 5); b = 1; } if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; } if (b === 0) { m = 1; for (t = 0; t < 3; t++) { v = Rl[(ps << 3) + m]; bound = (range >>> 11) * v; if (code < bound) { range = bound; Rl[(ps << 3) + m] = v + ((2048 - v) >>> 5); b = 0; } else { range -= bound; code -= bound; Rl[(ps << 3) + m] = v - (v >>> 5); b = 1; } if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; } m = (m << 1) + b; } len = m - 8; } else { v = Rc[1]; bound = (range >>> 11) * v; if (code < bound) { range = bound; Rc[1] = v + ((2048 - v) >>> 5); b = 0; } else { range -= bound; code -= bound; Rc[1] = v - (v >>> 5); b = 1; } if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; } if (b === 0) { m = 1; for (t = 0; t < 3; t++) { v = Rm[(ps << 3) + m]; bound = (range >>> 11) * v; if (code < bound) { range = bound; Rm[(ps << 3) + m] = v + ((2048 - v) >>> 5); b = 0; } else { range -= bound; code -= bound; Rm[(ps << 3) + m] = v - (v >>> 5); b = 1; } if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; } m = (m << 1) + b; } len = m - 8; len += 8; } else { m = 1; for (t = 0; t < 8; t++) { v = Rh[(0) + m]; bound = (range >>> 11) * v; if (code < bound) { range = bound; Rh[(0) + m] = v + ((2048 - v) >>> 5); b = 0; } else { range -= bound; code -= bound; Rh[(0) + m] = v - (v >>> 5); b = 1; } if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; } m = (m << 1) + b; } len = m - 256; len += 16; } }
        state = state < 7 ? 8 : 11;
      } else {
        rep3 = rep2; rep2 = rep1; rep1 = rep0;
        v = Lc[0]; bound = (range >>> 11) * v; if (code < bound) { range = bound; Lc[0] = v + ((2048 - v) >>> 5); b = 0; } else { range -= bound; code -= bound; Lc[0] = v - (v >>> 5); b = 1; } if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; } if (b === 0) { m = 1; for (t = 0; t < 3; t++) { v = Ll[(ps << 3) + m]; bound = (range >>> 11) * v; if (code < bound) { range = bound; Ll[(ps << 3) + m] = v + ((2048 - v) >>> 5); b = 0; } else { range -= bound; code -= bound; Ll[(ps << 3) + m] = v - (v >>> 5); b = 1; } if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; } m = (m << 1) + b; } len = m - 8; } else { v = Lc[1]; bound = (range >>> 11) * v; if (code < bound) { range = bound; Lc[1] = v + ((2048 - v) >>> 5); b = 0; } else { range -= bound; code -= bound; Lc[1] = v - (v >>> 5); b = 1; } if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; } if (b === 0) { m = 1; for (t = 0; t < 3; t++) { v = Lm[(ps << 3) + m]; bound = (range >>> 11) * v; if (code < bound) { range = bound; Lm[(ps << 3) + m] = v + ((2048 - v) >>> 5); b = 0; } else { range -= bound; code -= bound; Lm[(ps << 3) + m] = v - (v >>> 5); b = 1; } if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; } m = (m << 1) + b; } len = m - 8; len += 8; } else { m = 1; for (t = 0; t < 8; t++) { v = Lh[(0) + m]; bound = (range >>> 11) * v; if (code < bound) { range = bound; Lh[(0) + m] = v + ((2048 - v) >>> 5); b = 0; } else { range -= bound; code -= bound; Lh[(0) + m] = v - (v >>> 5); b = 1; } if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; } m = (m << 1) + b; } len = m - 256; len += 16; } }
        state = state < 7 ? 7 : 10;
        var slot;
        m = 1; for (t = 0; t < 6; t++) { v = posSlot[((len > 3 ? 3 : len) << 6) + m]; bound = (range >>> 11) * v; if (code < bound) { range = bound; posSlot[((len > 3 ? 3 : len) << 6) + m] = v + ((2048 - v) >>> 5); b = 0; } else { range -= bound; code -= bound; posSlot[((len > 3 ? 3 : len) << 6) + m] = v - (v >>> 5); b = 1; } if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; } m = (m << 1) + b; } slot = m - 64;
        if (slot < 4) rep0 = slot;
        else {
          var nd = (slot >>> 1) - 1, d = (2 | (slot & 1)) * Math.pow(2, nd), r = 0;
          if (slot < 14) { m = 1; r = 0; for (t = 0; t < nd; t++) { v = posDec[(d - slot) + m]; bound = (range >>> 11) * v; if (code < bound) { range = bound; posDec[(d - slot) + m] = v + ((2048 - v) >>> 5); b = 0; } else { range -= bound; code -= bound; posDec[(d - slot) + m] = v - (v >>> 5); b = 1; } if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; } m = (m << 1) + b; r |= b << t; } d += r; }
          else {
            for (k = nd - 4; k > 0; k--) {
              range = Math.floor(range / 2);
              b = code >= range ? 1 : 0;
              if (b) code -= range;
              r = r * 2 + b;
              if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; }
            }
            d += r * 16;
            m = 1; r = 0; for (t = 0; t < 4; t++) { v = align[(0) + m]; bound = (range >>> 11) * v; if (code < bound) { range = bound; align[(0) + m] = v + ((2048 - v) >>> 5); b = 0; } else { range -= bound; code -= bound; align[(0) + m] = v - (v >>> 5); b = 1; } if (range < 16777216) { range *= 256; code = code * 256 + src[ip++]; } m = (m << 1) + b; r |= b << t; }
            d += r;
          }
          rep0 = d;
        }
        if (rep0 === 0xFFFFFFFF) break;
      }
      len += 2;
      var from = pos - rep0 - 1;
      if (from < 0) throw new Error('LZMA : distance invalide');
      while (len-- > 0 && pos < outSize) out[pos++] = out[from++];
    }
    return pos;
  }

  // ------------------------------------------------------------------ deflate brut (RFC 1951)
  var LBASE = [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258];
  var LEXT = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0];
  var DBASE = [1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769, 1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577];
  var DEXT = [0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13];
  var CLORD = [16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15];
  function huffTable(lens) {  // { counts, symbols } façon puff.c
    var counts = new Uint16Array(16), offs = new Uint16Array(16), syms = new Uint16Array(lens.length), i;
    for (i = 0; i < lens.length; i++) counts[lens[i]]++;
    counts[0] = 0;
    for (i = 1; i < 16; i++) offs[i] = offs[i - 1] + counts[i - 1];
    for (i = 0; i < lens.length; i++) if (lens[i]) syms[offs[lens[i]]++] = i;
    return { counts: counts, syms: syms };
  }
  var FIXED_L, FIXED_D;
  function inflateRaw(src, outSize) {
    var out = new Uint8Array(outSize || src.length * 4 + 1024), op = 0, ip = 0, bitbuf = 0, bitcnt = 0;
    function need(n) { while (bitcnt < n) { bitbuf |= (ip < src.length ? src[ip] : 0) << bitcnt; ip++; bitcnt += 8; } }
    function bits(n) { need(n); var v = bitbuf & ((1 << n) - 1); bitbuf >>>= n; bitcnt -= n; return v; }
    function grow(n) { if (op + n > out.length) { var o = new Uint8Array(Math.max(out.length * 2, op + n)); o.set(out); out = o; } }
    function decode(h) {
      var code = 0, first = 0, index = 0;
      for (var len = 1; len < 16; len++) {
        code |= bits(1);
        var count = h.counts[len];
        if (code - count < first) return h.syms[index + (code - first)];
        index += count; first += count; first <<= 1; code <<= 1;
      }
      throw new Error('deflate : code invalide');
    }
    if (!FIXED_L) {
      var l = [], i;
      for (i = 0; i < 144; i++) l.push(8);
      for (; i < 256; i++) l.push(9);
      for (; i < 280; i++) l.push(7);
      for (; i < 288; i++) l.push(8);
      FIXED_L = huffTable(l);
      FIXED_D = huffTable(new Array(30).fill(5));
    }
    var last;
    do {
      last = bits(1);
      var type = bits(2);
      if (type === 0) {
        bitbuf = 0; bitcnt = 0;
        var len = src[ip] | src[ip + 1] << 8; ip += 4;
        grow(len); out.set(src.subarray(ip, ip + len), op); op += len; ip += len;
        continue;
      }
      var lt, dt;
      if (type === 1) { lt = FIXED_L; dt = FIXED_D; }
      else if (type === 2) {
        var nlen = bits(5) + 257, ndist = bits(5) + 1, ncode = bits(4) + 4, cl = new Array(19).fill(0), k;
        for (k = 0; k < ncode; k++) cl[CLORD[k]] = bits(3);
        var ch = huffTable(cl), lens = [];
        while (lens.length < nlen + ndist) {
          var sym = decode(ch);
          if (sym < 16) lens.push(sym);
          else if (sym === 16) { var pv = lens[lens.length - 1], r = 3 + bits(2); while (r--) lens.push(pv); }
          else if (sym === 17) { r = 3 + bits(3); while (r--) lens.push(0); }
          else { r = 11 + bits(7); while (r--) lens.push(0); }
        }
        lt = huffTable(lens.slice(0, nlen)); dt = huffTable(lens.slice(nlen));
      } else throw new Error('deflate : bloc invalide');
      for (;;) {
        var s = decode(lt);
        if (s < 256) { grow(1); out[op++] = s; }
        else if (s === 256) break;
        else {
          s -= 257;
          var ln = LBASE[s] + bits(LEXT[s]), ds = decode(dt), dist = DBASE[ds] + bits(DEXT[ds]);
          grow(ln);
          for (var q = 0; q < ln; q++) { out[op] = out[op - dist]; op++; }
        }
      }
    } while (!last);
    return out.subarray(0, op);
  }

  // ------------------------------------------------------------------ sources : BIN ou CHD
  // Un « fichier » est { name, size, read(offset, length) -> Promise<Uint8Array> }.
  function Window(file, size) {
    this.file = file; this.size = size || (16 << 20); this.start = 0; this.buf = new Uint8Array(0);
  }
  Window.prototype.get = async function (off, len) {
    if (off < this.start || off + len > this.start + this.buf.length) {
      this.start = off;
      this.buf = await this.file.read(off, Math.min(Math.max(this.size, len), this.file.size - off));
    }
    return this.buf.subarray(off - this.start, off - this.start + len);
  };

  function BinSource(file) { this.file = file; this.nsectors = Math.floor(file.size / SECTOR); this.win = new Window(file, 32 << 20); }
  BinSource.prototype.readRaw = async function (lba, n) {
    return (await this.win.get(lba * SECTOR, n * SECTOR)).slice();
  };

  function Bits(data) { this.d = data; this.pos = 0; }
  Bits.prototype.read = function (n) {
    var v = 0;
    for (var k = 0; k < n; k++) {
      var i = this.pos >> 3, byte = i < this.d.length ? this.d[i] : 0;
      v = v * 2 + ((byte >> (7 - (this.pos & 7))) & 1);
      this.pos++;
    }
    return v;
  };
  function Huffman(numcodes, maxbits, bits) {
    var numbits = maxbits >= 16 ? 5 : maxbits >= 8 ? 4 : 3, lens = new Array(numcodes).fill(0), cur = 0;
    while (cur < numcodes) {
      var nb = bits.read(numbits);
      if (nb !== 1) lens[cur++] = nb;
      else {
        nb = bits.read(numbits);
        if (nb === 1) lens[cur++] = nb;
        else { var rep = bits.read(numbits) + 3; while (rep--) lens[cur++] = nb; }
      }
    }
    var histo = new Array(33).fill(0);
    lens.forEach(function (l) { histo[l]++; });
    var start = 0;
    for (var cl = 32; cl > 0; cl--) { var nxt = (start + histo[cl]) >> 1; histo[cl] = start; start = nxt; }
    this.codes = new Map();
    for (var s = 0; s < numcodes; s++) if (lens[s]) { this.codes.set(lens[s] * 65536 + histo[lens[s]], s); histo[lens[s]]++; }
  }
  Huffman.prototype.decode = function (bits) {
    var code = 0;
    for (var l = 1; l <= 32; l++) {
      code = code * 2 + bits.read(1);
      var s = this.codes.get(l * 65536 + code);
      if (s !== undefined) return s;
    }
    throw new Error('CHD : code Huffman invalide');
  };

  function ChdSource(file) { this.file = file; this.win = new Window(file, 16 << 20); this.cache = new Map(); }
  ChdSource.prototype.open = async function () {
    var h = await this.file.read(0, 124);
    if (ascii(h, 0, 8) !== 'MComprHD' || u32be(h, 12) !== 5) throw new Error('CHD v5 attendu');
    this.codecs = [0, 1, 2, 3].map(function (i) { return ascii(h, 16 + 4 * i, 20 + 4 * i); });
    var big = function (o) { return u32be(h, o) * 4294967296 + u32be(h, o + 4); };
    this.logical = big(32); this.mapoff = big(40); this.metaoff = big(48);
    this.hunkbytes = u32be(h, 56);
    this.hunkcount = Math.ceil(this.logical / this.hunkbytes);
    var mh = await this.file.read(this.mapoff, 16);
    var mapbytes = u32be(mh, 0), firstoffs = u32be(mh, 4) * 65536 + (mh[8] << 8 | mh[9]);
    var lengthbits = mh[12], selfbits = mh[13], parentbits = mh[14];
    var bits = new Bits(await this.file.read(this.mapoff + 16, mapbytes));
    var huff = new Huffman(16, 8, bits), comp = [], rep = 0, last = 0, i;
    for (i = 0; i < this.hunkcount; i++) {
      if (rep > 0) { comp.push(last); rep--; continue; }
      var v = huff.decode(bits);
      if (v === 7) { comp.push(last); rep = 2 + huff.decode(bits); }
      else if (v === 8) { comp.push(last); rep = 2 + 16 + (huff.decode(bits) << 4); rep += huff.decode(bits); }
      else { comp.push(v); last = v; }
    }
    this.map = [];
    var cur = firstoffs, lastSelf = 0;
    for (i = 0; i < comp.length; i++) {
      var c = comp[i], length = 0, offset = 0;
      if (c <= 3) { length = bits.read(lengthbits); offset = cur; cur += length; bits.read(16); }
      else if (c === 4) { length = this.hunkbytes; offset = cur; cur += length; bits.read(16); }
      else if (c === 5) { offset = lastSelf = bits.read(selfbits); }
      else if (c === 6) { bits.read(parentbits); throw new Error('CHD avec parent non géré'); }
      else if (c === 9) { c = 5; offset = lastSelf; }
      else if (c === 10) { lastSelf++; c = 5; offset = lastSelf; }
      else throw new Error('CHD avec parent non géré');
      this.map.push([c, offset, length]);
    }
    // métadonnées : nombre de secteurs de la piste
    var off = this.metaoff, frames = 0, tracks = 0;
    while (off) {
      var m = await this.file.read(off, 24), len = m[5] << 16 | m[6] << 8 | m[7];
      var tag = ascii(m, 0, 4);
      if (tag === 'CHT2' || tag === 'CHTR') {
        var txt = ascii(await this.file.read(off + 24, len), 0, len).split('\0')[0];
        var fm = /FRAMES:(\d+)/.exec(txt);
        if (!/MODE[12]_RAW/.test(txt)) throw new Error('piste de données MODE2_RAW attendue');
        frames = +fm[1]; tracks++;
      }
      off = u32be(m, 8) * 4294967296 + u32be(m, 12);
    }
    if (tracks !== 1) throw new Error('un CHD à une seule piste est attendu');
    this.nsectors = frames;
    this.fph = this.hunkbytes / 2448;
    return this;
  };
  ChdSource.prototype.hunk = async function (hn) {
    var c = this.cache.get(hn);
    if (c) return c;
    var e = this.map[hn], res;
    if (e[0] === 5) res = await this.hunk(e[1]);
    else {
      var src = await this.win.get(e[1], e[2]), frames = this.fph;
      if (e[0] === 4) {
        var raw = new Uint8Array(frames * SECTOR);
        for (var f = 0; f < frames; f++) raw.set(src.subarray(f * 2448, f * 2448 + SECTOR), f * SECTOR);
        res = { data: raw, flags: new Uint8Array(frames) };
      } else {
        var codec = this.codecs[e[0]], eccBytes = (frames + 7) >> 3, clb = this.hunkbytes < 65536 ? 2 : 3;
        var hb = eccBytes + clb, clen = 0;
        for (var k = eccBytes; k < hb; k++) clen = clen * 256 + src[k];
        var base;
        if (codec === 'cdlz') {
          base = new Uint8Array(frames * SECTOR);
          lzmaDecode(src.subarray(hb, hb + clen), 0, base, frames * SECTOR, 3, 0, 2);
        } else if (codec === 'cdzl') {
          base = inflateRaw(src.subarray(hb, hb + clen), frames * SECTOR);
        } else throw new Error('codec CHD non géré : ' + codec);
        var flags = new Uint8Array(frames);
        for (var g = 0; g < frames; g++) flags[g] = (src[g >> 3] >> (g & 7)) & 1;
        res = { data: base, flags: flags };
      }
    }
    if (this.cache.size > 64) this.cache.clear();
    this.cache.set(hn, res);
    return res;
  };
  // ecc : régénère synchro + ECC des secteurs que chdman a allégés (sinon seules les données comptent)
  ChdSource.prototype.readRaw = async function (lba, n, ecc) {
    var out = new Uint8Array(n * SECTOR), fph = this.fph, done = 0;
    while (done < n) {
      var fr = lba + done, hn = Math.floor(fr / fph), first = fr - hn * fph;
      var h = await this.hunk(hn), k = Math.min(fph - first, n - done);
      out.set(h.data.subarray(first * SECTOR, (first + k) * SECTOR), done * SECTOR);
      if (ecc) {
        for (var i = 0; i < k; i++) if (h.flags[first + i]) {
          var o = (done + i) * SECTOR;
          for (var s = 0; s < 12; s++) out[o + s] = SYNC[s];
          fixEcc(out, o);
        }
      }
      done += k;
    }
    return out;
  };

  async function openSource(file) {
    var head = await file.read(0, 8);
    if (ascii(head, 0, 8) === 'MComprHD') return await new ChdSource(file).open();
    return new BinSource(file);
  }

  // ------------------------------------------------------------------ ISO 9660 (psxiso.py)
  function Disc(src) { this.src = src; this.nsectors = src.nsectors; }
  Disc.prototype.readUser = async function (lba, size, progress) {
    var n = Math.ceil(size / 2048), out = new Uint8Array(n * 2048), B = 4096;
    for (var s = 0; s < n; s += B) {
      var k = Math.min(B, n - s), raw = await this.src.readRaw(lba + s, k, false);
      for (var i = 0; i < k; i++) out.set(raw.subarray(i * SECTOR + 24, i * SECTOR + 24 + 2048), (s + i) * 2048);
      if (progress) progress((s + k) / n);
    }
    return out.subarray(0, size);
  };
  Disc.prototype.sector = async function (lba) {
    var r = await this.src.readRaw(lba, 1, false);
    return r.slice(24, 24 + (r[18] & 0x20 ? 2324 : 2048));
  };
  Disc.prototype.files = async function () {
    if (this._files) return this._files;
    var files = new Map(), self = this;
    async function walk(lba, size, prefix) {
      var data = await self.readUser(lba, size), i = 0;
      while (i < data.length) {
        var ln = data[i];
        if (ln === 0) { i = (Math.floor(i / 2048) + 1) * 2048; continue; }
        var elba = u32(data, i + 2), esize = u32(data, i + 10), flags = data[i + 25], nlen = data[i + 32];
        var name = ascii(data, i + 33, i + 33 + nlen).split(';')[0];
        if (name !== '\x00' && name !== '\x01') {
          var path = prefix ? prefix + '/' + name : name;
          if (flags & 2) await walk(elba, esize, path);
          else files.set(path, [elba, esize]);
        }
        i += ln;
      }
    }
    var pvd = await this.readUser(16, 2048);
    await walk(u32(pvd, 156 + 2), u32(pvd, 156 + 10), '');
    this._files = files;
    return files;
  };
  Disc.prototype.readFile = async function (path, progress) {
    var f = (await this.files()).get(path);
    if (!f) throw new Error('fichier absent : ' + path);
    return await this.readUser(f[0], f[1], progress);
  };

  // ------------------------------------------------------------------ VOX / DEMO (vox.py)
  var INIT = 0x10, SOUND = 0x01, CAPS1 = 0x03, CAPS2 = 0x06, END = 0xF0;
  function blocks(data, start) {
    var out = [], i = start;
    while (i + 3 <= data.length) {
      var code = data[i], size = u16(data, i + 1);
      if (size === 0) return out;
      out.push([code, i, size]);
      if (code === END) return out;
      i += size;
    }
    return out;
  }
  function banks(data) {
    var out = [], i = 0;
    while (i + 8 <= data.length) {
      if (data[i] !== INIT || u16(data, i + 1) !== 8) { i += 2048; continue; }
      var end = i, bl = blocks(data, i);
      if (bl.length) { var l = bl[bl.length - 1]; end = l[1] + l[2]; }
      out.push([i, end]);
      i = Math.ceil(end / 2048) * 2048;
    }
    return out;
  }
  function captionCount(data, off) {
    var j = off + u16(data, off + 14) + 4, n = 0;
    for (;;) { var size = u32(data, j); n++; if (size === 0) return n; j += size; }
  }
  function bankInfo(data, start) {
    var snd = 0, ncap = 0;
    blocks(data, start).forEach(function (b) {
      if (b[0] === SOUND) snd += b[2] - 4;
      else if (b[0] === CAPS1 || b[0] === CAPS2) ncap += captionCount(data, b[1]);
    });
    return { sound: snd, ncap: ncap };
  }

  // ------------------------------------------------------------------ RADIO.DAT (radio.py)
  function radioScan(data) {
    var voices = [], i = 0;
    while (i + 4 <= data.length) {
      if (data[i] !== 0xFF) { i++; continue; }
      var op = data[i + 1], size = data[i + 2] << 8 | data[i + 3];
      if (op === 2 && size >= 6) {
        var code = u32be(data, i + 4), end = i + 2 + size, talks = [], j = i + 8;
        while (j < end) {
          if (data[j] === 0xFF && data[j + 1] === 1) { talks.push(j); j += 2 + (data[j + 2] << 8 | data[j + 3]); }
          else j++;
        }
        voices.push([i, code, talks]);
        i = end;
      } else i++;
    }
    return voices;
  }

  // ------------------------------------------------------------------ appariement (voxalign.py)
  var GAP = 2.5;
  function bankTable(vox, radio) {
    var codec = new Set(radioScan(radio).map(function (v) { return v[1]; }));
    return banks(vox).map(function (b) {
      var inf = bankInfo(vox, b[0]), sec = b[0] / 2048;
      return { sec: sec, md5: digest(vox, b[0], b[1]), snd: inf.sound, ncap: inf.ncap, R: codec.has(sec) };
    });
  }
  function soundTestTable(st) {
    var out = new Map();
    for (var i = 0; i + 16 <= st.length;) {
      if (st[i] === 7 && st[i + 1] === 9 && st[i + 2] === 0x76 && st[i + 3] === 0x63 && st[i + 10] === 0 && st[i + 11] === 9) {
        var ok = true;
        for (var k = 4; k < 10; k++) if (st[i + k] < 0x30 || st[i + k] > 0x39) ok = false;
        if (ok) { out.set(ascii(st, i + 2, i + 10), u32be(st, i + 12)); i += 16; continue; }
      }
      i++;
    }
    return out;
  }
  function cost(a, b) {
    var c = a.R !== b.R ? 3.0 : 0.0;
    if (a.snd && b.snd) c += Math.abs(Math.log(a.snd / b.snd)) * 4;
    else if (a.snd !== b.snd) c += 3;
    return c + Math.abs(a.ncap - b.ncap) * 0.5 / (1 + Math.pow(Math.min(a.ncap, b.ncap), 0.5));
  }
  function nw(n, m, pairCost) {  // Needleman-Wunsch -> P (0 diag, 1 haut, 2 gauche)
    var P = new Int8Array((n + 1) * (m + 1)), prev = new Float64Array(m + 1), row = new Float64Array(m + 1), i, j;
    for (j = 0; j <= m; j++) { prev[j] = j * GAP; P[j] = 2; }
    P[0] = 0;
    for (i = 1; i <= n; i++) {
      row[0] = i * GAP; P[i * (m + 1)] = 1;
      for (j = 1; j <= m; j++) {
        var o0 = prev[j - 1] + pairCost(i - 1, j - 1), o1 = prev[j] + GAP, o2 = row[j - 1] + GAP, k, v;
        if (o0 <= o1 && o0 <= o2) { k = 0; v = o0; } else if (o1 <= o2) { k = 1; v = o1; } else { k = 2; v = o2; }
        row[j] = v; P[i * (m + 1) + j] = k;
      }
      var t = prev; prev = row; row = t;
    }
    return P;
  }
  function dp(F, U) {
    var n = F.length, m = U.length, P = nw(n, m, function (i, j) { return cost(F[i], U[j]); });
    var out = new Map(), i = n, j = m;
    while (i > 0 || j > 0) {
      var k = P[i * (m + 1) + j];
      if (k === 0) { out.set(i - 1, j - 1); i--; j--; } else if (k === 1) i--; else j--;
    }
    return out;
  }
  function bisectLeft(a, x) { var lo = 0, hi = a.length; while (lo < hi) { var mid = (lo + hi) >> 1; if (a[mid] < x) lo = mid + 1; else hi = mid; } return lo; }
  function increasing(pairs) {
    var items = Array.from(pairs.entries()).sort(function (a, b) { return a[0] - b[0]; });
    if (!items.length) return new Map();
    var tails = [], tidx = [], prev = new Array(items.length).fill(-1);
    items.forEach(function (it, k) {
      var p = bisectLeft(tails, it[1]);
      if (p === tails.length) { tails.push(it[1]); tidx.push(k); } else { tails[p] = it[1]; tidx[p] = k; }
      prev[k] = p ? tidx[p - 1] : -1;
    });
    var out = new Map(), k = tidx[tidx.length - 1];
    while (k >= 0) { out.set(items[k][0], items[k][1]); k = prev[k]; }
    return out;
  }
  function fill(F, U, anchors) {
    var out = new Map(anchors), prev = [-1, -1];
    var list = Array.from(anchors.entries()).sort(function (a, b) { return a[0] - b[0] || a[1] - b[1]; });
    list.push([F.length, U.length]);
    list.forEach(function (ab) {
      var a = ab[0], b = ab[1];
      if (a - prev[0] > 1 && b - prev[1] > 1) {
        dp(F.slice(prev[0] + 1, a), U.slice(prev[1] + 1, b)).forEach(function (y, x) { out.set(prev[0] + 1 + x, prev[1] + 1 + y); });
      }
      prev = [a, b];
    });
    return out;
  }
  function voiceVotes(F, U, al, radioFr, radioUk) {
    var sf = new Map(), su = new Map();
    F.forEach(function (b, i) { sf.set(b.sec, i); });
    U.forEach(function (b, i) { su.set(b.sec, i); });
    var vf = [], vu = [];
    radioScan(radioFr).forEach(function (v) { if (v[1] && sf.has(v[1])) vf.push(sf.get(v[1])); });
    radioScan(radioUk).forEach(function (v) { if (v[1] && su.has(v[1])) vu.push(su.get(v[1])); });
    var n = vf.length, m = vu.length;
    var P = nw(n, m, function (i, j) { var a = vf[i], b = vu[j]; return al.get(a) === b ? 0.0 : cost(F[a], U[b]) + 0.5; });
    var votes = new Map(), i = n, j = m;
    while (i > 0 && j > 0) {
      var k = P[i * (m + 1) + j];
      if (k === 0) {
        var a = vf[i - 1], b = vu[j - 1];
        if (!votes.has(a)) votes.set(a, new Map());
        var c = votes.get(a); c.set(b, (c.get(b) || 0) + 1);
        i--; j--;
      } else if (k === 1) i--; else j--;
    }
    return votes;
  }
  function align(F, U, anchors, radioFr, radioUk) {
    var al = fill(F, U, increasing(anchors));
    voiceVotes(F, U, al, radioFr, radioUk).forEach(function (cnt, a) {
      var best = null, total = 0;
      cnt.forEach(function (k, b) { total += k; if (!best || k > best[1]) best = [b, k]; });
      if (!al.has(a) && best[1] >= 2 && best[1] === total) al.set(a, best[0]);
    });
    return al;
  }
  function anchorsDisc2(F2, U2, tableFr, tableUk) {
    var sf = new Map(), su = new Map(), out = new Map();
    F2.forEach(function (b, i) { sf.set(b.sec, i); });
    U2.forEach(function (b, i) { su.set(b.sec, i); });
    tableFr.forEach(function (c, name) {
      if (tableUk.has(name) && sf.has(c) && su.has(tableUk.get(name))) out.set(sf.get(c), su.get(tableUk.get(name)));
    });
    return out;
  }
  function anchorsDisc1(F1, U1, F2, U2, pairs2) {
    var count = new Map();
    [F1, U1, F2, U2].forEach(function (t) { t.forEach(function (b) { count.set(b.md5, (count.get(b.md5) || 0) + 1); }); });
    var f2 = new Map(), u1 = new Map(), out = new Map();
    F2.forEach(function (b, i) { f2.set(b.md5, i); });
    U1.forEach(function (b, i) { u1.set(b.md5, i); });
    F1.forEach(function (b, i) {
      if (count.get(b.md5) > 4) return;
      var j2 = f2.get(b.md5);
      if (j2 !== undefined && pairs2.has(j2)) {
        var k = u1.get(U2[pairs2.get(j2)].md5);
        if (k !== undefined) out.set(i, k);
      }
    });
    return out;
  }

  // ------------------------------------------------------------------ nouveau VOX.DAT (vox_vostfr.py)
  var JIMAKU_MAX = 4088;
  function captionBlock(data, off) {
    var size = u24(data, off + 1), b = data.subarray(off + 4, off + size);
    var start = u32(b, 0), end = u32(b, 4), lipOff = u16(b, 8), subOff = u16(b, 10), fontOff = u32(b, 12);
    var caps = [], j = subOff;
    for (;;) {
      var nxt = u32(b, j), t = u32(b, j + 4), dur = u32(b, j + 8), z = b.indexOf(0, j + 16);
      var txt = b.subarray(j + 16, z);
      if (!(nxt === 0 && t === 0 && dur === 0 && !txt.length && !caps.length)) caps.push([t, dur, txt]);
      if (nxt === 0) break;
      j += nxt;
    }
    return { start: start, end: end, lips: b.subarray(lipOff, subOff), caps: caps, font: b.subarray(fontOff) };
  }
  function pad4(a) { var p = (4 - a.length % 4) % 4; if (!p) return a; var o = new Uint8Array(a.length + p); o.set(a); return o; }
  function encodeBlock(start, end, lips, caps, font) {
    lips = pad4(lips);
    var ents = caps.map(function (c, k) {
      var body = new Uint8Array(c[2].length + 1); body.set(c[2]);
      body = pad4(body);
      var e = new Uint8Array(16 + body.length);
      w32(e, 0, k + 1 < caps.length ? 16 + body.length : 0); w32(e, 4, c[0]); w32(e, 8, c[1]); w32(e, 12, 0);
      e.set(body, 16);
      return e;
    });
    if (!ents.length) ents = [new Uint8Array(20)];
    var sub = concat(ents);
    font = pad4(font);
    var subOff = 16 + lips.length, bodyLen = 16 + lips.length + sub.length + font.length;
    var out = new Uint8Array(4 + bodyLen);
    out[0] = CAPS1; out[1] = (bodyLen + 4) & 255; out[2] = ((bodyLen + 4) >> 8) & 255; out[3] = ((bodyLen + 4) >> 16) & 255;
    w32(out, 4, start); w32(out, 8, end);
    out[12] = 16; out[13] = 0; out[14] = subOff & 255; out[15] = subOff >> 8;
    w32(out, 16, subOff + sub.length);
    out.set(lips, 20); out.set(sub, 20 + lips.length); out.set(font, 20 + lips.length + sub.length);
    return out;
  }
  function warp(fr, uk) {
    if (fr.length === uk.length) return uk.map(function (c) { return [c[0], c[1]]; });
    if (!fr.length || !uk.length) return fr.map(function (c) { return [c[0], c[1]]; });
    var f0 = fr[0][0], f1 = Math.max.apply(null, fr.map(function (c) { return c[0] + c[1]; }));
    var u0 = uk[0][0], u1 = Math.max.apply(null, uk.map(function (c) { return c[0] + c[1]; }));
    var pf = fr.map(function (c) { return (c[0] - f0) / Math.max(f1 - f0, 1); });
    var pu = uk.map(function (c) { return (c[0] - u0) / Math.max(u1 - u0, 1); });
    var tol = 0.06, n = fr.length, m = uk.length, i, j;
    var D = [], P = [];
    for (i = 0; i <= n; i++) { D.push(new Float64Array(m + 1)); P.push(new Int8Array(m + 1)); }
    for (i = 0; i <= n; i++) {
      for (j = 0; j <= m; j++) {
        if (i === 0 && j === 0) continue;
        var bv = 1e9, bk = 0;
        var cand = function (v, k) { if (v < bv || (v === bv && k < bk)) { bv = v; bk = k; } };
        if (i && j && Math.abs(pf[i - 1] - pu[j - 1]) < tol) cand(D[i - 1][j - 1] + Math.abs(pf[i - 1] - pu[j - 1]), 0);
        if (i) cand(D[i - 1][j] + tol, 1);
        if (j) cand(D[i][j - 1] + tol, 2);
        D[i][j] = bv; P[i][j] = bk;
      }
    }
    var pts = [];
    i = n; j = m;
    while (i || j) {
      var k = P[i][j];
      if (k === 0) { pts.push([fr[i - 1][0], uk[j - 1][0]]); i--; j--; } else if (k === 1) i--; else j--;
    }
    pts.push([f0, u0], [f1, u1]);
    var seen = new Set();
    pts = pts.filter(function (p) { var key = p[0] + ',' + p[1]; if (seen.has(key)) return false; seen.add(key); return true; })
      .sort(function (a, b) { return a[0] - b[0] || a[1] - b[1]; });
    function w(x) {
      for (var q = 0; q + 1 < pts.length; q++) {
        var a = pts[q][0], b = pts[q][1], c = pts[q + 1][0], d = pts[q + 1][1];
        if (x <= c) return b + (x - a) * (d - b) / Math.max(c - a, 1);
      }
      return pts[pts.length - 1][1] + x - pts[pts.length - 1][0];
    }
    return fr.map(function (c, k) {
      var s = pyRound(w(c[0])), e = pyRound(w(c[0] + c[1]));
      if (k + 1 < fr.length) e = Math.min(e, pyRound(w(fr[k + 1][0])) - 1);
      return [s, Math.max(e - s, 1)];
    });
  }
  function buildBank(fr, fs, uk, us) {
    var frBlocks = blocks(fr, fs).filter(function (b) { return b[0] === CAPS1; }).map(function (b) { return captionBlock(fr, b[1]); });
    var frCaps = [];
    frBlocks.forEach(function (b) { b.caps.forEach(function (c) { frCaps.push(c); }); });
    var fb = frBlocks.filter(function (b) { return b.font.length; })[0];
    var font = fb ? fb.font : new Uint8Array(0);
    var ukList = blocks(uk, us);
    var ukBlocks = ukList.filter(function (b) { return b[0] === CAPS1; }).map(function (b) { return [b[1], captionBlock(uk, b[1])]; });
    if (!ukBlocks.length) {
      if (frCaps.length) return null;
      var l = ukList[ukList.length - 1];
      return uk.subarray(us, l[1] + l[2]);
    }
    var ukCaps = [];
    ukBlocks.forEach(function (ob, n) { ob[1].caps.forEach(function (c) { ukCaps.push([c, n]); }); });
    var times = warp(frCaps, ukCaps.map(function (x) { return x[0]; }));
    var per = ukBlocks.map(function () { return []; });
    frCaps.forEach(function (c, k) {
      var t = times[k][0], d = times[k][1], n;
      if (frCaps.length === ukCaps.length) n = ukCaps[k][1];
      else {
        n = ukBlocks.length - 1;
        for (var q = 0; q < ukBlocks.length; q++) if (t < ukBlocks[q][1].end) { n = q; break; }
      }
      var b = ukBlocks[n][1];
      t = Math.max(t, b.start);
      d = Math.max(1, Math.min(d, b.end - t));
      per[n].push([t, d, c[2]]);
    });
    var repl = new Map();
    ukBlocks.forEach(function (ob, n) {
      var blk = encodeBlock(ob[1].start, ob[1].end, ob[1].lips, per[n], font);
      if (blk.length - 4 > JIMAKU_MAX) throw new Error('bloc de sous-titres trop gros (' + blk.length + ' octets)');
      repl.set(ob[0], blk);
    });
    return concat(ukList.map(function (b) { return repl.get(b[1]) || uk.subarray(b[1], b[1] + b[2]); }));
  }
  function buildVox(fr, uk, mapping) {
    var bf = banks(fr), bu = banks(uk), parts = [], len = 0, secmap = new Map(), kept = 0;
    bf.forEach(function (b, i) {
      var bank = null;
      if (mapping.has(i)) bank = buildBank(fr, b[0], uk, bu[mapping.get(i)][0]);
      if (!bank) { bank = fr.subarray(b[0], b[1]); kept++; }
      secmap.set(b[0] / 2048, len / 2048);
      parts.push(bank); len += bank.length;
      var p = (2048 - len % 2048) % 2048;
      if (p) { parts.push(new Uint8Array(p)); len += p; }
    });
    return { data: concat(parts, len), secmap: secmap, kept: kept };
  }
  function renumberRadio(data, secmap) {
    var out = data.slice(), n = 0;
    radioScan(data).forEach(function (v) {
      if (secmap.has(v[1])) { w32be(out, v[0] + 4, secmap.get(v[1])); if (v[1] !== secmap.get(v[1])) n++; }
    });
    return { data: out, n: n };
  }
  function stageTable(st) {
    var size = u32(st, 0), ent = [];
    for (var k = 0; k < Math.floor(size / 12); k++) {
      var nm = ascii(st, 4 + 12 * k, 12 + 12 * k).replace(/\0+$/, '');
      ent.push([nm, u32(st, 12 + 12 * k) * 2048]);
    }
    var out = new Map();
    ent.forEach(function (e, k) { out.set(e[0], [e[1], k + 1 < ent.length ? ent[k + 1][1] : st.length]); });
    return out;
  }
  function gclInts(st, a, b, wanted) {
    var out = [];
    for (var i = a; i < b - 4; i++) {
      var c = st[i];
      if (c === 9 || c === 10) { var v = u32be(st, i + 1); if (v && wanted.has(v)) out.push([i, v]); }
    }
    return out;
  }
  function renumberStage(stFr, stUk, secmap, frToUk) {
    var out = stFr.slice(), tf = stageTable(stFr), tu = stageTable(stUk), ukSecs = new Set(frToUk.values()), done = 0, skipped = 0;
    tf.forEach(function (ab, name) {
      if (!tu.has(name)) return;
      var r = tu.get(name), ukVals = new Set(gclInts(stUk, r[0], r[1], ukSecs).map(function (x) { return x[1]; }));
      gclInts(stFr, ab[0], ab[1], secmap).forEach(function (x) {
        if (ukVals.has(frToUk.get(x[1]))) { w32be(out, x[0] + 1, secmap.get(x[1])); done++; } else skipped++;
      });
    });
    return { data: out, done: done, skipped: skipped };
  }

  // ------------------------------------------------------------------ cinématiques (demo_vostfr.py)
  function patchDemo(fr, uk) {  // modifie fr en place
    var bf = banks(fr), bu = banks(uk), swapped = 0;
    if (bf.length !== bu.length) throw new Error('DEMO.DAT : nombre de cinématiques différent');
    bf.forEach(function (b, n) {
      var sf = blocks(fr, b[0]).filter(function (x) { return x[0] === SOUND; });
      var su = blocks(uk, bu[n][0]).filter(function (x) { return x[0] === SOUND; });
      if (sf.length !== su.length || sf.some(function (x, k) { return x[2] !== su[k][2]; })) throw new Error('DEMO.DAT : blocs son incompatibles, cinématique ' + n);
      sf.forEach(function (x, k) {
        var a = fr.subarray(x[1] + 4, x[1] + x[2]), c = uk.subarray(su[k][1] + 4, su[k][1] + x[2]);
        for (var q = 0; q < a.length; q++) if (a[q] !== c[q]) { a.set(c); swapped++; break; }
      });
    });
    return { n: bf.length, swapped: swapped };
  }

  // ------------------------------------------------------------------ options (docs/patches.js)
  function applyRuns(data, runs) {
    runs.forEach(function (r) {
      var hx = r[1];
      for (var k = 0; k < hx.length; k += 2) data[r[0] + k / 2] = parseInt(hx.substr(k, 2), 16);
    });
  }

  // ------------------------------------------------------------------ reconstruction de l'image (isorebuild.py)
  async function rebuild(disc, replace, writer, progress) {
    var files = await disc.files(), order = Array.from(files.entries()).sort(function (a, b) { return a[1][0] - b[1][0]; });
    var nsec = function (size) { return Math.max(1, Math.ceil(size / 2048)); };
    var nw_ = new Map(), delta = 0;
    order.forEach(function (e) {
      var path = e[0], lba = e[1][0], size = e[1][1], rep = replace.has(path);
      var nsize = rep ? replace.get(path).length : size;
      nw_.set(path, [lba + delta, nsize]);
      if (rep) delta += nsec(nsize) - nsec(size);
    });
    var firstMove = disc.nsectors;
    files.forEach(function (v, p) { if (nw_.get(p)[0] !== v[0]) firstMove = Math.min(firstMove, v[0]); });
    // répertoires et descripteur de volume à corriger
    var patches = new Map();
    async function sector(lba) { if (!patches.has(lba)) patches.set(lba, await disc.sector(lba)); return patches.get(lba); }
    var pvd = await disc.sector(16), root = pvd.subarray(156, 190);
    var todo = [[u32(root, 2), u32(root, 10), '']];
    while (todo.length) {
      var t = todo.pop(), dl = t[0], dsize = t[1], prefix = t[2];
      if (dl + Math.ceil(dsize / 2048) > firstMove) throw new Error('un répertoire se trouve après un fichier déplacé');
      for (var s = 0; s < Math.ceil(dsize / 2048); s++) {
        var data = await disc.sector(dl + s), i = 0;
        while (i < 2048 && data[i]) {
          var ln = data[i], elba = u32(data, i + 2), esize = u32(data, i + 10), nlen = data[i + 32];
          var name = ascii(data, i + 33, i + 33 + nlen).split(';')[0], isdir = data[i + 25] & 2;
          var path = prefix ? prefix + '/' + name : name;
          if (isdir && name !== '\x00' && name !== '\x01' && elba !== dl) todo.push([elba, esize, path]);
          if (!isdir && nw_.has(path)) {
            var nv = nw_.get(path);
            if (nv[0] !== elba || nv[1] !== esize) {
              var sd = await sector(dl + s);
              w32(sd, i + 2, nv[0]); w32be(sd, i + 6, nv[0]); w32(sd, i + 10, nv[1]); w32be(sd, i + 14, nv[1]);
            }
          }
          i += ln;
        }
      }
    }
    var vol = u32(pvd, 80) + delta, p16 = await sector(16);
    w32(p16, 80, vol); w32be(p16, 84, vol);

    var total = disc.nsectors + delta, written = 0, B = 4096;
    async function emit(buf) { await writer.write(buf); written += buf.length / SECTOR; if (progress) progress(written / total); }
    async function copyRaw(lba, count, newLba) {
      for (var st = 0; st < count; st += B) {
        var k = Math.min(B, count - st), buf = await disc.src.readRaw(lba + st, k, true);
        for (var q = 0; q < k; q++) {
          var o = q * SECTOR, at = lba + st + q;
          if (newLba !== lba) setMsf(buf, o, newLba + st + q);
          if (patches.has(at)) { buf.set(patches.get(at), o + 24); fixForm1(buf, o); }
        }
        await emit(buf);
      }
    }
    async function changed(lba, data, dstLba) {
      var n = Math.ceil(data.length / 2048);
      for (var st = 0; st < n; st += B) {
        var k = Math.min(B, n - st), buf = await disc.src.readRaw(lba + st, k, true);
        for (var q = 0; q < k; q++) {
          var o = q * SECTOR, nd = new Uint8Array(2048), a = (st + q) * 2048;
          nd.set(data.subarray(a, Math.min(a + 2048, data.length)));
          if (dstLba !== lba) setMsf(buf, o, dstLba + st + q);
          var diff = false;
          for (var x = 0; x < 2048; x++) if (buf[o + 24 + x] !== nd[x]) { diff = true; break; }
          if (diff) { buf.set(nd, o + 24); fixForm1(buf, o); }
        }
        await emit(buf);
      }
    }
    async function form1(data, firstLba, sub, subLast) {
      var n = Math.max(1, Math.ceil(data.length / 2048));
      for (var st = 0; st < n; st += B) {
        var k = Math.min(B, n - st), buf = new Uint8Array(k * SECTOR);
        for (var q = 0; q < k; q++) {
          var o = q * SECTOR, a = (st + q) * 2048, sb = st + q === n - 1 ? subLast : sub;
          for (var y = 0; y < 12; y++) buf[o + y] = SYNC[y];
          buf[o + 15] = 2;
          setMsf(buf, o, firstLba + st + q);
          buf.set(sb, o + 16); buf.set(sb, o + 20);
          buf.set(data.subarray(a, Math.min(a + 2048, data.length)), o + 24);
          fixForm1(buf, o);
        }
        await emit(buf);
      }
    }
    var pos = 0;
    for (var e = 0; e < order.length; e++) {
      var path = order[e][0], lba = order[e][1][0], size = order[e][1][1], nv = nw_.get(path);
      if (lba > pos) await copyRaw(pos, lba - pos, pos + (nv[0] - lba));
      var ns = nsec(size);
      if (!replace.has(path)) await copyRaw(lba, ns, nv[0]);
      else if (Math.ceil(nv[1] / 2048) === ns) await changed(lba, replace.get(path), nv[0]);
      else {
        var first = await disc.src.readRaw(lba, 1, false), last = await disc.src.readRaw(lba + ns - 1, 1, false);
        await form1(replace.get(path), nv[0], first.slice(16, 20), last.slice(16, 20));
      }
      pos = lba + ns;
    }
    if (pos < disc.nsectors) await copyRaw(pos, disc.nsectors - pos, pos + delta);
    return { files: nw_, sectors: total };
  }

  // ------------------------------------------------------------------ identification des disques
  var IDS = { 'SLES_015.06': 'FR1', 'SLES_115.06': 'FR2', 'SLES_013.70': 'UK1', 'SLES_113.70': 'UK2' };
  async function identify(file) {
    var src = await openSource(file), disc = new Disc(src), files = await disc.files();
    var cnf = files.get('SYSTEM.CNF');
    if (!cnf) throw new Error('pas un disque PlayStation');
    var txt = ascii(await disc.readFile('SYSTEM.CNF'), 0, cnf[1]);
    var m = /cdrom:\\?([A-Z0-9_.]+)/i.exec(txt), id = m && IDS[m[1].toUpperCase()];
    return { id: id || null, exe: m ? m[1] : '?', disc: disc };
  }

  // ------------------------------------------------------------------ fabrication complète (build.py)
  // discs : { FR1, UK1, FR2, UK2 } (objets Disc) ; opts : ['carre', 'm9', ...] ;
  // openWriter(nom) -> { write(Uint8Array), close() } ; log(texte) ; progress(étape, fraction)
  async function build(discs, opts, openWriter, log, progress) {
    var PATCHES = G.MGS_PATCHES;
    log = log || function () {};
    progress = progress || function () {};
    var both = discs.FR2 && discs.UK2, tab = {}, keep = {};
    var order = both ? ['2', '1'] : ['1'];
    if (!discs.FR1 || !discs.UK1) order = ['2'];
    for (var oi = 0; oi < order.length; oi++) {
      var d = order[oi];
      for (var side of ['FR', 'UK']) {
        var disc = discs[side + d], label = side + d;
        progress('Lecture ' + label, 0);
        var vox = await disc.readFile('MGS/VOX.DAT', function (f) { progress('Lecture ' + label + ' : VOX.DAT', f); });
        var radio = await disc.readFile('MGS/RADIO.DAT');
        var stage = await disc.readFile('MGS/STAGE.DIR', function (f) { progress('Lecture ' + label + ' : STAGE.DIR', f); });
        tab[label] = { banks: bankTable(vox, radio), names: soundTestTable(stage) };
        if (oi === order.length - 1) keep[label] = { vox: vox, radio: radio, stage: stage };
        log(label + ' : ' + tab[label].banks.length + ' banques VOX');
      }
    }
    var anchors = { '1': new Map(), '2': new Map() };
    if (both) {
      anchors['2'] = anchorsDisc2(tab.FR2.banks, tab.UK2.banks, tab.FR2.names, tab.UK2.names);
      if (discs.FR1) anchors['1'] = anchorsDisc1(tab.FR1.banks, tab.UK1.banks, tab.FR2.banks, tab.UK2.banks, anchors['2']);
    }
    var outputs = [];
    for (var bi = order.length - 1; bi >= 0; bi--) {
      d = order[bi];
      var fr = discs['FR' + d], uk = discs['UK' + d], F = tab['FR' + d].banks, U = tab['UK' + d].banks;
      var k = keep['FR' + d] ? [keep['FR' + d], keep['UK' + d]] : null;
      delete keep['FR' + d]; delete keep['UK' + d];
      log('Disque ' + d);
      var files = await fr.files();
      var exeName = files.has('MGS/MGS1.EXE') ? 'MGS/MGS1.EXE' : 'MGS/MGS2.EXE';
      var rep = new Map();
      progress('Disque ' + d + ' : cinématiques', 0);
      var demo = await fr.readFile('MGS/DEMO.DAT', function (f) { progress('Disque ' + d + ' : DEMO.DAT FR', f); });
      var demoUk = await uk.readFile('MGS/DEMO.DAT', function (f) { progress('Disque ' + d + ' : DEMO.DAT UK', f); });
      var dr = patchDemo(demo, demoUk);
      demoUk = null;
      rep.set('MGS/DEMO.DAT', demo);
      log('  DEMO.DAT : ' + dr.n + ' cinématiques, ' + dr.swapped + ' blocs son anglais');
      var voxFr, voxUk, radioFr, radioUk, stFr, stUk;
      if (k) { voxFr = k[0].vox; radioFr = k[0].radio; stFr = k[0].stage; voxUk = k[1].vox; radioUk = k[1].radio; stUk = k[1].stage; }
      else {
        progress('Disque ' + d + ' : relecture', 0);
        voxFr = await fr.readFile('MGS/VOX.DAT', function (f) { progress('Disque ' + d + ' : VOX.DAT FR', f); });
        voxUk = await uk.readFile('MGS/VOX.DAT', function (f) { progress('Disque ' + d + ' : VOX.DAT UK', f); });
        radioFr = await fr.readFile('MGS/RADIO.DAT'); radioUk = await uk.readFile('MGS/RADIO.DAT');
        stFr = await fr.readFile('MGS/STAGE.DIR'); stUk = await uk.readFile('MGS/STAGE.DIR');
      }
      progress('Disque ' + d + ' : appariement des voix', 0);
      await new Promise(function (r) { setTimeout(r, 0); });
      var mapping = align(F, U, anchors[d], radioFr, radioUk);
      var alone = F.map(function (_, i) { return i; }).filter(function (i) { return !mapping.has(i); });
      log('  VOX.DAT : ' + mapping.size + '/' + F.length + ' banques appariées (FR seules : ' + alone.join(', ') + ')');
      progress('Disque ' + d + ' : nouveau VOX.DAT', 0);
      await new Promise(function (r) { setTimeout(r, 0); });
      var nv = buildVox(voxFr, voxUk, mapping);
      voxFr = voxUk = null;
      rep.set('MGS/VOX.DAT', nv.data);
      log('  VOX.DAT : ' + nv.data.length / 2048 + ' secteurs, ' + nv.kept + ' banque(s) gardée(s) en français');
      var rr = renumberRadio(radioFr, nv.secmap);
      rep.set('MGS/RADIO.DAT', rr.data);
      log('  RADIO.DAT : ' + rr.n + ' commandes VOICE renumérotées');
      var frToUk = new Map();
      mapping.forEach(function (b, a) { frToUk.set(F[a].sec, U[b].sec); });
      var stageCrc = opts.length ? crc32(stFr) : 0;
      var rs = renumberStage(stFr, stUk, nv.secmap, frToUk);
      stFr = stUk = null;
      log('  STAGE.DIR : ' + rs.done + ' codes VOX renumérotés (' + rs.skipped + ' faux positifs ignorés)');
      if (opts.length) {
        var pd = PATCHES && PATCHES.discs[d];
        if (!pd) throw new Error('patches.js manquant');
        var exe = await fr.readFile(exeName);
        if (crc32(exe) !== pd.exeCrc || stageCrc !== pd.stageCrc) throw new Error('disque ' + d + ' : version du jeu inattendue pour les options');
        PATCHES.order.forEach(function (o) {
          if (opts.indexOf(o) < 0) return;
          applyRuns(exe, pd.options[o].exe);
          applyRuns(rs.data, pd.options[o].stage);
          log('  option ' + o);
        });
        rep.set(exeName, exe);
      }
      rep.set('MGS/STAGE.DIR', rs.data);
      var name = 'Metal Gear Solid (VOSTFR) (Disc ' + d + ')';
      var writer = await openWriter(name + '.bin');
      progress('Disque ' + d + ' : écriture de l\'image', 0);
      var res = await rebuild(fr, rep, writer, function (f) { progress('Disque ' + d + ' : écriture de l\'image', f); });
      await writer.close();
      rep = null;
      var cue = 'FILE "' + name + '.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n';
      var cw = await openWriter(name + '.cue');
      await cw.write(new TextEncoder().encode(cue)); await cw.close();
      log('  ' + name + '.bin : ' + res.sectors + ' secteurs');
      outputs.push(name + '.cue');
    }
    outputs.sort();
    if (outputs.length === 2) {
      var mw = await openWriter('Metal Gear Solid (VOSTFR).m3u');
      await mw.write(new TextEncoder().encode(outputs.join('\n') + '\n')); await mw.close();
    }
    return outputs;
  }

  G.MGSVOSTFR = {
    identify: identify, openSource: openSource, Disc: Disc, build: build,
    _test: { lzmaDecode: lzmaDecode, crc32: crc32, fixForm1: fixForm1, banks: banks, bankTable: bankTable, align: align }
  };
})(typeof window !== 'undefined' ? window : globalThis);
