#!/usr/bin/env python3
"""校验 requirements.txt 与 pyproject.toml 的依赖是否同步。

依赖以 pyproject.toml 为准，requirements.txt 由其生成（对齐当前 venv 版本）。
CI / 本地在改依赖后运行：

    venv/bin/python scripts/check_requirements_sync.py

不同步时退出码非 0。
"""
import os
import re
import sys
import tomllib

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PYPROJECT = os.path.join(PROJECT_ROOT, "pyproject.toml")
REQUIREMENTS = os.path.join(PROJECT_ROOT, "requirements.txt")

_NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.\-]*)")


def _canonical(name: str) -> str:
    return name.lower().replace("_", "-")


def _base_name(spec: str) -> str | None:
    spec = spec.strip()
    if not spec or spec.startswith("#"):
        return None
    m = _NAME_RE.match(spec)
    return _canonical(m.group(1)) if m else None


def project_dependencies() -> set[str]:
    with open(PYPROJECT, "rb") as f:
        data = tomllib.load(f)
    specs = list(data["project"].get("dependencies", []))
    for group in data["project"].get("optional-dependencies", {}).values():
        specs.extend(group)
    result = set()
    for spec in specs:
        name = _base_name(spec)
        # 跳过项目自引用（如 weibo[test,dev]）
        if name and name != "weibo":
            result.add(name)
    return result


def requirements_dependencies() -> set[str]:
    result = set()
    with open(REQUIREMENTS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            name = _base_name(line)
            if name:
                result.add(name)
    return result


def main() -> int:
    pyproject_deps = project_dependencies()
    requirements_deps = requirements_dependencies()

    only_requirements = sorted(requirements_deps - pyproject_deps)
    only_pyproject = sorted(pyproject_deps - requirements_deps)

    failed = False
    if only_pyproject:
        failed = True
        print("[FAIL] pyproject.toml 有、requirements.txt 缺失：")
        for name in only_pyproject:
            print(f"  - {name}")
    if only_requirements:
        failed = True
        print("[FAIL] requirements.txt 有、pyproject.toml 未声明（可能已废弃）：")
        for name in only_requirements:
            print(f"  - {name}")

    if failed:
        print("\n请改 pyproject.toml 后同步生成 requirements.txt。")
        return 1

    print(f"[OK] requirements.txt 与 pyproject.toml 同步（共 {len(pyproject_deps)} 个依赖）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
