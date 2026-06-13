#!/usr/bin/env python3
"""
evaluate.py - 客服 FAQ 分类器评估脚本

用法：
  # 只评 mock
  python evaluate.py --mock results/hard_mock.json

  # 只评 baseline
  python evaluate.py --baseline results/hard_baseline.json

  # 只评 improved
  python evaluate.py --improved results/hard_improved.json

  # 同时评 baseline 和 improved，并对比差异
  python evaluate.py --baseline results/hard_baseline.json --improved results/hard_improved.json

  # 同时评所有三个
  python evaluate.py --mock results/hard_mock.json --baseline results/hard_baseline.json --improved results/hard_improved.json

结果文件中的 true_label 来自测试样本，无需额外传入。
错误记录默认写入结果文件同目录下，如 results/hard_improved_errors.json。
"""

import os
import sys
import json
import argparse


def load_json(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_accuracy(results: list) -> tuple[int, int, float]:
    with_gt = [r for r in results if r.get("true_label")]
    total = len(with_gt)
    correct = sum(1 for r in with_gt if r["predicted_category"] == r["true_label"])
    accuracy = correct / total * 100 if total > 0 else 0
    return correct, total, accuracy


def load_errors_json(path: str) -> list:
    if os.path.exists(path):
        return load_json(path)
    return []


def main():
    parser = argparse.ArgumentParser(
        description="FAQ 分类器评估：对比 baseline / improved / mock 的分类准确率",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mock",
        help="Mock（关键词）结果文件路径，如 results/hard_mock.json",
    )
    parser.add_argument(
        "--baseline",
        help="Baseline 结果文件路径，如 results/hard_baseline.json",
    )
    parser.add_argument(
        "--improved",
        help="Improved 结果文件路径，如 results/hard_improved.json",
    )
    parser.add_argument(
        "--errors",
        help="错误记录输出目录（默认与结果文件同目录）",
    )
    args = parser.parse_args()

    if not any([args.mock, args.baseline, args.improved]):
        print("[ERROR] 请至少指定 --mock / --baseline / --improved 之一")
        sys.exit(1)

    # 统一：{name: (path, label_name)}
    sources = []
    if args.mock:
        sources.append(("Mock", args.mock, "mock"))
    if args.baseline:
        sources.append(("Baseline", args.baseline, "baseline"))
    if args.improved:
        sources.append(("Improved", args.improved, "improved"))

    # 全部加载
    loaded = {}
    for name, path, _ in sources:
        if not os.path.exists(path):
            print(f"[ERROR] 文件不存在: {path}")
            sys.exit(1)
        loaded[name] = load_json(path)

    # 全部评估
    stats = {}
    for name, path, label in sources:
        correct, total, acc = compute_accuracy(loaded[name])
        stats[name] = {
            "correct": correct,
            "total": total,
            "accuracy": acc,
        }

    # 打印每个模式的摘要
    print()
    print("=" * 58)
    print("  分类器评估结果")
    print("=" * 58)
    for name, path, label in sources:
        s = stats[name]
        tag = ""
        if name == "Baseline" and "Improved" in stats and "Baseline" in stats:
            delta = stats["Improved"]["accuracy"] - s["accuracy"]
            tag = f"  (improved {'+' if delta >= 0 else ''}{delta:.1f}%)"
        elif name == "Improved" and "Baseline" in stats:
            delta = s["accuracy"] - stats["Baseline"]["accuracy"]
            tag = f"  (baseline {'+' if delta >= 0 else ''}{-delta:.1f}%)"
        print(f"  {name:<10s} {s['correct']:>3d}/{s['total']:<3d} ({s['accuracy']:5.1f}%){tag}")
    print("=" * 58)

    # 生成错误记录
    errors_dir = args.errors
    if not errors_dir:
        # 默认：每个结果文件各自生成同名的 _errors.json
        pass

    for name, path, label in sources:
        results = loaded[name]
        errors = [r for r in results if r["predicted_category"] != r["true_label"]]

        if not errors:
            print(f"\n{name}：无错分样本")
            continue

        # 确定错误记录输出路径
        if errors_dir:
            base = os.path.basename(path).replace(".json", "")
            err_path = os.path.join(errors_dir, f"{base}_errors.json")
        else:
            err_path = path.replace(".json", "_errors.json")
        os.makedirs(os.path.dirname(err_path) or ".", exist_ok=True)
        with open(err_path, "w", encoding="utf-8") as f:
            json.dump(errors, f, ensure_ascii=False, indent=2)

        # 打印错误表格
        print(f"\n{name} 错分样本 ({len(errors)} 条): {err_path}")
        print("-" * 70)
        print(f"  {'ID':>4s}  {'问题':<26s}  {'期望':<8s}  {'实际':<8s}")
        print("-" * 70)
        for e in errors:
            q = e["question"]
            if len(q) > 24:
                q = q[:22] + ".."
            print(f"  {e['id']:>4d}  {q:<26s}  {e['true_label']:<8s}  {e['predicted_category']:<8s}")
        print("-" * 70)

    # 两两对比：improved vs baseline 详细差异
    if "Baseline" in loaded and "Improved" in loaded:
        print()
        print("=" * 58)
        print("  Improved vs Baseline 差异分析")
        print("=" * 58)

        baseline_map = {r["id"]: r for r in loaded["Baseline"]}
        improved_map = {r["id"]: r for r in loaded["Improved"]}

        baseline_only_errors = []  # baseline 错 improved 对
        improved_only_errors = []  # improved 错 baseline 对
        both_errors = []           # 两者都错

        for bid, br in baseline_map.items():
            ir = improved_map.get(bid)
            if not ir:
                continue
            b_wrong = br["predicted_category"] != br["true_label"]
            i_wrong = ir["predicted_category"] != ir["true_label"]
            if b_wrong and not i_wrong:
                baseline_only_errors.append((br, ir))
            elif i_wrong and not b_wrong:
                improved_only_errors.append((br, ir))
            elif b_wrong and i_wrong:
                both_errors.append((br, ir))

        if baseline_only_errors:
            print(f"\n  Baseline 错 / Improved 对 ({len(baseline_only_errors)} 条):")
            sep = "  " + "-" * 4 + "  " + "-" * 30 + "  " + "-" * 8 + "  " + "-" * 8
            print(sep)
            print(f"  {'ID':>4s}  {'问题':<30s}  {'Baseline':>8s}  {'Improved':>8s}")
            print(sep)
            for br, ir in baseline_only_errors:
                q = br["question"]
                if len(q) > 28:
                    q = q[:26] + ".."
                print(f"  {br['id']:>4d}  {q:<30s}  {br['predicted_category']:>8s}  {ir['predicted_category']:>8s}")

        if improved_only_errors:
            print(f"\n  Improved 错 / Baseline 对 ({len(improved_only_errors)} 条):")
            sep = "  " + "-" * 4 + "  " + "-" * 30 + "  " + "-" * 8 + "  " + "-" * 8
            print(sep)
            print(f"  {'ID':>4s}  {'问题':<30s}  {'Baseline':>8s}  {'Improved':>8s}")
            print(sep)
            for br, ir in improved_only_errors:
                q = br["question"]
                if len(q) > 28:
                    q = q[:26] + ".."
                print(f"  {br['id']:>4d}  {q:<30s}  {br['predicted_category']:>8s}  {ir['predicted_category']:>8s}")

        if both_errors:
            print(f"\n  两者都错 ({len(both_errors)} 条):")
            sep = "  " + "-" * 4 + "  " + "-" * 30 + "  " + "-" * 8 + "  " + "-" * 8 + "  " + "-" * 8
            print(sep)
            print(f"  {'ID':>4s}  {'问题':<30s}  {'期望':>8s}  {'Baseline':>8s}  {'Improved':>8s}")
            print(sep)
            for br, ir in both_errors:
                q = br["question"]
                if len(q) > 28:
                    q = q[:26] + ".."
                print(f"  {br['id']:>4d}  {q:<30s}  {br['true_label']:>8s}  {br['predicted_category']:>8s}  {ir['predicted_category']:>8s}")

        if not baseline_only_errors and not improved_only_errors and not both_errors:
            print("  [两者结果完全一致]")

        print("=" * 58)

    # Mock vs DeepSeek 对比（baseline 和 improved 都是 deepseek）
    if "Mock" in loaded and "Baseline" in loaded:
        print()
        print("=" * 58)
        print("  Mock vs DeepSeek 对比")
        print("=" * 58)
        mock_map = {r["id"]: r for r in loaded["Mock"]}
        deep_map = {r["id"]: r for r in loaded["Baseline"]}

        for did, dr in deep_map.items():
            mr = mock_map.get(did)
            if not mr:
                continue
            m_correct = mr["predicted_category"] == mr["true_label"]
            d_correct = dr["predicted_category"] == dr["true_label"]
            if m_correct and not d_correct:
                status = "Mock 对 / DeepSeek 错"
            elif not m_correct and d_correct:
                status = "Mock 错 / DeepSeek 对"
            else:
                continue
            q = dr["question"]
            if len(q) > 24:
                q = q[:22] + ".."
            print(f"  {dr['id']:>3d}  [{status}]  {q}")
        print("=" * 58)


if __name__ == "__main__":
    main()
