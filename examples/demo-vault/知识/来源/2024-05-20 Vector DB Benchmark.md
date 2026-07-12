---
type: source
title: 2024-05-20 Vector DB Benchmark
status: stable
created: 2024-05-20
tags:
  - 来源
  - 数据库
  - Benchmark
concepts:
  - "[[向量数据库]]"
entities:
  - "[[Milvus]]"
outputs:
  - "[[RAG技术选型报告]]"
---
# 摘要
记录了对多个向量数据库在百万级文档场景下的写入速度、查询延迟、过滤能力和部署复杂度的对比。

# 关键结论
- [[向量数据库]] 的过滤表达能力会直接影响 RAG 场景中的权限控制与文档分层。
- [[Milvus]] 在规模扩展和生态支持上表现均衡。
- 这份 benchmark 为 [[选择Milvus作为向量数据库]] 提供了直接证据，也影响了 [[智能文档平台]] 的架构设计。
