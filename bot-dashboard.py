#!/usr/bin/env python3

import json
import requests
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from typing import Any, Callable, List, Tuple, TypeVar

@dataclass
class BotInfo:
    id: int
    name: str
    environment: Literal["staging", "production"]
    description: str

    def get_url(self) -> str:
        if self.environment == "staging":
            base_url = "https://lab.llvm.org/staging"
        elif self.environment == "production":
            base_url = "https://lab.llvm.org/buildbot"
        else:
            raise ValueError("Unknown environment")
        return f"{base_url}/#/builders/{self.id}"

@dataclass
class BuildInfo:
    id: int
    bot: BotInfo
    started_at: int
    result: Literal["pass", "fail", "in_progress", "other"]
    finished_at: int | None

    def get_url(self) -> str:
        return f"{self.bot.get_url()}/builds/{self.id}"

    def get_seconds_since_started(self):
        return int(time.time()) - self.started_at


@dataclass
class BotStatus:
    bot: BotInfo
    in_progress_build: BuildInfo | None
    last_completed_build: BuildInfo | None

def compile_template(template_str: str) -> Callable[..., str]:
    out = []
    indent = 0
    stack = []

    def emit_line(line: str) -> None:
        out.append(f"{'    ' * indent}{line}")

    emit_line("def _render():")
    indent += 1
    emit_line("out = []")

    for line_no, line in enumerate(template_str.splitlines(), start=1):
        if line.startswith("$"):
            pycmd = line[1:].strip()
            keyword = pycmd.partition(" ")[0]
            if keyword == "if":
                stack.append(keyword)
                emit_line(f"{pycmd}:")
                indent += 1
            elif keyword == "for":
                stack.append(keyword)
                emit_line(f"{pycmd}:")
                indent += 1
            elif keyword in ("elif", "else"):
                if stack[-1] != "if":
                    raise ValueError(f"Line {line_no}: Incorrectly nested '{keyword}'")
                indent -= 1
                emit_line(f"{pycmd}:")
                indent += 1
            elif keyword in ("endif", "endfor"):
                expected = stack.pop()
                if expected != keyword[3:]:
                    raise ValueError(
                        f"Line {line_no}: Expected end{expected}, got {pycmd}"
                    )
                if pycmd != keyword:
                    raise ValueError(f"Line {line_no}: Unexpected text after {keyword}")
                indent -= 1
            else:
                emit_line(f"{pycmd}")
            continue

        pos = 0
        while pos <= len(line):
            expr_start = line.find("{{", pos)
            if expr_start == -1:
                emit_line(f"out.append({repr(line[pos:])} '\\n')")
                break
            if expr_start != pos:
                emit_line(f"out.append({repr(line[pos:expr_start])})")
            expr_end = line.find("}}", expr_start)
            if expr_end == -1:
                raise ValueError(f"Line {line_no}: Couldn't find matching }}")
            emit_line(f"out.append(str({line[expr_start + 2 : expr_end]}))")
            pos = expr_end + 2
    if len(stack) != 0:
        raise ValueError(f"Unclosed '{stack[-1]}'")
    emit_line('return "".join(out)')
    py_code = "\n".join(out)
    compiled_code = compile(py_code, "<string>", "exec")

    def wrapper(**kwargs_as_globals: Any) -> str:
        exec(compiled_code, kwargs_as_globals)
        return kwargs_as_globals["_render"]()  # type: ignore

    return wrapper

def seconds_to_readable(seconds):
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    remaining_minutes = minutes % 60
    return f"{hours}h{remaining_minutes}m"

def timestamp_to_readable(timestamp):
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')

template_str=\
"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RISC-V LLVM CI status</title>
    <style>
        :root {
            --color-text: #000000;
            --color-text-secondary: #4b5563;
            --color-background: #ffffff;
            --color-border: #e5e7eb;
            --color-hover: #f9fafb;
            --font-mono: monospace;
            --font-sans: Cantarell, -apple-system, "Segoe UI", Roboto, sans-serif;
        }

        *, *::before, *::after {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        html, body {
            font-family: var(--font-sans);
            color: var(--color-text);
            background-color: var(--color-background);
            line-height: 1.5;
        }

        body {
            max-width: 900px;
            margin: 0 auto;
            padding: 2rem 1rem;
        }

        h1 {
            font-size: 1.5rem;
            font-weight: 600;
            margin-bottom: 1.5rem;
        }

        a {
            color:inherit;
            text-decoration:underline;
            text-decoration-color:#aaa;
            text-underline-offset:.15em;
        }
        a:hover {
            text-decoration-thickness:2px;
        }
        .build-number {
            font-family: var(--font-mono);
            font-size: 0.875rem;
        }

        .text-secondary {
            color: var(--color-text-secondary);
            font-size: 0.875rem;
        }

        .dashboard {
            width: 100%;
            overflow-x: auto;
            margin: 1.5rem 0;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.875rem;
            table-layout: fixed;
        }

        th {
            font-weight: 600;
            text-align: left;
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--color-border);
            overflow-wrap: break-word;
        }

        td {
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--color-border);
            vertical-align: top;
            overflow-wrap: break-word;
        }

        tr:hover {
            background-color: var(--color-hover);
        }

        .status-pass::before,
        .status-fail::before,
        .status-in_progress::before,
        .status-other::before {
            content: "";
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 0.5rem;
        }
        .status-pass::before {
            background-color: #10b981;
        }
        .status-fail::before {
            background-color: #ef4444;
        }
        .status-in_progress::before {
            background-color: #f59e0b;
        }
        .status-other::before {
            background-color: #ec4899;
        }
        summary {
            cursor: pointer;
        }
        footer {
            margin-top: 1.5rem;
        }
        .little-logo {
            max-height: 1em;
            vertical-align: middle;
            margin-left: 0.1em;
        }
        code {
            font-family: var(--font-mono);
        }
    </style>
</head>
<body>
    <h1>RISC-V LLVM CI status</h1>
    <p class="text-secondary">Generated at {{timestamp_to_readable(time.time())}}. Updated approximately every 20 minutes.</p>

    <div class="dashboard">
        <table>
            <thead>
                <tr>
                    <th>Bot</th>
                    <th>In progress build</th>
                    <th>Previous build</th>
                </tr>
            </thead>
            <tbody>
$ for bot_status in bot_statuses
                <tr>
                    <td>
                      <a href="{{bot_status.bot.get_url()}}">{{bot_status.bot.name}}</a>
                      <details class="text-secondary">
                        <summary>Info</summary>
                        {{bot_status.bot.description}}. Results reported to the {{bot_status.bot.environment}} buildbot coordinator.
                      </details>
                     </td>
$ if bot_status.in_progress_build
                    <td>
                        <span class="status-in_progress build-number"><a href="{{bot_status.in_progress_build.get_url()}}">#{{bot_status.in_progress_build.id}}</a></span>
                    <div class="text-secondary">{{seconds_to_readable(bot_status.in_progress_build.get_seconds_since_started())}} ago</div>
                    </td>
$ else
                    <td></td>
$ endif
                    <td>
$ if bot_status.last_completed_build
                        <div class="status-{{bot_status.last_completed_build.result}} build-number"><a href="{{bot_status.last_completed_build.get_url()}}">#{{bot_status.last_completed_build.id}}</a></div>
                        <div class="text-secondary">{{seconds_to_readable(bot_status.last_completed_build.finished_at - bot_status.last_completed_build.started_at)}} · {{timestamp_to_readable(bot_status.last_completed_build.finished_at)}}</div>
$ endif
                    </td>
                </tr>
$ endfor
            </tbody>
        </table>
    </div>
    <footer class="text-secondary">
    This dashboard and the <code>clang-*</code> bots operated by <a href="https://www.igalia.com/">Igalia<img src="igalia.svg" class="little-logo"></a>, supported by <a href="https://riseproject.dev/">RISE<img src="rise.svg" class="little-logo"></a>.</p>
</body>
</html>
"""

riscv_bots = [
BotInfo(87, "clang-riscv-rva20-2stage", "production", "Cross-compiled Clang, from x86_64 host to RVA20, with check-all and llvm-test-suite running under qemu-system"),
BotInfo(132, "clang-riscv-rva23-evl-vec-2stage", "production", "Cross-compiled Clang, from x86_64 host to RVA23 (with evl tail folding force enabled), with check-all and llvm-test-suite running under qemu-system"),
BotInfo(26, "clang-riscv-rva23-2stage", "staging", "RVA23 clang two-stage bootstrap and check-all running fully in qemu-system"),
BotInfo(188, "libc-riscv64-debian-dbg", "production", "LLVM libc RV64 build and tests running on physical hardware"),
BotInfo(183, "libc-riscv64-debian-fullbuild-dbg", "production", "LLVM libc RV64 build and tests running on physical hardware"),
BotInfo(196, "libc-riscv32-qemu-yocto-fullbuild-dbg", "production", "LLVM libc RV32 build and tests running by transferring each test to a Yocto build on qemu-system emulating RV32")
]

def get_bot_builds(bot):
    if bot.environment == "staging":
        buildbot_url = "https://lab.llvm.org/staging"
    elif bot.environment == "production":
        buildbot_url = "https://lab.llvm.org/buildbot"
    url = f"{buildbot_url}/api/v2/builders/{bot.name}/builds?limit=2&order=-number"
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for 4XX/5XX responses
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return None

def build_data_to_build_info(bot, build_data):
    build_id = build_data.get('number')
    started_at = int(build_data.get('started_at'))

    # See <https://buildbot.readthedocs.io/en/latest/developer/results.html>
    results = build_data.get('results')
    if results is None:
        result = "in_progress"
    elif results == 0 or results == 1:
        result = "pass"
    elif results == 2:
        result = "fail"
    else:
        result = "other"

    # Check if the build has finished
    finished_at = build_data.get('complete_at')
    if finished_at is not None:
        finished_at = int(finished_at)

    return BuildInfo(build_id, bot, started_at, result, finished_at)

def get_bot_status(bot, builds_data):
    if not builds_data or len(builds_data) == 0:
        return BotStatus(bot, None, None)

    build_info_0 = build_data_to_build_info(bot, builds_data[0])

    if len(builds_data) == 1:
        if build_info_0.result == "in_progress":
            return BotStatus(bot, build_info_0, None)
        else:
            return BotStatus(bot, None, build_info_0)
    build_info_1 = build_data_to_build_info(bot, builds_data[1])
    if build_info_0.result == "in_progress":
        return BotStatus(bot, build_info_0, build_info_1)
    else:
        return BotStatus(bot, None, build_info_0)

bot_statuses = [get_bot_status(bot, get_bot_builds(bot)['builds']) for bot in riscv_bots]
print(compile_template(template_str)(bot_statuses=bot_statuses, seconds_to_readable=seconds_to_readable, timestamp_to_readable=timestamp_to_readable, time=time))
