# 生物医学投稿前自查助手

[English README](README.md)

这是一个面向生物医学科研团队的本地化投稿前自查工具。

它帮助作者在投稿前检查图像、原始数据、source data、统计结果、文本、图文对应关系和报告材料是否一致、可追溯、可复核。

它**不是**“论文打假器”。它不会判定学术不端、造假、伪造、篡改或抄袭成立；它输出的是有证据支持的风险提示、缺失材料清单和投稿前行动项。报告统一使用中性措辞，并把机器可读 JSON 保留在报告末尾和单独 artifact 中。

从工程上看，这个项目包含本地 **CLI**、本地优先的 **Web App**、可安装的 Codex **Skill**，以及一组可脚本化运行的**检测与校准流水线**。

---

## 它能做什么，不能做什么

**它能做：**

- 筛查图像近重复、局部 patch 复用、同图内 copy-move 候选。
- 交叉核对你在 figure assembly manifest 中声明的 figure-to-raw 关系，并记录正向 provenance 证据。
- 记录本次审计的文件哈希快照、可选 claim-to-evidence 覆盖情况，并导出投稿前 QC packet。
- 检查源数据或汇总表中的数值/统计一致性，例如 SD/SEM/n、p-value 范围、整数计数可行性。
- 筛查包内文本重叠，并可选择运行外部短语检索 triage。
- 输出结构化方法学/报告规范准备度清单，供 ARRIVE、CONSORT、ICMJE、MIFlowCyt、组学 accession 等人工复核使用。
- 输出双语、人类可读的中性报告：包含 Quick Read、投稿准备状态、行动队列、Audit Coverage、需要补充的材料、发现卡片、技术附录和 `R0` 到 `R4` 风险登记。

**它不能做：**

- 判定学术不端、造假、伪造、篡改或抄袭。
- 证明论文正确，或证明图像真实。
- 进行全网级查重或接入商业查重数据库。
- 自动判定方法学/报告规范合规。现在的 checklist 只记录人工复核所需支撑材料的准备度。

> **最重要的一条：**“未发现问题”只表示在当前提供材料和当前检测范围内没有触发候选信号；它绝不等于“论文已被证明正确”。

---

## 适合谁使用

| 你是谁 | 建议从哪里开始 |
| --- | --- |
| **作者/课题组**，想做投稿前自查 | [`docs/self-audit-guide.md`](docs/self-audit-guide.md) 和下面的[快速开始](#快速开始) |
| **审稿人/研究诚信办公室**，想做公开材料 triage | [快速开始](#快速开始)，再看 [`docs/architecture.md`](docs/architecture.md) 中的外部 triage/回应模式 |
| **开发者/评测者** | [工作原理](#工作原理) 和 [开发者与评测者](#开发者与评测者) |

---

## 快速开始

请使用 Python 3.10+ 解释器，并用 editable 模式安装项目，这样
`biomed-audit` 等顶层命令才会出现在环境里：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

先运行内置示例包，查看生成的报告：

```bash
biomed-audit examples/minimal_package --scan-profile quick --output-dir audit_outputs/minimal
biomed-audit examples/full_presubmission_package --output-dir audit_outputs/full
```

如果你的 `python3` 已经指向 Python 3.10+，也可以直接用 `python3`。
如果是在源码目录中运行、还没有安装 console scripts，可以继续使用
`python scripts/audit_package.py ...`，参数相同。

每次运行会在输出目录写入：

- `audit-report.md`：双语的人类可读报告，包含 Quick Read、投稿准备状态、行动队列、scope、coverage、需要补充的材料、可追溯证据、发现卡片和技术附录。
- `AUDIT_JSON_SUMMARY.json`：同一批信息的机器可读摘要。
- `coverage.json`、`calibrated_findings.json` 和各检测器输出：用于复核的结构化细节。
- `audit_snapshot.json` 和 `file_hash_manifest.json`：记录本次审计到底审了哪个版本的材料，包括 SHA-256。
- `claim_coverage.json` / `claim_coverage.csv`：如果提供 `claim_manifest.csv`，这里会列出 claim-to-evidence 覆盖情况。
- `methodology_checklist.json` / `methodology_checklist.csv`：wet-lab、animal、clinical、cell、flow、omics 的人工复核准备度清单。
- `unresolved_actions.csv`、`resolved_actions.csv`、`accepted_with_reason.csv`：团队协作用的行动项跟踪表。
- `submission_qc_packet/`：投稿前留档包，包含报告、coverage、行动项跟踪表、已验证 traceability、缺失材料、文件哈希、claim coverage、methodology checklist 和 author sign-off 模板。

审计你自己的材料包时，把命令指向你的目录即可。默认模式是 `internal_presubmission`，也支持 `external_public_material` 和 `response_to_concern`：

```bash
biomed-audit /path/to/my_package --output-dir audit_outputs/my_package
```

**作者用户：**请先读 [`docs/self-audit-guide.md`](docs/self-audit-guide.md)。它会说明材料目录怎么准备、报告怎么看，以及哪些结论不能从工具输出中推出。

### 扫描档位

用 `--scan-profile` 控制速度和深度：

| 档位 | 适用场景 | 变化 |
| --- | --- | --- |
| `quick` | 第一次快速拖稿自查 | 保留快速 source/text/整图筛查；跳过耗时的 local-patch/copy-move 深度图像筛查和外部短语检索。 |
| `standard` | 默认投稿前 QC | 运行当前平衡的检测集合，并导出 submission QC packet。 |
| `deep` | 回应质疑或重点复核 | 保留当前全部筛查，并把本次运行标记为深度复核，方便后续 detector/profile 扩展。 |

### 可选：claim-to-evidence manifest

如果想做更完整的投稿前自查，可以在材料包根目录放一个 `claim_manifest.csv`，或运行时传
`--claim-manifest /path/to/claim_manifest.csv`。每一行把论文中的一个 claim 连接到 source data、
raw record、analysis code 和 protocol：

```csv
claim_id,claim_text,manuscript_location,figure_or_table,source_data,raw_record,analysis_code,protocol,owner,status
C001,"Treatment increases signal intensity",Results p.4,Fig1A,source_data/Fig1.csv,raw_images/acq_001.tif,statistics_code/fig1.ipynb,protocols/microscopy.md,first_author,ready
```

报告会新增 **Claim Coverage / 声明-证据覆盖** 区块。它只表示证据链完整性，不表示该科学结论已被证明正确。

### Re-audit diff

修改材料、补齐缺口后，可以比较两次审计输出：

```bash
biomed-audit-diff audit_outputs/v1 audit_outputs/v2 \
  --output audit_outputs/v2/re_audit_diff.json \
  --csv audit_outputs/v2/re_audit_diff.csv
```

也可以在第二次运行 `scripts/audit_package.py` 时加 `--compare-to audit_outputs/v1`。diff 会比较风险计数、缺失材料、已验证 traceability、未解决动作和 claim-evidence gaps；它不是通过/不通过判定。

### 本地 Web App（V0.5）

如果你更想用浏览器界面，可以构建并启动本地自查 app：

```bash
cd webapp/frontend && npm install && npm run build && cd ../..
biomed-audit-web
```

然后打开 `http://127.0.0.1:8765`。这个 Web App 只是 `scripts/audit_package.py` 的本地外壳：
它运行同一条流水线、读取同一批 artifact，并固定显示 Audit Coverage，避免把“未发现 finding”
误读成“论文已证明没问题”。它也提供本地材料准备工具，可以创建推荐目录结构，并在审计前写入
`figure_assembly/assembly_manifest.csv` 的 figure-source 声明关系。更多说明见 [`webapp/README.md`](webapp/README.md)。

源码运行 fallback：`python -m webapp`。

### 安装为 Codex Skill（可选）

如果想在 Codex 中作为 Skill 使用，可以把 skill 目录 symlink 到本地 Codex skills 目录：

```bash
mkdir -p ~/.codex/skills
ln -s "$(pwd)/skill/biomed-research-integrity-auditor" ~/.codex/skills/biomed-research-integrity-auditor
```

---

## R0–R4 风险等级

工具不会使用“造假成立”“学术不端成立”这类结论。每条 finding 只会被放在五级风险刻度中；即使是最高级别，也不是不端判定。

| 等级 | 含义 | 通常动作 |
| --- | --- | --- |
| `R0` | 在已提供材料和当前范围内未发现具体问题 | 说明审计范围和仍缺什么 |
| `R1` | 完整性或文档缺口 | 补充 raw/source records 后重跑 |
| `R2` | 可复核的报告问题或弱统计信号 | 修方法、图注或补充材料 |
| `R3` | 需要源数据或作者说明的实质性疑点 | 提供 raw records 并解释 |
| `R4` | 已提供内部材料之间存在直接矛盾 | 投稿前暂停并内部复核 |

两个约束会限制风险等级被过度抬高：公开材料 review 在没有内部直接矛盾时不能到 `R4`；弱统计/弱取证信号本身不能进入高等级。

---

## 工作原理

流水线把“发现候选信号”和“校准风险等级”分开，避免单个检测器直接给出过强结论：

```text
material intake → structured extraction → provenance graph → detectors
→ contextual join → risk calibration → evidence ledger → bilingual human report
```

- **Detectors** 只输出候选、证据和位置，不输出最终风险等级。
- **Provenance builders** 建模文件、raw/source 记录和你声明的 figure-to-raw 关系。
- **Context joiners** 加入披露信息、source/raw 可得性和 provenance 上下文。
- **Calibrator** 是唯一赋予 `calibrated_risk_level` 的组件，会考虑证据强度、材料完整性、披露情况、良性解释和模式风险上限。
- **Reporter** 只渲染已校准 finding，用中性双语写成人类先读的 Markdown，并拒绝未校准输入。

`scripts/audit_package.py` 是默认编排入口，会运行完整流程。完整设计见 [`docs/architecture.md`](docs/architecture.md)。

---

## 为什么它比较克制

项目的核心设计目标不是“多报问题”，而是让审计结果可复核、不越界：

- **职责分离。** 检测器只提出候选，calibrator 才能给风险等级。旧式手写 finding 会被拒绝；每条 finding 都必须来自通过 schema 验证的 detector candidate。
- **provenance-aware 校准。** 图像与已声明 raw/source 匹配时，会被记录为正向 traceability 证据。但一行作者自报 manifest 不能洗掉真实整体重复：如果两个 figure panel 被声明为 same field/same membrane，却又被检测为 whole-image near-duplicate，系统会报告 `manifest_conflict`，要求 raw records 核验。
- **不静默“全清”。** 每份报告和 `AUDIT_JSON_SUMMARY` 都包含 `audit_coverage`，列出哪些模块执行了、哪些没有执行、筛了多少图像、哪些图像不可读。空 finding list 不能被读成“论文已被证明没问题”。
- **契约失败即关闭。** detector、calibrated finding 和 summary 都要 schema 验证；`jsonschema` 不可用时 pipeline 会停止，而不是降级成宽松检查。没有可运行检测器的包会得到 `audit_coverage_gap`（R1）；单个检测器崩溃会得到 `detector_execution_failure`（R1），同时保留其它模块输出。
- **风险上限匹配证据。** 弱统计/弱取证信号最高 R2；完整性缺口是 R1；公开材料 triage 最高 R3；`R4` 需要带标签的直接矛盾。

---

## 仓库结构

| 路径 | 用途 |
| --- | --- |
| `skill/biomed-research-integrity-auditor/` | 可安装的 Codex skill，包括说明、模板、引用和辅助脚本。 |
| `scripts/audit_package.py` | 默认 contract-first 审计编排器。 |
| `detectors/` | 图像、统计、文本候选检测器；输出证据，不输出 verdict。 |
| `calibrators/` | 风险上限、证据强度校准和 contract validation。 |
| `provenance/` | 构建资源图，区分 expected traceability 与 reuse risk。 |
| `schemas/` | detector output、risk rules、source-data expectations 等 JSON/YAML 契约。 |
| `examples/` | 可直接运行的示例包：`minimal_package/` 和 `full_presubmission_package/`。 |
| `docs/self-audit-guide.md` | 面向非开发者的自查指南。 |
| `docs/architecture.md`、`docs/design-notes.md` | 架构和设计说明。 |
| `evals/` | 中性 synthetic packages、评测 harness 和 ground truth。 |
| `benchmarks/` | true PDF、scanned PDF OCR、real-image 回归基准，以及 PPPR public-concern benchmark scaffold。 |
| `webapp/` | 本地 FastAPI + React/Vite 自查界面，包装现有 CLI artifact。 |

---

## 开发者与评测者

### 运行 synthetic case 审计

```bash
biomed-audit evals/cases/case_004 --output-dir audit_outputs/case_004
```

### 非 LLM detector baseline

这个 baseline 调用 orchestrator，用来隔离检测/校准行为和 LLM 行为：

```bash
python3 evals/run_script_baseline.py --case case_004
```

生成 baseline audit outputs 后，可以用 ground truth 断言：

```bash
python3 evals/assert_audit_outputs.py --outputs-root audit_outputs
```

### 盲测 harness

生成 prompt，把每个 prompt 交给只能访问 skill 和单个 `cases/case_XXX` 包的 agent，保存报告到 `evals/outputs/case_XXX.md`，且报告末尾必须包含一个 `AUDIT_JSON_SUMMARY` fenced block，然后评分：

```bash
python3 evals/run_eval.py generate-prompts
python3 evals/run_eval.py score          # scorecard 写入 evals/scorecards/
```

这个 harness 同时奖励 recall 和克制：模型如果越界下结论、忽略良性解释、超过 risk cap，或使用 verdict language，也会失败。

**盲测规则：**被测 agent 只能看到 case package 路径，不能看到 `ground_truth/`、`outputs/`、`scorecards/` 或 `prompts/`。更严格的评测应把目标 case 复制到隔离 workspace，并把答案留在 agent 不可访问的位置。

### 已归档 eval run

已保留一份运行记录：
[`evals/llm_runs/2026-06-30-codex-orchestrated/`](evals/llm_runs/2026-06-30-codex-orchestrated/)。
该 run 的结果是 30/30 synthetic cases 通过，0 个 boundary violations，0 个 risk-cap violations。它证明当前 harness 已被实际运行并留痕；它**不是**独立第三方盲测，也不能代表真实论文场景性能。

### Benchmarks

```bash
python3 benchmarks/true_pdf/run_true_pdf_benchmark.py        # 压缩 machine-text PDF 提取
python3 benchmarks/scanned_pdf/run_scanned_pdf_benchmark.py  # image-only PDF OCR，需要 tesseract/PyMuPDF/pytesseract
python3 benchmarks/real_image/run_real_image_benchmark.py    # 真实 public-domain microscopy 图像 + 16-bit TIFF
```

`make validate` 会在缺少 OCR runtime 时跳过 scanned-PDF benchmark；CI 会安装 `tesseract-ocr` 并把它作为必过 gate。

`benchmarks/pppr_integrity_benchmark/` 是 post-publication public concern benchmark 的脚手架，
并带一个真实公开数据 smoke runner：PubPeer 只作为 discovery/弱公共关注元数据，
Crossref/Retraction Watch 作为 publication-status 元数据，PMC Open Access 作为合法文章材料来源，
ORI samples 作为小型图像单元测试。它不是 PubPeer 爬虫，不保存评论全文，也不把 PubPeer 评论当成
不端真值。

可以先跑最小真实公开数据 smoke：

```bash
python3 benchmarks/pppr_integrity_benchmark/scripts/run_public_smoke_benchmark.py --output-root tmp/pppr_public_smoke
```

当前基线保存在
[`benchmarks/pppr_integrity_benchmark/results/public_smoke_2026-06-30.json`](benchmarks/pppr_integrity_benchmark/results/public_smoke_2026-06-30.json)：
2 个公开 case 跑通，risk-cap/boundary-language 违规为 0，13 张 ORI 公开图像被筛查，2/2 个
当前 detector-scope 内的 ORI recall label 被命中（`finding_level_recall: 1.0`）。ORI same-section
overlap 和低对比 copy-move 样本被保留为 `scope_gap` 标签，用于后续检测器增强；它们不是“无问题”
结论。真正构建前请先读
[`docs/benchmarking_with_pubpeer_and_rwdb.md`](docs/benchmarking_with_pubpeer_and_rwdb.md) 和
[`docs/data_ethics_and_legal_boundaries.md`](docs/data_ethics_and_legal_boundaries.md)。

### 外部文献短语检索

私有自查默认离线。可以显式运行外部检索，也可以让 orchestrator 根据模式决定：

```bash
python3 detectors/text/external_literature_search.py <package_dir> --provider europepmc --output external_literature_candidates.json
```

orchestrator 参数 `--external-literature-provider auto|none|fixture|europepmc|crossref` 的行为是：有 package fixture 时使用 fixture；`external_public_material` 模式下查询 Europe PMC；私有 internal audit 默认离线，除非你显式指定 provider。外部检索结果只是 manual review 候选，不是查重数据库结果，也不是不端结论。

### 重新生成 synthetic cases

cases 已提交到仓库；需要时可确定性重生成：

```bash
python3 evals/generate_synthetic_cases.py
python3 evals/run_eval.py generate-prompts
```

---

## 当前限制

- 图像、local patch 和 same-image copy-move 检测只在单个 package 内运行，不跨论文或外部图像库搜索。
- 文本重叠筛查是 package-internal；可选外部短语检索只是 triage，不是穷尽式查重数据库覆盖，也不是 verdict。
- true-PDF intake 支持 machine-readable text 和可 OCR 的 scanned PDF；figure/caption extraction 仍有限。
- 图像 intake 会归一化高 bit-depth 灰度 TIFF，但对 multi-frame、Z-stack、channel microscopy 的广泛验证仍是未来工作。
- 统计筛查覆盖 p-value range/validity、SD/SEM/n 一致性、integer-count feasibility 和弱取证模式。弱 digit/rounding screen 默认至少需要 8 个可比值；integer-count feasibility 需要 n ≥ 6，并考虑报告精度。它**不实现** Benford-style first-digit analysis 或 p-value clustering/distribution tests；这些仍是人工检查。
- 公开材料 review 受 source/raw records 缺失限制，不能被读成学术不端结论。

---

## License

MIT。见 [`LICENSE`](LICENSE)。
