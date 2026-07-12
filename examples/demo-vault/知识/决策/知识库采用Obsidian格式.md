---
type: decision
title: 知识库采用Obsidian格式
status: stable
created: 2024-06-18
tags:
  - 决策
  - 知识管理
  - 格式
project: "[[智能文档平台]]"
related_outputs:
  - "[[RAG技术选型报告]]"
constraints:
  - "[[数据不出境]]"
---
# 决策内容
知识库底层采用兼容 Obsidian 的 Markdown + wikilink 格式，而不是强绑定某个在线 SaaS。

# 原因
- 可直接用 [[知识图谱]] 和 [[RAG（检索增强生成）]] 处理 Markdown 内容。
- 更利于沉淀像 [[AI客服助手]]、[[内部工具链]] 这样的跨项目知识。
- 配合 [[数据不出境]] 要求，本地优先的格式更可控。

# 影响
- [[智能文档平台]] 能更自然地维护对象关系。
- 输出型文档如 [[RAG技术选型报告]] 和 [[Agent开发规范]] 也能直接回流到知识库中。
