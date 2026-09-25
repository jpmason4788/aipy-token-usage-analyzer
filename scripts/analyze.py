#!/usr/bin/env python3
"""
AiPy Token 用量分析器
用法:
    python analyze.py                 # 分析全部历史任务
    python analyze.py --task <id>     # 分析指定任务
    python analyze.py --latest        # 只分析最近一个任务
    python analyze.py --json          # 输出 JSON
    python analyze.py --watch         # 监听模式：任务结束后自动分析
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path
DB_CANDIDATES = [
    Path.home() / "Library/Application Support/aipy-pro/aipy",      # macOS
    Path.home() / ".config/aipy-pro/aipy",                           # Linux
    Path(os.environ.get("APPDATA", "")) / "aipy-pro/aipy",           # Windows
]
def find_db() -> Path:
    for p in DB_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError("未找到 AiPy 主数据库，请确认 AiPy 已安装并运行过任务")
def open_db():
    """复制一份再打开，避免锁住正在运行的 AiPy。"""
    src = find_db()
    tmp = Path(tempfile.mkdtemp()) / "aipy_snapshot.db"
    shutil.copy2(src, tmp)
    # WAL 文件也一起复制，保证数据完整
    for suffix in ("-wal", "-shm"):
        s = Path(str(src) + suffix)
        if s.exists():
            try:
                shutil.copy2(s, Path(str(tmp) + suffix))
            except Exception:
                pass
    con = sqlite3.connect(str(tmp))
    con.row_factory = sqlite3.Row
    return con
def collect(con, task_id=None, latest=False, current=False):
    cur = con.cursor()
    if current:
        # 按当前工作目录自动识别当前对话任务
        import os
        wd = os.getcwd()
        cur.execute("SELECT * FROM task WHERE workdir = ? ORDER BY create_time DESC LIMIT 1", (wd,))
        row = cur.fetchone()
        if row:
            task_id = row["id"]
        else:
            # 回退：取最近一个有 LLM 调用的任务
            cur.execute("""SELECT t.* FROM task t WHERE t.id IN
                (SELECT DISTINCT task_id FROM task_event WHERE usage IS NOT NULL AND usage != '{}')
                ORDER BY t.create_time DESC LIMIT 1""")
            row = cur.fetchone()
            task_id = row["id"] if row else None
    if task_id:
        cur.execute("SELECT * FROM task WHERE id = ?", (task_id,))
    elif latest:
        # 取最近一个「确实产生过 LLM 调用」的任务
        cur.execute("""
            SELECT t.* FROM task t
            WHERE t.id IN (
                SELECT DISTINCT task_id FROM task_event
                WHERE usage IS NOT NULL AND usage != '{}'
            )
            ORDER BY t.create_time DESC LIMIT 1
        """)
    else:
        cur.execute("SELECT * FROM task")
    tasks = {r["id"]: dict(r) for r in cur.fetchall()}
    if not tasks:
        return {}, {}
    q = "SELECT task_id, usage FROM task_event WHERE usage IS NOT NULL AND usage != '{}'"
    params = ()
    if task_id:
        q += " AND task_id = ?"; params = (task_id,)
    cur.execute(q, params)
    per_task, tot = {}, dict(inp=0, out=0, total=0, reason=0, missing=0, calls=0, time=0)
    for r in cur.fetchall():
        if r["task_id"] not in tasks:
            continue
        try:
            u = json.loads(r["usage"])
        except Exception:
            continue
        if not isinstance(u, dict) or "input_tokens" not in u:
            continue
        d = per_task.setdefault(r["task_id"],
                                dict(inp=0, out=0, total=0, reason=0, missing=0, calls=0, time=0))
        for k, sk in [("inp", "input_tokens"), ("out", "output_tokens"), ("total", "total_tokens"),
                      ("reason", "reasoning_tokens"), ("missing", "missing_tokens"), ("time", "time")]:
            v = u.get(sk) or 0
            d[k] += v
            tot[k] += v
        d["calls"] += 1
        tot["calls"] += 1
    return per_task, tot
def fmt(n):
    return f"{n:,}"
def render(per_task, tot, tasks, as_json=False):
    result = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "tasks": len(per_task),
            "calls": tot["calls"],
            "input_tokens": tot["inp"],
            "output_tokens": tot["out"],
            "total_tokens": tot["total"],
            "reasoning_tokens": tot["reason"],
            "missing_tokens": tot["missing"],
            "io_ratio": round(tot["inp"] / tot["out"], 2) if tot["out"] else None,
            "output_ratio_pct": round(tot["out"] / tot["inp"] * 100, 2) if tot["inp"] else None,
            "avg_input_per_call": round(tot["inp"] / tot["calls"]) if tot["calls"] else 0,
            "avg_output_per_call": round(tot["out"] / tot["calls"]) if tot["calls"] else 0,
            "cache_hit_rate": round(1 - tot["missing"] / tot["inp"], 4) if tot["inp"] else None,
            "cache_data_available": tot["missing"] > 0,
        },
        "tasks": [],
    }
    for tid, d in sorted(per_task.items(), key=lambda x: -x[1]["total"]):
        t = tasks.get(tid, {})
        result["tasks"].append({
            "task_id": tid,
            "title": t.get("title"),
            "model": t.get("model"),
            "provider": t.get("provider"),
            "calls": d["calls"],
            "input_tokens": d["inp"],
            "output_tokens": d["out"],
            "total_tokens": d["total"],
            "io_ratio": round(d["inp"] / d["out"], 2) if d["out"] else None,
            "cache_hit_rate": round(1 - d["missing"] / d["inp"], 4) if d["inp"] else None,
        })
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result
    s = result["summary"]
    print("=" * 68)
    print("  AiPy Token 用量分析")
    print("=" * 68)
    print(f"  任务数: {s['tasks']}    LLM 调用: {fmt(s['calls'])} 次")
    print(f"  输入 Tokens:  {fmt(s['input_tokens'])}")
    print(f"  输出 Tokens:  {fmt(s['output_tokens'])}")
    print(f"  总 Tokens:    {fmt(s['total_tokens'])}")
    print("-" * 68)
    print(f"  input/output 比率:  {s['io_ratio']} : 1")
    print(f"  output/input 占比:  {s['output_ratio_pct']}%")
    print(f"  平均每次输入/输出:  {fmt(s['avg_input_per_call'])} / {fmt(s['avg_output_per_call'])} tokens")
    if s["cache_data_available"]:
        print(f"  缓存命中率:         {s['cache_hit_rate']*100:.2f}%")
    else:
        print(f"  缓存命中率:         数据不可用（Provider 未回传 missing_tokens）")
    print("=" * 68)
    if len(result["tasks"]) > 1:
        print(f"\n  {'任务':<34}{'调用':>6}{'输入':>12}{'输出':>11}{'I/O':>8}")
        print("-" * 68)
        for t in result["tasks"][:10]:
            title = (t["title"] or t["task_id"])[:32]
            print(f"  {title:<34}{t['calls']:>6}{t['input_tokens']:>12,}{t['output_tokens']:>11,}"
                  f"{(t['io_ratio'] or 0):>8.1f}")
    return result
def main():
    ap = argparse.ArgumentParser(description="AiPy Token 用量分析器")
    ap.add_argument("--task", help="指定任务 ID")
    ap.add_argument("--latest", action="store_true", help="只分析最近一个任务")
    ap.add_argument("--current", action="store_true", help="分析当前对话任务（按工作目录识别）")
    ap.add_argument("--json", action="store_true", help="输出 JSON 格式")
    ap.add_argument("--out", help="同时保存结果到指定文件")
    args = ap.parse_args()
    con = open_db()
    try:
        per_task, tot = collect(con, task_id=args.task, latest=args.latest, current=args.current)
    finally:
        con.close()
    if not per_task:
        print("未找到带 Token 用量的任务记录。")
        return 1
    con2 = open_db()
    try:
        c2 = con2.cursor()
        c2.execute("SELECT * FROM task")
        tasks = {r["id"]: dict(r) for r in c2.fetchall()}
    finally:
        con2.close()
    result = render(per_task, tot, tasks, as_json=args.json)
    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n结果已保存: {args.out}")
    return 0
if __name__ == "__main__":
    sys.exit(main())