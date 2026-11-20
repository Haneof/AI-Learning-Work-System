# API 契约（MVP）

版本：V1.0  
状态：逻辑契约；具体 HTTP 框架与路径前缀由实现 ADR 决定。

## 1. 通用约定

- JSON UTF-8；时间统一 ISO 8601 UTC。
- ID 使用 UUID；分页使用 cursor/limit。
- 所有异步操作返回 task_id 或 job_id，不在 HTTP 请求中长时间阻塞。
- 写请求支持 Idempotency-Key；重复请求不得重复创建副作用。
- 每个响应包含 request_id；后台任务另含 trace_id。
- 错误统一结构：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable summary",
    "details": {},
    "retryable": false
  },
  "request_id": "uuid"
}
```

## 2. 核心接口草案

### 健康检查
- GET /health
- 返回服务状态、版本和依赖可用性摘要；不得泄露密钥或内部路径。

### 登记资料
- POST /v1/experts/{expert_id}/sources
- 输入：source_type、original_name、storage_uri/upload_ref、sha256、mime_type、size_bytes、metadata。
- 输出：source_id、ingest_state、duplicate_of（如重复）。
- 只登记元数据和受控文件引用；上传通道由部署环境决定。

### 启动解析
- POST /v1/sources/{source_id}/ingestion-jobs
- 输入：parser_profile、options、idempotency_key。
- 输出：job_id、state。
- 解析完成生成 source_segment，不覆盖原始资料。

### 查询解析结果
- GET /v1/ingestion-jobs/{job_id}
- 返回 state、progress、warnings、error_code、segment_count、resource_metrics。

### 创建知识候选
- POST /v1/experts/{expert_id}/knowledge-items
- 输入：knowledge_type、statement、epistemic_type、confidence_label、evidence_refs[]。
- 输出：knowledge_item_id、lifecycle_state。
- 缺少证据时只能进入 CANDIDATE / REVIEW_REQUIRED，不得自动 APPROVED。

### 审核知识
- POST /v1/knowledge-items/{knowledge_item_id}/reviews
- 输入：decision（APPROVE / REJECT / REQUEST_CHANGES）、comment。
- 输出：review_id、new_state。
- 调用者权限由服务端判定，不接受模型自报审批身份。

### 创建技能候选
- POST /v1/experts/{expert_id}/skills
- 输入：slug、name、description、package_manifest、source_evidence_refs[]。
- 输出：skill_id、version_id、validation_state。

### 验证技能
- POST /v1/skill-versions/{version_id}/validation-runs
- 输入：test_suite_ref、sandbox_profile。
- 输出：test_run_id、state。
- 沙箱策略由服务端强制；调用者不能通过请求体关闭隔离。

### 创建任务
- POST /v1/experts/{expert_id}/tasks
- 输入：goal、input、allowed_tools、requested_permission_scope。
- 输出：task_id、state。
- requested scope 是申请，不是授权；实际权限取服务端策略与审批交集。

### 查询任务
- GET /v1/tasks/{task_id}
- 返回 state、events cursor、result、approval_required、failure_reason。

### 审批高风险动作
- POST /v1/approvals/{approval_id}/decision
- 输入：decision、approved_action_hash、comment。
- 输出：approval_state。
- 只允许具备审批权限的真实用户调用；审批必须绑定具体动作和参数摘要。

## 3. 访问控制要求

- 所有资源访问都校验 expert scope。
- 不信任客户端传入的 actor、role、approval_state 或权限等级。
- 工具权限由后端策略引擎计算，默认拒绝。
- 列表接口不得跨专家泄露存在性、数量或内容。
- 审批接口必须防重放并记录审计事件。

## 4. 版本策略

- API 采用 /v1 前缀；破坏性契约变更升级主版本。
- schema 变更需兼容性测试和迁移说明。
- OpenAPI 文件由实现代码生成或与实现同步，不维护脱节的手写副本。
- 本文为实现前契约，不代表接口已经实现。
