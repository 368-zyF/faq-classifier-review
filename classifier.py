#!/usr/bin/env python3
"""
客服 FAQ 自动分类脚本 - 优化版本

支持 mock 模式和 deepseek 模式双运行，支持 baseline/improved 两种 prompt，
输出规范化标签和 JSON 结果文件。
"""

import os
import sys
import json
import argparse
import re
import time

from dotenv import load_dotenv
load_dotenv()

try:
    from openai import OpenAI
except ImportError:
    raise ImportError(
        "openai 包未安装，请运行: pip install openai\n"
        "或切换到 mock 模式: python classifier.py --mode mock ..."
    )

from prompts import BASELINE_PROMPT, IMPROVED_SYSTEM_PROMPT, IMPROVED_USER_PROMPT

VALID_LABELS = ["退款退货", "物流查询", "账号问题", "商品咨询", "投诉建议", "其他"]


# ============================================================================
# 标签规范化
# ============================================================================

def normalize_label(raw_text: str) -> str:
    """
    将 LLM 返回的原始文本规范化为标准标签。

    处理逻辑：
    - 去掉首尾空格。
    - 去掉常见前缀（如"类别："、"分类结果："等）。
    - 去掉标点符号。
    - 如果规范化后的文本精确匹配某个合法标签，直接返回。
    - 否则在文本中搜索包含某个合法标签的子串并返回。
    - 找不到任何合法标签时返回"其他"。
    """
    if not raw_text:
        return "其他"

    text = raw_text.strip()

    # 去掉常见前缀
    for prefix in ["类别：", "分类结果：", "分类：", "标签："]:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break

    # 去掉首尾标点
    text = text.strip("，。、！？：；.,!?…~…#*[]{}()（）「」『』【】")

    # 精确匹配
    if text in VALID_LABELS:
        return text

    # 子串匹配：允许 LLM 返回 "【退款退货】" 或 "退款退货类" 等变体
    for label in VALID_LABELS:
        if label in text:
            return label

    return "其他"


# ============================================================================
# Mock 分类器（keyword-based）
# ============================================================================

def _build_mock_classifier():
    """
    Mock 分类器：纯关键词匹配，无 prompt 概念。
    """

    def mock_classify(question: str) -> str:
        q = question
        # 边界案例：寒暄/无意义
        if q in ("你好", "嗯嗯好的谢谢", "？？？") or re.match(r"^[\s?？.。,，]*$", q):
            return "其他"
        # 边界案例：问号
        if q.strip() in ("？？？", "?", "？"):
            return "其他"
        # 特殊规则：纯感谢
        if "谢谢" in q and len(q) < 10 and "退款" not in q and "快递" not in q:
            return "其他"

        # 冲突处理：抱怨退货流程 => 投诉建议（强于退款退货）
        if re.search(r"(退货流程|退货.*太麻|太麻.*退货|搞不懂|流程.*不清)", q):
            return "投诉建议"
        if re.search(r"(太差|太差了|态度差|什么破|破质量)", q):
            return "投诉建议"

        # 主诉求优先：退款 + 退货 + 换货 + 部分退
        if any(w in q for w in ["退款", "退货", "退掉", "换货", "退的订单", "取消退货", "只退", "部分退"]):
            return "退款退货"

        # 物流查询
        if any(w in q for w in ["快递", "物流", "包裹", "签收", "派送", "快递柜", "寄错地址", "改派送", "放错快递柜"]):
            return "物流查询"

        # 账号问题
        if any(w in q for w in ["密码", "账号", "登录", "手机号", "冻结", "异地登录"]):
            return "账号问题"

        # 商品咨询
        if any(w in q for w in ["尺码", "材质", "有货", "库存", "支持", "真皮", "硅胶", "飞机", "规格", "功能", "颜色", "款", "这款", "这个商品", "这款鞋", "这个耳机", "这个手机壳", "这个包", "这个充电宝"]):
            return "商品咨询"

        # 投诉建议
        if any(w in q for w in ["投诉", "举报", "态度", "质量", "建议", "破质量", "太差", "太麻烦", "搞不懂"]):
            return "投诉建议"

        return "其他"

    return mock_classify


# ============================================================================
# DeepSeek 分类
# ============================================================================

def _classify_deepseek(question: str, prompt_version: str) -> str:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("环境变量 DEEPSEEK_API_KEY 未设置，请检查 .env 文件")

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )

    if prompt_version == "baseline":
        content = BASELINE_PROMPT.format(question=question)
        messages = [{"role": "user", "content": content}]
    else:
        messages = [
            {"role": "system", "content": IMPROVED_SYSTEM_PROMPT},
            {"role": "user", "content": IMPROVED_USER_PROMPT.format(question=question)},
        ]

    # 简单重试：最多 3 次
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                temperature=0,
            )
            raw = response.choices[0].message.content.strip()
            return normalize_label(raw)
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            # 最后一次也失败，抛出异常而非静默 fallback
            raise RuntimeError(f"DeepSeek API 调用失败（已重试 3 次）: {e}")


# ============================================================================
# 主分类接口
# ============================================================================

def classify_question(question: str, mode: str = "mock") -> str:
    """
    对单条用户问题进行分类。

        Args:
        question: 用户问题文本
        mode: "mock"（关键词匹配）或 "deepseek"（调用 DeepSeek LLM）
              deepseek 模式请直接用 classify_question_deepseek()

    Returns:
        标准化的分类标签
    """
    if mode == "mock":
        classifier = _build_mock_classifier()
        return classifier(question)

    elif mode == "deepseek":
        raise ValueError("deepseek mode requires prompt_version; use classify_question_deepseek() instead")

    else:
        raise ValueError(f"Unknown mode: {mode}. Must be 'mock' or 'deepseek'.")


def classify_question_deepseek(question: str, prompt_version: str) -> str:
    """
    对单条用户问题进行分类（DeepSeek 模式）。

    Args:
        question: 用户问题文本
        prompt_version: "baseline" 或 "improved"

    Returns:
        标准化的分类标签
    """
    return _classify_deepseek(question, prompt_version)


# ============================================================================
# 批量分类
# ============================================================================

def batch_classify(input_file: str, output_file: str, mode: str = "mock", prompt_version: str = "improved"):
    """
    批量分类，读取 JSON 输入，输出带分类结果的 JSON。
    mock 模式忽略 prompt_version；deepseek 模式使用它选择 prompt。
    """
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = []
    errors = []

    for item in data:
        try:
            question = item["question"]
            if mode == "mock":
                predicted = classify_question(question, mode="mock")
                results.append({
                    "id": item.get("id"),
                    "question": question,
                    "true_label": item.get("label"),
                    "predicted_category": predicted,
                    "mode": mode,
                })
            else:
                predicted = classify_question_deepseek(question, prompt_version=prompt_version)
                results.append({
                    "id": item.get("id"),
                    "question": question,
                    "true_label": item.get("label"),
                    "predicted_category": predicted,
                    "mode": mode,
                    "prompt_version": prompt_version,
                })
        except Exception as e:
            print(f"[WARN] Failed to classify id={item.get('id')}: {e}", file=sys.stderr)
            errors.append({"id": item.get("id"), "question": item.get("question"), "error": str(e)})
            if mode == "mock":
                results.append({
                    "id": item.get("id"),
                    "question": item.get("question"),
                    "true_label": item.get("label"),
                    "predicted_category": "其他",
                    "mode": mode,
                    "error": True,
                })
            else:
                # deepseek 模式出错直接中断，不静默 fallback
                print(f"[ERROR] deepseek 模式出错，分类中断。请检查 API 配置或网络。", file=sys.stderr)
                sys.exit(1)

    # 保存主结果
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 保存错误记录
    if errors:
        err_file = output_file.replace(".json", "_errors_detail.json")
        with open(err_file, "w", encoding="utf-8") as f:
            json.dump(errors, f, ensure_ascii=False, indent=2)

    return results


# ============================================================================
# CLI 入口
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="客服 FAQ 分类脚本")
    parser.add_argument("--input", required=True, help="输入 JSON 文件路径")
    parser.add_argument("--output", required=True, help="输出 JSON 文件路径")
    parser.add_argument(
        "--mode", choices=["mock", "deepseek"], default="mock",
        help="运行模式：mock（关键词模拟）或 deepseek（调用 DeepSeek LLM）"
    )
    parser.add_argument(
        "--prompt", choices=["baseline", "improved"], default="improved",
        help="Prompt 版本（仅 deepseek 模式生效，mock 模式忽略此参数）"
    )
    args = parser.parse_args()

    print(f"[INFO] mode={args.mode}, prompt={args.prompt}")
    print(f"[INFO] input={args.input}, output={args.output}")

    results = batch_classify(
        input_file=args.input,
        output_file=args.output,
        mode=args.mode,
        prompt_version=args.prompt,
    )

    print(f"\n[DONE] Classified {len(results)} questions.")
    print(f"[RESULT] Results saved to: {args.output}")


if __name__ == "__main__":
    main()
