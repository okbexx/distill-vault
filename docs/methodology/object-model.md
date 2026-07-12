# 对象类型

## 目的

- 定义 private acceptance vault 的一等公民对象。
- 所有运行时都必须遵守这里的语义，不得私自创造平行类型。

## 核心对象

### 来源

原始来源。系统唯一可信入口。

最小字段：

- `id`
- `type`
- `title`
- `source_type`
- `created_at`
- `source_url`
- `author`
- `reliability`
- `status`
- `projects`
- `concepts`
- `entities`
- `outputs`

规则：

- 来源保留原始内容，不改写正文。
- 来源可以补充元数据、摘要、链接，但原文层不可被覆盖。
- 所有外部输入先成为来源，再考虑晋升。

### 项目

围绕一项工作积累的知识档案，记录已经发生的成果、里程碑、决策、约束和证据。

最小字段：

- `id`
- `type`
- `title`
- `status`
- `updated`
- `goal`
- `summary`
- `sources`
- `decisions`
- `constraints`
- `concepts`
- `entities`
- `key_outputs`

规则：

- 项目是主导航对象。
- 已完成事实中的长期信息必须最终汇总到项目。
- 项目页直接呈现成果和稳定结论，不承载原始记录全文。
- 正在做、下一步、待办、优先级和截止时间属于日程工具，不进入项目对象。
- 全量输出关系由输出对象的 `project` 回链和图投影计算，项目只保存精选 `key_outputs`。

### 概念

可复用的方法、概念、长期判断。

最小字段：

- `id`
- `type`
- `title`
- `definition`
- `status`
- `source_basis`
- `related_projects`
- `related_concepts`

规则：

- 只有可泛化、可复用、非一次性的内容才能成为概念。
- 概念必须能回溯到来源或稳定输出。

### 实体

人、团队、公司、产品、工具、系统。

最小字段：

- `id`
- `type`
- `title`
- `entity_type`
- `description`
- `related_projects`
- `related_sources`

### 决策

已经做出的取舍。

最小字段：

- `id`
- `type`
- `title`
- `status`
- `project`
- `context`
- `decision_date`
- `evidence`
- `constraints`
- `supersedes`
- `related_outputs`

规则：

- 决策必须记录原因，不允许只写结果。
- 新决策若推翻旧结论，必须显式写 `supersedes`。

### 约束

限制、坑、边界、失败经验。

最小字段：

- `id`
- `type`
- `title`
- `status`
- `project`
- `severity`
- `evidence`
- `related_decisions`
- `workaround`

规则：

- 约束优先服务于减少返工。
- 约束可以失效，但不能静默消失。

### 输出

对内或对外产物。

最小字段：

- `id`
- `type`
- `title`
- `output_type`
- `created_at`
- `audience`
- `project`
- `derived_from`
- `status`

规则：

- 日报、周报、报告、PPT 都属于输出。
- 输出不是知识本体，但可以成为概念或决策的证据来源。

## 运维对象

### 会话

一次工作过程或一次交互整理。

### 队列项

进入收件、晋升、评审、归档的排队项。

### 健康检查

知识库巡检结果，包括冲突、孤儿、重复、过时项。

### Agent 规格

某类 agent 的职责、输入、输出、边界。

### 自动化规格

某个自动任务的触发条件、输入源、输出目标。
