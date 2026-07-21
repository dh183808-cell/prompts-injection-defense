"""单元测试：数据生成器模块（纯本地，无网络调用）。"""

import json
import os
from pathlib import Path

import pytest

from pi_defense.generator.base_tasks import ALL_TASKS, BaseTask
from pi_defense.generator.benign import generate_benign_cases
from pi_defense.generator.direct import FAMILY_GENERATORS, generate_direct_cases
from pi_defense.generator.indirect import SURFACE_FORMS, ATTACK_TYPES, POSITIONS, generate_indirect_cases
from pi_defense.generator.pipeline import parse_args, run
from pi_defense.schemas import ExperimentCase


# ── Fixtures ───────────────────────────────────────────


@pytest.fixture
def base_tasks() -> list[BaseTask]:
    return ALL_TASKS


# ── base_tasks.py ─────────────────────────────────────


class TestBaseTasks:
    def test_all_tasks_non_empty(self, base_tasks):
        assert len(base_tasks) > 0, "应该至少有一个基础任务"

    def test_each_task_has_all_fields(self, base_tasks):
        for t in base_tasks:
            assert isinstance(t, BaseTask)
            assert t.task_id
            assert t.zh_instruction
            assert t.en_instruction
            assert t.zh_content
            assert t.en_content
            assert t.expected_answer

    def test_each_task_is_deterministic(self, base_tasks):
        """同一 task_id 应总是返回相同的 instruction 和 content。"""
        for t in base_tasks:
            assert t.instruction("zh") == t.zh_instruction
            assert t.instruction("en") == t.en_instruction
            assert t.content("zh") == t.zh_content
            assert t.content("en") == t.en_content

    def test_task_categories_represented(self, base_tasks):
        """检查各类任务是否都有覆盖。"""
        tids = [t.task_id for t in base_tasks]
        categories = {"sentiment", "spam", "duplicate", "nli", "extract", "qa"}
        found = set()
        for tid in tids:
            for cat in categories:
                if tid.startswith(cat):
                    found.add(cat)
        for cat in categories:
            assert cat in found, f"缺少任务类别：{cat}"


# ── direct.py ─────────────────────────────────────────


class TestDirect:
    def test_all_families_generate(self, base_tasks):
        """5 种直接攻击家族都应能生成至少一个案例。"""
        cases = generate_direct_cases(
            base_tasks=base_tasks,
            per_family=1,
            languages=["zh"],
            seed=42,
        )
        families_generated = {c.attack_family for c in cases}
        for name, _ in FAMILY_GENERATORS:
            assert name in families_generated, f"缺少攻击家族：{name}"

    def test_each_case_is_valid_schema(self, base_tasks):
        cases = generate_direct_cases(
            base_tasks=base_tasks,
            per_family=1,
            languages=["zh", "en"],
            seed=42,
        )
        for c in cases:
            parsed = ExperimentCase.model_validate(c.model_dump())
            assert parsed.kind == "direct"

    def test_all_cases_have_provenance(self, base_tasks):
        cases = generate_direct_cases(
            base_tasks=base_tasks,
            per_family=1,
            languages=["zh"],
            seed=42,
        )
        for c in cases:
            assert c.source_family is not None, f"{c.case_id} 缺少 source_family"
            assert c.source_type is not None
            assert c.reference is not None
            assert c.adaptation_note is not None

    def test_deterministic_repeat(self, base_tasks):
        a = generate_direct_cases(
            base_tasks=base_tasks,
            per_family=2,
            languages=["zh", "en"],
            seed=42,
        )
        b = generate_direct_cases(
            base_tasks=base_tasks,
            per_family=2,
            languages=["zh", "en"],
            seed=42,
        )
        assert len(a) == len(b)
        for ca, cb in zip(a, b):
            assert ca.case_id == cb.case_id
            assert ca.user_input == cb.user_input
            assert ca.expected_answer == cb.expected_answer


# ── indirect.py ───────────────────────────────────────


class TestIndirect:
    def test_all_combinations_covered(self, base_tasks):
        """3 种载体 × 3 种攻击类型 × 3 种注入位置 = 27 个组合。"""
        cases = generate_indirect_cases(
            base_tasks=base_tasks,
            per_cell=1,
            languages=["zh"],
            seed=42,
        )
        cells = {c.base_case_id for c in cases}
        for sf in SURFACE_FORMS:
            for at in ATTACK_TYPES:
                for pos in POSITIONS:
                    cell = f"{sf}_{at}_{pos}_zh"
                    assert cell in cells, f"缺少组合单元：{cell}"

    def test_each_case_is_valid_schema(self, base_tasks):
        cases = generate_indirect_cases(
            base_tasks=base_tasks,
            per_cell=1,
            languages=["zh", "en"],
            seed=42,
        )
        for c in cases:
            parsed = ExperimentCase.model_validate(c.model_dump())
            assert parsed.kind == "indirect"

    def test_external_content_non_empty(self, base_tasks):
        cases = generate_indirect_cases(
            base_tasks=base_tasks,
            per_cell=1,
            languages=["zh"],
            seed=42,
        )
        for c in cases:
            assert c.external_content, f"{c.case_id} 的 external_content 为空"

    def test_deterministic_repeat(self, base_tasks):
        a = generate_indirect_cases(
            base_tasks=base_tasks,
            per_cell=2,
            languages=["zh", "en"],
            seed=42,
        )
        b = generate_indirect_cases(
            base_tasks=base_tasks,
            per_cell=2,
            languages=["zh", "en"],
            seed=42,
        )
        assert len(a) == len(b)
        for ca, cb in zip(a, b):
            assert ca.case_id == cb.case_id
            assert ca.external_content == cb.external_content


# ── benign.py ─────────────────────────────────────────


class TestBenign:
    def test_generates_benign_cases(self, base_tasks):
        cases = generate_benign_cases(
            base_tasks=base_tasks,
            benign_count=10,
            languages=["zh", "en"],
            seed=42,
        )
        for c in cases:
            parsed = ExperimentCase.model_validate(c.model_dump())
            assert parsed.kind == "benign"
            assert parsed.attack_family is None

    def test_has_hard_benign_examples(self, base_tasks):
        cases = generate_benign_cases(
            base_tasks=base_tasks,
            benign_count=10,
            languages=["zh", "en"],
            seed=42,
        )
        hard = [c for c in cases if "hard" in c.case_id]
        assert len(hard) > 0, "应该包含困难正常样本"


# ── pipeline.py ───────────────────────────────────────


class TestPipeline:
    def test_cli_parse_defaults(self):
        args = parse_args([])
        assert args.direct_per_family == 5
        assert args.indirect_per_cell == 2
        assert args.benign_count == 35
        assert args.languages == ["zh", "en"]
        assert args.seed == 42

    def test_cli_parse_custom(self):
        args = parse_args([
            "--direct-per-family", "3",
            "--indirect-per-cell", "1",
            "--benign-count", "20",
            "--languages", "zh",
            "--seed", "7",
        ])
        assert args.direct_per_family == 3
        assert args.indirect_per_cell == 1
        assert args.benign_count == 20
        assert args.languages == ["zh"]
        assert args.seed == 7

    def test_run_generates_valid_output(self, tmp_path, base_tasks):
        """验证 run() 输出可以直接被 ExperimentCase 解析。"""
        output = tmp_path / "test.jsonl"
        canary_map = tmp_path / "test_canary.json"
        args = parse_args([
            "--output", str(output),
            "--canary-map", str(canary_map),
            "--direct-per-family", "2",
            "--indirect-per-cell", "1",
            "--benign-count", "10",
            "--languages", "zh",
            "--seed", "123",
        ])
        cases, canaries = run(args)

        # 验证每条都是有效 ExperimentCase
        for c in cases:
            ExperimentCase.model_validate(c.model_dump())

        # 验证金丝雀映射
        assert len(canaries) == len(cases)
        for c in cases:
            assert c.case_id in canaries
            assert canaries[c.case_id].startswith("CANARY_")

    def test_deterministic_repeat(self, tmp_path):
        """相同参数两次运行产生完全相同的数据集。"""
        output_a = tmp_path / "a.jsonl"
        output_b = tmp_path / "b.jsonl"

        args = parse_args([
            "--output", str(output_a),
            "--direct-per-family", "2",
            "--indirect-per-cell", "1",
            "--benign-count", "10",
            "--languages", "zh",
            "--seed", "42",
        ])
        cases_a, _ = run(args)

        args = parse_args([
            "--output", str(output_b),
            "--direct-per-family", "2",
            "--indirect-per-cell", "1",
            "--benign-count", "10",
            "--languages", "zh",
            "--seed", "42",
        ])
        cases_b, _ = run(args)

        assert len(cases_a) == len(cases_b)
        for ca, cb in zip(cases_a, cases_b):
            assert ca.model_dump_json() == cb.model_dump_json()