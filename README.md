# 客服 FAQ 自动分类脚本 Code Review 与优化

## 1. 项目背景

本项目对客服 FAQ 自动分类脚本进行全面的代码审查（Code Review）、Prompt 优化、评估验证和工程化改进。

**当前任务：** 将用户问题自动分类到以下 6 个标签之一：

- 退款退货
- 物流查询
- 账号问题
- 商品咨询
- 投诉建议
- 其他

---

## 2. 原始问题分析 / Code Review

通过对 `classifier.py` 的全面审查，发现以下问题，按严重程度排序：

| 严重程度 | 问题描述 | 影响分析 | 改进方案 |
|---------|---------|---------|---------|
| **P0 - 极高** | API Key 明文写死在代码中 | 安全风险：密钥泄露后可能被滥用，产生非授权费用 | 改为从环境变量 `DEEPSEEK_API_KEY` 读取，代码中不再存储任何密钥 |
| **P0 - 极高** | 无异常处理机制 | API 调用失败、网络超时、限流时整个程序直接崩溃中断 | 增加 `try/except` 包裹 API 调用，实现指数退避重试（最多 3 次），失败时 fallback 返回"其他" |
| **P1 - 高** | Prompt 过于简单，无分类定义 | 没有边界规则、冲突处理规则，混合诉求（如"退款的事顺便看看快递"）容易分错 | 重写 Prompt，加入 6 类标签定义、主要诉求优先规则和输出格式约束 |
| **P1 - 高** | 无输出校验（normalize_label） | LLM 可能返回"类别：退款退货"或带标点符号，后续路由逻辑无法正确匹配 | 增加 `normalize_label()` 函数，去掉前缀、标点，子串匹配合法标签，无匹配时返回"其他" |
| **P2 - 中** | 没有评估脚本 | 无法量化上线效果，无法证明 Prompt 优化是否有效，迭代缺乏数据支撑 | 新增 `evaluate.py`，支持 baseline/improved 对比，输出准确率和错分样本 |
| **P3 - 低** | 批量处理缺少日志和错误文件 | 线上问题无法排查，失败样本无法追溯分析 | 输出 `results/` 目录，包含 `baseline_results.json`、`improved_results.json`、`errors.json` |

---

## 3. Prompt 优化思路

### 3.1 旧 Prompt 的问题

原始 Prompt（`docs/classification_prompt.md` 中的 v1.0）存在以下缺陷：

1. **没有 System Prompt**：所有指令堆在一条 User Message 中，缺少角色设定和结构化约束。
2. **没有标签定义**：仅列出 6 个类别名称，没有说明每个类别包含哪些典型场景。
3. **没有冲突处理规则**：当问题同时涉及多个类别时（如"退款的事顺便看看快递到没到"），没有告诉模型如何决策。
4. **没有边界案例说明**：寒暄、问号、无意义内容等边界情况未做说明。
5. **输出约束不足**：只说"只回复类别名称"，但没有防止 LLM 返回前缀（如"类别："）或标点。
6. **没有退款进度 vs 物流查询的区分**：模型可能将"退款什么时候到账"误归为"物流查询"。

### 3.2 新 Prompt 的改进

**Improved Prompt**（`prompts.py` 中定义）做了以下改进：

1. **结构化 System Prompt**：明确角色定位为"电商客服 FAQ 分类器"，强调只能输出 6 个标签之一。
2. **详细的分类规则**：每个标签给出了 3-6 条具体说明和典型场景，覆盖常见边界情况。
3. **冲突处理规则**：
   - 同时涉及多类别时，以用户主要诉求为准。
   - "退款进度查询"归入"退款退货"而非"物流查询"。
   - "包裹已签收但未收到"归入"物流查询"。
   - 抱怨退货流程时归入"投诉建议"。
   - 纯寒暄/感谢/问号归入"其他"。
4. **输出格式约束强化**：明确要求"只输出标签名称，不要解释，不要标点，不要输出 JSON"。
5. **将 User Message 拆离**：System Prompt 提供分类规则，User Message 只传递具体问题，结构更清晰。

---

## 4. 工程化改进

本次优化完成了以下工程改进：

| 序号 | 改进项 | 说明 |
|-----|-------|-----|
| 1 | **API Key 环境变量管理** | 不再硬编码，从 `DEEPSEEK_API_KEY` 环境变量读取 |
| 2 | **异常处理与重试** | API 调用包裹 try/except，指数退避重试 3 次，失败 fallback 返回"其他" |
| 3 | **输出标签校验** | `normalize_label()` 函数去掉前缀/标点，子串匹配合法标签，无匹配返回"其他" |
| 4 | **mock/deepseek 双模式** | `--mode mock` 使用本地关键词模拟分类器，无需 API；`--mode deepseek` 调用 DeepSeek API |
| 5 | **评估脚本** | `evaluate.py` 读取 classifier 输出文件，输出准确率、错分样本和对比分析 |
| 6 | **结果持久化** | `results/` 目录自动创建，输出 `baseline_results.json`、`improved_results.json`、`errors.json` |
| 7 | **完整 README** | 企业笔试风格文档，包含 Code Review、Prompt 优化、运行说明、GitHub 上传指南 |
| 8 | **CLI 参数化** | 支持 `--input`、`--output`、`--mode`、`--prompt` 多参数灵活配置 |

---

## 5. 如何运行

### 5.1 安装依赖

```bash
pip install -r requirements.txt
```

### 5.2 两个脚本的职责

| 脚本 | 职责 | 何时用 |
|------|------|--------|
| `classifier.py` | **分类**：读取输入 JSON，调用 mock 或 DeepSeek，将结果写入文件 | 每次运行分类时用 |
| `evaluate.py` | **评估**：读取 classifier 输出的结果文件，和真实标签对比，输出准确率和错分样本 | 分类完成后用 |

**原则：分类只管分类，评估只管评估，互不依赖。**

### 5.3 测试集

| 文件 | 说明 |
|------|------|
| `docs/test_samples.json` | 30 条普通测试样本（所有模型都能答对，无区分度） |
| `docs/test_hard_cases.json` | 25 条边界测试样本（用于验证 baseline/improved 的差异） |

### 5.4 快速运行（无需 API Key）

```bash
# 1. Mock 模式分类（关键词分类器，无需 API）
python classifier.py --mode mock --input docs/test_hard_cases.json --output results/hard_mock.json

# 2. 评估
python evaluate.py --mock results/hard_mock.json
```

### 5.5 DeepSeek API 模式（需要 API Key）

```bash
# 1. 编辑 .env，填入 DEEPSEEK_API_KEY

# 2. 同时跑 baseline 和 improved
python classifier.py --mode deepseek --prompt baseline --input docs/test_hard_cases.json --output results/hard_baseline.json
python classifier.py --mode deepseek --prompt improved --input docs/test_hard_cases.json --output results/hard_improved.json

# 3. 评估 baseline vs improved
python evaluate.py --baseline results/hard_baseline.json --improved results/hard_improved.json

# 4. 同时评所有三个模式
python evaluate.py --mock results/hard_mock.json --baseline results/hard_baseline.json --improved results/hard_improved.json
```

### 5.6 真实测试集一键评估

使用原始测试集 `docs/test_samples.json` 进行完整评估流程：

```bash
# 1. Mock 模式分类
python classifier.py --mode mock --input docs/test_samples.json --output results/test_mock.json

# 2. DeepSeek + Baseline
python classifier.py --mode deepseek --prompt baseline --input docs/test_samples.json --output results/test_baseline.json

# 3. DeepSeek + Improved
python classifier.py --mode deepseek --prompt improved --input docs/test_samples.json --output results/test_improved.json

# 4. 评估所有结果
python evaluate.py --mock results/test_mock.json --baseline results/test_baseline.json --improved results/test_improved.json
```

> 注意：`docs/test_samples.json` 为原始给定测试集，baseline 和 improved 均全对（无区分度）。
> 如需验证 prompt 优化效果，请使用 `docs/test_hard_cases.json` 边界测试集。

---

## 6. 准确率对比

### 普通测试集（`docs/test_samples.json`，30 条）

| 版本 | 正确数 | 总数 | 准确率 |
|------|--------|------|--------|
| Baseline | 30 | 30 | 100.00% |
| Improved | 30 | 30 | 100.00% |

> 普通测试集过于简单，baseline 和 improved 无法区分。**请使用边界测试集验证 prompt 差异。**

### 边界测试集（`docs/test_hard_cases.json`，25 条）

| 版本 | 正确数 | 总数 | 准确率 |
|------|--------|------|--------|
| Mock（关键词） | 15 | 25 | 60.0% |
| Baseline | 21 | 25 | 84.0% |
| Improved | 23 | 25 | **92.0%** |

Improved 相比 Baseline 提升 **+8%**。

**Improved 相比 Baseline 的改进点：**
- "你们支持七天无理由吗" → Baseline 判"商品咨询"，Improved 判"退款退货"（Improved 有明确退货规则）
- "东西收到了但是颜色和图片差很多" → Baseline 判"商品咨询"，Improved 判"投诉建议"（识别不满情绪）

---

## 7. 错误记录

评估完成后，每个结果文件会生成对应的 `_errors.json`：

```bash
# 默认输出到结果文件同目录
results/hard_baseline_errors.json
results/hard_improved_errors.json
results/hard_mock_errors.json

# 自定义输出目录
python evaluate.py --baseline results/hard_baseline.json --improved results/hard_improved.json --errors results/my_errors/
```

---

## 8. 开发工具截图

> 以下截图需要手动补充到 `screenshots/` 目录后上传。

| 截图说明 | 文件路径 |
|---------|---------|
| 开发过程截图（IDE 代码截图） | `screenshots/ide_process.png` |
| 评估运行结果截图（终端输出截图） | `screenshots/eval_result.png` |

补充方法：在 Mac 上按 `Cmd + Shift + 4` 截取所需区域，保存到 `screenshots/` 目录即可。

---

## 9. AI 工具使用情况

本项目使用 **ChatGPT / Cursor AI** 辅助完成以下工作：

1. **Code Review**：使用 AI 辅助分析原始代码的安全风险、异常处理缺失和输出校验问题。
2. **Prompt 优化**：基于 `docs/categories.md` 和 `docs/classification_prompt.md`，由 AI 生成结构化的 Improved Prompt 方案。
3. **代码重构**：AI 辅助设计 mock 分类器的关键词规则、normalize_label 函数的匹配逻辑。
4. **评估脚本设计**：AI 辅助设计 `evaluate.py` 的结果输出格式和错分样本对比逻辑。
5. **README 编写**：AI 辅助生成企业笔试风格的完整项目文档。

**最终结果均经过本地运行验证**，确保代码可执行、结果可复现。运行命令：
```bash
python classifier.py --mode mock --input docs/test_hard_cases.json --output results/hard_mock.json && python evaluate.py --mock results/hard_mock.json
```

---

## 10. GitHub 上传说明

### 10.1 初始化仓库

如果还没有初始化 git 仓库：

```bash
git init
git add .
git commit -m "feat: improve faq classifier with prompt optimization and evaluation"
```

### 10.2 关联远程仓库并推送

```bash
git branch -M main
git remote add origin https://github.com/你的用户名/faq-classifier-review.git
git push -u origin main
```

### 10.3 注意事项

- **不要上传真实 API Key**：`.env` 已在 `.gitignore` 中忽略，确保不要将包含真实 Key 的文件加入暂存区。
- **results 目录已保留**：便于展示运行结果和评估对比数据，无需额外处理。
- **screenshots 目录已保留**：需要手动补充 `ide_process.png` 和 `eval_result.png` 截图文件后，再执行 `git add screenshots/`。
- 如果需要克隆已有仓库：
  ```bash
  git clone https://github.com/你的用户名/faq-classifier-review.git
  cd faq-classifier-review
  pip install -r requirements.txt
  python classifier.py --mode mock --input docs/test_samples.json --output results/improved.json && python evaluate.py --improved results/improved.json
  ```

---

## 11. 项目文件结构

```
faq-classifier-review/
├── classifier.py          # 分类脚本（支持 mock/deepseek、baseline/improved）
├── prompts.py             # Prompt 定义（baseline + improved）
├── evaluate.py            # 评估脚本
├── requirements.txt       # Python 依赖
├── .env                   # API Key（已在 .gitignore 中，不上传）
├── .gitignore             # Git 忽略配置
├── README.md              # 本文档
├── docs/
│   ├── categories.md              # 分类标签定义（退款退货/物流查询/账号问题/商品咨询/投诉建议/其他）
│   ├── classification_prompt.md   # Prompt 优化过程文档
│   ├── test_samples.json         # 30 条普通测试样本
│   └── test_hard_cases.json      # 25 条边界测试样本
├── results/                   # 每次运行自动创建
│   ├── hard_mock.json         # Mock 模式结果
│   ├── hard_baseline.json     # Baseline 结果
│   ├── hard_improved.json     # Improved 结果
│   ├── *_errors.json          # 错分记录（自动生成）
│   └── custom_errors/         # --errors 参数指定目录
└── screenshots/
    ├── ide_process.png    # [需手动补充] 开发过程截图
    └── eval_result.png    # [需手动补充] 评估结果截图
```

---

## 12. 核心代码说明

### normalize_label()

`classifier.py` 中的 `normalize_label()` 函数是输出校验的核心：

```python
def normalize_label(raw_text: str) -> str:
    # 去掉常见前缀（"类别："、"分类结果："等）
    # 去掉标点符号
    # 精确匹配 VALID_LABELS
    # 子串匹配（允许 "【退款退货】" 等变体）
    # 无匹配返回"其他"
```

### Mock 分类器

`classifier.py` 中的 mock 分类器是纯关键词匹配，无 prompt 概念。用于在没有 API Key 的情况下快速验证分类逻辑。

mock 分类器使用改进版关键词规则，支持主诉求优先、冲突处理（退货流程投诉优先归投诉建议）、寒暄/问号边界排除等。
