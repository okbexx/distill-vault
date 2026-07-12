---
type: constraint
title: 所有AI接口必须做内容审核
status: active
created: 2024-06-19
tags:
  - 约束
  - 安全
  - 审核
related_decisions:
  - "[[采用Agent架构而非纯链式调用]]"
workaround:
  - "[[Agent开发规范]]"
---
# 约束说明
所有对外提供回复、建议、摘要或自动操作指令的 AI 接口，都必须经过内容审核与风险分级，不允许直接裸输出模型结果。

# 影响范围
- [[AI客服助手]] 是首要执行对象。
- [[内部工具链]] 中所有具备自动执行能力的 Agent 也要遵守。
- [[Prompt Engineering]] 需要显式设计高风险回复的降级路径。

# 关联
- 决策：[[采用Agent架构而非纯链式调用]]
- 输出：[[Agent开发规范]]
