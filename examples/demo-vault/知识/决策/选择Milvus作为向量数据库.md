---
type: decision
title: 选择Milvus作为向量数据库
status: stable
created: 2024-06-16
tags:
  - 决策
  - 向量数据库
  - 选型
project: "[[智能文档平台]]"
evidence:
  - "[[2024-05-20 Vector DB Benchmark]]"
constraints:
  - "[[数据不出境]]"
related_outputs:
  - "[[RAG技术选型报告]]"
---
# 决策内容
在 [[智能文档平台]] 中，向量检索层优先采用 [[Milvus]]，暂不选择托管型海外服务。

# 原因
- [[2024-05-20 Vector DB Benchmark]] 显示它在规模扩展、性能稳定性和生态成熟度之间较平衡。
- 对 [[数据不出境]] 的约束更友好，可在本地或私有云部署。
- 与 [[向量数据库]] 的使用模式契合，能满足 [[RAG（检索增强生成）]] 的召回需求。

# 影响
- 推动了 [[RAG技术选型报告]] 的最终建议。
- 让 [[智能文档平台]] 的索引设计更偏向元数据过滤和混合检索。
