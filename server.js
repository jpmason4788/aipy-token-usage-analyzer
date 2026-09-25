#!/usr/bin/env node
/**
 * AiPy Token 用量分析器 - MCP Server (Streamable HTTP)
 * 符合 AiPy Pro 智能体集市规范：
 *  - Streamable HTTP Server
 *  - 随机端口，启动后打印端口号到 STDOUT
 *  - 提供 addition-system-instruction Prompt
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { createServer } from "http";
import { execFile } from "child_process";
import { promisify } from "util";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import { existsSync } from "fs";
import { homedir } from "os";
import { z } from "zod";
const execFileAsync = promisify(execFile);
const __dirname = dirname(fileURLToPath(import.meta.url));
const ANALYZE = join(__dirname, "scripts", "analyze.py");
function findPython() {
  const cands = [
    process.env.AIPY_PYTHON,
    join(homedir(), "Library/Application Support/aipy-pro/venv/bin/python"),
    "/usr/bin/python3",
    "python3",
    "python",
  ].filter(Boolean);
  for (const p of cands) {
    if (p.includes("/") && existsSync(p)) return p;
    if (!p.includes("/")) return p;
  }
  return "python3";
}
async function runAnalyze(args) {
  const py = findPython();
  const { stdout } = await execFileAsync(py, [ANALYZE, ...args], {
    maxBuffer: 32 * 1024 * 1024,
    timeout: 120000,
  });
  return JSON.parse(stdout);
}
function buildStatsText(data) {
  const s = data.summary;
  const lines = [
    "## AiPy Token 用量统计",
    "",
    `- 任务数：${s.tasks} 个，LLM 调用：${s.calls} 次`,
    `- 输入 Tokens：${s.input_tokens.toLocaleString()}`,
    `- 输出 Tokens：${s.output_tokens.toLocaleString()}`,
    `- 总 Tokens：${s.total_tokens.toLocaleString()}`,
    `- **input/output 比率：${s.io_ratio} : 1**`,
    `- output/input 占比：${s.output_ratio_pct}%`,
    `- 平均每次输入/输出：${s.avg_input_per_call.toLocaleString()} / ${s.avg_output_per_call.toLocaleString()} tokens`,
  ];
  if (s.cache_data_available) {
    lines.push(`- 缓存命中率：${(s.cache_hit_rate * 100).toFixed(2)}%`);
  } else {
    lines.push("- 缓存命中率：数据不可用（Provider 未回传 missing_tokens）");
  }
  if (data.tasks.length > 1) {
    lines.push("", "### 消耗排行 Top 10", "", "| 任务 | 调用 | 输入 | 输出 | I/O比 |", "|---|---|---|---|---|");
    for (const t of data.tasks.slice(0, 10)) {
      const title = (t.title || t.task_id).slice(0, 28);
      lines.push(`| ${title} | ${t.calls} | ${t.input_tokens.toLocaleString()} | ${t.output_tokens.toLocaleString()} | ${t.io_ratio} |`);
    }
  }
  return lines.join("\n");
}
function buildBriefText(data) {
  const s = data.summary;
  const lines = [
    "📊 **本次任务 Token 用量**",
    `- 输入：${s.input_tokens.toLocaleString()} tokens`,
    `- 输出：${s.output_tokens.toLocaleString()} tokens`,
    `- 合计：${s.total_tokens.toLocaleString()} tokens（${s.calls} 次 LLM 调用）`,
    `- input/output 比率：**${s.io_ratio} : 1**`,
  ];
  if (s.cache_data_available) {
    lines.push(`- 缓存命中率：${(s.cache_hit_rate * 100).toFixed(2)}%`);
  } else {
    lines.push("- 缓存命中率：数据不可用（Provider 未回传）");
  }
  if (s.io_ratio && s.io_ratio > 50) {
    lines.push("", `💡 **优化提示**：I/O 比高达 ${s.io_ratio}:1，上下文重复携带较多，建议启用上下文压缩或 Prompt Caching。`);
  }
  return lines.join("\n");
}
const server = new McpServer({ name: "token-usage-analyzer", version: "1.0.0" });
server.tool(
  "analyze_token_usage",
  "统计 AiPy 本地历史任务的 Token 用量，返回 input/output 比率、缓存命中率、任务消耗排行",
  { task_id: z.string().optional().describe("可选，指定任务 ID"), latest: z.boolean().optional().describe("可选，只分析最近一个任务") },
  async ({ task_id, latest }) => {
    const a = ["--json"];
    if (task_id) a.push("--task", task_id);
    else if (latest) a.push("--latest");
    try {
      const data = await runAnalyze(a);
      return { content: [{ type: "text", text: buildStatsText(data) }] };
    } catch (e) {
      return { content: [{ type: "text", text: `执行失败: ${e.message}` }], isError: true };
    }
  }
);
server.tool(
  "task_token_brief",
  "生成指定任务（或最近任务）的 Token 用量简报，适合任务收尾时调用",
  { task_id: z.string().optional().describe("可选，指定任务 ID") },
  async ({ task_id }) => {
    const a = ["--json"];
    if (task_id) a.push("--task", task_id);
    else a.push("--latest");
    try {
      const data = await runAnalyze(a);
      return { content: [{ type: "text", text: buildBriefText(data) }] };
    } catch (e) {
      return { content: [{ type: "text", text: `执行失败: ${e.message}` }], isError: true };
    }
  }
);
// addition-system-instruction Prompt（官方要求）
server.prompt(
  "addition-system-instruction",
  "向当前任务注入 Token 用量分析相关的系统提示",
  () => ({
    messages: [{
      role: "user",
      content: {
        type: "text",
        text: "当用户询问 Token 用量、输入输出比、缓存命中率、消耗统计时，请调用 token-usage-analyzer 扩展的 analyze_token_usage 或 task_token_brief 工具。注意：若返回结果中提示缓存数据不可用，请如实告知用户，不要用 100% 命中率误导。"
      }
    }]
  })
);
// 无状态模式：每个请求创建独立 transport，避免 session 冲突
const httpServer = createServer(async (req, res) => {
  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined,
    enableJsonResponse: true,
  });
  res.on("close", () => { transport.close(); });
  try {
    await server.connect(transport);
    await transport.handleRequest(req, res);
  } catch (e) {
    console.error("[token-usage-analyzer] request error:", e);
    if (!res.headersSent) {
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ jsonrpc: "2.0", error: { code: -32603, message: String(e) }, id: null }));
    }
  }
});
// 随机端口
httpServer.listen(0, "127.0.0.1", () => {
  const port = httpServer.address().port;
  // 官方要求：STDOUT 打印端口号
  console.log(port);
  console.error(`[token-usage-analyzer] HTTP MCP server listening on http://127.0.0.1:${port}`);
});
