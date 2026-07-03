# 自审指南

针对您自己的论文包进行投稿前研究诚信自审的实用非开发者指南。

本工具帮助您在投稿前**组织证据并发现风险**。它**不会**做出学术不端结论，也**不会**证明论文正确。请先阅读[边界说明](#this-tool-is-and-is-not)章节。

---

## 必须记住的一条规则

> **"未发现问题"不等于"已被证明正确"。**

审计工具只检查您提供的材料，使用有限的自动检测器。清洁报告意味着**在所提供材料和当前检测器范围内未发现问题**。它绝不意味着研究已被验证或图片是真实的。每份报告都包含一个**本次检查覆盖**部分，明确说明了什么被检查了，什么没有。请务必阅读。

---

## 本工具是什么和不是什么

**它是：**

- 投稿前检查清单和证据整理工具。
- 自动筛查工具：图像近似重复和同图像复制粘贴、图像-原始材料可追溯性、汇总表中的数值/统计一致性，以及包内文本重叠。
- 使用 R0-R4 风险量表的中性报告生成器。

**它不是：**

- 学术不端、欺诈、伪造或抄袭检测器或裁定工具。
- 网页规模的抄袭数据库搜索工具。
- 自动的方法学合规决定。ARRIVE/CONSORT/ICMJE/MIFlowCyt/组学评审被组织为结构化的手工检查清单。
- 您、您的合作者或期刊进行人工审查的替代品。

如果报告读起来像是指控，您就是在误读它。使用中性语言，例如"需要解释的诚信问题"和"现有材料不足以解决这一问题"。

---

## 第1步：准备您的材料

将您的材料放在一个文件夹中，使用以下布局。您不需要每个文件夹；包含您拥有的即可。更完整的包可以被更全面地检查。

```text
my_package/
├── manuscript.docx             您的稿件（DOCX、PDF、TXT 或 MD）
├── supplementary/              补充文件
├── figures/                    论文中显示的图片（PNG/JPG/TIFF）
├── raw_images/                 图片来自的原始/未裁剪采集
├── figure_assembly/
│   ├── assembly_manifest.csv   声明每个图片来自哪个原始文件
│   ├── figure_layout.pptx      可选：幻灯片文本可声明路径；嵌入图像被导出用于审核
│   └── figure_layout.key       可选：基于 zip 的 Keynote 嵌入图像被导出用于审核
├── source_data/                图片背后的数字（CSV / TSV / XLSX / 基础 PZFX）
├── protocols/                  样本图、方法说明、批次记录
├── statistics_code/            分析说明或脚本
└── claim_manifest.csv          可选：将每个稿件声明链接到证据文件
```

DOCX 稿件可直接读取正文、标题式段落和表格单元格文本。如果存在 Word 注释、跟踪更改或嵌入对象，报告会将它们标记为材料准备警告，因为这些层不被读作正文/标题/表格证据。旧版 Word `.doc` 文件仍需保存为 DOCX、机器可读 PDF、TXT 或 MD。源数据可以是 CSV/TSV/XLSX；基础 GraphPad Prism `.pzfx` XML 列表也被解析用于统计检查。旧版 Excel `.xls` 和复杂/无法解析的 Prism 项目仍应导出到 `source_data/` 下的 CSV/XLSX；否则报告应被读作对这些统计检查不完整。

机器可读 PDF 也可以生成 `pdf_structure.json`，一个最佳努力的标题式和表格式文本块列表。审计还在栅栏图像可被从 PDF 导出时写出 `pdf_embedded_images.json` 和 `pdf_embedded_images/`。这些 PDF 衍生文件仅是演示层次的摄入工件；请仍提供实际图板导出加上原始/未裁剪图像用于具备可追溯性意识的图像筛查。

### 组装清单（强烈推荐）

如果您提供 `figure_assembly/assembly_manifest.csv`，工具可以确认每个图片与您声明其来自的原始文件匹配，并将其报告为**正向可追溯性证据**而不是可能的重用问题。格式：

```csv
figure_panel,source_record,relation_type,modality,notes
figures/Figure_1A.png,raw_images/acquisition_001.png,declared_derived_from,microscopy,exported from raw 001
```

清单行是一个*声明*，不是证明。工具进行交叉检查：声明为"同一字段/同一通道"但实际上是完整图像重复的两个图片之间的关系被报告为 `manifest_conflict`，而不是被清除。因此您不能通过写清单行使真实重复消失。

如果您还包含 PPTX 组装文件，请在幻灯片文本、演讲者说明或形状 alt 文本中放置明确的相对路径，例如 `figures/Figure_1A.png` 和 `raw_images/acquisition_001.tif`。文本级 PPTX 链接是有用的可追溯性提示。嵌入的 PPTX 栅栏图像被导出到 `pptx_embedded_images/` 用于摄入审查，但它们是演示层次的组装工件，不是原始记录或可追溯性证明。

基于 zip 的 Keynote `.key` 文件可类似生成 `key_embedded_images/`。不透明文件如 `.psd`、`.ai`、`.indd` 和旧版 `.ppt` 被列为覆盖缺口；导出最终图板到 PNG/JPG/TIFF 并保留原始项目文件用于手工审查。

### 声明清单（投稿质量控制推荐）

如果您提供 `claim_manifest.csv`，报告包含**声明覆盖**：有多少个稿件声明有源数据、原始记录、分析代码和协议的链接。格式：

```csv
claim_id,claim_text,manuscript_location,figure_or_table,source_data,raw_record,analysis_code,protocol,owner,status
C001,"Treatment increases signal intensity",Results p.4,Fig1A,source_data/Fig1.csv,raw_images/acq_001.tif,statistics_code/fig1.ipynb,protocols/microscopy.md,first_author,ready
```

声明覆盖仅是完整性检查。它不说明声明是否为真。本地 web 应用的包准备面板可为您创建此 CSV，如果您不喜欢手工编辑的话。

---

## 第2步：启动本地 web 应用

对于大多数作者和 PI，本地 web 应用是最简单的路径。从源检查，运行：

```bash
make preflight PYTHON=.venv/bin/python
make run
```

preflight 检查 Python 包、图像/OCR 依赖和本地 web UI 构建运行时。如果它报告缺少依赖，请先安装该环境。`make run` 创建或重用 `.venv`，安装依赖，在 `npm` 可用时构建前端，在 `http://127.0.0.1:8765` 启动应用，并打开您的浏览器。应用在您的机器上运行；上传的 zip 包在本地解包。

在浏览器中：

1. 输入您的包文件夹路径，或拖入包的 zip。
2. 选择 `quick` 进行首次检查，`standard` 进行普通投稿前质量控制，或 `deep` 进行专注的重新检查。
3. 对私人草稿保持外部文献搜索离线，除非您明确希望进行公开提供者查询。
4. 阅读**本次检查覆盖**和**行动追踪器**，然后再阅读发现项卡片。

web 应用公开与 CLI 相同的输出，并保持行动追踪器可见，因此它是非开发者的推荐起点。

### CLI 替代方案

使用 Python 3.10+ 解释器，然后在可编辑模式下安装项目，以便 `biomed-audit` 命令可用：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e ".[webapp,ocr]"
```

运行审计（投稿前内部模式是默认）：

```bash
biomed-audit /path/to/my_package --output-dir audit_outputs/my_package
```

如果您的 `python3` 已指向 Python 3.10+，您可以使用 `python3` 而不是 `python3.11`。源检查回退：`python scripts/audit_package.py /path/to/my_package --output-dir audit_outputs/my_package`。

当速度或深度重要时选择扫描配置文件：

```bash
biomed-audit /path/to/my_package --scan-profile quick --output-dir audit_outputs/quick
biomed-audit /path/to/my_package --scan-profile standard --output-dir audit_outputs/standard
biomed-audit /path/to/my_package --scan-profile deep --output-dir audit_outputs/deep
```

- `quick` 用于首次传递。它保持快速检查并明确跳过昂贵的关键点/本地补丁/复制移动深度图像筛查和外部短语搜索。
- `standard` 是默认的投稿前自审。
- `deep` 用于专注的重新检查或回应问题工作。对于期刊/审稿人问题，请遵循 `docs/response-to-concern-guide.md`。

输出落在 `audit_outputs/my_package/`：

- `audit-report.md` — 双语人类可读报告。
- `AUDIT_JSON_SUMMARY.json` — 机器可读摘要。
- `coverage.json`、`calibrated_findings.json` 和检测器输出 — 支持细节。
- `audit_snapshot.json` / `file_hash_manifest.json` — 审查的精确包版本的文件哈希。
- `claim_coverage.json` / `claim_coverage.csv` — 在提供 `claim_manifest.csv` 时的声明-证据覆盖。
- `methodology_checklist.json` / `methodology_checklist.csv` — 手工方法学审查的支持材料准备提示。
- `image_metadata.json` — 图像文件的帧/通道/Z/T 元数据摄入，包括可用时的 OME/TIFF 提示。
- `unresolved_actions.csv`、`resolved_actions.csv`、`accepted_with_reason.csv` — 行动队列的团队追踪器，包括所有者/状态列和为发现衍生行动复制即用的中性询问/材料请求文本。
- `submission_qc_packet/` — 留下的包，包含行动追踪器、已验证可追溯性、缺失材料、文件哈希、声明覆盖、方法学检查清单、当存在图像文件时的图像审查目标包、特定受众的可编辑草稿和作者签署模板。
- `submission_qc_packet/audience_exports/` — PI 简报、合作者行动请求和期刊/审稿人回应草稿框架。在分享前编辑这些；它们是沟通辅助，不是结论。
- `re_audit_diff.md` — 当运行使用 `--compare-to` 时，已不再出现、新出现和仍存在的发现项以及仍缺失材料的人类可读视图。

---

## 第3步：首先尝试捆绑示例

两个现成的示例包让您在几分钟内看到真实报告。它们是带有合成图像的教学样本 — 不是真实数据。

### 最小示例（最快）

```bash
biomed-audit examples/minimal_package --scan-profile quick --output-dir audit_outputs/minimal
```

预期结果：总体风险 **R1**，没有发现项，以及一个**需要补充的材料**表（图片、原始图像、协议等），因为包故意很小。审计覆盖部分显示统计和文本筛查运行了，图像筛查被跳过（没有图像），外部搜索保持离线，方法学准备只是手工检查清单。这是诚实的"小范围，无法得出很多结论"结果。

### 完整投稿前示例（现实布局）

```bash
biomed-audit examples/full_presubmission_package --output-dir audit_outputs/full
```

预期结果：总体风险 **R1**，**两个正向可追溯性链接**（每个图片相对其声明的原始采集被确认，显示在"已验证可追溯性证据"下），两个带有源/原始/代码/协议覆盖的声明声明，没有风险发现项，以及一个短的缺失材料列表。这是诚实的"范围内清洁，带已验证可追溯性，但不是完整审计"结果。

> 用 `python3 examples/generate_example_assets.py` 重新生成示例图像（可选；图像已经提交，所以示例按原样运行）。

---

## 第4步：阅读报告

报告默认为双语。首先阅读人类 Markdown 部分；仅在另一个工具需要机器可读数据时使用最终 `AUDIT_JSON_SUMMARY` 块。

| 部分 | 它告诉您什么 |
| --- | --- |
| **快速结论** | 顶级风险、候选发现项数量、审查的材料、缺失类别，以及没有发现项不是正确性证明的提醒。从这里开始。 |
| **范围** | 模式、扫描配置文件、案例 ID、包根目录，以及报告仅涵盖提供的材料和执行的模块的提醒。 |
| **必须处理** | 投稿前需要处理的最高优先级项目，带建议的所有者/状态字段。如果为空，仍阅读需要补充的材料和本次检查覆盖。 |
| **需要补充的材料** | 预期的未找到的材料类别，每个作为完整性缺口。 |
| **投稿准备状态** | 必须处理的行动是否仍然存在的工作流状态。它不是通过/未通过决定。 |
| **投稿前行动队列** | 实际任务队列分组为必须解决、提供材料、澄清/披露和低优先级检查，带中性跟进文本您可复制到合作者请求中。 |
| **本次检查覆盖** | 哪些检测器模块运行了，哪些没有，图像图板被筛查了，无法读取的图像文件，检测器失败，以及范围说明。使用这个知道什么被实际检查了。 |
| **声明-证据覆盖** | 当提供 `claim_manifest.csv` 时的声明-证据完整性。这不是声明正确性。 |
| **已验证可追溯性证据** | 工具确认为正向可追溯性证据的图像-原始链接。 |
| **风险登记** | 每个候选发现项一行，包含级别、模块、位置和类型。 |
| **发现项与证据台账** | 人类可读的发现项卡片：观察、为什么重要、证据摘要、良性解释、所需材料和建议行动。 |
| **下一步清单** | 紧凑的旧版视图。对团队跟进优先使用行动队列和追踪器 CSV。 |
| **技术附录** | 紧凑的技术细节加 `calibrated_findings.json` 和检测器输出的指针。 |
| **机器可读摘要** | 同一审计摘要在一个机器可读的围栏 JSON 块中。 |

### R0-R4 风险量表，用简明语言

| 级别 | 含义 | 要做什么 |
| --- | --- | --- |
| **R0** | 在提供的材料中未发现问题（在范围内）。 | 说明范围和缺少什么。不是清洁的健康检查。 |
| **R1** | 完整性缺口 — 检查声明所需的内容缺失。 | 添加原始/源记录并重新运行。 |
| **R2** | 轻微报告问题，或弱统计信号。 | 修复方法/图注/补充；文档。 |
| **R3** | 需要解释的诚信问题；良性解释存在。 | 提供原始记录并在投稿前澄清。 |
| **R4** | 提供的材料内的直接冲突。 | 暂停并在投稿前在内部解决。 |

即使 **R4 也不是学术不端行为结论。** 它意味着两个提供的东西直接矛盾，必须调和。

---

## 第5步：您可以和不可以得出什么结论

**您可以：**

- 使用报告查找缺失材料、修复报告和添加原始/源记录。
- 将 R3/R4 视为"投稿前必须解释或更正"。
- 将中性发现项引用给您的合作者作为质量控制项目。

**您不可以：**

- 得出任何人犯了学术不端、欺诈、伪造或抄袭行为的结论。
- 将清洁（R0/R1）报告视为研究正确或数字真实的证明。
- 将缺失材料缺口视为不端行为的证据。
- 在公开场合使用报告作为指控。

与合作者提出问题时，使用中性短语，例如："我们能否添加未裁剪的印迹和样本图，以便记录这个图板与其原始记录的关系？"

---

## 常见令人困惑的结果

**"它说`图像组装`缺失，但我包含了`assembly_manifest.csv`。"**

名为*图像组装*的需要补充的材料行指的是组装/设计项目文件（PowerPoint、Photoshop、Illustrator 等）。您的结构化 CSV/YAML 清单仍被读取并由工具使用 — 查看**已验证可追溯性证据**部分，其中列出了它从您的清单确认的图像-原始链接。这正是为什么您应该阅读整个报告，而不仅仅是需要补充的材料列表。

**"总体风险是 R1，但没有发现项。"**

这里 R1 来自缺失材料，而不是检测到的问题。添加缺失的记录并重新运行以缩小未检查内容的范围。

**"我的 16 位 TIFF/多通道图像并非全部被筛查了。"**

图像支持在改进但仍然有限。检查审计覆盖部分中的 `被筛查的图像图板` 和 `无法读取的图像文件`。无法读取的文件被报告，从不静默丢弃 — 但它们不被筛查。

**"它没有发现明显的问题。"**

自动检测器是筛查，不是保证。覆盖有意诚实地说明这一点。将工具与对 `methodology_checklist.json` / `.csv` 的手工审查和 `skill/biomed-research-integrity-auditor/references/` 中的更深入参考说明相结合。

---

## 投稿后

1. 在投稿前解决每个 R4，并解释或更正每个 R3。
2. 为您可以关闭的 R1 完整性缺口添加原始/源记录。
3. 完成 `methodology_checklist.csv`："供应的材料"意味着已准备好进行人工审查，不是符合。在需要时添加缺失的协议、伦理、登记、FCS、登记号或分析代码记录。
4. 将 `AUDIT_JSON_SUMMARY.json` 与您的投稿记录一起保存作为质量控制追踪。

完整的自审是**自动筛查 + 您对原始/源记录的手工审查 + 方法学检查清单项目** — 不仅仅是工具。
