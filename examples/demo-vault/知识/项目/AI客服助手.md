---
type: project
title: AI客服助手
status: active
created: 2024-06-15
tags:
  - 项目
  - 客服
  - AI应用
concepts:
  - "[[RAG（检索增强生成）]]"
  - "[[Agent]]"
  - "[[Prompt Engineering]]"
decisions:
  - "[[采用Agent架构而非纯链式调用]]"
constraints:
  - "[[所有AI接口必须做内容审核]]"
  - "[[数据不出境]]"
outputs:
  - "[[Agent开发规范]]"
---
# 项目目标
构建一个面向企业客服团队的 AI 助手，负责知识问答、工单摘要、风险投诉识别和人工升级建议。

# 当前方案
- 使用 [[RAG（检索增强生成）]] 连接知识库，保证答案可追溯。
- 使用 [[Agent]] 编排多步骤流程，包括检索、风险评估、回复草拟和 CRM 写回。
- 使用 [[Prompt Engineering]] 控制话术、输出格式和兜底策略。

# 关键依赖
- 约束：[[所有AI接口必须做内容审核]]、[[数据不出境]]
- 决策：[[采用Agent架构而非纯链式调用]]
- 输出：[[Agent开发规范]]
- 相关来源：[[2024-01-15 Anthropic发布Claude 3]]、[[2024-03-01 LangChain vs LlamaIndex对比]]

# 近期问题
客服经理最关心的是错误升级和情绪识别漏判，因此项目也间接依赖 [[RAG技术选型报告]] 的证据质量要求。
