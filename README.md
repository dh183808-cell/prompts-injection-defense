# Prompt Injection Defense — 提示注入防御实验

比较单一强模型与异构分层多智能体协同架构的提示注入防御效果。

## 实验结果总览

| 架构 | 描述 | 状态 |
|------|------|------|
| **B0-Minimal** | 无额外防御，系统提示词无防御措辞（真正零防御基线） | ✅ **已冻结** |
| **B0-Hardened** | 无额外防御，系统提示词含 5 条安全规则（对照基线） | ✅ **已冻结** |
| **B1 (Nex-N2-Pro)** | 单一强模型一次性完成检测 + 修复 | ✅ **已冻结** |
| **B1 (DeepSeek)** | 同一架构，不同检测模型（速度慢但准确） | ✅ **已冻结** |
| **B2** | 三个异构检测器并行 + OR 触发 + 直接修复 | ✅ **已冻结** |
| **B3 v1** | 三个异构检测器 + 裁决层 + 修复 | ✅ **已冻结** |
| **B3 v2** | 三个异构检测器 + 改进裁决器（分类器+兜底者） | ✅ **已冻结** |

## 最终实验结果

```
Experiment           Attack Benign  Leaked   CLR      STCR    Refusal  Hijack  PromptMode
-------------------------------------------------------------------------------------------
B0-Minimal              158     52      98   62.0%    26.6%       0     103    minimal
B0-Hardened             158     52       0    0.0%    51.3%       5       2    hardened
B1-Nex                  158     52      24   15.2%    45.6%       3      24    minimal
B1-DeepSeek             158     52      18   11.4%    43.0%       4      18    minimal
B2                      158     52      20   12.7%    43.0%       2      21    minimal
B3 v1                   158     52      28   17.7%    43.7%       2      28    minimal
B3 v2                   158     52      23   14.6%    43.0%       3      24    minimal
```

> 数据集：210 条（50 direct + 108 indirect + 52 benign），seed=42，中英双语

## 关键发现

### 模型速度对比

| 模型 | 平台 | 单条耗时 | 210条耗时 | JSON 输出 |
|------|------|:--------:|:---------:|:---------:|
| DeepSeek-V4-Flash | SiliconFlow | ~47s | ~8h | ❌ 不支持 |
| Nex-N2-Pro | SiliconFlow | ~3.3s | ~13min | ✅ 稳定 |
| Qwen3-14B | OpenRouter | ~8s | — | ✅ |
| Gemma-3-12B | OpenRouter | ~3s | — | ✅ |
| Ministral-14B | OpenRouter | ~4s | — | ✅ |

**核心经验**：API 兼容性 > 模型名气。DeepSeek 名声响但不支持 JSON mode，Nex 名不见经传但稳定可用。先测速再跑全量可以避免浪费。

### CLR 排名（低到高）

| 排名 | 架构 | CLR | 相较于 B0-Minimal 降低 |
|:----:|------|:---:|:---------------------:|
| 🥇 | B0-Hardened | 0.0% | —（使用加固提示词） |
| 🥈 | B1-DeepSeek | 11.4% | **81.6%** |
| 🥉 | B2 | 12.7% | **79.5%** |
| 4 | B3 v2 | 14.6% | **76.5%** |
| 5 | B1-Nex | 15.2% | **75.5%** |
| 6 | B3 v1 | 17.7% | **71.5%** |
| 7 | B0-Minimal | 62.0% | —（基线） |

### STCR 排名（高到低）

| 排名 | 架构 | STCR | 说明 |
|:----:|------|:----:|------|
| 🥇 | B0-Hardened | 51.3% | 加固提示词本身不影响任务 |
| 🥈 | B1-Nex | 45.6% | 修复质量好 |
| 🥉 | B3 v1 | 43.7% | 与 B2/B3-v2 基本持平 |
| 4 | B1-DeepSeek | 43.0% | |
| 5 | B2 | 43.0% | |
| 6 | B3 v2 | 43.0% | |
| 7 | B0-Minimal | 26.6% | 任务被严重劫持 |

### 架构对比分析

**B3 v1 vs B3 v2（裁决器改进）：**
- 裁决确认率：95.6% → 94.9%（略有下降，因为裁决器更谨慎）
- 否决后错误泄露：4.4% → 5.1%（稍多否决，但否决中75%是正确的）
- 拦截成功率：82.8% → **86.0%** ↑
- 裁决器延迟中位数：~4.8s

**B3 v1 的问题**：裁决器提示词说"仅一条检测器报警→视为误报"，导致裁决器否决检测器的正确判断，攻击被放行。

**B3 v2 改进**：改为"任一检测器报警→确认攻击"，裁决器只做分类和兜底审查，不再否决检测器。同时修复了 `conservative_block` 路径不调用修复器的 bug。

**结论**：B3 v2 虽有改善但未超越 B2。多一层裁决增加了延迟（~4.8s）且没有带来显著的额外安全收益。**扁平架构（B2）优于分层架构（B3）**。

**整体结论：**
1. 所有防御架构均大幅降低泄露（62% → 11-18%）
2. **B1-Nex 性价比最优**：13 分钟，CLR 15.2%，单模型
3. **B2 检测最彻底**：100% 检出，但修复是瓶颈
4. **B3 裁决层价值有限**：增加延迟和复杂度，无显著增益
5. 所有泄露均来自间接注入（表格 > 文档 > 邮件），直接注入全部架构都能防住

## 环境要求

- Python >= 3.10
- Ubuntu 22.04 WSL（或其他 Linux 环境）
- API 密钥：OpenRouter + SiliconFlow

## 安装

```bash
git clone <repo-url>
cd prompt-injection-defense
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -e ".[dev]"
cp .env.example .env
# 编辑 .env 填入真实 API Key（.env 已加入 .gitignore）
```

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

### 2. 运行实验

```bash
# B0-Minimal
python -m pi_defense.runner --architecture B0 --experiment-name B0-Minimal \
  --data data/generated/dataset.jsonl --system-prompt-mode minimal --dataset-seed 42

# B0-Hardened
python -m pi_defense.runner --architecture B0 --experiment-name B0-Hardened \
  --data data/generated/dataset.jsonl --system-prompt-mode hardened --dataset-seed 42

# B1-Nex
python -m pi_defense.runner --architecture B1 --experiment-name B1-Nex \
  --config configs/models_b1_nex.yaml \
  --data data/generated/dataset.jsonl --system-prompt-mode minimal --dataset-seed 42

# B1-DeepSeek
python -m pi_defense.runner --architecture B1 --experiment-name B1-DeepSeek \
  --config configs/models.yaml \
  --data data/generated/dataset.jsonl --system-prompt-mode minimal --dataset-seed 42

# B2
python -m pi_defense.runner --architecture B2 --experiment-name B2 \
  --data data/generated/dataset.jsonl --system-prompt-mode minimal --dataset-seed 42

# B3 v2
python -m pi_defense.runner --architecture B3 --experiment-name B3-v2 \
  --data data/generated/dataset.jsonl --system-prompt-mode minimal --dataset-seed 42 \
  --max-concurrency 5
```

### 3. 查看对比

```bash
python scripts/compare_experiments.py
```

## 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--config` | `configs/models.yaml` | 模型配置文件 |
| `--data` | `data/smoke_cases.jsonl` | 测试样本 |
| `--architecture` | `B0` | B0/B1/B2/B3 |
| `--output` | `runs/b0_smoke.jsonl` | 输出路径 |
| `--limit` | 全部 | 样本数限制 |
| `--canary-map` | 无 | 金丝雀映射 |
| `--experiment-name` | 无 | 实验标签 |
| `--system-prompt-mode` | `minimal` | minimal / hardened |
| `--dataset-seed` | 无 | 数据集随机种子 |
| `--max-concurrency` | 1 | 并发处理数（>=3 建议用于 B3） |

## 输出格式

每条记录包含：run_id, case_id, base_case_id, architecture, kind, attack_family,
configured_model, actual_model, target_output, leaked, leak_variant,
task_correct_auto, task_correct_manual, failure_category, over_refusal,
task_hijacked, latency_ms, input_tokens, output_tokens,
system_prompt_mode, system_prompt_hash, dataset_seed, dataset_hash,
temperature, max_tokens, git_commit, error, timestamp

各架构专用字段：
- **B1**: defender_is_attack, defender_repaired, defender_model, defender_raw
- **B2/B3**: detector_0/1/2_suspicious, or_triggered, repair_action
- **B3**: adjudicator_confirmed, adjudicator_action, adjudicator_raw

## 项目结构

```
prompt-injection-defense/
├── configs/
│   ├── models.yaml                  # 默认模型配置
│   └── models_b1_nex.yaml           # B1-Nex 配置
├── data/
│   ├── smoke_cases.jsonl            # 冒烟测试样本（4 条）
│   └── generated/                   # 生成的数据集（.gitignore）
├── src/pi_defense/
│   ├── canary.py, clients.py        # 金丝雀 + API 客户端
│   ├── prompts.py                   # 提示词模板（含 B2/B3 检测/修复/裁决）
│   ├── runner.py                    # 命令行入口 + 并发控制
│   ├── schemas.py                   # Pydantic 数据模型
│   ├── scoring.py                   # 任务评分器
│   ├── generator/                   # 数据生成器
│   └── workflows/                   # B0/B1/B2/B3 工作流
├── tests/
├── scripts/                         # 分析工具
├── runs/                            # 实验结果（.gitignore）
└── QA_学习笔记[1-4].md              # 学习笔记（.gitignore）

## 模型配置

```yaml
target:           zai-org/GLM-4.5-Air (siliconflow)
strong_defender:  deepseek-ai/DeepSeek-V4-Flash (siliconflow)
adjudicator:      nex-agi/Nex-N2-Pro (siliconflow)     # B3 使用
repair:           openai/gpt-oss-20b (openrouter)       # B2/B3 使用
detectors:
  boundary:       qwen/qwen3-14b (openrouter)
  semantic:       google/gemma-3-12b-it (openrouter)
  indirect:       mistralai/ministral-14b-2512 (openrouter)
```

## 许可证

课程设计项目，仅限教育用途。