# 生物医学研究诚信风险审计器

[English README](README.md)

这是一个帮助你在投稿前**筛查生物医学论文包研究诚信风险**的工具。它会把图像、源数据、文本重叠、材料缺口和检测覆盖范围整理成一份克制、中性的审计报告。

它**不是**“论文打假器”。它不会判定学术不端、造假、伪造、篡改或抄袭成立；它只做三件事：呈现有证据支持的风险、列出可能的良性解释、指出还需要哪些材料才能继续核验。报告统一使用 `R0` 到 `R4` 的风险等级，并保持中性措辞。

从工程上看，这个项目包含三部分：一个可安装的 Codex **Skill**、一组可脚本化运行的**检测与校准流水线**，以及一个用于盲测的**评测框架**。

---

## 它能做什么，不能做什么

**它能做：**

- 筛查图像近重复、局部 patch 复用、同图内 copy-move 候选。
- 交叉核对你在 figure assembly manifest 中声明的 figure-to-raw 关系，并记录正向 provenance 证据。
- 检查源数据或汇总表中的数值/统计一致性，例如 SD/SEM/n、p-value 范围、整数计数可行性。
- 筛查包内文本重叠，并可选择运行外部短语检索 triage。
- 输出带有 `R0` 到 `R4` 风险表、证据台账和 Audit Coverage 的中性报告。

**它不能做：**

- 判定学术不端、造假、伪造、篡改或抄袭。
- 证明论文正确，或证明图像真实。
- 进行全网级查重或接入商业查重数据库。
- 自动完成方法学/报告规范合规审查。ARRIVE、CONSORT、ICMJE、MIFlowCyt、组学 accession 等目前是**人工清单**，不是自动检测器输出。

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

需要 Python 3.10+ 和项目依赖：

```bash
python3 -m pip install -r requirements.txt
```

先运行内置示例包，查看生成的报告：

```bash
python3 scripts/audit_package.py examples/minimal_package --output-dir audit_outputs/minimal
python3 scripts/audit_package.py examples/full_presubmission_package --output-dir audit_outputs/full
```

每次运行会在输出目录写入：

- `audit-report.md`：给人读的报告，包含 scope、coverage、缺失材料、风险表和证据台账。
- `AUDIT_JSON_SUMMARY.json`：同一批信息的机器可读摘要。
- `coverage.json`、`calibrated_findings.json` 和各检测器输出：用于复核的结构化细节。

审计你自己的材料包时，把命令指向你的目录即可。默认模式是 `internal_presubmission`，也支持 `external_public_material` 和 `response_to_concern`：

```bash
python3 scripts/audit_package.py /path/to/my_package --output-dir audit_outputs/my_package
```

**作者用户：**请先读 [`docs/self-audit-guide.md`](docs/self-audit-guide.md)。它会说明材料目录怎么准备、报告怎么看，以及哪些结论不能从工具输出中推出。

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
→ contextual join → risk calibration → evidence ledger → human-reviewable report
```

- **Detectors** 只输出候选、证据和位置，不输出最终风险等级。
- **Provenance builders** 建模文件、raw/source 记录和你声明的 figure-to-raw 关系。
- **Context joiners** 加入披露信息、source/raw 可得性和 provenance 上下文。
- **Calibrator** 是唯一赋予 `calibrated_risk_level` 的组件，会考虑证据强度、材料完整性、披露情况、良性解释和模式风险上限。
- **Reporter** 只渲染已校准 finding，并拒绝未校准输入。

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
| `benchmarks/` | true PDF、scanned PDF OCR 和 real-image 回归基准。 |

---

## 开发者与评测者

### 运行 synthetic case 审计

```bash
python3 scripts/audit_package.py evals/cases/case_004 --output-dir audit_outputs/case_004
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
