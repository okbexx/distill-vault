---
type: output
title: Agent开发规范
status: active
created: 2024-06-22
tags:
  - 输出
  - 规范
  - Agent
project: "[[AI客服助手]]"
derived_from:
  - "[[2024-01-15 Anthropic发布Claude 3]]"
  - "[[2024-03-01 LangChain vs LlamaIndex对比]]"
---
# 规范目标
沉淀一套适用于 [[Agent]] 应用开发的共识，包括工具设计、状态管理、审计日志、失败回退和内容安全。

# 核心条款
- 所有 Agent 必须声明目标、工具、输入输出格式与边界条件。
- 涉及对外回复的系统，必须符合 [[所有AI接口必须做内容审核]]。
- 访问知识库时，优先走 [[RAG（检索增强生成）]] 并输出引用证据。
- 面向客服场景时，参考 [[AI客服助手]] 的升级策略与 [[Prompt Engineering]] 模板。

# 关联对象
- 决策：[[采用Agent架构而非纯链式调用]]
- 项目：[[AI客服助手]]、[[内部工具链]]
- 来源：[[2024-01-15 Anthropic发布Claude 3]]、[[2024-03-01 LangChain vs LlamaIndex对比]]、[[2024-06-01 微服务架构最佳实践]]
