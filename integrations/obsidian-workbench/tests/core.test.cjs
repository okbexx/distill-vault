const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {safeName, vaultFolder, safeWebsite, directoryPath, passwordReference, classify, capture, searchUri} = require('../.test-build/core.cjs');

test('filenames cannot escape or inject links; unicode is retained', () => {
  for (const name of ['../a\\b:bad|[]#^?.png', '.', 'CON', 'x'.repeat(500)]) {
    const safe = safeName(name);
    assert.ok(safe.length > 0 && safe.length <= 100);
    assert.doesNotMatch(safe, /[/\\:*?"<>|\[\]#^]/);
    assert.ok(!safe.startsWith('.'));
  }
  assert.match(safeName('中文图片.png'), /中文图片/);
});
test('folders reject traversal, hidden config and absolute paths', () => {
  for (const p of ['../Inbox', '/Inbox', 'A/../B', '.obsidian', 'A//B', 'C:\\x', 'A/.hidden']) assert.throws(() => vaultFolder(p));
  assert.equal(vaultFolder('工作/收件箱'), '工作/收件箱');
});
test('entry protocols are not command execution surfaces', () => {
  for (const u of ['javascript:alert(1)', 'file:///tmp/a', 'https://user:pass@example.com', 'obsidian://advanced-uri?commandid=x']) assert.equal(safeWebsite(u), null);
  assert.equal(safeWebsite('https://example.com/docs'), 'https://example.com/docs');
  assert.equal(directoryPath('/Users/example/My Project'), '/Users/example/My Project');
  assert.equal(directoryPath('$(whoami)'), null);
  assert.equal(passwordReference('1Password / 示例保险库 / 示例服务'), '1Password / 示例保险库 / 示例服务');
  assert.equal(passwordReference('op://ExampleVault/ExampleItem/password'), 'op://ExampleVault/ExampleItem/password');
  assert.equal(passwordReference('bad\nreference'), null);
});
test('properties drive classification; no required project assignment', () => {
  assert.equal(classify('Other/A.md', {type:'project'}, 'Inbox'), 'project');
  assert.equal(classify('Other/A.md', {type:'access'}, 'Inbox'), 'access');
  assert.equal(classify('Inbox/A.md', {}, 'Inbox'), 'inbox');
  assert.equal(classify('Inboxish/A.md', {}, 'Inbox'), null);
  assert.equal(classify('Inbox/attachments/A.md', {type:'project'}, 'Inbox'), null);
  assert.equal(classify('Other/A.md', {password:'ignored'}, 'Inbox'), null);
});
test('search URI encodes a full-vault query without undocumented APIs', () => {
  const uri = new URL(searchUri('Vault & 中文', 'tag:#x "a"'));
  assert.equal(uri.hostname, 'search');
  assert.equal(uri.searchParams.get('vault'), 'Vault & 中文');
  assert.equal(uri.searchParams.get('query'), 'tag:#x "a"');
});
async function fixture(t, failNote=false) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'obsidian-workbench-'));
  t.after(() => fs.rm(root, {recursive:true, force:true}));
  return {root, store: {
    mkdir: p => fs.mkdir(path.join(root,p), {recursive:true}),
    exists: async p => {try {await fs.stat(path.join(root,p)); return true;} catch(e) {if(e.code==='ENOENT') return false; throw e;}},
    create: async (p,data) => {if(failNote && p.endsWith('.md')) throw new Error('disk failure'); await fs.writeFile(path.join(root,p), typeof data==='string'?data:Buffer.from(data), {flag:'wx'});}
  }};
}
test('real filesystem capture preserves text and bytes without overwriting', async t => {
  const {root,store} = await fixture(t);
  const input = {folder:'Inbox', title:'../same', text:'Hello 中文', attachments:[{name:'../../image.png', data:new Uint8Array([137,80,78,71]).buffer}]};
  const a = await capture(store,input,()=> 'fixed');
  const b = await capture(store,input,()=> 'fixed');
  assert.notEqual(a.path,b.path);
  assert.notEqual(a.attachments[0],b.attachments[0]);
  const note = await fs.readFile(path.join(root,a.path),'utf8');
  assert.match(note,/Hello 中文/);
  assert.match(note,/type: source\nstatus: raw\nsource_type: note\ncreated_at:/);
  assert.doesNotMatch(note,/project:/);
  assert.ok(note.includes(`![[${a.attachments[0]}]]`));
  assert.deepEqual(await fs.readFile(path.join(root,a.attachments[0])),Buffer.from([137,80,78,71]));
});
test('attachment-only capture works, empty capture is rejected', async t => {
  const {store} = await fixture(t);
  await assert.rejects(capture(store,{folder:'Inbox',title:'',text:' ',attachments:[]}),/内容或附件/);
  const result = await capture(store,{folder:'Inbox',title:'',text:'',attachments:[{name:'a.pdf',data:new ArrayBuffer(1)}]});
  assert.ok(result.path.endsWith('.md'));
});
test('concurrent captures retry exclusive-create collisions', async t => {
  const {store} = await fixture(t);
  const input = {folder:'Inbox',title:'same',text:'content',attachments:[]};
  const results = await Promise.all(Array.from({length:8},()=>capture(store,input,()=> 'fixed')));
  assert.equal(new Set(results.map(r=>r.path)).size,8);
});
test('failed note save reports retained attachments; never destroys user data', async t => {
  const {root,store} = await fixture(t,true);
  await assert.rejects(capture(store,{folder:'Inbox',title:'x',text:'draft',attachments:[{name:'a.png',data:new ArrayBuffer(2)}]}),e => {
    assert.equal(e.retainedPaths.length,1);
    assert.match(e.message,/附件保留/);
    return true;
  });
  assert.equal((await fs.readdir(path.join(root,'Inbox','attachments'))).length,1);
});

test('source body preserves exact text including trailing newlines', async t => {
  const {root,store}=await fixture(t);
  for(const text of ['  original  ', 'original\n', 'original\n\n', '---\nnot: properties\n---\n原文\n']) {
    const result=await capture(store,{folder:'收件箱',title:'quote: "\n---',text,attachments:[]});
    const saved=await fs.readFile(path.join(root,result.path),'utf8');
    const delimiter='\n---\n\n';
    assert.equal(saved.slice(saved.indexOf(delimiter)+delimiter.length),text);
  }
});
test('long unicode filenames fit filesystem limits and preserve extension', async t => {
  const {root,store}=await fixture(t);
  const result=await capture(store,{folder:'收件箱',title:'中文'.repeat(200),text:'long title',attachments:[{name:'截图'.repeat(200)+'.png',data:new ArrayBuffer(1)}]});
  assert.ok(Buffer.byteLength(path.basename(result.path))<=255);
  assert.ok(result.attachments[0].endsWith('.png'));
  assert.equal((await fs.stat(path.join(root,result.attachments[0]))).size,1);
});
test('failure during a later attachment reports only completed files', async t => {
  const {root,store}=await fixture(t);
  const create=store.create;
  let calls=0;
  store.create=async(p,data)=>{if(++calls===2)throw new Error('disk full');return create(p,data);};
  await assert.rejects(capture(store,{folder:'收件箱',title:'x',text:'draft',attachments:[{name:'a.png',data:new ArrayBuffer(1)},{name:'b.png',data:new ArrayBuffer(2)}]}),e=>e.retainedPaths.length===1);
  assert.deepEqual(await fs.readdir(path.join(root,'收件箱')),['attachments']);
  assert.equal((await fs.readdir(path.join(root,'收件箱','attachments'))).length,1);
});
