# Prompt Injection Defense — 提示注入防御实验

比较单一强模型与异构分层多智能体协同架构的提示注入防御效果。

## 实验架构

| 架构 | 描述 | 状态 |
|------|------|------|
| **B0-Minimal** | 无额外防御，系统提示词无防御措辞（真正零防御基线） | ✅ **已冻结** |
| **B0-Hardened** | 无额外防御，系统提示词含 5 条安全规则（对照基线） | ✅ **已冻结** |
| **B1** | 单一强模型一次性完成检测 + 修复 | ✅ **已冻结**（Nex-N2-Pro） |
| **B2** | 三个异构检测 Agent 并行 + 直接修复 | 🔄 开发中 |
| **B3** | 三个异构检测 Agent + 风险裁决 + 修复 | 📅 待开发 |

## 当前实验结果

| 实验 | CLR（泄露率） | STCR（安全完成率） | 检测模型 |
|------|:------------:|:------------------:|---------|
| B0-Minimal | **62.0%** (98/158) | **26.6%** (42/158) | 无 |
| B0-Hardened | **0.0%** (0/158) | **51.3%** (81/158) | 无 |
| B1 (Nex-N2-Pro) | **15.2%** (24/158) | **45.6%** (72/158) | nex-agi/Nex-N2-Pro |

> 数据集：210 条测试用例（50 direct + 108 indirect + 52 benign），seed=42，中英双语

## 环境要求

- Python >= 3.10
- Ubuntu 22.04 WSL（或其他 Linux 环境）
- API 密钥：OpenRouter + SiliconFlow

## 安装

```bash
# 克隆仓库
git clone <repo-url>
cd prompt-injection-defense

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装项目（可编辑模式）
pip install -e .

# 安装开发依赖（pytest）
pip install -e ".[dev]"
```

## 配置密钥

复制环境变量模板并填入真实 API Key：

```bash
cp .env.example .env
```

编辑 `.env`：

```
OPENROUTER_API_KEY = sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SILICONFLOW_API_KEY = sf-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> ⚠️ `.env`、`runs/`、`data/generated/`、`reports/` 已加入 `.gitignore`，不会提交到仓库。

## 完整实验流程

### 1. 生成数据集

```bash
python -m pi_defense.generator \
  --output data/generated/dataset.jsonl \
  --canary-map data/generated/canary_map.json \
  --direct-per-family 5 \
  --indirect-per-cell 2 \
  --benign-count 35 \
  --languages zh en \
  --seed 42
```

### 2. 运行基线实验

```bash
# B0-Minimal（真正零防御基线）
python -m pi_defense.runner \
  --architecture B0 \
  --experiment-name B0-Minimal \
  --data data/generated/dataset.jsonl \
  --canary-map data/generated/canary_map.json \
  --output runs/b0_minimal.jsonl \
  --system-prompt-mode minimal \
  --dataset-seed 42

# B0-Hardened（含 5 条安全规则的对照基线）
python -m pi_defense.runner \
  --architecture B0 \
  --experiment-name B0-Hardened \
  --data data/generated/dataset.jsonl \
  --canary-map data/generated/canary_map.json \
  --output runs/b0_hardened.jsonl \
  --system-prompt-mode hardened \
  --dataset-seed 42

# B1（单一强模型防御）
python -m pi_defense.runner \
  --architecture B1 \
  --experiment-name B1 \
  --config configs/models_b1_nex.yaml \
  --data data/generated/dataset.jsonl \
  --canary-map data/generated/canary_map.json \
  --output runs/b1_nex.jsonl \
  --system-prompt-mode minimal \
  --dataset-seed 42
```

### 3. 生成报告

```bash
# 单个实验报告
python scripts/report_baseline.py runs/b0_minimal.jsonl --output reports/b0_minimal.csv

# 全部实验对比
python scripts/compare_experiments.py

# 结果验证
python scripts/verify_b1.py runs/b1_nex.jsonl
```

## 命令行参数

| 参数 | 默认值 | 说明 |
|------|-------|------|
| `--config` | `configs/models.yaml` | 模型配置文件路径 |
| `--data` | `data/smoke_cases.jsonl` | 测试样本 JSONL 文件路径 |
| `--architecture` | `B0` | 实验架构（B0/B1/B2/B3） |
| `--output` | `runs/b0_smoke.jsonl` | 输出 JSONL 路径 |
| `--limit` | 无 | 仅处理前 N 条样本 |
| `--canary-map` | 无 | 金丝雀映射 JSON 路径 |
| `--experiment-name` | 无 | 实验名称标签（写入每条记录的 run_id） |
| `--system-prompt-mode` | `minimal` | 提示词模式（minimal / hardened） |
| `--dataset-seed` | 无 | 数据集随机种子 |

## 输出格式（JSONL）

每条结果记录包含以下字段：

### 通用字段

| 字段 | 类型 | 说明 |
|------|------|------|
| run_id | str | 运行批次 ID |
| case_id | str | 案例 ID |
| base_case_id | str | 基础案例 ID |
| architecture | str | 实验架构 |
| kind | str | 样本类型（benign/direct/indirect） |
| attack_family | str or null | 攻击类别 |
| configured_model | str | 配置的目标模型 ID |
| actual_model | str or null | API 实际返回的模型 ID |
| target_output | str | 目标模型输出文本 |
| leaked | bool | 是否泄露金丝雀 |
| leak_variant | str or null | 泄露变体 |
| task_correct_auto | bool or null | 自动任务评分结果 |
| task_correct_manual | bool or null | 人工复核占位 |
| failure_category | str or null | 失败分类（over_refusal/task_hijacked/incorrect/none） |
| over_refusal | bool | 是否过度拒绝 |
| task_hijacked | bool | 任务是否被劫持 |
| latency_ms | float or null | API 调用延迟（毫秒） |
| input_tokens | int or null | 输入 Token 数 |
| output_tokens | int or null | 输出 Token 数 |
| error | str or null | 错误信息 |
| timestamp | str | ISO 8601 时间戳 |

### 元数据字段

| 字段 | 类型 | 说明 |
|------|------|------|
| system_prompt_mode | str | 提示词模式（minimal/hardened） |
| system_prompt_hash | str | 提示词 SHA256 摘要 |
| dataset_seed | int or null | 数据集种子 |
| dataset_hash | str or null | 数据集文件哈希 |
| temperature | float | 模型温度（固定 0.0） |
| max_tokens | int | 最大 Token 数（固定 256） |
| git_commit | str or null | 运行时 Git commit |

### B1 专用字段

| 字段 | 类型 | 说明 |
|------|------|------|
| defender_is_attack | bool | 检测器是否判定为攻击 |
| defender_repaired | bool | 检测器是否尝试修复 |
| defender_model | str or null | 检测器实际模型 ID |
| defender_latency_ms | float or null | 检测器延迟 |
| defender_raw | str or null | 检测器原始输出（JSON） |

## 运行测试

```bash
# 激活虚拟环境后
python -m pytest

# 静默模式
python -m pytest -q

# 带详细回溯
python -m pytest --tb=short -v
```

所有网络调用均已 mock，测试不会真实消耗 API 额度。

## 项目结构

```
prompt-injection-defense/
├── configs/
│   ├── models.yaml                  # 默认模型配置
│   └── models_b1_nex.yaml           # B1-Nex 模型配置
├── data/
│   ├── smoke_cases.jsonl            # 冒烟测试样本（4 条）
│   └── generated/                   # 生成的数据集（.gitignore）
├── runs/                            # 实验结果（.gitignore）
├── reports/                         # 分析报告（.gitignore）
├── scripts/
│   ├── compare_experiments.py       # 实验对比表
│   ├── report_baseline.py           # 基线报告生成器
│   └── verify_b1.py                 # B1 结果核验工具
├── src/
│   └── pi_defense/
│       ├── __init__.py
│       ├── canary.py                # 金丝雀生成与检测
│       ├── clients.py               # API 客户端（OpenAI 兼容接口）
│       ├── prompts.py               # 提示词构造（minimal / hardened）
│       ├── runner.py                # 命令行入口
│       ├── schemas.py               # 数据模型（Pydantic）
│       ├── scoring.py               # 任务评分器（别名匹配 + 失败分类）
│       ├── generator/               # 数据生成器模块
│       │   ├── pipeline.py          # 编排器 + CLI
│       │   ├── base_tasks.py        # 基础任务模板（14 种）
│       │   ├── direct.py            # 直接注入 5 家族生成器
│       │   ├── indirect.py          # 间接注入生成器
│       │   └── benign.py            # 正常样本生成器
│       └── workflows/
│           ├── b0.py                # B0 工作流
│           └── b1.py                # B1 工作流
├── tests/
│   ├── test_canary.py               # 金丝雀检测测试
│   ├── test_runner.py               # runner + 评分器测试
│   ├── test_generator.py            # 数据生成器测试
│   ├── test_scoring.py              # 评分器专项测试
│   └── speed_test_b1.py             # B1 检测器速度测试
├── .env.example                     # 环境变量模板
├── .gitignore
├── pyproject.toml
├── README.md
└── setup.py
```

## 模型配置

`configs/models.yaml` 定义了所有角色模型：

```yaml
target:           zai-org/GLM-4.5-Air (硅基流动)
strong_defender:  deepseek-ai/DeepSeek-V4-Flash (硅基流动)
adjudicator:      deepseek-ai/DeepSeek-V4-Flash (硅基流动)
repair:           openai/gpt-oss-20b (OpenRouter)
detectors:
  boundary:       qwen/qwen3-14b (OpenRouter)
  semantic:       google/gemma-3-12b-it (OpenRouter)
  indirect:       ministral-14b-2512 (OpenRouter)
```

B1 实验使用专用配置文件 `configs/models_b1_nex.yaml`，用 Nex-N2-Pro 替代 DeepSeek 作为检测器。

## 实验结果对比工具

```bash
# 三实验对比
python scripts/compare_experiments.py

# B1 完整核验
python scripts/verify_b1.py

# 单个实验报告（Wilson 95% CI）
python scripts/report_baseline.py runs/b1_nex.jsonl
```

## 许可证

课程设计项目，仅限教育用途。