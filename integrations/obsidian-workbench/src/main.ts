import {App, ItemView, Modal, Notice, Plugin, PluginSettingTab, Setting, TFolder, WorkspaceLeaf} from 'obsidian';
import {capture, CaptureError, classify, directoryPath, passwordReference, safeWebsite, searchUri, Store, vaultFolder} from './core';

const VIEW = 'distill-workbench';
interface Settings {inbox: string;}
const DEFAULTS: Settings = {inbox:'收件箱'};

function vaultStore(app: App): Store {
  return {
    exists: async path => !!app.vault.getAbstractFileByPath(path) || await app.vault.adapter.exists(path),
    mkdir: async path => {
      let partial = '';
      for (const part of path.split('/')) {
        partial = partial ? `${partial}/${part}` : part;
        const existing = app.vault.getAbstractFileByPath(partial);
        if (existing instanceof TFolder) continue;
        if (existing) throw new Error('目录被同名文件占用');
        try {await app.vault.createFolder(partial);} catch(e) {if (!(app.vault.getAbstractFileByPath(partial) instanceof TFolder)) throw e;}
      }
    },
    create: async (path, data) => typeof data === 'string' ? app.vault.create(path,data) : app.vault.createBinary(path,data)
  };
}

class CaptureModal extends Modal {
  private files: File[] = [];
  private busy = false;
  constructor(app:App, private plugin:WorkbenchPlugin) {super(app);}
  onOpen(): void {
    this.contentEl.addClass('distill-capture');
    this.contentEl.createEl('h2',{text:'快捷记录 → 收件箱'});
    this.contentEl.createEl('p',{text:'无需选择项目。请勿粘贴密码、密钥或恢复码；凭据放在独立密码管理器。关闭窗口将丢弃未保存草稿。'});
    const title = this.contentEl.createEl('input',{attr:{type:'text',placeholder:'标题（可选）','aria-label':'标题'}});
    const text = this.contentEl.createEl('textarea',{attr:{placeholder:'记录内容；可粘贴截图，也可拖入文件。','aria-label':'记录内容',rows:'10'}});
    const picker = this.contentEl.createEl('input',{attr:{type:'file',multiple:'','aria-label':'选择附件'}});
    const list = this.contentEl.createDiv();
    const renderFiles = () => {
      list.empty();
      this.files.forEach((file,i) => {
        const row = list.createDiv({cls:'distill-file'});
        row.createSpan({text:`${file.name} (${Math.ceil(file.size/1024)} KB)`});
        const remove = row.createEl('button',{text:'移除',attr:{type:'button','aria-label':`移除 ${file.name}`}});
        remove.onclick = () => {if(!this.busy) {this.files.splice(i,1);renderFiles();}};
      });
    };
    const add = (files:File[]) => {
      if(this.busy) return;
      const all = [...this.files,...files];
      if(all.some(f=>f.size>50*1024*1024) || all.reduce((s,f)=>s+f.size,0)>100*1024*1024) {new Notice('附件限制：单个 50 MB，总计 100 MB');return;}
      this.files = all;renderFiles();
    };
    picker.onchange = () => {add(Array.from(picker.files ?? []));picker.value='';};
    text.addEventListener('paste',e => {const files=Array.from(e.clipboardData?.files ?? []);if(files.length) {e.preventDefault();add(files);const pasted=e.clipboardData?.getData('text/plain');if(pasted) text.setRangeText(pasted,text.selectionStart,text.selectionEnd,'end');}});
    this.contentEl.addEventListener('dragover',e=>{e.preventDefault();});
    this.contentEl.addEventListener('drop',e=>{e.preventDefault();add(Array.from(e.dataTransfer?.files ?? []));});
    this.contentEl.createEl('p',{text:'附件仅在保存时复制进库；不会执行、上传或解析附件。Cmd/Ctrl + Enter 保存。',cls:'distill-muted'});
    const status = this.contentEl.createDiv({attr:{role:'status','aria-live':'polite'}});
    const save = this.contentEl.createEl('button',{text:'保存到收件箱',cls:'mod-cta'});
    const submit = async () => {
      if(this.busy) return;
      this.busy=true;save.disabled=true;picker.disabled=true;text.disabled=true;title.disabled=true;
      let partialFailure=false;
      try {
        const attachments = await Promise.all(this.files.map(async f=>({name:f.name,data:await f.arrayBuffer()})));
        const result = await capture(vaultStore(this.app),{folder:this.plugin.settings.inbox,title:title.value,text:text.value,attachments});
        new Notice(`已保存：${result.path}`);this.close();
        void this.app.workspace.openLinkText(result.path,'',false).catch(()=>new Notice('记录已保存，但打开笔记失败。请从收件箱进入。'));
      } catch(e) {
        status.setText(e instanceof Error ? e.message : '保存失败，草稿仍在窗口中');
        partialFailure=e instanceof CaptureError && e.retainedPaths.length>0;
        if(partialFailure) status.createEl('p',{text:'为避免重复附件，本窗口不再重试。请复制草稿，在收件箱手动恢复上述附件链接。'});
      } finally {
        this.busy=partialFailure;save.disabled=partialFailure;picker.disabled=partialFailure;text.disabled=false;title.disabled=false;
      }
    };
    save.onclick=()=>void submit();
    this.scope.register(['Mod'],'Enter',()=>{void submit();return false;});
    text.focus();
  }
  onClose():void {this.files=[];this.contentEl.empty();}
}

class WorkbenchView extends ItemView {
  constructor(leaf:WorkspaceLeaf, private plugin:WorkbenchPlugin) {super(leaf);}
  getViewType():string {return VIEW;}
  getDisplayText():string {return '工作台';}
  getIcon():string {return 'layout-dashboard';}
  async onOpen():Promise<void> {
    this.render();
    this.registerEvent(this.app.metadataCache.on('changed',()=>this.render()));
    this.registerEvent(this.app.metadataCache.on('resolved',()=>this.render()));
    this.registerEvent(this.app.vault.on('delete',()=>this.render()));
    this.registerEvent(this.app.vault.on('rename',()=>this.render()));
  }
  render():void {
    const el = this.contentEl;el.empty();el.addClass('distill-workbench');
    el.createEl('h2',{text:'工作台'});
    const toolbar=el.createDiv({cls:'distill-toolbar'});
    toolbar.createEl('button',{text:'＋ 快捷记录'}).onclick=()=>new CaptureModal(this.app,this.plugin).open();
    toolbar.createEl('button',{text:'刷新'}).onclick=()=>this.render();
    const search = el.createEl('form',{cls:'distill-toolbar'});
    const query = search.createEl('input',{attr:{type:'search',placeholder:'全库搜索（支持 Obsidian 查询语法）','aria-label':'全库搜索'}});
    search.createEl('button',{text:'全局搜索',attr:{type:'submit'}});
    search.onsubmit=e=>{e.preventDefault();window.open(searchUri(this.app.vault.getName(),query.value));};
    el.createEl('p',{text:'使用 Obsidian 原生搜索；需启用核心插件「搜索」。',cls:'distill-muted'});

    const groups = {inbox:el.createDiv(),project:el.createDiv(),access:el.createDiv()};
    const labels = {inbox:'收件箱',project:'项目',access:'访问资料'};
    const count = {inbox:0,project:0,access:0};
    for(const key of ['inbox','project','access'] as const) groups[key].createEl('h3',{text:labels[key]});
    for(const file of this.app.vault.getMarkdownFiles().sort((a,b)=>b.stat.mtime-a.stat.mtime)) {
      const p = this.app.metadataCache.getFileCache(file)?.frontmatter ?? {};
      const kind=classify(file.path,p,this.plugin.settings.inbox);if(!kind) continue;
      count[kind]++;
      const row = groups[kind].createDiv({cls:'distill-card'});
      const link=row.createEl('a',{text:typeof p.title==='string'?p.title:file.basename,cls:'internal-link',href:file.path,attr:{'data-href':file.path}});
      link.onclick=e=>{e.preventDefault();void this.app.workspace.openLinkText(file.path,'',e.ctrlKey||e.metaKey).catch(()=>new Notice('无法打开此笔记'));};
      row.createEl('small',{text:file.path,cls:'distill-muted'});
      if(kind==='inbox') continue;
      if(typeof p.status==='string') row.createEl('span',{text:`状态：${p.status}`});
      const fields: Record<string,string> = {environment:'环境',category:'分类',account:'账号标识',storage_method:'存储方式',auth_method:'认证方式',verified_at:'核验时间'};
      for(const [key,label] of Object.entries(fields)) {
        const value=p[key];
        if(typeof value==='string' || typeof value==='number') row.createEl('small',{text:`${label}：${value}`});
        else if(key==='verified_at') row.createEl('small',{text:'核验时间：未核验'});
      }
      const website=safeWebsite(p.service_url ?? p.url);if(website)this.external(row,'打开网址',website);
      const folder=directoryPath(p.local_path);
      if(folder) {
        row.createEl('code',{text:folder});
        row.createEl('button',{text:'复制目录（Finder）'}).onclick=()=>{void navigator.clipboard.writeText(folder).then(()=>new Notice('路径已复制：Finder 按 Cmd+Shift+G 后粘贴。不执行命令。')).catch(()=>new Notice('剪贴板不可用，请手动复制显示的路径'));};
      }
      // Never render arbitrary properties or secret values.
      const ref=passwordReference(p.credential_ref ?? p.password_ref);
      if(ref) row.createEl('small',{text:`密码管理器位置（手动查找）：${ref}`});
      else if(kind==='access') row.createEl('small',{text:'凭据仅在独立密码管理器中保存；请设置 credential_ref 位置引用（不是密码值）。'});
    }
    for(const key of ['inbox','project','access'] as const) if(!count[key]) groups[key].createEl('p',{text:key==='inbox'?`暂无记录（${this.plugin.settings.inbox}/）`:`暂无 ${key} properties 笔记；见插件 README。`,cls:'distill-muted'});
  }
  private external(el:HTMLElement,label:string,url:string):void {el.createEl('a',{text:label,href:url,cls:'external-link',attr:{target:'_blank',rel:'noopener noreferrer'}});}
}

class WorkbenchSettings extends PluginSettingTab {
  constructor(app:App,private plugin:WorkbenchPlugin){super(app,plugin);}
  display():void {
    this.containerEl.empty();
    new Setting(this.containerEl).setName('收件箱目录').setDesc('库内相对目录；保存时才创建，不搬动既有记录。').addText(t=>t.setValue(this.plugin.settings.inbox).onChange(async value=>{
      try {vaultFolder(value);} catch {return;}
      this.plugin.settings.inbox=value;await this.plugin.saveSettings();
    }));

  }
}
export default class WorkbenchPlugin extends Plugin {
  settings:Settings={...DEFAULTS};
  async onload():Promise<void> {
    const saved=await this.loadData();
    if(typeof saved?.inbox==='string') {try {this.settings.inbox=vaultFolder(saved.inbox);}catch{new Notice('收件箱配置无效，使用「收件箱」');}}

    this.registerView(VIEW,leaf=>new WorkbenchView(leaf,this));
    this.addCommand({id:'quick-capture',name:'快捷记录到收件箱',callback:()=>new CaptureModal(this.app,this).open()});
    this.addCommand({id:'open-workbench',name:'打开工作台',callback:()=>void this.activate().catch(()=>new Notice('无法打开工作台'))});
    this.addRibbonIcon('inbox','快捷记录',()=>new CaptureModal(this.app,this).open());
    this.addRibbonIcon('layout-dashboard','工作台',()=>void this.activate().catch(()=>new Notice('无法打开工作台')));
    this.addSettingTab(new WorkbenchSettings(this.app,this));
  }
  async activate():Promise<void> {
    const leaf=this.app.workspace.getLeavesOfType(VIEW)[0] ?? this.app.workspace.getLeaf('tab');
    await leaf.setViewState({type:VIEW,active:true});await this.app.workspace.revealLeaf(leaf);
  }
  async saveSettings():Promise<void> {await this.saveData(this.settings);for(const leaf of this.app.workspace.getLeavesOfType(VIEW))if(leaf.view instanceof WorkbenchView)leaf.view.render();}
}
