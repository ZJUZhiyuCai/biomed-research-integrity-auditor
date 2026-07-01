# 产品诊断报告：biomed-research-integrity-auditor

> 评审日期：2026-07-02
> 评审立场：顶级产品经理，目标用户=忙碌、不太懂技术的生物医学导师（PI），体验标尺=「100 分」
> 评审方式：通读核心报告/README/自查指南/上次评审记录 + 三路深度审计（webapp 交互体验、编排器/检测器能力、文档体系）
> 代码版本：v0.6.2 ｜ 已对照 `docs/REVIEW-2026-06-29.md` 逐条核验当前状态
> 存档性质：本文档为产品视角诊断，与 `REVIEW-2026-06-29.md`（工程可信度视角）互补

---

## 一句话结论

**这是一个工程纪律优秀、定位克制的好底子，但它在「导师真正拿真实论文来用」这条主路径上，离 100 分还差一个闭环。** 上次评审（06-29）的 17 条问题已修 12 条，可信骨架已立住；但当前最伤导师的不是检测算法，而是三件事：**①真实材料吃不下、②审计过程零反馈、③行动项处理与重跑 diff 两处闭环断裂**。这三件不修，导师拿到的是一个"看似干净的报告"——对一个诚信工具，这比没有工具更危险。

---

## 一、先把「100 分」翻译成可衡量标准

"100 分"不是"修完所有 bug"，而是导师视角的可验证体验。拆成 6 条标准，所有诊断对着它打分：

| # | 100 分标准 | 当前得分 |
|---|---|---|
| 1 | **3 分钟上手**：打开即懂"能干什么/第一步干嘛"，有样例一键试跑 | **30** |
| 2 | **吃得下真实论文**：Word/Prism/嵌图 PDF 不被静默丢弃 | **35** |
| 3 | **跑审计有反馈**：能看到进度、能取消、失败有人话、僵尸不锁死 | **25** |
| 4 | **报告即行动**：读完知道下一步做什么，能在工具内处理行动项 | **55** |
| 5 | **改完能验证**：重跑 diff 能告诉我"哪条修好了/有没有新问题" | **30** |
| 6 | **诚实不误导**：没扫到 ≠ 干净，零结果不等于通过 | **80** |

第 6 条是项目最大的亮点（诚实工程做得最扎实），但前 5 条都被同一个根因拖累。**综合：当前约 50 分。** 离 100 分的差距集中在 1–5，不在 6。

---

## 二、三大根因（不是问题清单，是问题背后的根）

### 根因 A：工具假设导师会准备"规范包"，但真实导师手里是 Word + Prism + 嵌图 PDF

`docs/self-audit-guide.md:53` 只说 "manuscript (PDF or text)"，但生物医学导师的 manuscript 极多为 `.docx`。代码层面：

- `detectors/text/text_overlap_screen.py:15` `TEXT_EXTS = {".txt",".md",".pdf"}` → **.docx 对全部文本检测器不可见**
- `detectors/stats/pseudoreplication_screen.py:14-18` 只认 `.csv/.tsv/.xlsx` → **.xls（legacy Excel）和 .pzfx（GraphPad Prism，生物统计主流）被静默丢弃**
- `scripts/audit_package.py:56` `IMAGE_EXTS` 无 `.pdf` → **supplement 是嵌图 PDF 时，图像检测器扫 0 张图**

而 `build_package_manifest.py` 明确把 `.docx/.pzfx` 列为 expected 格式——**manifest 认得，检测器不认**。导师交了 Word + Prism，拿到 `candidates: []`、`errors: []`，和"干净"无法区分。对一个诚信工具，这是最危险的设计：**诚实的零结果 + 静默的格式缺口 = 虚假的安心感**。这与项目第 6 条"诚实不误导"的核心价值直接冲突。

### 根因 B：审计过程对导师是"黑箱等待"

`webapp/backend/app.py:689` 用 `process.communicate()` 阻塞到子进程结束，期间 `stdout_tail` 永远是空字符串。导师跑一个 deep 扫描（可能十几分钟），整个等待期只看到"等待 pipeline 输出…"六个字——不知道在跑、卡住了、还是要完了。叠加三个问题：

- `app.py:195` daemon 线程 + `app.py:358` running 状态 409 拒删 → uvicorn 重启后**僵尸审计永远删不掉**（死锁）
- 无"取消审计"按钮，选错包只能干等
- 失败时 `Workspace.tsx:124` 直接把 Python traceback 甩给导师

### 根因 C：「读报告 → 处理行动项 → 改 → 重跑」闭环两处断裂

- **处理断裂**：`SubmissionWorkspacePanel.tsx:96` 行动项只有"下载 CSV"，`README:77` 明确写 inline 编辑 "Not included"。导师想标记"这条已补材料/接受+理由"，必须跳到 Excel 改 CSV，下次重跑这些状态**全不回灌**。
- **diff 断裂**：`scripts/submission_qc.py:737-773` `build_re_audit_diff` 只比 6 个标量计数（risk_counts、missing_material_count 等），**根本不加载 `calibrated_findings.json`**，不做 per-finding 匹配。导师改了 Figure 5 重跑，工具只告诉他"R2 从 3 个变 2 个"，**不告诉他"哪个问题修好了、有没有新问题"**——这是重跑的核心价值，当前不支持。

---

## 三、P0 级问题（不修就到不了 60 分）

按导师旅程排序，每条都是"导师会直接撞到"的：

1. **Word/.docx 手稿静默不扫**（根因 A）— `text_overlap_screen.py:15` + `external_literature_search.py` 复用同套收集。导师最常交的格式，对文本检测器零可见。修复：加 `python-docx`，或至少对"manifest 声明但检测器不支持"的格式发显式 coverage gap finding（而非静默丢）。

2. **Prism `.pzfx` / legacy `.xls` 静默丢弃**（根因 A）— `pseudoreplication_screen.py:14-18`、`stats_consistency_check.py:16-18`。生物统计主流工具的原始数据，统计检测器返回空被误读为"无异常"。

3. **审计运行零真实进度 + 僵尸死锁**（根因 B）— `app.py:689` communicate() 阻塞；`app.py:195` daemon + `app.py:358` 409 拒删。修复：改 `Popen` 逐行读 stdout + 启动时扫孤儿任务标 failed + 加"取消"按钮。

4. **行动项无法在 webapp 内处理**（根因 C）— `SubmissionWorkspacePanel.tsx:96` 只有下载 CSV。`types.ts:69-83` 的 ActionTrackerRow 已定义 owner/status/human_note/accepted_with_reason 字段，但前后端都无写入路径。修复：加 `PATCH /api/audits/{id}/actions/{action_id}` 写回 CSV，前端加 inline 编辑。

5. **re-audit diff 不做 per-finding 匹配**（根因 C）— `submission_qc.py:737-773`。修复：加载两侧 `calibrated_findings.json`，按 `finding_id` 做 fixed/new/persisted 三分类。

6. **self-audit-guide 把导师推进 CLI，漏掉 webapp 一键入口** — `docs/self-audit-guide.md:96-142` Step 2 只给 venv+pip+`biomed-audit`，完全不提 `make run`。最不技术的导师被推进最技术的路径，与 `webapp-plan.md:2-6`「面向 ordinary researchers」的产品定位直接矛盾。

7. **【上次评审未关的最大根因】作者自报 manifest 仍可一行洗白 local-patch 重复** — `calibrators/contextual_joiner.py:248-255`：local-patch 范围的 declared pair 仍被直接清成 positive evidence，无任何像素/hash 核验；`provenance/parse_assembly_manifest.py:263` 魔法短语 `"figure panels map to"` 仍触发自动压制。上次评审 P0.1 只关了一半（figure-to-figure 已修，local-patch 仍开着）。这是对抗鲁棒性的核心缺口。

---

## 四、P1 级问题（修到 85 分）

### Webapp 交互

- `webapp` 零引用 `examples/` 样例包，无 onboarding（`App.tsx:41` 初始空 + `Workspace.tsx:45` 空状态文案假设导师懂"材料目录"）— 加"用样例包试跑（约 2 分钟）"按钮
- `Sidebar.tsx:103-141` enum 选项全英文黑话（`internal_presubmission`/`europepmc`），`i18n.ts` 无翻译—全部走 i18n 翻成人话
- `FindingsPanel.tsx:36-45` findings 不按风险排序，R4/R0 混排—默认 R4→R0 降序
- `SubmissionWorkspacePanel.tsx:115,167,236` 三处 `slice(0,8)` 静默截断行动项—30 条只看到 8 条，无"显示更多"
- `styles.css` 全文无 `@media print`—无法从浏览器导出 PDF 报告
- failed 状态直接甩 traceback（`Workspace.tsx:124`）—先显示人话原因 + "用相同参数重跑"按钮，traceback 折叠
- `compareTo` 下拉显示原始 audit_id（`Sidebar.tsx:149`）—改成 `{包名}·{时间}·{风险}`

### 检测器能力边界

- `local_patch_reuse.py:753-795` within-image 先吃光共享预算 → cross-image 跨图复用（最高价值项）被静默牺牲—重排预算优先级
- `contextual_joiner.py:79,102` disclosed_legitimate_reuse 是**包级**推断：Methods 提一句"loading control reused" → 全包所有图复用被 cap 到 R2（`risk_rules.yaml:89-90`）—从包级降到 candidate 级
- `external_literature_search.py:50-53` 段落解析失败 `except Exception: continue`，无 errors 记录—**全仓最严重的真·静默吞错**
- 检测器崩溃只 cap 在 R1（`audit_package.py:283`），关键图崩溃不显眼—主报告顶部醒目列出"未完成模块"
- `contextual_joiner.py:44-47` 静默吞包内文本读取失败 → package_context 从残缺语料算出
- `calibrators/contract_validation.py` 之后校准/报告层 fail-fast，检测器跑完后才炸，无部分结果

### 文档

- Word/.docx 全仓零指引（`self-audit-guide.md:53`）—加"Word 请先另存为 PDF"
- `response_to_concern` 模式无操作指南（`self-audit-guide.md:129` + `architecture.md:126-128`）—导师被期刊质疑图像时最需要工具，却没流程；模板 `author-query-letter.md` 已存在但没串进指南
- `docs/design-notes.md:49` 把已实现的 true-PDF 抽取仍写成"已知缺口"，与 `architecture.md:96` + CHANGELOG v0.4.1 矛盾
- `.cursor/plans/local_self-audit_webapp_*.plan.md` 全 12 项 pending，但实际 v0.6.2 已基本完成—误导进度判断，应删除或同步

---

## 五、P2 级问题（修到 95 分）

- `README.zh-CN.md:213-225` 仓库结构表缺 submission_qc 一行（英文版有）
- `styles.css` 多处 11–12px 字号 + `--muted:#6b7568` 对比度 ~4.0:1 不到 WCAG AA（年长 PI 吃力）
- `CoveragePanel.tsx:33-37` 指标标签硬编码英文，中文界面下突兀
- `EvidenceLightbox.tsx:34` 无 focus trap；全文无 skip-to-content
- 输出目录 20+ 文件平铺无索引—生成 `START_HERE.md` 指向 `audit-report.md` 和 `submission_qc_packet/`
- `external_literature_search.py` 无缓存无重试 → 跨时间不可复现（对审计工具是硬伤）
- `image_io.py:17-25` 16-bit 拉伸用全局 min/max，热像素会压垮动态范围—改百分位拉伸
- `risk_rules.yaml` 3 个死键仍开着（`local_patch_within_declared_raw_source` 等 contextual_joiner 从不产出）
- `schemas/source_data/*.yaml` 4 份 assay 契约是死契约，stats 检测器不加载它们
- 真实包时间预期、联网说明、scan profile 决策树缺失（导师不知道"50 图要跑多久""要不要联网"）

---

## 六、100 分路径（分阶段路线图）

| 阶段 | 目标 | 关键动作 | 达到分数 |
|---|---|---|---|
| **S1 闭环止血** | 让真实闭环跑通 | 修 P0 的 3/4/5/6：webapp 进度+取消+孤儿清理、行动项 inline 编辑、per-finding diff、self-audit-guide 加 webapp 入口 | **70 分** |
| **S2 真实材料兼容** | 不再静默丢格式 | 修 P0 的 1/2：.docx/.xls/.pzfx/嵌图 PDF intake，对不支持格式发显式 gap finding 而非静默丢 | **82 分** |
| **S3 对抗根因** | 关掉 P0.1 | local-patch declared pair 强制像素/hash 交叉核验，"作者自报且无法核验"降级为 R1 待核而非 positive evidence；删魔法短语自动压制 | **90 分** |
| **S4 体验打磨** | P1 全清 | enum 翻译、findings 排序、去 slice(0,8)、@media print、failed 人话、disclosed_reuse 降到 candidate 级、response 模式指南 | **95 分** |
| **S5 长板加长** | P2 + 验证 | 可复现性（缓存+重试）、输出索引、无障碍 AA、真跑一轮 LLM eval 落 scorecard | **97 分** |

---

## 七、一个产品判断（给项目所有者）

这个项目有一处**深层张力**值得直面：工具的"诚实性"（第 6 条，80 分）要求"没扫到 ≠ 干净"，但 intake 的格式缺口（根因 A）恰恰让"诚实的零结果"对导师变成误导。**这两者不能分开修**——只修体验不修 intake，会把"虚假安心感"放大；只修 intake 不修体验，导师根本走不到第一次跑通。所以 S1（闭环）和 S2（兼容）必须捆绑推进，这是"100 分体验"的最短路径。

剩下的 3 分是**能力天花板**，要诚实承认：任意角度旋转/透视/弹性形变/splice 取证（上次评审 P1.6b，已声明为限制）不做 keypoint 特征匹配是补不上的，这需要引入 OpenCV/特征点匹配，是另一个工程量级。导师若需要对抗这类篡改，应外接 ImageTwin/Proofig。这 3 分不靠文档能补，建议在报告里更显眼地引导"本工具是投稿前自查的第一道筛，不替代专业图像取证"。

**最关键的一句话**：P0.1（作者自报即真相）是上次评审留的半个口子，团队用 4 个版本（v0.4.1→v0.6.0→v0.6.2→Unreleased）逐 case 打补丁，但"声明是材料不是证据，压制前必须交叉核验"这个通用原则始终没作为 invariant 实现。建议把它作为 S3 的北极星，一次关死，而不是等下一个旁路被发现。

---

## 附：与 REVIEW-2026-06-29.md 的关系

- `REVIEW-2026-06-29.md` 是**工程可信度视角**（检测算法、对抗鲁棒性、契约/校准、eval 验证），17 条中 12 条已修、3 条部分修复、1 条声明为限制。
- 本文档是**导师体验视角**，新增覆盖：webapp 交互闭环、intake 真实格式兼容、re-audit diff 价值、self-audit-guide 入口断层。
- 两份文档的交集是 P0.1（manifest 压制）和 intake 静默丢弃——前者是上次评审的半个口子，后者是本次新识别的、与"诚实不误导"核心价值直接冲突的根因 A。
- 修复优先级建议：S1 闭环止血（体验）与 S2 真实材料兼容（intake）捆绑推进，再回到 S3 关 P0.1（对抗根因）。
