# 系统架构

版本：V1.0

## 分层结构
1. 资料接入：视频、录屏、PDF、Office、图片、网页、操作日志和历史任务。
2. 资料处理：识别、去重、切分、OCR、ASR、关键帧、时间戳和元数据。
3. 知识学习：提取事实、概念、流程、条件、例外和风险；保留证据并识别冲突。
4. 技能编译：将知识转成包含步骤、判断、异常处理、输出和验证的技能。
5. 专业记忆：知识、技能、任务、决策、成功经验和失败经验分开管理。
6. 执行层：通过 API、浏览器 DOM、Accessibility Tree、GUI、Shell/Python 等执行。
7. 评估进化：评估知识、技能、技能组合、迁移能力、异常处理和真实任务表现。
8. 调度治理：管理专家生命周期、任务队列、权限、人工审批、审计和资源调度。

## 核心数据流
资料导入 → 原始文件登记 → 多模态解析 → 带证据知识条目 → 冲突处理/审核 → 技能候选 → 沙箱测试 → 技能版本发布 → 任务执行 → 结果验证 → 经验沉淀 → 能力缺口识别 → 新学习任务。

每个阶段记录状态、输入输出、模型与工具版本、耗时、错误和重试信息。

## 技能数据契约
每项技能至少包含：唯一 ID、名称、版本、状态、目标、适用范围、前置条件、输入输出结构、执行步骤、成功判据、条件分支、异常恢复、工具与权限、风险说明、来源定位、测试用例、测试结果、创建和变更记录。

建议技能包采用目录结构：SKILL.md、scripts、references、assets、tests 和 metadata。具体 schema 后续独立版本化。

## 专家状态机
CREATED → INGESTING → LEARNING → TRAINING → EVALUATING → READY → WORKING。
异常状态包括 BLOCKED、NEEDS_REVIEW、SUSPENDED、DEGRADED。状态变化必须由明确事件触发并记录原因，不得由模型自行宣称晋级。

## 服务边界
- Model Gateway：统一模型调用、版本、上下文和能力声明。
- Ingestion Worker：文件登记、拆分和解析队列。
- Media Pipeline：FFmpeg、ASR、OCR、抽帧和时间轴对齐。
- Knowledge Service：知识、证据、冲突、版本和审核。
- Skill Compiler：技能生成、静态检查和依赖清单。
- Sandbox Runner：隔离运行脚本与工具调用。
- Evaluation Service：测试集、评分、回归和晋级决策。
- Memory Service：专家隔离的记忆读写与检索。
- Agent Runtime：计划、工具路由、执行、观察和恢复。
- Orchestrator / Audit：专家调度、权限审批和审计。

MVP 可先采用模块化单体，避免过早拆分微服务。

## 存储建议
原始媒体使用文件/对象存储；结构化元数据优先 PostgreSQL，原型可用 SQLite；向量检索评估 Qdrant；技能和配置用 Git 版本管理；任务状态和审计以关系型数据库为准。

## 模型与资源
主模型候选为本地无审查 Qwen 3.5 4B/9B，统一测试后定默认版本。必须登记精确模型 ID、权重来源、量化、上下文、视觉能力、后端和许可。视觉、OCR、ASR、视频理解作为专用模块按需加载或异步处理。8GB VRAM / 16GB RAM 下必须限制并发、分辨率和缓存。

## 可观测性
任务记录 trace_id、expert_id、task_id、source_id、skill_id/version、模型与工具版本、权限判定、结果验证、耗时、资源占用和错误码。敏感数据按策略脱敏。