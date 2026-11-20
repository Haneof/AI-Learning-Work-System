# 核心数据模型（MVP）

版本：V1.0  
状态：逻辑模型，具体 ORM / SQL 类型由实现任务确定。

## 1. 设计原则

- 所有业务数据显式归属 expert；平台级数据使用明确的 system/platform scope。
- 原始资料不可被解析结果覆盖；解析结果、知识、技能均版本化。
- 证据定位必须指向原始 source 与 segment。
- 状态字段使用受控枚举；状态变更写入事件/审计。
- 文件字节存文件系统或对象存储，数据库保存 URI、哈希和元数据。
- 不把向量数据库作为事实主库；关系型数据库保存权威记录。

## 2. 实体

### expert
- id（UUID，PK）
- name、domain、description
- lifecycle_state（CREATED / LEARNING / TRAINING / READY / SUSPENDED / ARCHIVED）
- config_json、created_at、updated_at

### source
- id（UUID，PK）
- expert_id（FK，可空仅限显式共享资料）
- source_type（VIDEO / AUDIO / PDF / DOCUMENT / IMAGE / WEB / LOG / OTHER）
- original_name、storage_uri、sha256、mime_type、size_bytes
- ingest_state、trust_level、metadata_json
- created_at、created_by

### source_segment
- id（UUID，PK）
- source_id（FK）
- segment_type（PAGE / TIME_RANGE / PARAGRAPH / FRAME / REGION / OTHER）
- locator_json（例如 page、start_ms/end_ms、frame_timestamp_ms）
- text_content、media_uri、content_hash
- parser_name、parser_version、created_at

### knowledge_item
- id（UUID，PK）
- expert_id（FK）
- knowledge_type（FACT / CONCEPT / PROCEDURE / RULE / EXCEPTION / RISK）
- statement、content_json
- epistemic_type（DIRECT_QUOTE / EXTRACTED_FACT / INFERENCE / RECOMMENDATION）
- lifecycle_state（CANDIDATE / REVIEW_REQUIRED / APPROVED / SUPERSEDED / REJECTED）
- confidence_label（LOW / MEDIUM / HIGH；非概率保证）
- version、created_at、updated_at

### evidence_link
- id（UUID，PK）
- knowledge_item_id（FK）
- source_segment_id（FK）
- relation（SUPPORTS / CONTRADICTS / CONTEXT）
- quote_or_excerpt、review_state、created_at

### skill
- id（UUID，PK）
- expert_id（FK）
- slug、name、description
- current_version_id（FK，可空）
- lifecycle_state（DRAFT / VALIDATING / APPROVED / DEPRECATED / SUSPENDED）
- created_at、updated_at

### skill_version
- id（UUID，PK）
- skill_id（FK）
- version、package_uri、package_hash
- manifest_json（输入输出、工具、权限、风险、依赖）
- source_evidence_json
- validation_state、created_at、created_by

### skill_test_run
- id（UUID，PK）
- skill_version_id（FK）
- test_suite_version、status（QUEUED / RUNNING / PASSED / FAILED / BLOCKED / TIMED_OUT）
- input_ref、report_uri、metrics_json、environment_json
- started_at、finished_at

### task
- id（UUID，PK）
- expert_id（FK）
- task_type、goal、input_json
- state（QUEUED / RUNNING / WAITING_APPROVAL / SUCCEEDED / FAILED / CANCELLED）
- requested_permissions_json、result_json、trace_id
- created_at、started_at、finished_at

### task_event
- id（UUID，PK）
- task_id（FK）
- sequence_no、event_type、payload_json、created_at
- UNIQUE(task_id, sequence_no)

### audit_event
- id（UUID，PK）
- actor_type、actor_id、expert_id、task_id
- action、resource_type、resource_id
- decision（ALLOW / DENY / REQUIRE_APPROVAL）
- reason_code、details_redacted_json、created_at

## 3. 关系

- expert 1:N source / knowledge_item / skill / task。
- source 1:N source_segment。
- knowledge_item N:M source_segment，通过 evidence_link 关联。
- skill 1:N skill_version。
- skill_version 1:N skill_test_run。
- task 1:N task_event。
- audit_event 可关联 expert/task/resource，但审计记录不得依赖业务对象仍然存在。

## 4. 必须实现的约束

1. 同一 expert 内 source.sha256 可用于重复导入识别；不得跨 expert 自动暴露资料。
2. evidence_link 指向的 source_segment 必须与 knowledge_item 的 expert scope 匹配，除非显式共享授权。
3. APPROVED 知识必须至少有一条有效支持证据；纯推断应显式标记且走独立审核策略。
4. APPROVED 技能版本必须存在通过的测试报告，并且测试报告对应同一 package_hash。
5. skill_version 不可原地修改；变更必须创建新版本。
6. task_event sequence_no 单调递增；任务终态不可无审计地回退。
7. L3 操作审批记录需绑定动作参数摘要；参数变化后审批失效。
8. 日志与审计不得存储明文密钥、访问令牌或不必要的个人数据。

## 5. MVP 暂缓

- 完整组织/租户计费。
- 复杂知识图谱和跨专家自动共享。
- 自动遗忘/合规保留策略引擎。
- 大规模向量索引分片。
- 多区域分布式事务。

这些不属于阶段 0 的准入条件。
