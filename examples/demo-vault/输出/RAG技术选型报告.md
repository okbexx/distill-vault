---
type: output
title: RAG技术选型报告
status: stable
created: 2024-06-21
tags:
  - 输出
  - 报告
  - RAG
project: "[[智能文档平台]]"
derived_from:
  - "[[2024-03-01 LangChain vs LlamaIndex对比]]"
  - "[[2024-04-10 知识图谱在RAG中的应用]]"
  - "[[2024-05-20 Vector DB Benchmark]]"
---
# 报告目标
这份报告用于向团队解释为什么当前阶段的 RAG 技术路线应围绕 [[RAG（检索增强生成）]]、[[向量数据库]] 与 [[知识图谱]] 的组合展开。

# 主要结论
- 在 [[智能文档平台]] 中，语义召回层建议基于 [[Milvus]] 实现。
- 对于复杂问答，应把 [[知识图谱]] 纳入召回或重排流程。
- [[RAG（检索增强生成）]] 的最终效果不仅取决于模型，也取决于索引质量与证据组织方式。

# 证据来源
- [[2024-03-01 LangChain vs LlamaIndex对比]]
- [[2024-04-10 知识图谱在RAG中的应用]]
- [[2024-05-20 Vector DB Benchmark]]
- 决策：[[选择Milvus作为向量数据库]]、[[知识库采用Obsidian格式]]
