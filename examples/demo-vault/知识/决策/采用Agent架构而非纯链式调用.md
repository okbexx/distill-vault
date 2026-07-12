---
type: decision
title: 采用Agent架构而非纯链式调用
status: active
created: 2024-06-17
tags:
  - 决策
  - Agent
  - 架构
project: "[[AI客服助手]]"
evidence:
  - "[[2024-01-15 Anthropic发布Claude 3]]"
  - "[[2024-03-01 LangChain vs LlamaIndex对比]]"
constraints:
  - "[[所有AI接口必须做内容审核]]"
related_outputs:
  - "[[Agent开发规范]]"
---
# 决策内容
[[AI客服助手]] 不再使用单条固定链路完成全部任务，而是切换为受约束的 [[Agent]] 架构。

# 原因
- 客服流程涉及检索、分类、风险判断、工单写回等多步动作，纯链式调用难以适配。
- [[2024-01-15 Anthropic发布Claude 3]] 证明模型在复杂角色保持和工具使用上已经足够可靠。
- [[2024-03-01 LangChain vs LlamaIndex对比]] 也说明真正的难点是流程编排与边界控制，而不是框架本身。

# 影响
- 强化了 [[Prompt Engineering]] 在工具描述和输出约束上的重要性。
- 直接产出了 [[Agent开发规范]]。
- 需要持续接受 [[所有AI接口必须做内容审核]] 的约束审视。
