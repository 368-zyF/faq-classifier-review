# 客服 FAQ 自动分类器

## 1. 项目背景

对客服 FAQ 分类脚本进行代码审查与优化，目标是将用户问题自动归类到以下六个类别之一：

- 退款退货
- 物流查询
- 账号问题
- 商品咨询
- 投诉建议
- 其他

---

## 2. 代码审查与问题分析

对原始 `classifier.py` 进行全面审查，发现以下问题：

| 级别 | 问题 | 影响 | 改进方案 |
|------|------|------|---------|
| P0 | API Key 明文写在代码中 | 安全风险，密钥可能泄露 | 改为环境变量 `DEEPSEEK_API_KEY` 读取 |
| P0 | 无异常处理机制 | API 失败或网络超时时程序直接崩溃 | 增加 try/except + 指数退避重试（最多 3 次），失败 fallback 返回"其他" |
| P1 | Prompt 过于简单，无分类定义 | 边界情况、混合诉求无法正确处理 | 重写 Prompt，加入分类定义、冲突规则、输出格式约束 |
| P1 | 无输出校验 | LLM 可能返回"类别：退款退货"等带前缀内容，后续路由无法匹配 | 新增 `normalize_label()` 函数，子串匹配合法标签，无匹配返回"其他" |
| P2 | 无评估脚本 | 无法量化分类效果，无法验证优化是否有效 | 新增 `evaluate.py`，支持 baseline/improved 对比，准确率和错分样本输出 |
| P3 | 批量处理缺少错误记录 | 线上问题无法追溯 | `results/` 目录持久化，每次运行自动创建 |

---

## 3. Prompt 优化

### 旧版 Prompt 的问题

1. 没有 System Prompt，所有指令堆在一条 User Message 中
2. 没有标签定义，仅列出六个类别名称
3. 没有冲突处理规则，混合诉求（如"退款的事顺便看看快递"）无法决策
4. 没有边界案例说明（寒暄、问号、无意义内容等）
5. 输出约束不足，LLM 可能返回前缀（如"类别："）或标点
6. 没有区分"退款进度查询"与"物流查询"

### 新版 Prompt 的改进

1. **结构化 System Prompt**：明确角色定位，强调只能输出六个标签之一
2. **详细分类规则**：每个标签给出 3-6 条具体说明和典型场景
3. **冲突处理规则**：
   - 多类别同时涉及时，以主要诉求为准
   - "退款进度查询"归入"退款退货"而非"物流查询"
   - "包裹已签收但未收到"归入"物流查询"
   - 抱怨退货流程时归入"投诉建议"
   - 纯寒暄/感谢/问号归入"其他"
4. **强化输出格式约束**："只输出标签名称，不要解释，不要标点，不要 JSON"
5. **User Message 拆离**：System Prompt 提供规则，User Message 仅传递问题文本

---

## 4. 工程改进

| 序号 | 改进项 | 说明 |
|------|--------|------|
| 1 | API Key 环境变量管理 | 不硬编码，从 `DEEPSEEK_API_KEY` 读取 |
| 2 | 异常处理与重试 | try/except + 指数退避，最多重试 3 次 |
| 3 | 输出标签校验 | `normalize_label()` 去掉前缀/标点，子串匹配合法标签 |
| 4 | mock/deepseek 双模式 | `--mode mock` 关键词分类（无需 API），`--mode deepseek` 调用 LLM |
| 5 | 评估脚本 | `evaluate.py` 读取结果文件，对比准确率和错分样本 |
| 6 | 结果持久化 | `results/` 目录自动创建，包含分类结果和错误记录 |
| 7 | CLI 参数化 | 支持 `--input`、`--output`、`--mode`、`--prompt` 灵活配置 |

---

## 5. 运行说明

### 安装依赖

```bash
pip install -r requirements.txt
```

### 脚本说明

| 脚本 | 职责 |
|------|------|
| `classifier.py` | 分类：读取 JSON，调用 mock 或 DeepSeek，输出结果文件 |
| `evaluate.py` | 评估：读取结果文件，对比真实标签，输出准确率和错分样本 |

### 测试集

| 文件 | 说明 |
|------|------|
| `docs/test_samples.json` | 给定的原始测试集（30 条） |
| `docs/test_hard_cases.json` | 自行构造的边界测试集（25 条，用于验证 baseline/improved 差异） |

### 运行命令

#### 快速验证（无需 API Key）

```bash
# Mock 模式分类
python classifier.py --mode mock --input docs/test_hard_cases.json --output results/hard_mock.json

# 评估结果
python evaluate.py --mock results/hard_mock.json
```

#### 完整评估（需要 API Key）

```bash
# 1. 配置 API Key：在 .env 文件中填入 DEEPSEEK_API_KEY

# 2. Mock 模式
python classifier.py --mode mock --input docs/test_hard_cases.json --output results/hard_mock.json

# 3. DeepSeek + Baseline
python classifier.py --mode deepseek --prompt baseline --input docs/test_hard_cases.json --output results/hard_baseline.json

# 4. DeepSeek + Improved
python classifier.py --mode deepseek --prompt improved --input docs/test_hard_cases.json --output results/hard_improved.json

# 5. 评估所有结果
python evaluate.py --mock results/hard_mock.json --baseline results/hard_baseline.json --improved results/hard_improved.json
```

#### 真实测试集评估

```bash
python classifier.py --mode mock --input docs/test_samples.json --output results/test_mock.json
python classifier.py --mode deepseek --prompt baseline --input docs/test_samples.json --output results/test_baseline.json
python classifier.py --mode deepseek --prompt improved --input docs/test_samples.json --output results/test_improved.json
python evaluate.py --mock results/test_mock.json --baseline results/test_baseline.json --improved results/test_improved.json
```

---

## 6. 评估结果

### 边界测试集（`docs/test_hard_cases.json`，25 条）

| 版本 | 正确数 | 总数 | 准确率 |
|------|--------|------|--------|
| Mock（关键词） | 15 | 25 | 60.0% |
| Baseline | 21 | 25 | 84.0% |
| Improved | 23 | 25 | **92.0%** |

Improved 相比 Baseline 提升 **+8%**。

**主要改进点：**

- "你们支持七天无理由吗" → Baseline 判"商品咨询"，Improved 判"退款退货"
- "东西收到了但是颜色和图片差很多" → Baseline 判"商品咨询"，Improved 判"投诉建议"

### 真实测试集（`docs/test_samples.json`，30 条）

| 版本 | 正确数 | 总数 | 准确率 |
|------|--------|------|--------|
| Baseline | 30 | 30 | 100.00% |
| Improved | 30 | 30 | 100.00% |

---

## 7. 项目结构

```
faq-classifier-review/
├── classifier.py              # 分类脚本
├── prompts.py                # Prompt 定义（baseline / improved）
├── evaluate.py               # 评估脚本
├── requirements.txt          # 依赖
├── .env                      # API Key（不提交）
├── .gitignore
├── README.md
├── docs/
│   ├── categories.md             # 分类标签定义
│   ├── classification_prompt.md  # Prompt 优化文档
│   ├── test_samples.json         # 原始测试集（30 条）
│   └── test_hard_cases.json      # 边界测试集（25 条）
├── results/                      # 分类结果
│   ├── hard_mock.json
│   ├── hard_baseline.json
│   ├── hard_improved.json
│   └── *_errors.json             # 错分记录
└── screenshots/
    ├── cursor使用截图.png    # 开发过程截图
    ├── hard.png             # 边界测试集评估截图
    └── test.png             # 真实测试集评估截图
```

---

## 8. 关键实现

### normalize_label()

处理 LLM 输出可能包含前缀或标点的情况：

```python
def normalize_label(raw_text: str) -> str:
    # 去掉常见前缀（"类别："、"分类结果："等）
    # 去掉标点符号
    # 精确匹配 VALID_LABELS
    # 子串匹配
    # 无匹配返回"其他"
```

### Mock 分类器

纯关键词匹配，用于无需 API 的快速验证。支持主诉求优先、冲突处理、寒暄排除等规则。
