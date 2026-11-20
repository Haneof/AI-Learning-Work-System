# 核心状态机

版本：V1.0  
状态：逻辑定义，实施时必须以代码枚举、迁移校验和测试固化。

## 1. 资料导入与解析

```text
REGISTERED -> QUEUED -> PROCESSING -> COMPLETED
                              |-> PARTIAL
                              |-> FAILED
QUEUED -> CANCELLED
```

- REGISTERED：元数据登记完成，原文件只读。
- QUEUED：等待处理。
- PROCESSING：解析器正在执行。
- COMPLETED：所有必需处理步骤成功。
- PARTIAL：部分产物成功，存在可恢复警告。
- FAILED：不可恢复错误或重试耗尽。
- CANCELLED：用户/系统取消。

重试规则：仅对可重试错误执行；重试次数有上限；每次尝试独立记录 parser_version、attempt 和错误。

## 2. 知识生命周期

```text
CANDIDATE -> REVIEW_REQUIRED -> APPROVED
     |              |             |
     |              +-> REJECTED  +-> SUPERSEDED
     +-> REJECTED
```

- 自动抽取结果默认 CANDIDATE。
- 缺证据、来源冲突或高影响知识进入 REVIEW_REQUIRED。
- APPROVED 只能由有权限的审核事件触发。
- 旧知识被新版本取代时标记 SUPERSEDED，保留历史和证据。
- 不允许模型直接写入 APPROVED 状态。

## 3. 技能生命周期

```text
DRAFT -> VALIDATING -> APPROVED -> DEPRECATED
  |          |
  |          +-> DRAFT (修订新版本)
  +-> SUSPENDED
APPROVED -> SUSPENDED
```

- DRAFT：候选技能。
- VALIDATING：静态检查和沙箱测试中。
- APPROVED：满足策略和测试门槛的特定不可变版本。
- DEPRECATED：不再推荐新任务使用。
- SUSPENDED：发现安全问题或回归失败，立即停止调度。
- 任何内容变更创建新 skill_version；旧版本保留。
- APPROVED 不等于获得 L3 权限。

## 4. 任务生命周期

```text
QUEUED -> RUNNING -> SUCCEEDED
            |-----> FAILED
            |-----> WAITING_APPROVAL -> RUNNING
            |-----> CANCELLED
```

- WAITING_APPROVAL 时暂停外部副作用，不得在后台继续执行该动作。
- 审批通过只对已绑定 action_hash 生效；参数变化须重新审批。
- 终态 SUCCEEDED / FAILED / CANCELLED 不允许直接回到 RUNNING。
- 重试创建新 attempt 或新 task，并关联 parent_task_id。

## 5. 专家生命周期

```text
CREATED -> INGESTING -> LEARNING -> TRAINING -> EVALUATING -> READY
                                                        |        |
                                                        +-> BLOCKED
READY -> WORKING -> READY
  |         |
  +-> SUSPENDED <-+
  +-> DEGRADED
```

实际状态按能力阶段与运行状态分离实现，避免单一枚举混合“培养阶段”和“是否正在执行”。建议字段：
- capability_stage：P1 / P2 / P3 / P4
- operational_state：IDLE / BUSY / BLOCKED / SUSPENDED / DEGRADED

阶段晋级必须由评估服务基于冻结测试集、阈值和人工批准（如策略要求）产生事件。

## 6. 状态机实现要求

- 所有状态迁移走统一 transition 函数或领域服务。
- 每条迁移定义允许的 source state、target state、actor、guard、side effects。
- 非法迁移返回稳定错误码并写审计。
- 事件写入与状态更新需保证一致性；MVP 可使用数据库事务与 outbox 模式。
- 并发更新使用版本号/乐观锁。
- 每个状态机必须覆盖合法路径、非法路径、重复事件、重试、取消和崩溃恢复测试。
