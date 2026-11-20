# 技术选型与验证策略

版本：V1.0。开源优先、按需引入、先验证再定案。以下均为候选而非生产依赖。

## 模型策略
主模型方向固定为本地无审查 Qwen 3.5，4B 与 9B 两个候选。需确认精确模型仓库与 revision、是否具备视觉输入、权重许可、量化格式、推理后端、上下文长度和实际资源占用。4B/9B 使用同一测试集和一致提示模板比较，不预设参数更大就一定更好。业务逻辑不得绑定单一模型 API。

## 开源候选
| 领域 | 项目 | 用途 | 当前定位 |
|---|---|---|---|
| 视频转技能 | [Video-to-Skill](https://github.com/brenoepics/video-to-skill) | 视频转录、关键帧、步骤提取、技能草案 | 优先小样本实验 |
| 电脑操作 | [OpenGCUA](https://github.com/Tongyi-MAI/OpenGCUA) | GUI、代码执行、电脑使用 Agent | 候选，需测成熟度 |
| 电脑操作研究 | [Agent S](https://github.com/simular-ai/Agent-S) | 操作经验与评测方法参考 | 研究参考 |
| GUI 视觉 | [UI-Venus](https://github.com/inclusionAI/UI-Venus) | GUI 屏幕理解 | 资源需求待实测 |
| 视频理解 | [InternVideo](https://github.com/OpenGVLab/InternVideo) | 视频表征与长视频理解 | 后续评估 |
| 视频理解 | [MOSS-VL](https://github.com/OpenMOSS/MOSS-VL) | 多模态/视频理解研究 | 后续评估 |
| 技能格式 | [Agent Skills](https://github.com/anthropics/skills) | 可移植技能目录参考 | 借鉴格式 |
| 浏览器自动化 | [Playwright](https://github.com/microsoft/playwright) | 浏览器控制与测试 | 优先评估 |
| 浏览器 Agent | [Browser Use](https://github.com/browser-use/browser-use) | 浏览器任务自动化 | 候选 |
| 桌面自动化 | [CUA](https://github.com/trycua/cua) | 桌面环境控制 | 候选 |
| ASR | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | 本地语音识别 | 优先评估 |
| OCR | [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | 文档与屏幕 OCR | 优先评估 |
| 媒体处理 | [FFmpeg](https://ffmpeg.org/) | 转码、抽帧、音轨处理 | 基础工具 |
| 向量检索 | [Qdrant](https://github.com/qdrant/qdrant) | 语义检索 | MVP 评估 |
| 工作流编排 | [LangGraph](https://github.com/langchain-ai/langgraph) | 状态化 Agent 工作流 | 候选 |

代码许可、模型权重许可和数据集许可必须分别核查。代码开源不代表权重或数据可自由商用。

## 本地资源策略
原型设备为 8GB VRAM / 16GB RAM。先单模型低并发；视频离线分段、代理分辨率、抽帧和转录；OCR/ASR 按需加载；任务队列支持断点续跑和缓存。9B 是否可用必须实测，不以参数量推断。

## 统一基准测试
比较知识提取与证据引用、视频步骤理解、技能生成完整性、多步骤推理、电脑操作成功率、异常处理、未见任务迁移、延迟/吞吐、显存/内存和长任务稳定性。若主模型不支持视觉输入，则评估其对视觉模块解析结果的理解能力。

## 技术准入
候选依赖进入主干前，完成许可证与维护状态检查、可重复安装、Windows 兼容性、资源测量、最小功能测试、安全边界和替代方案比较。未通过者留在实验区。