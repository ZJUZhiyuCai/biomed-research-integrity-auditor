# BRIA-Bench Independent Reviewer Guide

## Scope

This is an `independent_blinded` packet from a sealed test corpus. Review only the supplied research materials. Do not run this project's audit tool, an external integrity-screening tool, or an LLM on the packet. Do not seek the source case identity, compare answers with another reviewer, or inspect files outside the packet.

The packet does not establish author intent or a research-integrity conclusion. Record reproducible observations, uncertainty, plausible benign explanations, materials needed for resolution, and a proportionate verification request.

## Complete Each Form

Each JSON file under `forms/` starts with one blank row. Use one row per distinct observation and number copied rows sequentially with the existing reviewer case prefix. For example, a second row for `BRIA-R001` is `BRIA-R001-O002`.

For each row record:

- `presence`: `present`, `absent`, or `insufficient_materials`;
- `issue_family`: a short neutral category such as image similarity, statistical consistency, text overlap, traceability, or materials completeness;
- `comment_class`: `major`, `minor`, or `materials_request` as allowed by the form;
- `risk_range`: the lowest and highest proportionate review levels from `R0` through `R4`;
- the precise file, figure, panel, table, sheet, row, column, page, or region in `locations`;
- the directly observed fact, its scientific relevance, and the minimum reasonable reviewer comment;
- plausible benign explanations, materials required to distinguish them, and a recommended next action.

Use `absent` only when no reviewable observation is present; it must be the sole row. Use `insufficient_materials` when the supplied record cannot support a determination and identify the missing material. Do not use an absence response as a statement that the work is correct or complete.

Use the R-level range proportionately: `R0` for an expected or directly verified relationship that needs no risk comment; `R1` for a completeness or routine verification request; `R2` for a reproducible candidate pattern that remains indirect; `R3` for a direct contradiction or strong anomaly requiring source-record verification; and `R4` only when primary records plus independent corroboration establish the observation. These levels describe review priority and evidence strength, never intent.

## Independence And Locking

Do not view another reviewer's packet or answers. Do not revise a completed form after it has been locked. If a genuine correction is required, retain the original lock and create a separately identified superseding submission rather than overwriting it.

An external coordinator locks both submissions, computes agreement, and sends only disagreements to a distinct adjudicator. Unresolved disagreements remain ambiguous and are excluded from headline detection metrics.

---

## 中文说明

这是来自封存测试集的 `independent_blinded` 复核包。请只查看包内科研材料，不要运行本项目、其他研究诚信筛查工具或大语言模型，也不要搜索案例来源、查看另一位复核者的答案，或读取包外文件。

本复核不判断作者意图，也不产生学术不端行为结论。请记录可以复现的观察、仍存在的不确定性、可能的良性解释、解除不确定性所需材料，以及与证据强度相称的核查请求。

每个 `forms/` 文件起始只有一行空模板。每项独立观察填写一行；复制新行时按原 case 前缀连续编号，例如 `BRIA-R001-O002`。请填写：

- `presence`：`present`、`absent` 或 `insufficient_materials`；
- `issue_family`：简短、中性的类别，例如图像相似性、统计一致性、文本重叠、溯源关系或材料完整性；
- `comment_class`：按表单约束选择 `major`、`minor` 或 `materials_request`；
- `risk_range`：从 `R0` 到 `R4` 中填写最低与最高合理复核等级；
- `locations`：准确到文件、图片、panel、表格、sheet、行列、页码或图像区域；
- 直接观察到的事实、科学意义、最低限度的合理审稿意见；
- 可能的良性解释、需要补充的材料和建议行动。

只有完全没有可复核观察时才使用 `absent`，且它必须是表单唯一一行；这不表示研究“已经证明正确”。材料不足时使用 `insufficient_materials`，并明确缺少什么。

R 等级应与证据强度相称：`R0` 表示预期关系或已直接核验、无需提出风险意见；`R1` 表示材料完整性或常规核验请求；`R2` 表示可复现但仍属间接证据的候选模式；`R3` 表示直接矛盾或需用源记录核验的强异常；只有在原始记录与独立证据共同确认观察事实时才使用 `R4`。这些等级只描述复核优先级和证据强度，不描述主观意图。

请独立完成，不要查看另一位复核者的材料或答案。表单锁定后不得修改；确需纠正时，应保留原锁定版本并形成新的替代提交，不能覆盖原文件。协调者会在两份提交锁定后计算一致性，只把分歧交给第三位独立裁决者；无法裁决的案例保留为 `ambiguous`，不进入 headline 检测指标。
