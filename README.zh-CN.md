# 生物医学投稿前自查助手

[English README](README.md)

一个面向生物医学科研团队的本地工具，帮助你在投稿前系统检查论文材料包的内部一致性——图像、原始数据、统计结果、文本重叠、图文溯源关系。

它**不是**论文打假器。它不会判定学术不端，不会下"造假""伪造""篡改""抄袭"这类结论。它输出的是：有证据支撑的风险提示（finding）、缺失材料清单、以及团队需要逐条解决的投稿前行动项。全程中性措辞。

> **最重要的一条：**"未发现问题"只表示*在当前提供的材料和当前检测范围内没有触发信号*，绝不等于"论文已被证明正确"。

从工程上看：本地 **CLI** + 本地 **Web App** + 可安装的 Codex **Skill** + 可脚本化的检测器流水线（detector pipeline）。

---

## 适合谁

| 你是… | 建议入口 |
| --- | --- |
| **作者/课题组**，想做投稿前自查 | [`docs/self-audit-guide.md`](docs/self-audit-guide.md) 和下方[快速开始](#快速开始) |
| **审稿人/研究诚信办公室**，需要 triage 公开材料 | [快速开始](#快速开始)，再看 [`docs/architecture.md`](docs/architecture.md) 中的外部/回应模式 |
| **开发者/评测者** | [工作原理](#工作原理) 和 [开发者与评测者](#开发者与评测者) |

---

## 快速开始

需要 Python 3.10+。

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

如果想一键部署并把命令链接到 `~/.local/bin`：

```bash
python3.11 scripts/install_local_commands.py
# 或
make install-local
```

会安装 `biomed-audit`、`biomed-audit-diff`、`biomed-audit-web`、`biomed-self-audit-webapp`。确认 `~/.local/bin` 在你的 `PATH` 里。

### 跑第一次审计

```bash
biomed-audit examples/minimal_package --scan-profile quick --output-dir audit_outputs/minimal
biomed-audit examples/full_presubmission_package --output-dir audit_outputs/full
```

如果 `python3` 已指向 3.10+，可以直接用 `python3`。未安装 console scripts 时，用 `python scripts/audit_package.py ...`，参数相同。

### 审计你自己的材料包

```bash
biomed-audit /path/to/my_package --output-dir audit_outputs/my_package
```

默认模式是 `--mode internal_presubmission`，另有 `external_public_material` 和 `response_to_concern` 可选。

**作者用户：**请先读 [自查指南](docs/self-audit-guide.md)。它说明了材料目录怎么准备、报告怎么读、以及哪些结论不能从工具输出中推出。

### 每次运行产出什么

**报告**（面向人类）：

- `audit-report.md` — 双语 Markdown 报告：Quick Read、投稿准备状态、行动队列、覆盖范围（coverage）、需补充材料、发现卡片（finding cards）、技术附录。

**结构化证据**（机器可读）：

- `AUDIT_JSON_SUMMARY.json` — 同一批发现的 JSON 格式。
- `coverage.json`、`calibrated_findings.json`、各检测器（detector）输出 — 复核用细节。
- `audit_snapshot.json`、`file_hash_manifest.json` — 本次审计的精确材料版本（SHA-256）。
- `claim_coverage.json` / `.csv` — 声明-证据覆盖（claim-to-evidence coverage），需提供 `claim_manifest.csv`。
- `methodology_checklist.json` / `.csv` — ARRIVE、CONSORT、ICMJE、MIFlowCyt、omics 人工复核准备度。
- `writing_readiness.json` / `.csv` — 写作与投稿准备度提示（不影响 R0–R4）。

**团队协作**：

- `unresolved_actions.csv`、`resolved_actions.csv`、`accepted_with_reason.csv` — 行动项跟踪表。
- `correction_plan.md` / `.csv` — 投稿前更正计划。
- `submission_qc_packet/` — 留档包：报告、coverage、跟踪表、已验证溯源、文件哈希、作者签字模板。

---

## 工作原理

流水线把"发现候选信号"和"给风险定级"分开，避免任何单个组件放大结果：

```text
material intake → structured extraction → provenance graph → detectors
→ contextual join → risk calibration → evidence ledger → bilingual human report
```

- **检测器（Detectors）** 只输出候选信号和证据位置，不给最终风险等级。
- **溯源构建器（Provenance builders）** 建模文件关系和你声明的 figure-to-raw 对应。
- **上下文连接器（Context joiners）** 补充披露信息、source/raw 可得性和 provenance 上下文。
- **校准器（Calibrator）** 是唯一赋予 `calibrated_risk_level` 的组件，考虑证据强度、材料完整性、披露情况、良性解释和模式风险上限。
- **报告器（Reporter）** 只渲染已校准的 finding，用中性双语呈现，拒绝未校准输入。

`scripts/audit_package.py` 是默认编排器，运行完整流程。完整设计见 [`docs/architecture.md`](docs/architecture.md)。

---

## R0–R4 风险等级

每条 finding 被放在五级刻度上。即使是最高级别，也不是不端判定。

| 等级 | 含义 | 通常动作 |
| --- | --- | --- |
| `R0` | 在已提供材料和当前范围内未发现问题 | 说明审计范围和仍缺什么 |
| `R1` | 完整性或文档缺口 | 补充 raw/source records 后重跑 |
| `R2` | 可复核的报告问题或弱统计信号 | 修方法、图注或补充材料 |
| `R3` | 需要源数据或作者说明的实质性疑点 | 提供 raw records 并解释 |
| `R4` | 已提供材料之间存在直接矛盾 | 投稿前暂停并内部复核 |

两条护栏：公开材料 review 在没有内部直接矛盾时不能到 R4；弱统计信号本身不能进入高等级。

---

## 审计模式与选项

### 扫描档位（Scan profiles）

用 `--scan-profile` 控制速度和深度：

| 档位 | 适用场景 | 变化 |
| --- | --- | --- |
| `quick` | 第一次快速自查 | 保留快速 source/text/整图筛查；跳过 local-patch 深度图像筛查和外部短语检索。 |
| `standard` | 默认投稿前 QC | 运行平衡检测集合，导出 submission QC packet。 |
| `deep` | 回应质疑或重点复核 | 更严格的图像相似度阈值，在 coverage 中记录 deep-profile 参数。 |

### 声明-证据清单（Claim manifest）

在材料包根目录放 `claim_manifest.csv`（或传 `--claim-manifest`），每行把论文中的一个 claim 链接到证据链：

```csv
claim_id,claim_text,manuscript_location,figure_or_table,source_data,raw_record,analysis_code,protocol,owner,status
C001,"Treatment increases signal intensity",Results p.4,Fig1A,source_data/Fig1.csv,raw_images/acq_001.tif,statistics_code/fig1.ipynb,protocols/microscopy.md,first_author,ready
```

报告会新增 **Claim Coverage / 声明-证据覆盖** 区块。它只表示证据链完整性，不表示科学结论正确。

### Re-audit diff

修改材料后，比较两次审计输出：

```bash
biomed-audit-diff audit_outputs/v1 audit_outputs/v2 \
  --output audit_outputs/v2/re_audit_diff.json \
  --csv audit_outputs/v2/re_audit_diff.csv
```

也可以第二次运行时加 `--compare-to audit_outputs/v1`。diff 比较风险计数、缺失材料、traceability、未解决动作和 claim-evidence gaps。

### 本地 Web App

源码目录一键启动：

```bash
make run
```

它会创建 `.venv`、安装依赖、构建前端（检测到 `npm` 时）、启动 `127.0.0.1:8765` 并打开浏览器。如果端口已有服务在运行，直接打开现有界面。

开发时手动执行：

```bash
cd webapp/frontend && npm install && npm run build && cd ../..
biomed-audit-web
```

Web App 包装了与 CLI 相同的流水线，固定显示 Audit Coverage，并提供本地材料准备工具。详见 [`webapp/README.md`](webapp/README.md)。

源码 fallback：`python -m webapp`。

---

## 为什么结果可信

- **职责分离。** 检测器只提出候选，校准器才能定级。每条 finding 都必须来自 schema 验证过的 detector candidate。
- **溯源感知的校准。** 图像与已声明 raw/source 匹配时，记录为正向 traceability 证据。但一行作者自报 manifest 不能洗掉真实整图重复——如果两个 panel 被声明为 same source，却检测为 whole-image near-duplicate，系统报告 `manifest_conflict`，要求 raw records 核验。
- **不静默"全清"。** 每份报告都带 `audit_coverage`：哪些模块跑了、哪些没跑、筛了多少图像、哪些文件不可读。空 finding 不能被读成"论文没问题"。
- **契约失败即关闭。** schema 验证是强制的——缺失时 pipeline 停止而非降级。检测器崩溃产生 `detector_execution_failure`（R1），同时保留其它模块输出。
- **风险上限匹配证据。** 弱统计信号最高 R2，完整性缺口最高 R1，公开材料 triage 最高 R3，R4 需要带标签的直接矛盾。

---

## 当前范围与限制

### 图像筛查

图像、局部 patch（local patch）和同图内 copy-move 检测只在单个材料包内运行，不跨论文或外部图像库搜索。当前不覆盖：任意角度旋转、透视变换、弹性形变、大幅缩放、splice forensics（JPEG ghost、CFA/噪声不一致）、光照/阴影不一致。报告会显式列出这一边界。

大图包的 local-patch 筛查有运行时 tile/comparison 预算。触发预算时，报告记录 R1 覆盖缺口并建议 focused deep scan。

### 统计筛查

覆盖 SD/SEM/n 一致性、p-value 范围、整数计数可行性，以及带样本量门槛的弱分布提示（Benford-style 首位数字 ≥ 30 值、p-value clustering ≥ 20 值、digit/rounding ≥ 8 值、integer-count n ≥ 6）。这些弱筛查只有在达到门槛时才自动运行，只能作为 triage 信号，不能单独作为证据。

### 文本、引用与 PDF

文本重叠筛查是包内的（package-internal）；外部短语检索是可选 triage，非穷尽式查重。Reference checking 需要 opt-in，目前限于 DOI/reference 元数据提示（Crossref-style lookup）。True-PDF intake 支持 machine-readable text 和可 OCR 的 scanned PDF；figure/caption extraction 有限。公开材料 review 受 source/raw 缺失限制，不能被读成学术不端结论。

---

## 仓库结构

| 路径 | 用途 |
| --- | --- |
| `skill/biomed-research-integrity-auditor/` | 可安装的 Codex skill：说明、模板、引用、辅助脚本。 |
| `scripts/audit_package.py` | 默认 contract-first 审计编排器。 |
| `detectors/` | 图像、统计、文本候选检测器——输出证据，不输出 verdict。 |
| `calibrators/` | 风险上限校准、证据强度校准、contract validation。 |
| `provenance/` | 资源图构建器，区分 expected traceability 与 reuse risk。 |
| `schemas/` | detector output、risk rules、source-data expectations 的 JSON/YAML 契约。 |
| `examples/` | 可直接运行的示例包：`minimal_package/`、`full_presubmission_package/`。 |
| `docs/self-audit-guide.md` | 面向非开发者的自查指南。 |
| `docs/architecture.md`、`docs/design-notes.md` | 架构与设计说明。 |
| `evals/` | synthetic packages、评测 harness 和 ground truth。 |
| `benchmarks/` | True-PDF、scanned-PDF OCR、real-image 回归、PPPR public-concern benchmark。 |
| `webapp/` | 本地 FastAPI + React/Vite 自查界面。 |

---

## 开发者与评测者

### 运行 synthetic case 审计

```bash
biomed-audit evals/cases/case_004 --output-dir audit_outputs/case_004
```

### 非 LLM detector baseline

隔离检测/校准行为，不经过 LLM：

```bash
python3 evals/run_script_baseline.py --case case_004
```

用 ground truth 断言输出：

```bash
python3 evals/assert_audit_outputs.py --outputs-root audit_outputs
```

### 盲测 harness

生成 prompt，交给只能看到 skill + 单个 case 包的 agent，保存报告到 `evals/outputs/`，评分：

```bash
python3 evals/run_eval.py generate-prompts
python3 evals/run_eval.py score          # scorecards 写入 evals/scorecards/
```

harness 同时奖励 recall 和克制：越界下结论、忽略良性解释、超 risk cap、使用 verdict 措辞都算失败。

**盲测规则：** 被测 agent 只能看到 case 包路径，不能看到 `ground_truth/`、`outputs/`、`scorecards/`、`prompts/`。严格评测应把 case 隔离到独立 workspace。

### 已归档 eval run

[`evals/llm_runs/2026-06-30-codex-orchestrated/`](evals/llm_runs/2026-06-30-codex-orchestrated/)：30/30 synthetic cases 通过，0 violations。这证明 harness 已被实际运行并留痕——不是独立第三方盲测，不代表真实论文场景性能。

### Public-concern benchmark

`benchmarks/pppr_integrity_benchmark/` 是 post-publication concern benchmark 脚手架，含真实公开数据 smoke runner。PubPeer 只作为 discovery 元数据，Crossref/Retraction Watch 作为 publication-status 元数据，PMC Open Access 作为合法材料来源，ORI samples 作为图像单元用例。不是 PubPeer 爬虫，不保存评论。

```bash
python3 benchmarks/pppr_integrity_benchmark/scripts/run_public_smoke_benchmark.py --output-root tmp/pppr_public_smoke
python3 benchmarks/pppr_integrity_benchmark/scripts/build_rwdb_index.py --help
python3 benchmarks/pppr_integrity_benchmark/scripts/evaluate_audit_outputs.py --help
```

当前基线：[`benchmarks/pppr_integrity_benchmark/results/public_smoke_2026-06-30.json`](benchmarks/pppr_integrity_benchmark/results/public_smoke_2026-06-30.json) — 2 个公开 case，0 violations，13 张 ORI 图像筛查，`finding_level_recall: 1.0`。ORI same-section overlap 和低对比 copy-move 样本保留为 `scope_gap` 标签，用于后续检测器增强。

构建前请先读 [`docs/benchmarking_with_pubpeer_and_rwdb.md`](docs/benchmarking_with_pubpeer_and_rwdb.md) 和 [`docs/data_ethics_and_legal_boundaries.md`](docs/data_ethics_and_legal_boundaries.md)。

### 其它 benchmark

```bash
python3 benchmarks/true_pdf/run_true_pdf_benchmark.py        # 压缩 machine-text PDF 提取
python3 benchmarks/scanned_pdf/run_scanned_pdf_benchmark.py  # image-only PDF OCR（需 tesseract/PyMuPDF/pytesseract）
python3 benchmarks/real_image/run_real_image_benchmark.py    # 真实 public-domain 显微图 + 16-bit TIFF
```

`make validate` 在缺少 OCR runtime 时跳过 scanned-PDF benchmark；CI 安装 `tesseract-ocr` 并作为必过 gate。

### 外部文献短语检索

私有自查默认离线：

```bash
python3 detectors/text/external_literature_search.py <package_dir> --provider europepmc --output external_literature_candidates.json
```

orchestrator 参数 `--external-literature-provider auto|none|fixture|europepmc|crossref`：有 fixture 时用 fixture；`external_public_material` 模式查询 Europe PMC；私有 audit 默认离线，除非显式指定 provider。结果只是 manual review 候选，不是查重结论。

### 重新生成 synthetic cases

cases 已提交到仓库，需要时确定性重生成：

```bash
python3 evals/generate_synthetic_cases.py
python3 evals/run_eval.py generate-prompts
```

---

## 发布与安装选项

### Release artifacts

```bash
make release-artifacts
```

构建前端、Python wheel/sdist、源码 bundle 和 SHA-256 manifest，写入 `dist/release/`。GitHub Actions 模板在 `packaging/github-workflows/`；启用需要 maintainer token。PyPI 与 Homebrew 发布需要维护者凭据；详见 [`packaging/README.md`](packaging/README.md)。

### 安装为 Codex Skill

```bash
mkdir -p ~/.codex/skills
ln -s "$(pwd)/skill/biomed-research-integrity-auditor" ~/.codex/skills/biomed-research-integrity-auditor
```

---

## License

MIT。见 [`LICENSE`](LICENSE)。
