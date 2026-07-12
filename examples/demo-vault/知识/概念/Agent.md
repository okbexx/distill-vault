---
type: concept
title: Agent
status: stable
created: 2024-06-11
tags:
  - AI
  - 工作流
  - 自动化
related_concepts:
  - "[[RAG（检索增强生成）]]"
  - "[[Prompt Engineering]]"
related_projects:
  - "[[AI客服助手]]"
  - "[[内部工具链]]"
source_basis:
  - "[[2024-01-15 Anthropic发布Claude 3]]"
  - "[[2024-03-01 LangChain vs LlamaIndex对比]]"
---
# 定义
[[Agent]] 指的是能够根据目标自主拆解步骤、调用工具、读取上下文并根据反馈调整行为的智能体模式。相比纯提示词拼接，Agent 更像一个可组合的软件层。

# 为什么重要
- [[AI客服助手]] 需要 Agent 来协调检索、内容审核、工单写入和升级策略。
- [[内部工具链]] 把 Agent 当作操作入口，用来统一脚本、知识查询和故障排查。
- [[2024-01-15 Anthropic发布Claude 3]] 让我意识到大上下文只是基础，真正决定可用性的是 Agent 编排。

# 工程经验
- Agent 如果没有好的 [[Prompt Engineering]]，很容易在任务分解阶段偏航。
- Agent 需要明确边界，尤其要受 [[所有AI接口必须做内容审核]] 与 [[数据不出境]] 约束。
- 当 Agent 能访问 [[RAG（检索增强生成）]] 时，必须限定它的检索范围与引用格式。

# 关联对象
- 项目：[[AI客服助手]]、[[内部工具链]]、[[智能文档平台]]
- 决策：[[采用Agent架构而非纯链式调用]]
- 输出：[[Agent开发规范]]
- 来源：[[2024-01-15 Anthropic发布Claude 3]]、[[2024-03-01 LangChain vs LlamaIndex对比]]
