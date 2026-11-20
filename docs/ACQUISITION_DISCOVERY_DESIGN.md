# 教程发现与采集中心：平台搜索接口设计

版本：V1.0  
状态：SearchService、平台目录与 Bilibili 适配器代码已提交；真实网络可用性尚待运行环境验证

## 1. 目标交互

1. 用户先选择平台。
2. 输入一个或多个关键词。
3. 系统向该平台适配器发起分页搜索。
4. 搜索结果以统一候选卡片展示。
5. 用户可以查看详情、筛选、勾选、批量加入采集队列。
6. 采集队列调用独立下载引擎，下载完成后登记媒体资产。
7. 后续筛选、ASR/OCR、知识提取和技能学习只消费统一的资源/资产对象，不依赖平台原始 API。

搜索和下载必须分离：搜索只获取候选元数据，不应默认下载所有搜索结果。

## 2. 模块边界

| 模块 | 职责 | 不负责 |
|---|---|---|
| Platform Catalog | 展示平台、能力、适配器状态 | 实际搜索 |
| SourceSearchAdapter | 单个平台的关键词搜索、分页、字段映射 | 全局队列和下载 |
| SearchService | 并发调度、超时、错误归一化、结果汇总 | 平台签名/API细节 |
| Candidate Repository | 候选登记、去重、搜索批次、人工选择状态 | 下载文件 |
| Curation Service | 相关性、质量、重复内容和人工复核 | 平台登录 |
| Download Scheduler | 下载任务、重试、暂停恢复、限速 | 页面搜索 |
| Download Engine Adapter | 调用 yt-dlp / aria2 等现成工具 | 自行实现媒体协议 |
| Asset Registry | 原始文件、哈希、来源和派生资产登记 | 重新抓取来源 |

## 3. 已落地的 Python 契约

当前新增：

- `SearchRequest`：平台、关键词、页码、页大小、语言和可选过滤器。
- `ResourceCandidate`：统一 URL、标题、作者、简介、发布时间、时长、语言、封面、互动指标和原始元数据。
- `SearchPage`：分页结果、是否有下一页、警告和适配器版本。
- `SourceSearchAdapter`：异步平台搜索协议。
- `AdapterRegistry`：显式注册和按平台查找适配器。
- `canonicalize_url`：去除 URL fragment 和常见跟踪参数；保留平台可能需要的查询参数，例如 xsec_token。
- `deduplicate_candidates`：按平台 + 规范化 URL 去重，保留首次发现记录。\n- `SearchService`：有界并发、超时、平台失败隔离、跨平台结果汇总。\n- `PlatformCatalog`：平台能力与实现/验证状态目录。\n- `BilibiliSearchAdapter`：WBI 签名视频关键词搜索、分页、标题/作者/时长/互动指标映射；支持可注入 HTTP transport 和可选 Cookie。\n- `CandidateRepository`：SQLite 持久化、跨搜索批次去重关联、人工筛选状态和受控状态迁移。\n- `DownloadService`：显式区分视频页面和普通 HTTP 文件，分别调用 `YtDlpAdapter` / `Aria2Adapter`，不自行实现媒体下载协议。\n- `DownloadVerifier`：文件存在性、非空、SHA-256 校验；可选调用 FFprobe 检查媒体流。\n- CLI：`aios discover-search --platform bilibili --keyword "关键词"` 可执行真实平台搜索并将结果写入 SQLite；可通过环境变量 `BILIBILI_COOKIE` 提供可选会话 Cookie。\n- `SearchService`：有界并发、超时、平台失败隔离、跨平台结果汇总。\n- `PlatformCatalog`：平台能力和实现/验证状态目录。\n- `BilibiliSearchAdapter`：WBI 签名视频关键词搜索、分页、元数据映射；支持可注入 HTTP transport 和可选 Cookie。

接口层不内置伪造搜索结果。Bilibili 适配器使用站点 WBI 搜索接口，默认通过 Python 标准库发起 HTTP 请求；测试通过注入 transport 验证签名请求与字段映射。当前 CI 的 mock transport 测试不等于外网实测，真实运行可能遇到 -412 风控响应，届时会明确报错而不会返回假结果。

## 4. 平台适配器选择策略

先建立平台能力目录，不假定所有平台都支持相同功能：

- `keyword_search`
- `pagination`
- `creator_search`
- `video_detail`
- `direct_media_url`
- `subtitle`
- `authenticated_session`

每个平台/适配器必须报告：
- provider 名称、版本和代码来源；
- 平台能力矩阵及最后验证时间；
- 是否需要用户登录态；
- 返回字段覆盖率；
- 错误类型、限流/验证码状态；
- 是否真实网络验证，还是仅 mock/fixture 测试。

平台搜索不可用时应返回明确的 `unsupported` 或 `temporarily_unavailable` 状态，不得返回 mock 候选并显示为真实搜索结果。

## 5. 外部项目评估结论

### MediaCrawler Video Workbench

它有平台选择、关键词/作者/榜单检索、候选筛选、下载和任务恢复等完整工作台流程，适合做交互和流程参考。

当前不作为本仓库可直接复用的依赖：其仓库和上游 MediaCrawler 标注为非商业学习许可证。若未来需要直接复用代码，先取得明确授权。不得把其功能说明当成我们自己的实现状态。

### Authurzk/mediacrawler

它展示了较清晰的平台 Adapter 注册、异步并发搜索和 SSE 进度推送设计，可作为接口设计参考。其仓库说明抖音真实搜索尚未打通；当前不应将其宣称为三平台全可用的生产连接器。正式接入前必须逐平台检查许可证、代码、测试和真实网络表现。

## 6. 下载引擎复用策略

不开发自有下载器内核。

| 输入类型 | 首选工具 | 责任边界 |
|---|---|---|
| 视频页面 / 平台媒体 | yt-dlp | 解析站点、提取媒体、HLS/DASH 下载 |
| 普通 HTTP 大文件 | aria2 | 多连接分段、断点续传；服务器支持 Range 时生效 |
| 媒体探测/合并/抽取 | FFmpeg / ffprobe | 媒体信息探测、音视频合并、音轨/关键帧处理 |

统一下载任务由本系统管理。引擎适配器只负责命令参数转换、进程生命周期、进度/错误解析和退出码处理。下载后需检查文件存在、非空、媒体流、时长和哈希，再登记为 MediaAsset。

HLS/DASH 分片并发优先使用 yt-dlp 的原生能力；需要时配置 aria2c external downloader。普通 HTTP 文件只有在服务端支持 Range 时才启用分段，否则退化为顺序下载。

## 7. 数据流与状态

`SearchRequest` → `SearchPage` → `ResourceCandidate` → 人工/规则筛选 → `DownloadJob` → 下载引擎 → 文件校验 → `MediaAsset` → 内容理解。

候选状态建议：

`DISCOVERED → REVIEW_PENDING → SELECTED → QUEUED → DOWNLOADING → DOWNLOADED → VERIFIED`

分支状态：

- `REJECTED`：人工或规则拒绝，保留原因。
- `DUPLICATE`：指向已有候选/资产。
- `RETRY_WAIT`：可重试错误。
- `FAILED`：重试耗尽或不可恢复。
- `NEEDS_REVIEW`：低置信度或元数据冲突。

搜索任务与下载任务使用不同 ID。相同候选可出现在多个搜索批次，但只应有一个可复用的资产/下载记录。

## 8. 实施顺序

1. 已完成：统一搜索请求、候选、分页结果和 Adapter Registry 契约。
2. 下一步：Platform Catalog + SearchService（超时、并发、部分成功、错误归一化）。
3. 接入第一个许可清晰、可验证的平台适配器；优先选择 API/接口稳定且测试可复现的平台。
4. 候选存储、筛选状态和批量入队。
5. yt-dlp / aria2 下载适配器和 FFmpeg 媒体校验。
6. 端到端真实平台搜索 → 人工选中 → 下载 → Asset Registry 验收。

## 9. 验收标准

- 无效关键词、平台、分页参数在发起网络请求前被拒绝。
- 一个平台失败不应抹掉其他平台已经成功返回的结果。
- 同平台同 URL 的跟踪参数变体被去重；不同平台的相同 URL 不被误合并。
- 平台访问 token 等可能影响资源定位的查询参数不得被错误删除。
- 每条候选记录能追溯搜索关键词、平台、适配器名称/版本和发现时间。
- 搜索本身不自动下载。
- 未真实执行的适配器必须明确标记为未验证；mock 测试不能作为平台可用性证明。
