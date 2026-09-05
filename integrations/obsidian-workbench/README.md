# Distill Workbench — Obsidian 轻工作台

独立桌面插件，**不含聊天、模型、Agent 入口、网络请求、后台命令或密码管理器集成**。只写用户主动保存的 source 笔记和附件；既有项目/访问资料只读展示。无需 Bases、Dataview 或 Distill 服务运行，离线也能记录和浏览本地笔记。

## 构建与安装

开发环境：Node.js 22、npm。依赖只有构建工具和 Obsidian 官方类型，精确版本及 lockfile 随目录提供；无运行时 npm 依赖。

```sh
cd integrations/obsidian-workbench
npm ci --ignore-scripts
npm run build
npm test
```

安装到**测试库**的 `.obsidian/plugins/distill-workbench/`，只复制本目录的 `main.js`、`manifest.json`、`styles.css`。macOS Finder 可用 Cmd+Shift+. 显示隐藏目录。重载 Obsidian 后，在设置 → 第三方插件启用 Distill Workbench。最低声明版本 1.5.0；桌面限定。不要将源码、node_modules 或测试产物复制到库内。

命令面板提供「快捷记录到收件箱」「打开工作台」，侧栏也有入口。可在 Obsidian 设置 → 快捷键自行绑定（避免强占用户现有快捷键）。记录窗口内 Cmd/Ctrl+Enter 保存。

## 记录与引擎契约

- 默认目录 `收件箱`，设置中可改为其他库内相对路径。目录只在首次保存时创建；切换设置不会移动旧文件。非法目录输入不会保存。
- 标题可选，内容或附件至少其一。没有项目归属选择，也不自动归档、改写原文或触发引擎。
- 附件支持文件选择、多选、拖入；内容框支持粘贴图片，混合剪贴板中的纯文本也会插入。单件最大 50 MB，总计 100 MB。
- 附件复制进 `收件箱/attachments/`；原文件不动。常见光栅图片写 Obsidian 嵌入链接，其他文件写普通 Obsidian 链接（SVG/HTML 不自动嵌入）。不解析、不执行附件。Markdown 附件不会再次被工作台当作收件箱条目。
- 快捷记录与引擎一致：`type: source`、`status: raw`、`source_type: note`、`created_at`（ISO UTC）、`title`。**没有新的 capture 类型系统**。
- 保存内容为 frontmatter + 空行 + 原文；不 trim 正文，保留正文中的空格、尾换行。存在附件时仅在原文后追加空行和 `## 附件` 链接区。浏览器 textarea 本身会把输入的 CRLF 规范化成 LF；插件不承诺剪贴板原始字节级保真，但保存其取得的文本原样。二进制附件按字节复制。
- 文件名清理路径分隔符、控制字符、链接语法字符及平台保留名；Unicode 保留且按 UTF-8 字节限长。随机 ID + 冲突序号，使用 Vault `create` / `createBinary`，不使用覆盖写入。目录禁止绝对路径、隐藏目录和 `..`。

### 保存失败的明确语义

Obsidian Vault 没有跨多个文件的事务。本插件**先写附件，再写笔记**。如果后续附件或笔记保存失败，已经成功写入的附件保留，不删除任何文件；错误区域列出完整保留路径。此时禁用本窗口重试以防重复附件，正文仍可选择复制，用户可手动创建记录并补上这些链接。请不要关闭窗口直到复制好草稿。

无附件成功写入的失败可重试。窗口关闭会丢弃未保存草稿；保存进行中请勿关闭窗口。极端磁盘故障若底层创建调用抛错却留下部分字节，可能存在未能报告的部分文件，需要人工检查附件目录；不把失败误报为成功，也不冒险自动清理用户文件。

## 工作台与 properties

工作台按更新时间倒序呈现收件箱、项目、访问资料，笔记链接使用官方 `workspace.openLinkText`；Cmd/Ctrl+点击可新标签打开。基于 metadata cache 更新，提供手动刷新。收件箱按配置路径识别，其他条目按 `type: project` / `type: access` 识别（兼容 `kind`，以 `type` 为准）。不要求放在固定项目目录。项目和访问资料直接在 Obsidian properties/Markdown 中编辑。

访问资料示例（仅虚构位置，**不是密码值**）：

```yaml
---
type: access
title: 示例开发服务
category: 开发服务
environment: 开发
service_url: https://example.com
account: 示例账号（非真实）
credential_ref: 密码库名称 / 分组 / 条目标题或ID
storage_method: 外部加密密码库
auth_method: 密码与第二因素（示例）
verified_at: null
---
```

项目使用 `type: project`，可同样设置 `environment`、`verified_at`、`service_url` 和可选 `local_path`。卡片只展示标题、状态及环境/分类/账号标识/存储方式/认证方式/核验时间，网址、目录和凭据位置。`verified_at: null` 显示「未核验」，不会伪造已验证状态。兼容旧字段 `url` 和 `password_ref`，优先采用 `service_url` 和 `credential_ref`。

凭据位置支持普通人可读文本以及已有的密码管理器位置 URI；只显示，不解引用、不点击启动、不读密码库。没有 password、secret、token 输入或存储字段，也不遍历渲染任意 properties。**无法从任意自由文本中可靠识别密码**：快捷记录会如实保存用户输入，误将真实密码放到正文、附件或 `credential_ref` 一样会写入/暴露在普通库中。禁止这样使用；访问资料只记录外部位置，不填写实际密码、恢复码、密钥或带签名凭据的 URL。Obsidian 笔记本身不是密码保险库。

## macOS 入口与搜索

- `service_url` 只接受无用户名/密码的 HTTP(S) 地址；用户点击才由普通外链打开。拒绝 javascript、file、自定义命令协议。不生成启动脚本，不运行终端命令。
- `local_path` 可填当前 Mac 的绝对目录或 `~/...`。按钮是**复制目录，不是一键打开 Finder**：复制后切到 Finder → Cmd+Shift+G → 粘贴 → 回车。剪贴板不可用时可手动复制已显示路径。插件不验证该目录在 Mac 上存在，也不复用 Linux 开发机路径。
- 全局搜索使用官方 `obsidian://search?vault=...&query=...`，支持 Obsidian 原生查询语法。需启用核心「搜索」插件。多个库同名时 URI 可能有歧义，请使用不同库名。不会调用未公开的 `app.internalPlugins`。

## 已验证与待验收

在 Linux / Node.js 22 真实执行 `npm run build`（TypeScript strict 检查 + esbuild CommonJS 产物）和 `npm test`，**13 项测试通过**。其中入口烟测加载真实 `main.js`，以最小 Obsidian host stub 验证注册命令与设置白名单（不算 GUI 验收）。其余测试运行编译后的核心逻辑，真实临时文件系统覆盖：路径/文件名约束、Unicode 长文件名、属性分类、URL 协议及搜索编码、文本/附件落盘、无归属、同名及并发冲突不覆盖、附件单独记录、原文尾换行保真、后续附件失败和笔记失败时保留路径。不是仅源代码字符串断言。

**未验收 macOS 或 Obsidian GUI**。手工验收清单：

1. 测试库安装后启用/禁用/重新启用；打开多个工作台页签，关闭后无残余事件。
2. 中文/特殊符号标题、无标题、纯附件；粘贴截图、拖入文件、移除文件；重复标题不覆盖。
3. 保存后打开笔记，核对 source properties、正文和二进制附件；确认收件箱无需项目归属。
4. 打开仓库 `examples/personal-workbench` 的测试副本，核对项目及访问资料卡片字段，未核验不会显示成功状态。
5. Cmd/Ctrl+点击原生笔记链接；全局搜索含中文/引号的查询；禁用搜索插件时确认提示说明。
6. 填测试 Mac 的真实目录，复制后使用 Finder Cmd+Shift+G；网址只在点击后打开。
7. 使用只读测试目录模拟失败，确认草稿/保留路径提示；不拿真实资料做故障注入。

## 官方 API 核验与维护工作流

实现依据官方文档核验 Modal、ItemView/registerView、Vault create/createBinary/createFolder、metadata cache 事件和 openLinkText；类型检查使用官方 `obsidian` npm 类型。Modals 文档页面提取返回 Not found，因此补核官方 API 类型声明中的 Modal 接口，而不是依赖该失败页面。

- https://docs.obsidian.md/Plugins/User+interface/Views
- https://docs.obsidian.md/Plugins/Vault
- https://github.com/obsidianmd/obsidian-api/blob/master/obsidian.d.ts
- https://help.obsidian.md/uri （Open search）

维护时先补核心行为测试，在临时目录真实验证失败/冲突，再修改 Vault 适配层，最后重新构建 `main.js`。发布只带上述三个运行文件。不要将 Node 文件系统测试通过表述为 Obsidian/macOS GUI 已通过。
