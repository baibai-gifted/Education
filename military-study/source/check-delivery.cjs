// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 baibai
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const raw = JSON.parse(fs.readFileSync(path.join(__dirname, 'questions-raw.json'), 'utf8'));
const bank = JSON.parse(fs.readFileSync(path.join(__dirname, 'questions.json'), 'utf8'));
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
assert.equal(bank.questions.length, 4733);
const ids = new Set();
for (let i = 0; i < raw.length; i++) {
  const before = raw[i], after = bank.questions[i];
  for (const field of ['id','number','type','stem','options','answer','explanation','sourceAnswer','sourceCitation','sourceRef'])
    assert.deepEqual(after[field], before[field], `${after.id}: changed source field ${field}`);
  assert(!ids.has(after.id)); ids.add(after.id);
  assert(after.explanation.trim() || after.supplementalExplanation?.trim(), `Missing explanation: ${after.id}`);
  for (const key of after.answer) assert(after.options.some(o => o.key === key));
}
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script\s*>/gi)];
assert.equal(scripts.length, 1);
new vm.Script(scripts[0][1], {filename: 'index.html'});
assert(!/<script\b[^>]*\bsrc\s*=/i.test(html));
assert(!/<link\b[^>]*\brel\s*=\s*["']stylesheet/i.test(html));
assert.equal(bank.integrity.supplementedExplanationCount, 101);
assert.equal(bank.integrity.effectiveMissingExplanationCount, 0);
assert.equal(bank.integrity.learningModuleCount, 10);
assert.equal(bank.questions.filter(q => q.answerStatus === 'review').length, 6);
assert(!html.includes('__AUTHOR_AVATAR_DATA_URI__'));
assert(/src="data:image\/jpeg;base64,[A-Za-z0-9+/=]+"/.test(html));
assert(html.includes('https://github.com/baibai-gifted/military-theory-practice/releases'));
assert(html.includes('AGPL-3.0'));
console.log(JSON.stringify({status:'PASS',questions:4733,sourceFieldsPreserved:true,
  originalExplanations:4632,supplementedExplanations:101,modules:10,
  pitfalls:bank.questions.filter(q=>q.pitfall).length,reviewOnly:6,
  javascriptSyntax:'PASS',externalRuntimeDependencies:0,htmlBytes:Buffer.byteLength(html)},null,2));
