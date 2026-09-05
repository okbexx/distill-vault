export function safeName(value: string): string {
  const normalized = value.normalize('NFC').replace(/[\u0000-\u001f\u007f/\\:*?"<>|\[\]#^]/g, '-').replace(/^[. ]+|[. ]+$/g, '');
  let cleaned = '';
  for(const char of normalized) {if(new TextEncoder().encode(cleaned+char).length>100) break;cleaned+=char;}
  cleaned=cleaned.replace(/[. ]+$/g, '');
  return !cleaned ? 'untitled' : /^(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\.|$)/i.test(cleaned) ? `_${cleaned}`.slice(0,100) : cleaned;
}
export function vaultFolder(value: string): string {
  if (!value || value.split('/').some(p => !p || p.startsWith('.') || p.trim() !== p || /[\\:*?"<>|\[\]#^\u0000-\u001f]/.test(p))) throw new Error('目录必须是库内相对路径，不能包含隐藏目录或 ..');
  return value;
}
export function safeWebsite(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) && !u.username && !u.password ? u.href : null; } catch { return null; }
}
export function directoryPath(value: unknown): string | null {
  return typeof value === 'string' && /^(\/|~\/)/.test(value) && !/[\u0000-\u001f]/.test(value) ? value : null;
}
export function passwordReference(value: unknown): string | null {
  // Location only; never dereference it, never call a password manager.
  // Human-readable references are part of the vault contract, not just URIs.
  return typeof value === 'string' && value.trim().length > 0 && value.length <= 500 && !/[\u0000-\u001f]/.test(value) ? value.trim() : null;
}
export function classify(path: string, properties: Record<string, unknown>, inbox: string): 'inbox'|'project'|'access'|null {
  if(path.startsWith(`${inbox}/attachments/`)) return null;
  if (path.startsWith(`${inbox}/`)) return 'inbox';
  const kind = properties.type ?? properties.kind;
  return kind === 'project' || kind === 'access' ? kind : null;
}
export function searchUri(vault: string, query: string): string {
  return `obsidian://search?vault=${encodeURIComponent(vault)}&query=${encodeURIComponent(query)}`;
}
export interface Store {
  mkdir(path: string): Promise<unknown>;
  exists(path: string): Promise<boolean>;
  /** Must fail if the file exists. Never implement this using modify(). */
  create(path: string, data: string|ArrayBuffer): Promise<unknown>;
}
export interface CaptureInput {
  folder: string; title: string; text: string;
  attachments: {name: string; data: ArrayBuffer}[];
}
export class CaptureError extends Error {
  constructor(public retainedPaths: string[]) {super(`保存失败；草稿仍在窗口中。${retainedPaths.length ? `附件保留（请勿重复导入）：${retainedPaths.join('，')}` : '未完成写入，请检查目录或磁盘。'}`);}
}
async function createUnique(store: Store, folder: string, name: string, data: string|ArrayBuffer): Promise<string> {
  const dot = name.lastIndexOf('.');
  const stem = dot > 0 ? name.slice(0,dot) : name;
  const ext = dot > 0 ? name.slice(dot) : '';
  for (let n=0; n<1000; n++) {
    const path = `${folder}/${stem}${n ? `-${n}` : ''}${ext}`;
    if (await store.exists(path)) continue;
    try {await store.create(path,data); return path;} catch(error) {if (!(await store.exists(path))) throw error;}
  }
  throw new Error('Too many filename collisions');
}
export async function capture(store: Store, input: CaptureInput, nonce: ()=>string = ()=>crypto.randomUUID()): Promise<{path:string; attachments:string[]}> {
  const folder = vaultFolder(input.folder);
  if (!input.text.trim() && !input.attachments.length) throw new Error('请填写内容或附件');
  if (input.attachments.some(a=>a.data.byteLength>50*1024*1024) || input.attachments.reduce((s,a)=>s+a.data.byteLength,0)>100*1024*1024) throw new Error('附件限制：单个 50 MB，总计 100 MB');
  const created: string[] = [];
  try {
    await store.mkdir(folder);
    if(input.attachments.length) await store.mkdir(`${folder}/attachments`);
    for(const a of input.attachments) {
      const ext = /\.[a-zA-Z0-9]{1,12}$/.exec(a.name)?.[0] ?? '';
      const name = `${safeName(nonce())}-${safeName(ext ? a.name.slice(0,-ext.length) : a.name)}${ext}`;
      created.push(await createUnique(store,`${folder}/attachments`,name,a.data));
    }
    const links = created.map(p => `${/\.(png|jpe?g|gif|webp|bmp|avif)$/i.test(p) ? '!' : ''}[[${p}]]`).join('\n');
    const body = `---\ntype: source\nstatus: raw\nsource_type: note\ncreated_at: ${JSON.stringify(new Date().toISOString())}\ntitle: ${JSON.stringify(input.title.trim() || '快捷记录')}\n---\n\n${input.text}${links ? `\n\n## 附件\n\n${links}\n` : ''}`;
    const path = await createUnique(store, folder, `${safeName(nonce())}-${safeName(input.title || '快捷记录')}.md`, body);
    return {path,attachments:created};
  } catch {throw new CaptureError(created);}
}
