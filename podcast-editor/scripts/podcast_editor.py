#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

if sys.version_info < (3, 10):
    print("剪播客需要 Python 3.10 或更高版本。", file=sys.stderr)
    raise SystemExit(1)

from podcast_editor.errors import PodcastEditorError
from podcast_editor.contracts import ApiStateUpdate, project_word_ids
from podcast_editor.storage import read_json
from podcast_editor.server import create_server
from podcast_editor.storage import ProjectStore
from podcast_editor.workflow import prepare_project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="转录播客、审核口误并生成剪映草稿。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="转录音频并建立审核项目")
    prepare.add_argument("--input", action="append", required=True, help="音频路径；多人分轨时重复传入")
    prepare.add_argument("--workdir", help="工作目录；未指定时写入桌面 output 目录")

    serve = subparsers.add_parser("serve", help="启动本地审核页")
    serve.add_argument("--project", required=True, help="包含 project.json 的工作目录")
    serve.add_argument("--draft-root", help="剪映草稿根目录；也可设置 JY_PROJECTS_ROOT")
    serve.add_argument("--port", type=int, default=0, help="监听端口；0 表示自动选择")
    serve.add_argument("--no-open", action="store_true", help="不自动打开浏览器")

    seed = subparsers.add_parser("seed-selection", help="把 Codex 预选的口误写入审核项目")
    seed.add_argument("--project", required=True, help="包含 project.json 的工作目录")
    seed.add_argument("--word-id", action="append", default=[], help="要预选的词条 ID；可重复传入")
    seed.add_argument("--from-json", help="包含 ID 数组或 selectedWordIds 字段的 JSON 文件")
    seed.add_argument("--mode", choices=("replace", "merge"), default="replace", help="替换或合并已有预选")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            store = prepare_project(args.input, args.workdir)
            print(json.dumps({"projectPath": str(store.root)}, ensure_ascii=False))
            return 0

        if args.command == "seed-selection":
            store = ProjectStore(Path(args.project))
            project = store.load_project()
            state = store.load_state(project)
            selected = list(args.word_id)
            if args.from_json:
                loaded = read_json(Path(args.from_json).expanduser().resolve())
                if isinstance(loaded, dict):
                    loaded = loaded.get("selectedWordIds")
                if not isinstance(loaded, list) or any(not isinstance(item, str) for item in loaded):
                    raise PodcastEditorError("invalid_selection_file", "预选 JSON 必须是词条 ID 数组，或包含 selectedWordIds。")
                selected.extend(loaded)
            if args.mode == "merge":
                selected = [*state["selectedWordIds"], *selected]
            selected = list(dict.fromkeys(selected))
            unknown = sorted(set(selected) - project_word_ids(project))
            if unknown:
                raise PodcastEditorError("unknown_words", "预选中包含未知词条。", details=unknown)
            saved = store.update_state(
                ApiStateUpdate(
                    state["revision"],
                    selected,
                    dict(state["speakerNames"]),
                    dict(state["speakerOverrides"]),
                )
            )
            print(json.dumps({"revision": saved["revision"], "selectedWordIds": saved["selectedWordIds"]}, ensure_ascii=False))
            return 0

        store = ProjectStore(Path(args.project))
        store.load_project()
        server = create_server(
            store,
            port=args.port,
            draft_root=args.draft_root,
        )
        host, port = server.server_address[:2]
        url_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
        url = f"http://{url_host}:{port}/"
        print(f"审核页：{url}")
        if not args.no_open:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    except PodcastEditorError as exc:
        print(json.dumps(exc.as_dict(), ensure_ascii=False), file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError) as exc:
        error = PodcastEditorError("invalid_input", str(exc))
        print(json.dumps(error.as_dict(), ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
