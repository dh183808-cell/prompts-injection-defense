# Prompt Injection Defense — 提示注入防御实验

比较单⼀强模型与异构分层多智能体协同架构的提示注⼊防御效果。

## 实验架构

| 架构 | 描述 |
|------|------|
| B0 | 无额外防御（基线） |
| B1 | 单⼀强模型⼀体化防御 |
| B2 | 三个异构检测 Agent 并行 + 直接修复 |
| B3 | 三个异构检测 Agent + 风险裁决 + 修复 |

**当前里程碑状态**：B0 已完成并可稳定运行。B1/B2/B3 待实现。

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

> ⚠️ `.env` 已加入 `.gitignore`，不会提交到仓库。

## 运行 B0 基线实验

```bash
cd prompt-injection-defense

# 默认配置（configs/models.yaml + data/smoke_cases.jsonl）
python -m pi_defense.runner --architecture B0

# 指定参数
python -m pi_defense.runner --architecture B0 --config configs/models.yaml --data data/smoke_cases.jsonl --output runs/b0_smoke.jsonl --limit 5

# 仅运行冒烟测试（--limit 2）
python -m pi_defense.runner --architecture B0 --limit 2
```

### 命令行参数

| 参数 | 默认值 | 说明 |
|------|-------|------|
| `--config` | `configs/models.yaml` | 模型配置文件路径 |
| `--data` | `data/smoke_cases.jsonl` | 测试样本 JSONL 文件路径 |
| `--architecture` | `B0` | 实验架构（本轮仅支持 B0） |
| `--output` | `runs/b0_smoke.jsonl` | 输出 JSONL 路径 |
| `--limit` | 无（全部处理） | 仅处理前 N 条样本 |

### 输出格式（JSONL）

每条结果包含以下字段：

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
| leak_variant | str or null | 泄露变体（raw/reverse/base64/hex…） |
| task_correct | bool or null | 任务正确性 |
| latency_ms | float or null | API 调用延迟（毫秒） |
| input_tokens | int or null | 输入 Token 数 |
| output_tokens | int or null | 输出 Token 数 |
| error | str or null | 错误信息（如有） |
| timestamp | str | ISO 8601 时间戳 |

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
│   └── models.yaml              # 模型配置
├── data/
│   └── smoke_cases.jsonl        # 冒烟测试样本
├── runs/                        # 运行结果输出（.gitignore）
├── src/
│   └── pi_defense/
│       ├── __init__.py
│       ├── canary.py            # 金丝雀生成与检测
│       ├── clients.py           # API 客户端
│       ├── prompts.py           # 提示词构造
│       ├── runner.py            # 命令行入口
│       ├── schemas.py           # 数据模型
│       └── workflows/
│           └── b0.py            # B0 工作流
├── tests/
│   ├── test_canary.py           # 金丝雀检测测试
│   └── test_runner.py           # runner 模块测试
├── .env.example                 # 环境变量模板
├── .gitignore
├── pyproject.toml
├── README.md
└── setup.py
```

## 模型配置

`configs/models.yaml` 结构：

```yaml
target:
  provider: siliconflow
  model: "zai-org/GLM-4.5-Air"

strong_defender:
  provider: siliconflow
  model: "deepseek-ai/DeepSeek-V4-Flash"

adjudicator:
  provider: siliconflow
  model: "deepseek-ai/DeepSeek-V4-Flash"

repair:
  provider: openrouter
  model: "openai/gpt-oss-20b"

detectors:
  boundary:
    provider: openrouter
    model: "qwen/qwen3-14b"
  semantic:
    provider: openrouter
    model: "google/gemma-3-12b-it"
  indirect:
    provider: openrouter
    model: "mistralai/ministral-14b-2512"
```

> 当前 B0 仅使用 `target` 段。B1/B2/B3 的 `strong_defender` / `adjudicator` / `repair` / `detectors` 为后续里程碑预留。

## 许可证

课程设计项目，仅限教育用途。