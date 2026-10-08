#!/usr/bin/env node
/* Builds data/lemmas.json, the list of related word forms that the page's search uses.
 *
 * Usage:  npm install --no-save wink-lemmatizer@3.0.4  and then  node scripts/build-lemmas.js
 *
 * It reads the words in the course titles, special topics and catalog descriptions, asks wink-lemmatizer
 * (a WordNet based tool) for the base form of each word, and keeps only the words whose base form differs
 * from the word itself, for example studies > study, women > woman, taught > teach.
 * The page folds accents and lowercases text the same way, so the keys here are plain a to z words.
 * If this step fails, the site keeps its last lemmas.json, and search still finds exact words.
 */
const fs = require('fs');
const path = require('path');
const lemmatize = require('wink-lemmatizer');

const dataDir = path.join(__dirname, '..', 'data');
const read = (name) => JSON.parse(fs.readFileSync(path.join(dataDir, name), 'utf8'));
const fold = (t) => String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

const words = new Set();
const take = (text) => (fold(text).match(/[a-z]{3,}/g) || []).forEach((w) => words.add(w));
for (const c of read('electives.json').courses) {
  take(c.title);
  for (const sections of Object.values(c.terms)) sections.forEach((s) => take(s.topic));
}
const catalog = fs.existsSync(path.join(dataDir, 'catalog.json')) ? read('catalog.json').courses : {};
for (const d of Object.values(catalog)) { take(d.d); take(d.p); }

const forms = {};
for (const w of [...words].sort()) {
  const bases = new Set([lemmatize.noun(w), lemmatize.verb(w), lemmatize.adjective(w)]);
  bases.delete(w);
  if (bases.size) forms[w] = [...bases].sort();
}
if (words.size < 500) throw new Error(`Only ${words.size} words found, so the data files may be incomplete.`);
fs.writeFileSync(path.join(dataDir, 'lemmas.json'), JSON.stringify({ generated: new Date().toISOString(), forms }));
console.log(`Wrote data/lemmas.json: ${Object.keys(forms).length} of ${words.size} words have a different base form.`);
