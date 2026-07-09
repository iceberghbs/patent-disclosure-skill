# 安装说明

本技能遵循 [AgentSkills](https://agentskills.io) 常见布局：仓库根目录即技能根目录，内含 `SKILL.md`。

## Claude Code

在 **git 仓库根目录** 下安装：

```bash
mkdir -p .claude/skills
git clone <本仓库 URL> .claude/skills/patent-disclosure-skill
```

或使用本地路径复制到 `.claude/skills/patent-disclosure-skill`。

运行时环境通常会设置 **`CLAUDE_SKILL_DIR`** 指向该技能目录；`SKILL.md` 中的 `${CLAUDE_SKILL_DIR}/prompts/...` 即解析到此路径。

## Cursor

Cursor 支持 [Agent Skills](https://www.cursor.com/docs/context/skills) 约定：每个技能是一个**子文件夹**，内含根级 `SKILL.md`（`name` 字段须与文件夹名一致，本仓库为 `patent-disclosure-skill`）。可将**本仓库完整内容**（含 `prompts/`、`tools/` 等）放在下列位置之一，重启 Cursor 后在 **Settings → Rules** 中查看是否已被发现；亦可用 Agent 输入 `/` 后选择技能名。

### 用户主目录（全局，所有项目可用）

| 系统 | 推荐路径 |
|------|----------|
| Windows | `%USERPROFILE%\.cursor\skills\patent-disclosure-skill\`（即 `C:\Users\<用户名>\.cursor\skills\patent-disclosure-skill\`） |
| macOS / Linux | `~/.cursor/skills/patent-disclosure-skill/` |

示例（将仓库克隆到全局技能目录）：

```bash
mkdir -p ~/.cursor/skills
git clone <本仓库 URL> ~/.cursor/skills/patent-disclosure-skill
```

Windows（PowerShell）：

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.cursor\skills"
git clone <本仓库 URL> "$env:USERPROFILE\.cursor\skills\patent-disclosure-skill"
```

### 项目目录（仅当前仓库）

将本技能放在当前工作区下的：

`<项目根>/.cursor/skills/patent-disclosure-skill/`

（同样需包含完整仓库文件树，且 **`SKILL.md` 中 `name: patent-disclosure-skill` 与文件夹名一致**。）

### 与「仅打开文件夹」等价关系

若未使用上述 `skills/` 布局，也可**直接用 Cursor 打开本仓库根目录**作为工作区；此时将 **`CLAUDE_SKILL_DIR`** 理解为「包含 `SKILL.md` 的目录」，prompts 路径为 `./prompts/*.md`，与 `SKILL.md` 示例命令中的 **`${CLAUDE_SKILL_DIR}`** 同义。

为与 Claude Code 迁移一致，Cursor 也会扫描 **`~/.claude/skills/`**、项目内 **`.claude/skills/`** 等路径；详见 Cursor 官方文档与当前版本设置项。

## 可选依赖

若仅使用交底书 Markdown 流程，不必安装 Python。

若需使用 **`tools/md_to_docx.py`**（Markdown → Word）、**`tools/docx_to_md.py`**（Word → Markdown + 图片）或 **`tools/pptx_to_md.py`**（PPT → Markdown + 图片，供扫描）：

```bash
pip install -r requirements.txt
```

交底书定稿须同时产出 **.md + .docx**，且将 **mermaid**（**4.1 系统框图**与 **4.2 流程图**，**须** B/W 主题）经 **`tools/build_docx.py`**（调用 `mmdc` + `pandoc`）转为 PNG 嵌入并生成含 OMML 原生公式的 Word。**mermaid** 须 **Node.js**：在 **`tools/`** 执行 **`npm install`**（含 **`puppeteer`**）；若 **`mmdc`** 报找不到 Chrome，再执行 **`npx puppeteer browsers install chrome-headless-shell`**。**pandoc** 须 `apt-get install pandoc`。详见 **`tools/README.md`**。

## 可选：国知局公布公告站抓取（Step 5 查新优先路径）

若需使用 **`tools/cnipa_epub_search.py`**（一步，推荐）或 **`tools/cnipa_epub_crawler.py`** / **`tools/cnipa_epub_parse.py`**（[epub.cnipa.gov.cn](http://epub.cnipa.gov.cn/)，见 `prompts/prior_art_search.md`），**浏览器后端二选一**：

### 方式一：Playwright（Python，默认）

```bash
pip install -r tools/requirements-cnipa.txt
python -m playwright install chromium
```

### 方式二：agent-browser（Rust CLI，可选）

[agent-browser](https://agent-browser.dev) 是面向 AI Agent 的纯 Rust 浏览器自动化 CLI（通过 CDP 驱动 Chrome），更贴合 Agent/Shell 驱动的工作流，无须 Python 浏览器依赖：

```bash
npm i -g agent-browser
agent-browser install          # 首次使用下载 Chrome
```

两种后端通过环境变量 **`EPUB_BROWSER_BACKEND`** 切换（默认 `auto`：agent-browser 在 PATH 且 Playwright 未装时自动降级到 agent-browser）：

```bash
EPUB_BROWSER_BACKEND=agent-browser python tools/cnipa_epub_search.py 图像拼接
EPUB_BROWSER_BACKEND=playwright   python tools/cnipa_epub_search.py 图像拼接
```

agent-browser 后端额外环境变量：`AGENT_BROWSER_BIN`（可执行路径）、`AGENT_BROWSER_HEADED=1`（有界面调试）、`AGENT_BROWSER_TIMEOUT`（单命令超时秒）。

**Windows 终端中文**：`cnipa_epub_search.py` / `cnipa_epub_crawler.py` 已对 stdout/stderr 尝试 **UTF-8**（`reconfigure`）。若仍乱码，可在运行前执行 **`chcp 65001`**，或设置环境变量 **`PYTHONUTF8=1`**，以便复制 **`EPUB_HITS_JSON:`** 一行给 Agent 时不误判为失败。

与主流程 `requirements.txt` **独立**；未安装时 Step 5 仍可按该 prompt 降级为 **WebSearch**（如 Google 学术）。
