#!/usr/bin/env python3
"""
任务完成后自动生成 Token 用量简报。
设计为可被 AiPy 任务收尾流程调用，或单独执行。
用法:
    python auto_report.py                    # 分析最近一个任务并打印简报
    python auto_report.py --task <id>        # 分析指定任务
    python auto_report.py --save             # 同时保存到任务工作目录
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
ANALYZE = HERE / "analyze.py"
def run_analyze(args):
    r = subprocess.run([sys.executable, str(ANALYZE)] + args,
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None
def brief(data):
    if not data:
        return "⚠️ 无法获取 Token 用量数据"
    s = data["summary"]
    lines = [
        "📊 **本次任务 Token 用量**",
        f"- 输入：{s['input_tokens']:,} tokens",
        f"- 输出：{s['output_tokens']:,} tokens",
        f"- 合计：{s['total_tokens']:,} tokens（{s['calls']} 次 LLM 调用）",
        f"- input/output 比率：**{s['io_ratio']} : 1**",
    ]
    if s.get("cache_data_available"):
        lines.append(f"- 缓存命中率：{s['cache_hit_rate']*100:.2f}%")
    else:
        lines.append("- 缓存命中率：数据不可用（Provider 未回传）")
    # 健康度提示
    if s["io_ratio"] and s["io_ratio"] > 50:
        lines.append(f"\n💡 **优化提示**：I/O 比高达 {s['io_ratio']}:1，上下文重复携带较多，"
                     "建议启用上下文压缩或 Prompt Caching。")
    return "\n".join(lines)
def main():
    ap = argparse.ArgumentParser(description="任务完成后自动 Token 简报")
    ap.add_argument("--task", help="指定任务 ID")
    ap.add_argument("--save", action="store_true", help="保存简报到工作目录")
    args = ap.parse_args()
    a = ["--json"]
    if args.task:
        a += ["--task", args.task]
    else:
        a += ["--latest"]
    data = run_analyze(a)
    text = brief(data)
    print(text)
    if args.save and data:
        out = Path.cwd() / "token_usage_report.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n明细已保存: {out}")
    return 0
if __name__ == "__main__":
    sys.exit(main())