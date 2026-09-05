"use strict";
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/main.ts
var main_exports = {};
__export(main_exports, {
  default: () => WorkbenchPlugin
});
module.exports = __toCommonJS(main_exports);
var import_obsidian = require("obsidian");

// src/core.ts
function safeName(value) {
  const normalized = value.normalize("NFC").replace(/[\u0000-\u001f\u007f/\\:*?"<>|\[\]#^]/g, "-").replace(/^[. ]+|[. ]+$/g, "");
  let cleaned = "";
  for (const char of normalized) {
    if (new TextEncoder().encode(cleaned + char).length > 100) break;
    cleaned += char;
  }
  cleaned = cleaned.replace(/[. ]+$/g, "");
  return !cleaned ? "untitled" : /^(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\.|$)/i.test(cleaned) ? `_${cleaned}`.slice(0, 100) : cleaned;
}
function vaultFolder(value) {
  if (!value || value.split("/").some((p) => !p || p.startsWith(".") || p.trim() !== p || /[\\:*?"<>|\[\]#^\u0000-\u001f]/.test(p))) throw new Error("\u76EE\u5F55\u5FC5\u987B\u662F\u5E93\u5185\u76F8\u5BF9\u8DEF\u5F84\uFF0C\u4E0D\u80FD\u5305\u542B\u9690\u85CF\u76EE\u5F55\u6216 ..");
  return value;
}
function safeWebsite(value) {
  if (typeof value !== "string") return null;
  try {
    const u = new URL(value);
    return ["https:", "http:"].includes(u.protocol) && !u.username && !u.password ? u.href : null;
  } catch {
    return null;
  }
}
function directoryPath(value) {
  return typeof value === "string" && /^(\/|~\/)/.test(value) && !/[\u0000-\u001f]/.test(value) ? value : null;
}
function passwordReference(value) {
  return typeof value === "string" && value.trim().length > 0 && value.length <= 500 && !/[\u0000-\u001f]/.test(value) ? value.trim() : null;
}
function classify(path, properties, inbox) {
  if (path.startsWith(`${inbox}/attachments/`)) return null;
  if (path.startsWith(`${inbox}/`)) return "inbox";
  const kind = properties.type ?? properties.kind;
  return kind === "project" || kind === "access" ? kind : null;
}
function searchUri(vault, query) {
  return `obsidian://search?vault=${encodeURIComponent(vault)}&query=${encodeURIComponent(query)}`;
}
var CaptureError = class extends Error {
  constructor(retainedPaths) {
    super(`\u4FDD\u5B58\u5931\u8D25\uFF1B\u8349\u7A3F\u4ECD\u5728\u7A97\u53E3\u4E2D\u3002${retainedPaths.length ? `\u9644\u4EF6\u4FDD\u7559\uFF08\u8BF7\u52FF\u91CD\u590D\u5BFC\u5165\uFF09\uFF1A${retainedPaths.join("\uFF0C")}` : "\u672A\u5B8C\u6210\u5199\u5165\uFF0C\u8BF7\u68C0\u67E5\u76EE\u5F55\u6216\u78C1\u76D8\u3002"}`);
    this.retainedPaths = retainedPaths;
  }
};
async function createUnique(store, folder, name, data) {
  const dot = name.lastIndexOf(".");
  const stem = dot > 0 ? name.slice(0, dot) : name;
  const ext = dot > 0 ? name.slice(dot) : "";
  for (let n = 0; n < 1e3; n++) {
    const path = `${folder}/${stem}${n ? `-${n}` : ""}${ext}`;
    if (await store.exists(path)) continue;
    try {
      await store.create(path, data);
      return path;
    } catch (error) {
      if (!await store.exists(path)) throw error;
    }
  }
  throw new Error("Too many filename collisions");
}
async function capture(store, input, nonce = () => crypto.randomUUID()) {
  const folder = vaultFolder(input.folder);
  if (!input.text.trim() && !input.attachments.length) throw new Error("\u8BF7\u586B\u5199\u5185\u5BB9\u6216\u9644\u4EF6");
  if (input.attachments.some((a) => a.data.byteLength > 50 * 1024 * 1024) || input.attachments.reduce((s, a) => s + a.data.byteLength, 0) > 100 * 1024 * 1024) throw new Error("\u9644\u4EF6\u9650\u5236\uFF1A\u5355\u4E2A 50 MB\uFF0C\u603B\u8BA1 100 MB");
  const created = [];
  try {
    await store.mkdir(folder);
    if (input.attachments.length) await store.mkdir(`${folder}/attachments`);
    for (const a of input.attachments) {
      const ext = /\.[a-zA-Z0-9]{1,12}$/.exec(a.name)?.[0] ?? "";
      const name = `${safeName(nonce())}-${safeName(ext ? a.name.slice(0, -ext.length) : a.name)}${ext}`;
      created.push(await createUnique(store, `${folder}/attachments`, name, a.data));
    }
    const links = created.map((p) => `${/\.(png|jpe?g|gif|webp|bmp|avif)$/i.test(p) ? "!" : ""}[[${p}]]`).join("\n");
    const body = `---
type: source
status: raw
source_type: note
created_at: ${JSON.stringify((/* @__PURE__ */ new Date()).toISOString())}
title: ${JSON.stringify(input.title.trim() || "\u5FEB\u6377\u8BB0\u5F55")}
---

${input.text}${links ? `

## \u9644\u4EF6

${links}
` : ""}`;
    const path = await createUnique(store, folder, `${safeName(nonce())}-${safeName(input.title || "\u5FEB\u6377\u8BB0\u5F55")}.md`, body);
    return { path, attachments: created };
  } catch {
    throw new CaptureError(created);
  }
}

// src/main.ts
var VIEW = "distill-workbench";
var DEFAULTS = { inbox: "\u6536\u4EF6\u7BB1" };
function vaultStore(app) {
  return {
    exists: async (path) => !!app.vault.getAbstractFileByPath(path) || await app.vault.adapter.exists(path),
    mkdir: async (path) => {
      let partial = "";
      for (const part of path.split("/")) {
        partial = partial ? `${partial}/${part}` : part;
        const existing = app.vault.getAbstractFileByPath(partial);
        if (existing instanceof import_obsidian.TFolder) continue;
        if (existing) throw new Error("\u76EE\u5F55\u88AB\u540C\u540D\u6587\u4EF6\u5360\u7528");
        try {
          await app.vault.createFolder(partial);
        } catch (e) {
          if (!(app.vault.getAbstractFileByPath(partial) instanceof import_obsidian.TFolder)) throw e;
        }
      }
    },
    create: async (path, data) => typeof data === "string" ? app.vault.create(path, data) : app.vault.createBinary(path, data)
  };
}
var CaptureModal = class extends import_obsidian.Modal {
  constructor(app, plugin) {
    super(app);
    this.plugin = plugin;
    this.files = [];
    this.busy = false;
  }
  onOpen() {
    this.contentEl.addClass("distill-capture");
    this.contentEl.createEl("h2", { text: "\u5FEB\u6377\u8BB0\u5F55 \u2192 \u6536\u4EF6\u7BB1" });
    this.contentEl.createEl("p", { text: "\u65E0\u9700\u9009\u62E9\u9879\u76EE\u3002\u8BF7\u52FF\u7C98\u8D34\u5BC6\u7801\u3001\u5BC6\u94A5\u6216\u6062\u590D\u7801\uFF1B\u51ED\u636E\u653E\u5728\u72EC\u7ACB\u5BC6\u7801\u7BA1\u7406\u5668\u3002\u5173\u95ED\u7A97\u53E3\u5C06\u4E22\u5F03\u672A\u4FDD\u5B58\u8349\u7A3F\u3002" });
    const title = this.contentEl.createEl("input", { attr: { type: "text", placeholder: "\u6807\u9898\uFF08\u53EF\u9009\uFF09", "aria-label": "\u6807\u9898" } });
    const text = this.contentEl.createEl("textarea", { attr: { placeholder: "\u8BB0\u5F55\u5185\u5BB9\uFF1B\u53EF\u7C98\u8D34\u622A\u56FE\uFF0C\u4E5F\u53EF\u62D6\u5165\u6587\u4EF6\u3002", "aria-label": "\u8BB0\u5F55\u5185\u5BB9", rows: "10" } });
    const picker = this.contentEl.createEl("input", { attr: { type: "file", multiple: "", "aria-label": "\u9009\u62E9\u9644\u4EF6" } });
    const list = this.contentEl.createDiv();
    const renderFiles = () => {
      list.empty();
      this.files.forEach((file, i) => {
        const row = list.createDiv({ cls: "distill-file" });
        row.createSpan({ text: `${file.name} (${Math.ceil(file.size / 1024)} KB)` });
        const remove = row.createEl("button", { text: "\u79FB\u9664", attr: { type: "button", "aria-label": `\u79FB\u9664 ${file.name}` } });
        remove.onclick = () => {
          if (!this.busy) {
            this.files.splice(i, 1);
            renderFiles();
          }
        };
      });
    };
    const add = (files) => {
      if (this.busy) return;
      const all = [...this.files, ...files];
      if (all.some((f) => f.size > 50 * 1024 * 1024) || all.reduce((s, f) => s + f.size, 0) > 100 * 1024 * 1024) {
        new import_obsidian.Notice("\u9644\u4EF6\u9650\u5236\uFF1A\u5355\u4E2A 50 MB\uFF0C\u603B\u8BA1 100 MB");
        return;
      }
      this.files = all;
      renderFiles();
    };
    picker.onchange = () => {
      add(Array.from(picker.files ?? []));
      picker.value = "";
    };
    text.addEventListener("paste", (e) => {
      const files = Array.from(e.clipboardData?.files ?? []);
      if (files.length) {
        e.preventDefault();
        add(files);
        const pasted = e.clipboardData?.getData("text/plain");
        if (pasted) text.setRangeText(pasted, text.selectionStart, text.selectionEnd, "end");
      }
    });
    this.contentEl.addEventListener("dragover", (e) => {
      e.preventDefault();
    });
    this.contentEl.addEventListener("drop", (e) => {
      e.preventDefault();
      add(Array.from(e.dataTransfer?.files ?? []));
    });
    this.contentEl.createEl("p", { text: "\u9644\u4EF6\u4EC5\u5728\u4FDD\u5B58\u65F6\u590D\u5236\u8FDB\u5E93\uFF1B\u4E0D\u4F1A\u6267\u884C\u3001\u4E0A\u4F20\u6216\u89E3\u6790\u9644\u4EF6\u3002Cmd/Ctrl + Enter \u4FDD\u5B58\u3002", cls: "distill-muted" });
    const status = this.contentEl.createDiv({ attr: { role: "status", "aria-live": "polite" } });
    const save = this.contentEl.createEl("button", { text: "\u4FDD\u5B58\u5230\u6536\u4EF6\u7BB1", cls: "mod-cta" });
    const submit = async () => {
      if (this.busy) return;
      this.busy = true;
      save.disabled = true;
      picker.disabled = true;
      text.disabled = true;
      title.disabled = true;
      let partialFailure = false;
      try {
        const attachments = await Promise.all(this.files.map(async (f) => ({ name: f.name, data: await f.arrayBuffer() })));
        const result = await capture(vaultStore(this.app), { folder: this.plugin.settings.inbox, title: title.value, text: text.value, attachments });
        new import_obsidian.Notice(`\u5DF2\u4FDD\u5B58\uFF1A${result.path}`);
        this.close();
        void this.app.workspace.openLinkText(result.path, "", false).catch(() => new import_obsidian.Notice("\u8BB0\u5F55\u5DF2\u4FDD\u5B58\uFF0C\u4F46\u6253\u5F00\u7B14\u8BB0\u5931\u8D25\u3002\u8BF7\u4ECE\u6536\u4EF6\u7BB1\u8FDB\u5165\u3002"));
      } catch (e) {
        status.setText(e instanceof Error ? e.message : "\u4FDD\u5B58\u5931\u8D25\uFF0C\u8349\u7A3F\u4ECD\u5728\u7A97\u53E3\u4E2D");
        partialFailure = e instanceof CaptureError && e.retainedPaths.length > 0;
        if (partialFailure) status.createEl("p", { text: "\u4E3A\u907F\u514D\u91CD\u590D\u9644\u4EF6\uFF0C\u672C\u7A97\u53E3\u4E0D\u518D\u91CD\u8BD5\u3002\u8BF7\u590D\u5236\u8349\u7A3F\uFF0C\u5728\u6536\u4EF6\u7BB1\u624B\u52A8\u6062\u590D\u4E0A\u8FF0\u9644\u4EF6\u94FE\u63A5\u3002" });
      } finally {
        this.busy = partialFailure;
        save.disabled = partialFailure;
        picker.disabled = partialFailure;
        text.disabled = false;
        title.disabled = false;
      }
    };
    save.onclick = () => void submit();
    this.scope.register(["Mod"], "Enter", () => {
      void submit();
      return false;
    });
    text.focus();
  }
  onClose() {
    this.files = [];
    this.contentEl.empty();
  }
};
var WorkbenchView = class extends import_obsidian.ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.plugin = plugin;
  }
  getViewType() {
    return VIEW;
  }
  getDisplayText() {
    return "\u5DE5\u4F5C\u53F0";
  }
  getIcon() {
    return "layout-dashboard";
  }
  async onOpen() {
    this.render();
    this.registerEvent(this.app.metadataCache.on("changed", () => this.render()));
    this.registerEvent(this.app.metadataCache.on("resolved", () => this.render()));
    this.registerEvent(this.app.vault.on("delete", () => this.render()));
    this.registerEvent(this.app.vault.on("rename", () => this.render()));
  }
  render() {
    const el = this.contentEl;
    el.empty();
    el.addClass("distill-workbench");
    el.createEl("h2", { text: "\u5DE5\u4F5C\u53F0" });
    const toolbar = el.createDiv({ cls: "distill-toolbar" });
    toolbar.createEl("button", { text: "\uFF0B \u5FEB\u6377\u8BB0\u5F55" }).onclick = () => new CaptureModal(this.app, this.plugin).open();
    toolbar.createEl("button", { text: "\u5237\u65B0" }).onclick = () => this.render();
    const search = el.createEl("form", { cls: "distill-toolbar" });
    const query = search.createEl("input", { attr: { type: "search", placeholder: "\u5168\u5E93\u641C\u7D22\uFF08\u652F\u6301 Obsidian \u67E5\u8BE2\u8BED\u6CD5\uFF09", "aria-label": "\u5168\u5E93\u641C\u7D22" } });
    search.createEl("button", { text: "\u5168\u5C40\u641C\u7D22", attr: { type: "submit" } });
    search.onsubmit = (e) => {
      e.preventDefault();
      window.open(searchUri(this.app.vault.getName(), query.value));
    };
    el.createEl("p", { text: "\u4F7F\u7528 Obsidian \u539F\u751F\u641C\u7D22\uFF1B\u9700\u542F\u7528\u6838\u5FC3\u63D2\u4EF6\u300C\u641C\u7D22\u300D\u3002", cls: "distill-muted" });
    const groups = { inbox: el.createDiv(), project: el.createDiv(), access: el.createDiv() };
    const labels = { inbox: "\u6536\u4EF6\u7BB1", project: "\u9879\u76EE", access: "\u8BBF\u95EE\u8D44\u6599" };
    const count = { inbox: 0, project: 0, access: 0 };
    for (const key of ["inbox", "project", "access"]) groups[key].createEl("h3", { text: labels[key] });
    for (const file of this.app.vault.getMarkdownFiles().sort((a, b) => b.stat.mtime - a.stat.mtime)) {
      const p = this.app.metadataCache.getFileCache(file)?.frontmatter ?? {};
      const kind = classify(file.path, p, this.plugin.settings.inbox);
      if (!kind) continue;
      count[kind]++;
      const row = groups[kind].createDiv({ cls: "distill-card" });
      const link = row.createEl("a", { text: typeof p.title === "string" ? p.title : file.basename, cls: "internal-link", href: file.path, attr: { "data-href": file.path } });
      link.onclick = (e) => {
        e.preventDefault();
        void this.app.workspace.openLinkText(file.path, "", e.ctrlKey || e.metaKey).catch(() => new import_obsidian.Notice("\u65E0\u6CD5\u6253\u5F00\u6B64\u7B14\u8BB0"));
      };
      row.createEl("small", { text: file.path, cls: "distill-muted" });
      if (kind === "inbox") continue;
      if (typeof p.status === "string") row.createEl("span", { text: `\u72B6\u6001\uFF1A${p.status}` });
      const fields = { environment: "\u73AF\u5883", category: "\u5206\u7C7B", account: "\u8D26\u53F7\u6807\u8BC6", storage_method: "\u5B58\u50A8\u65B9\u5F0F", auth_method: "\u8BA4\u8BC1\u65B9\u5F0F", verified_at: "\u6838\u9A8C\u65F6\u95F4" };
      for (const [key, label] of Object.entries(fields)) {
        const value = p[key];
        if (typeof value === "string" || typeof value === "number") row.createEl("small", { text: `${label}\uFF1A${value}` });
        else if (key === "verified_at") row.createEl("small", { text: "\u6838\u9A8C\u65F6\u95F4\uFF1A\u672A\u6838\u9A8C" });
      }
      const website = safeWebsite(p.service_url ?? p.url);
      if (website) this.external(row, "\u6253\u5F00\u7F51\u5740", website);
      const folder = directoryPath(p.local_path);
      if (folder) {
        row.createEl("code", { text: folder });
        row.createEl("button", { text: "\u590D\u5236\u76EE\u5F55\uFF08Finder\uFF09" }).onclick = () => {
          void navigator.clipboard.writeText(folder).then(() => new import_obsidian.Notice("\u8DEF\u5F84\u5DF2\u590D\u5236\uFF1AFinder \u6309 Cmd+Shift+G \u540E\u7C98\u8D34\u3002\u4E0D\u6267\u884C\u547D\u4EE4\u3002")).catch(() => new import_obsidian.Notice("\u526A\u8D34\u677F\u4E0D\u53EF\u7528\uFF0C\u8BF7\u624B\u52A8\u590D\u5236\u663E\u793A\u7684\u8DEF\u5F84"));
        };
      }
      const ref = passwordReference(p.credential_ref ?? p.password_ref);
      if (ref) row.createEl("small", { text: `\u5BC6\u7801\u7BA1\u7406\u5668\u4F4D\u7F6E\uFF08\u624B\u52A8\u67E5\u627E\uFF09\uFF1A${ref}` });
      else if (kind === "access") row.createEl("small", { text: "\u51ED\u636E\u4EC5\u5728\u72EC\u7ACB\u5BC6\u7801\u7BA1\u7406\u5668\u4E2D\u4FDD\u5B58\uFF1B\u8BF7\u8BBE\u7F6E credential_ref \u4F4D\u7F6E\u5F15\u7528\uFF08\u4E0D\u662F\u5BC6\u7801\u503C\uFF09\u3002" });
    }
    for (const key of ["inbox", "project", "access"]) if (!count[key]) groups[key].createEl("p", { text: key === "inbox" ? `\u6682\u65E0\u8BB0\u5F55\uFF08${this.plugin.settings.inbox}/\uFF09` : `\u6682\u65E0 ${key} properties \u7B14\u8BB0\uFF1B\u89C1\u63D2\u4EF6 README\u3002`, cls: "distill-muted" });
  }
  external(el, label, url) {
    el.createEl("a", { text: label, href: url, cls: "external-link", attr: { target: "_blank", rel: "noopener noreferrer" } });
  }
};
var WorkbenchSettings = class extends import_obsidian.PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }
  display() {
    this.containerEl.empty();
    new import_obsidian.Setting(this.containerEl).setName("\u6536\u4EF6\u7BB1\u76EE\u5F55").setDesc("\u5E93\u5185\u76F8\u5BF9\u76EE\u5F55\uFF1B\u4FDD\u5B58\u65F6\u624D\u521B\u5EFA\uFF0C\u4E0D\u642C\u52A8\u65E2\u6709\u8BB0\u5F55\u3002").addText((t) => t.setValue(this.plugin.settings.inbox).onChange(async (value) => {
      try {
        vaultFolder(value);
      } catch {
        return;
      }
      this.plugin.settings.inbox = value;
      await this.plugin.saveSettings();
    }));
  }
};
var WorkbenchPlugin = class extends import_obsidian.Plugin {
  constructor() {
    super(...arguments);
    this.settings = { ...DEFAULTS };
  }
  async onload() {
    const saved = await this.loadData();
    if (typeof saved?.inbox === "string") {
      try {
        this.settings.inbox = vaultFolder(saved.inbox);
      } catch {
        new import_obsidian.Notice("\u6536\u4EF6\u7BB1\u914D\u7F6E\u65E0\u6548\uFF0C\u4F7F\u7528\u300C\u6536\u4EF6\u7BB1\u300D");
      }
    }
    this.registerView(VIEW, (leaf) => new WorkbenchView(leaf, this));
    this.addCommand({ id: "quick-capture", name: "\u5FEB\u6377\u8BB0\u5F55\u5230\u6536\u4EF6\u7BB1", callback: () => new CaptureModal(this.app, this).open() });
    this.addCommand({ id: "open-workbench", name: "\u6253\u5F00\u5DE5\u4F5C\u53F0", callback: () => void this.activate().catch(() => new import_obsidian.Notice("\u65E0\u6CD5\u6253\u5F00\u5DE5\u4F5C\u53F0")) });
    this.addRibbonIcon("inbox", "\u5FEB\u6377\u8BB0\u5F55", () => new CaptureModal(this.app, this).open());
    this.addRibbonIcon("layout-dashboard", "\u5DE5\u4F5C\u53F0", () => void this.activate().catch(() => new import_obsidian.Notice("\u65E0\u6CD5\u6253\u5F00\u5DE5\u4F5C\u53F0")));
    this.addSettingTab(new WorkbenchSettings(this.app, this));
  }
  async activate() {
    const leaf = this.app.workspace.getLeavesOfType(VIEW)[0] ?? this.app.workspace.getLeaf("tab");
    await leaf.setViewState({ type: VIEW, active: true });
    await this.app.workspace.revealLeaf(leaf);
  }
  async saveSettings() {
    await this.saveData(this.settings);
    for (const leaf of this.app.workspace.getLeavesOfType(VIEW)) if (leaf.view instanceof WorkbenchView) leaf.view.render();
  }
};
