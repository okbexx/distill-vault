---
type: concept
title: Prompt Engineering
status: active
created: 2024-06-10
tags:
  - 提示词
  - AI
  - 设计
related_concepts:
  - "[[Agent]]"
related_projects:
  - "[[AI客服助手]]"
source_basis:
  - "[[2024-01-15 Anthropic发布Claude 3]]"
---
# 定义
[[Prompt Engineering]] 是围绕任务说明、上下文组织、示例设计、工具描述与输出约束所展开的系统设计工作。它不是写一句好提示词，而是让模型在复杂任务里持续稳定地按要求工作。

# 在项目中的作用
- [[AI客服助手]] 用它来区分售前咨询、售后申诉和高风险投诉场景。
- [[Agent]] 的工具说明、失败回退和输出 schema 都属于 Prompt Engineering 的范畴。
- 我把一些稳定模板沉淀到了 [[Agent开发规范]]，避免每个新项目都从零开始摸索。

# 经验
- 好提示词通常依赖来自 [[2024-01-15 Anthropic发布Claude 3]] 的模型能力观察。
- Prompt 模板要和 [[所有AI接口必须做内容审核]] 对齐，否则上线后会出现风格漂移和越权回复。
- 当上下文来自 [[RAG（检索增强生成）]] 时，提示词需要强制引用证据来源。
