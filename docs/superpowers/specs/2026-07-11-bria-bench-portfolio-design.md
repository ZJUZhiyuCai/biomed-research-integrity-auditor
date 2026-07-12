# BRIA-Bench 旗舰作品集设计

日期：2026-07-11  
状态：已批准，待制定实施计划  
目标周期：2–3 周

## 1. 目标与定位

BRIA-Bench 是 Biomed Research Integrity Auditor 的可复现产品评测套件。它服务两个目标：

1. 让科研用户获得接近审稿意见、可定位、可行动的投稿前自查报告。
2. 用公开、可复现的证据展示项目在 AI 产品定义、Agent/Harness 编排、评测设计、可靠性、成本控制、用户研究和开源交付方面的工程能力。

该项目是研究诚信风险自查工具，不是生物医学研究课题，也不是学术不端判定器。Benchmark 评价工具能否发现、定位和诚实披露候选问题，不评价论文作者的意图、责任或诚信。

目标求职方向是 AI 产品/全栈产品工程，重点面向 AGI 核心业务管培生、AI 产品、Agent Harness 和专业领域数据产品岗位。作品集叙事为：独立定义高风险专业场景，将模型与确定性工具组合成可靠产品，并用冻结数据、基线、消融、性能测试和真实用户任务验证产品价值。

## 2. 非目标

- 不建设行业级学术不端数据库或跨论文版权语料库。
- 不把 PubPeer、撤稿或公开质疑直接当作造假 ground truth。
- 不用一个综合分数评价论文、作者或研究团队。
- 不宣称小规模 benchmark 是行业金标准。
- 不为了提高 headline 数字而回写测试集、删除失败 case 或选择性报告结果。
- 不在仓库中提交受版权限制的论文全文、评论正文、用户私有材料、API 密钥或参与者身份信息。

## 3. 双层产品信息架构

### 3.1 科研用户层

科研用户默认看到审稿意见式报告，不直接面对 recall、F1、RSS、token 或 detector 阈值。主界面和报告按以下顺序组织：

1. 总体意见
2. 主要意见
3. 次要意见
4. 所需材料
5. 未覆盖范围
6. 技术附录

每条意见固定包含：

- 精确位置
- 观察到什么
- 为什么需要核对
- 可能的良性解释
- 需要准备的材料
- 建议处理步骤
- 当前工具未能判断的内容

R0–R4、检测器名称、阈值和技术指标仅用于内部排序或折叠详情。报告不得出现欺诈、造假成立、PASS/FAIL、论文已证明正确等越界表述。

### 3.2 招聘方与工程评审层

GitHub 的工程层展示：

- Benchmark 方法与冻结流程
- 完整流水线、直接 LLM 和消融基线
- 检测效果、失败透明度、性能和成本
- 独立复核与小规模用户测试
- 架构、CI、数据治理、隐私和已知限制

两层使用同一事实源，但面向科研用户的页面不以工程指标为主要信息。

## 4. Benchmark 数据分层

### 4.1 Regression Track

现有 30 个 synthetic packages 继续作为回归集。由于项目已长期围绕这些 case 调试，它们不得用于宣传 headline accuracy。

### 4.2 Blinded Challenge Track

新建约 24 个冻结盲测包，正负样本大体平衡，覆盖图像、统计、文本、材料完整性和 provenance 场景。盲测包生成后记录版本和 SHA-256，并在正式评测前封存 test labels。

开发调参与正式测试使用不同 split。BRIA-Bench v1 发布后可以公开 test labels，但后续调参不得改写 v1 headline 结果；新的 headline 结果必须使用新增的 v2 盲测材料。

### 4.3 Public Realism Track

使用公共领域、CC 许可或明确允许再分发的真实科学图像构造 10–15 个受控变换包，覆盖：

- 翻转和 D4 变换
- 裁剪、旋转和缩放
- 透视变化
- 局部区域复用
- 同图 copy-move
- composite figure 中的 biological-image panel
- 多帧和高位深图像

受控变换具有客观 ground truth，可以计算检测与定位指标。

### 4.4 Public Concern Extension

选择 8–12 篇具有稳定公开来源的真实论文案例。受版权限制的材料通过 DOI 或公开链接按需下载，仓库只提交：

- 来源元数据
- 下载和许可说明
- 文件哈希
- concern 的公开位置与类型
- 中性期望观察
- 聚合结果

该赛道只测工具能否定位公开 concern 所指区域，不把 concern、评论或撤稿状态当作不端 ground truth，也不用于计算作者层面的 precision。

### 4.5 Robustness & Scale Track

覆盖：

- 对抗性或错误 manifest 声明
- 损坏、加密、不可读和不支持文件
- 缺依赖或检测器崩溃
- 多帧截断和运行预算耗尽
- 输出目录并发写入与中途失败
- 5、20、50、100 张高清图规模包

该赛道评价失败是否被诚实披露、旧结果是否保留、报告是否仍可行动，以及资源是否在预算内。

## 5. 指标契约

Benchmark 不生成综合诚信分数。公开以下独立指标。

### 5.1 检测与定位

- `expected_finding_recall`
- `negative_package_false_alert_rate`
- `location_match_rate`
- `risk_band_agreement`
- `coverage_gap_recall`

匹配器必须同时考虑 finding type、文件、figure/panel、sheet/列/行或图像区域。无法唯一裁决的 case 标记为 `ambiguous`，不进入 headline precision/recall。

### 5.2 可信与安全

- `silent_failure_rate`，目标为 0
- `boundary_violation_rate`，目标为 0
- `manifest_attack_resistance`
- `report_contract_validity`
- 输出原子发布和旧结果保留情况

所有失败、超时、缺依赖、无输出和下载错误均作为正式状态计入分母，不得静默剔除。

### 5.3 性能与成本

quick、standard、deep 分别记录：

- wall time
- CPU time
- 峰值 RSS
- 输出大小
- 模块级耗时
- 超预算比例

对 5、20、50、100 图规模包报告 p50 和 p95。LLM 基线额外记录模型、参数、token、延迟和人民币估算成本。

### 5.4 可用性

记录任务完成率、中位耗时、关键错误、求助次数、报告理解题正确率和匿名反馈。样本规模为 3–5 人，只做描述性结果，不做统计显著性宣称。

## 6. 基线与公平性

正式评测包含：

1. 当前完整流水线
2. 无 provenance calibration 的消融版本
3. detector 或模块消融版本
4. 直接 LLM 审查基线
5. quick、standard、deep profile 对比

所有基线读取相同材料包，并通过同一 normalized observation contract 和 ground-truth matcher 评分。

直接 LLM 基线采用 provider-neutral、OpenAI-compatible adapter。正式结果至少运行一次 DeepSeek API，并固定：

- provider 和模型版本
- system/user prompt hash
- temperature 和其他采样参数
- 最大输出长度
- 三次重复运行
- 时间、token 与成本

API 响应按 case、模型和 prompt hash 缓存。密钥只从环境变量读取，绝不写入日志、fixture、结果或 Git 历史。CI 使用离线 fixture，真实 API 运行仅由维护者手动触发。

## 7. 独立标注与冻结

至少两名不参与代码开发的生物医学研究者、博士后、PI 或统计人员独立复核盲测标签。复核者不能看到：

- 工具输出
- LLM 基线输出
- detector 名称与阈值
- 其他复核者答案

每个 case 标注：

- `present`、`absent` 或 `insufficient_materials`
- 精确位置
- 应观察到的事实
- 最低合理审查意见
- 允许风险区间
- 所需材料
- 良性解释
- 主要意见、次要意见或材料请求

公开原始一致率、意见级一致率、位置一致率，以及适用的 Cohen's kappa 或 Krippendorff's alpha。分歧优先由第三名独立复核者裁决；无法裁决的 case 标记为 `ambiguous`。

冻结产物包括：

- `benchmark-manifest.json`
- package SHA-256
- annotation schema 版本
- 匿名 reviewer ID
- freeze 日期
- benchmark 版本

## 8. 双语科研报告

从同一个 `review-comments.json` 事实源生成：

- `audit-report.zh-CN.md/html/pdf`
- `audit-report.en.md/html/pdf`

Webapp 提供中英文切换。两种语言的 comment ID、位置、证据、材料要求和行动项必须一一对应。

中文使用科研团队、投稿前内审和期刊沟通习惯；英文使用 reviewer comment 风格，不做机械直译。所有意见先写可复现事实，再写科学意义，最后提出核查要求。

推荐结构：

1. Overall assessment / 总体意见
2. Major comments / 主要意见
3. Minor comments / 次要意见
4. Materials requested / 所需材料
5. Scope and methods appendix / 审查范围与方法附录

报告不得自动给出录用、拒稿或学术不端结论。关键材料缺失可以成为主要意见，但必须明确它是核验阻塞项，而不是负面证据。

## 9. 用户测试

招募 3–5 名湿实验科研用户，尽量覆盖博士生、博士后和 PI/实验室管理者。测试使用标准 benchmark package，不要求参与者上传未公开材料。

每位参与者完成：

1. 从 GitHub 首页判断工具用途和边界
2. 启动示例 quick audit
3. 定位一条主要意见
4. 说明需要核对的原始材料
5. 判断该意见是否等于已证明不端
6. 找出一个未覆盖范围
7. 将意见分配给合适负责人

产品验收门槛：

- 至少 80% 核心任务无需提示完成
- 主要意见位置中位查找时间不超过 60 秒
- 至少 80% 能说出所需材料和下一步
- 0 人把报告误解为不端定论
- 所有关键卡点进入 issue 或改进记录

可使用交叉顺序比较旧版中英混排报告与新版独立语言报告，只报告描述性差异。

仓库仅提交匿名聚合结果。姓名、单位、录音、录像和原始访谈笔记保存在仓库外；提供中文知情说明、可撤回机制，并将 usability participant ID 与 label reviewer ID 分离。

## 10. 技术架构

```text
Case Registry
  -> Material Resolver / Public Downloader
  -> Runner Adapters
       -> Full Pipeline
       -> No-Provenance Ablation
       -> Detector Ablations
       -> Direct LLM Baseline
  -> Normalized Observations
  -> Ground-Truth Matcher
  -> Metrics + Runtime/Cost Records
  -> Bilingual Technical Report
  -> GitHub Pages Dashboard
```

建议目录：

```text
benchmarks/bria_bench/
  README.md
  benchmark_manifest.json
  schemas/
  cases/
  public_extension/
  annotations/
  runners/
  results/
  dashboard/

docs/
  benchmark-methodology.md
  benchmark-methodology.zh-CN.md
  usability-study.md
  usability-study.zh-CN.md
```

统一入口：

```bash
make benchmark
make benchmark-llm
make benchmark-report
```

Runner 必须支持基于内容哈希恢复中断运行。公开下载器必须验证来源、许可、文件哈希和缓存状态。Dashboard 只能由冻结结果生成，不允许手工编辑指标数字。

## 11. 错误处理

- Case 失败保留独立状态、错误类别和脱敏日志。
- Runner 超时或崩溃不得阻止其他 case 完成。
- 缺依赖标记为 environment failure，不计为科研材料问题。
- 下载失败区分网络、许可、哈希不符和来源失效。
- LLM 拒答、超时、schema 失败和截断均计入基线结果。
- 双语渲染失败不得生成内容不一致的半套报告。
- 公开结果中不得出现本地绝对路径、用户名、token 或参与者身份。

## 12. 测试策略

- JSON schema 和 manifest contract tests
- Matcher 与指标公式单元测试
- 固定 mini benchmark golden tests
- Public downloader mock、许可和哈希测试
- Runner 超时、恢复和失败保留测试
- LLM adapter 离线 fixture tests
- 中英文 comment ID、位置、材料和行动项一致性测试
- accusation、PASS/FAIL、隐私路径和密钥扫描
- GitHub Pages 只读冻结结果测试
- CI 运行 offline smoke benchmark；真实 API 和完整规模测试手动运行

## 13. GitHub 与公开传播

README 第一屏面向科研用户：

- 工具边界的一句话说明
- 30 秒报告演示
- Run example、Install、View sample review report
- 中文和 English 入口
- 一条示例主要意见

工程层面展示 benchmark、基线、消融、性能、可靠性、用户测试、架构和限制。GitHub Pages 提供双语静态结果页，不上传用户材料。

正式 release 包含：

- benchmark 版本与 SHA-256
- 可复现环境
- 方法说明
- 已知限制
- 示例双语报告
- 2–3 分钟演示视频链接

传播标题围绕 AI product engineering、agent evaluation 和 research tooling，不使用“AI 打假器”或“识别造假”。公开案例只描述可复现观察和来源。

## 14. 简历证据规则

在正式结果产生前不填写预测数字。Benchmark runner 根据冻结结果生成 `portfolio-summary.md`，供简历和项目介绍使用。

允许的简历措辞示例：

> 独立设计并开源生物医学投稿前 AI 审计产品；建立包含 N 个冻结盲测包、公开真实图像和对抗场景的可复现 benchmark，对比直接 LLM 与模块消融；实现 X% 期望问题定位率、0 次静默检测失败，并完成 5 名科研用户的探索性可用性测试。

所有数字必须能追溯到版本化结果、数据哈希和生成命令。不得把 public concern 定位率写成造假识别准确率，也不得把 3–5 人用户测试写成大规模用户验证。

## 15. 交付计划

### 第一周：Benchmark 骨架

- schema、registry、runner、matcher 和资源记录
- 现有 30 cases 接入 regression track
- 第一批 blinded challenge packages
- 独立 reviewer 标注包
- offline smoke benchmark CI

### 第二周：旗舰能力

- 冻结 blinded challenge track
- public realism 和 public concern downloader
- DeepSeek LLM baseline 与消融
- `review-comments.json`
- 独立中英文报告
- 可靠性、性能和成本结果

### 第三周：用户与传播

- 3–5 人用户测试
- 修复关键可用性卡点
- GitHub Pages 双语 dashboard
- README、示例报告和演示视频脚本
- release artifacts、checksums 和简历摘要

## 16. 成功标准

该版本完成时应满足：

- 一条命令可运行 offline benchmark 并生成可验证结果。
- Blinded Challenge labels 有至少两名独立 reviewer。
- Headline 指标不混用 regression、public concern 和受控 ground truth。
- 直接 LLM、消融和完整流水线使用同一匹配器。
- Silent failure 和 boundary violation 被明确统计。
- 科研用户默认读取审稿意见式中文或英文报告。
- 双语报告事实一致，且技术指标位于次要层级。
- GitHub 首页能同时服务科研用户和 AI 产品招聘评审。
- 所有公开数字可追溯到版本、命令、哈希和原始聚合结果。

