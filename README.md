# AiPy Token 用量分析器
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
AiPy Pro 扩展 —— 统计本地历史任务的 Token 用量，帮助用户了解和控制 AI 使用成本。
## ✨ 功能特性
- 📊 **全量统计**：分析所有历史任务的 input/output token 用量
- 📈 **核心指标**：input/output 比率、缓存命中率、平均单次消耗
- 🏆 **消耗排行**：按任务维度排出 Token 消耗 Top 榜
- 📝 **任务简报**：单任务执行完毕后自动生成用量简报
## 📦 安装
### 方式一：DXT 导入（推荐）
下载 `token-usage-analyzer-1.0.1.dxt`，在 AiPy Pro 中导入即可。
### 方式二：手动安装
```bash
# 1. 克隆仓库
git clone https://github.com/jpmason4788/aipy-token-usage-analyzer.git
cd aipy-token-usage-analyzer
# 2. 安装依赖
npm install
# 3. 复制到 AiPy 扩展目录
# macOS
cp -r . ~/Library/Application\ Support/aipy-pro/extensions/@aipy-pro/token-usage-analyzer
# Windows: %APPDATA%/aipy-pro/extensions/@aipy-pro/token-usage-analyzer
# Linux: ~/.config/aipy-pro/extensions/@aipy-pro/token-usage-analyzer
```
## 🚀 使用
安装后重启 AiPy，直接对话即可：
> "看看我的 token 用量"
> "输入输出比是多少"
> "哪个任务最费 token"
### MCP 工具
| 工具名 | 说明 |
|---|---|
| `analyze_token_usage` | 统计历史任务 Token 用量，返回 I/O 比率、缓存命中率、消耗排行 |
| `task_token_brief` | 生成指定/最近任务的 Token 用量简报 |
### 命令行
```bash
python scripts/analyze.py            # 全量历史
python scripts/analyze.py --latest   # 最近一个任务
python scripts/analyze.py --task <id> # 指定任务
python scripts/analyze.py --json     # JSON 输出
```
## 📐 指标口径
| 指标 | 公式 |
|---|---|
| input/output 比率 | Σinput_tokens / Σoutput_tokens |
| 缓存命中率 | 1 - Σmissing_tokens / Σinput_tokens |
> ⚠️ 部分 Provider（如 trustoken、Helix）不回传 `missing_tokens`，此时缓存数据标记为不可用，不会以 100% 误导用户。
## 🔧 技术实现
- **数据源**：AiPy 主数据库 `task` / `task_event` 表（`usage` 字段）
- **读取方式**：复制数据库快照后读取，不锁定正在运行的 AiPy
- **服务类型**：Streamable HTTP Server（符合 AiPy 集市规范）
- **端口策略**：随机端口，启动后打印端口号到 STDOUT
- **系统提示注入**：提供 `addition-system-instruction` Prompt
## 📁 目录结构
```
.
├── manifest.json          # DXT 扩展元数据
├── package.json           # Node 依赖
├── server.js              # MCP Server（Streamable HTTP）
├── icon.svg               # 图标
├── scripts/
│   ├── analyze.py         # 核心分析脚本
│   └── auto_report.py     # 任务简报脚本
└── README.md
```
## 📄 License
MIT
