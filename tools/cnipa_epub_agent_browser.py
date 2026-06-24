# -*- coding: utf-8 -*-
"""
国知局公布公告站（http://epub.cnipa.gov.cn/）检索的 **agent-browser 后端**。

与 ``cnipa_epub_crawler.py``（Playwright 后端）**契约等价**：同样对外暴露
``fetch_epub_result_html(keyword) -> str``，返回结果页全页 HTML 字符串，供
``cnipa_epub_parse.parse_search_result_html`` 解析。

--------------------------------------------------------------------------------
为何提供此后端
--------------------------------------------------------------------------------
- Playwright 后端须 ``pip install playwright`` + ``python -m playwright install chromium``，
  环境准备步骤较多。
- **agent-browser**（https://agent-browser.dev，npm 包 ``agent-browser``，纯 Rust CLI + 守护进程，
  通过 CDP 驱动 Chrome）安装方式为 ``npm i -g agent-browser && agent-browser install``，
  更贴合 Agent/CLI 驱动的工作流。两者可二选一。

--------------------------------------------------------------------------------
流程（与 Playwright 后端逐一对齐）
--------------------------------------------------------------------------------
1. ``agent-browser --session <name> --user-agent <桌面UA> open <站点首页>``
   启动守护进程 + 浏览器并导航（``open`` 等同 ``goto`` / ``navigate``）。
2. **等待首页可检索**：站点 WAF/前端脚本未通过前不会渲染 ``#searchStr``。
   本实现周期性轮询 ``agent-browser ... get count "#searchStr"``（每 ``step`` 秒一次，
   总时长 ``EPUB_WAF_MAX_WAIT_SEC``，默认 180s），命中即继续。
3. ``agent-browser ... fill "#searchStr" "<keyword>"`` 填入关键词。
4. ``agent-browser ... eval "document.getElementById('indexForm').submit()"`` 提交表单，
   再 ``wait --load networkidle`` + 固定短时 ``wait <ms>`` 安定结果页。
5. ``agent-browser ... eval "JSON.stringify(document.documentElement.outerHTML)"`` 取全页 HTML
   （包成 JSON 字符串，避免内部换行/引号污染 stdout），本地 ``json.loads`` 还原。
6. ``finally`` 中 ``agent-browser ... close`` 关闭会话（守护进程随之回收）。

--------------------------------------------------------------------------------
环境变量
--------------------------------------------------------------------------------
  EPUB_WAF_MAX_WAIT_SEC   轮询等待 #searchStr 的最长时间，默认 180
  AGENT_BROWSER_BIN       agent-browser 可执行文件路径，默认自动探测 PATH
  AGENT_BROWSER_HEADED    设为 1 时 --headed 显示浏览器窗口（调试用）
  AGENT_BROWSER_TIMEOUT   单条子命令超时（秒），默认 120
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

EPUB_BASE = "http://epub.cnipa.gov.cn/"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _ensure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError, TypeError):
            pass


def resolve_binary() -> str:
    """返回 agent-browser 可执行文件路径；不在 PATH 时抛 FileNotFoundError。"""
    explicit = os.environ.get("AGENT_BROWSER_BIN", "").strip()
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            return str(p)
        found = shutil.which(explicit)
        if found:
            return found
        raise FileNotFoundError(f"AGENT_BROWSER_BIN 指定的 agent-browser 不存在: {explicit}")
    found = shutil.which("agent-browser")
    if not found:
        raise FileNotFoundError(
            "未找到 agent-browser；请先安装: npm i -g agent-browser && agent-browser install"
        )
    return found


def is_available() -> bool:
    """快速判断 agent-browser 后端是否可用（不抛异常）。"""
    try:
        return bool(resolve_binary())
    except FileNotFoundError:
        return False


def _max_wait_sec() -> float:
    return float(os.environ.get("EPUB_WAF_MAX_WAIT_SEC", "180"))


def _headed() -> bool:
    return os.environ.get("AGENT_BROWSER_HEADED", "").strip() in ("1", "true", "yes")


def _cmd_timeout() -> float:
    return float(os.environ.get("AGENT_BROWSER_TIMEOUT", "120"))


def _new_session_name() -> str:
    return f"cnipa-{os.getpid()}-{int(time.time())}"


def _base_args(binary: str, session: str) -> list[str]:
    args = [binary, "--session", session]
    if _headed():
        args.append("--headed")
    return args


def _run(
    binary: str,
    session: str,
    extra: list[str],
    *,
    timeout: float | None = None,
) -> str:
    """执行一条 agent-browser 子命令，返回 stdout 文本；非零退出码抛 RuntimeError。"""
    cmd = _base_args(binary, session) + extra
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout if timeout is not None else _cmd_timeout(),
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            "agent-browser 命令超时 (%.0fs): %s" % ((e.timeout or 0), " ".join(extra))
        ) from e
    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        raise RuntimeError(
            "agent-browser 非零退出 (%d): %s | stderr: %s"
            % (proc.returncode, " ".join(extra), err[:500])
        )
    return proc.stdout


def _wait_for_search_box(binary: str, session: str) -> None:
    """轮询等待首页 #searchStr 出现（WAF 通过的标志）。"""
    limit = _max_wait_sec()
    step = 3.0
    deadline = time.time() + limit
    last_count = -1
    while time.time() < deadline:
        out = _run(binary, session, ["--json", "get", "count", "#searchStr"], timeout=30)
        try:
            data = json.loads(out)
            count = int(_extract_value(data))
        except (ValueError, TypeError):
            count = 0
        last_count = count
        if count >= 1:
            return
        time.sleep(step)
    raise TimeoutError(
        "%ds 内未出现检索框 #searchStr（末次 count=%d）；"
        "可增大 EPUB_WAF_MAX_WAIT_SEC 或设置 AGENT_BROWSER_HEADED=1 人工辅助"
        % (int(limit), last_count)
    )


def _submit_and_settle(binary: str, session: str) -> None:
    """提交 #indexForm，等待结果页安定。"""
    _run(
        binary,
        session,
        ["eval", "document.getElementById('indexForm').submit()"],
        timeout=60,
    )
    # 结果页 load + networkidle（超时则忽略，与 Playwright 后端一致）
    for args, to in ((["wait", "--load", "load"], 30), (["wait", "--load", "networkidle"], 25)):
        try:
            _run(binary, session, args, timeout=to)
        except RuntimeError:
            pass
    try:
        _run(binary, session, ["wait", "800"], timeout=5)
    except RuntimeError:
        pass


def _extract_value(data) -> str:
    """从 eval/get 的 --json 输出里抽字符串值，容忍多种封装形态。"""
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for key in ("value", "result", "data", "count", "text", "html"):
            if key in data:
                return str(data[key])
        # 兜底：取第一个标量字段
        for v in data.values():
            if isinstance(v, (str, int, float)):
                return str(v)
    if isinstance(data, (int, float)):
        return str(data)
    return str(data)


def _get_page_html(binary: str, session: str) -> str:
    """取全页 outerHTML（包成 JSON 字符串再还原，避免换行/引号污染）。"""
    out = _run(
        binary,
        session,
        ["eval", "JSON.stringify(document.documentElement.outerHTML)"],
        timeout=60,
    )
    try:
        data = json.loads(out)
        raw = _extract_value(data)
        # eval 返回的是 JSON.stringify 的结果，可能被 agent-browser 再包一层字符串
        if raw.startswith('"') and raw.endswith('"'):
            return json.loads(raw)
        return raw
    except (json.JSONDecodeError, ValueError):
        # 兜底：直接当作 HTML（部分版本 eval 不带引号）
        return out


def fetch_epub_result_html(keyword: str) -> str:
    """
    用 agent-browser 后端拉取国知局公布站检索结果页 HTML（不解析正文）。
    解析请使用 ``cnipa_epub_parse.parse_search_result_html(html)``。
    """
    binary = resolve_binary()
    session = _new_session_name()

    # 1. 启动 + 导航首页（带桌面 UA，降低自动化指纹）
    _run(
        binary,
        session,
        ["--user-agent", DEFAULT_USER_AGENT, "open", EPUB_BASE],
        timeout=120,
    )
    try:
        # 2. 等待 WAF 通过、检索框出现
        _wait_for_search_box(binary, session)
        # 3. 填关键词
        _run(binary, session, ["fill", "#searchStr", keyword], timeout=30)
        # 4. 提交 + 等结果页安定
        _submit_and_settle(binary, session)
        # 5. 取全页 HTML
        return _get_page_html(binary, session)
    finally:
        try:
            _run(binary, session, ["close"], timeout=15)
        except RuntimeError:
            pass


def search_epub_keyword(keyword: str) -> tuple[str, list]:
    """与 cnipa_epub_crawler.search_epub_keyword 同形：返回 (html, hits)。"""
    from cnipa_epub_parse import parse_search_result_html

    html = fetch_epub_result_html(keyword)
    return html, parse_search_result_html(html)


def _dump_home_debug() -> None:
    """调试：仅拉取首页并保存 WAF 通过后 HTML。"""
    binary = resolve_binary()
    session = _new_session_name()
    _run(binary, session, ["--user-agent", DEFAULT_USER_AGENT, "open", EPUB_BASE])
    try:
        _wait_for_search_box(binary, session)
        html = _get_page_html(binary, session)
        out = Path(__file__).resolve().parent / "_last_home_agent_browser.html"
        out.write_text(html, encoding="utf-8")
        print("已保存:", out)
    finally:
        try:
            _run(binary, session, ["close"], timeout=15)
        except RuntimeError:
            pass


if __name__ == "__main__":
    _ensure_utf8_stdio()
    argv = [a for a in sys.argv[1:] if a.strip()]
    if argv and argv[0] in ("--dump-home", "-d"):
        _dump_home_debug()
        sys.exit(0)
    if not argv:
        print("usage: python tools/cnipa_epub_agent_browser.py <term> [--dump-home|-d]", file=sys.stderr)
        sys.exit(2)
    kw = argv[0].strip()
    try:
        html, hits = search_epub_keyword(kw)
    except Exception as e:
        print("CNIPA_EPUB_ERROR:", e, file=sys.stderr)
        sys.exit(1)
    from cnipa_epub_parse import hits_to_jsonable

    print("结果页长度", len(html), "解析条目数", len(hits), file=sys.stderr, flush=True)
    print("EPUB_HITS_JSON:", json.dumps(hits_to_jsonable(hits), ensure_ascii=False), flush=True)
