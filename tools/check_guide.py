"""Lint the Korean guide: personal values, broken relative links, unescaped table pipes."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGETS = [ROOT / "guide", ROOT / "README.md"]

FORBIDDEN = [
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "GUID(구독·테넌트·개체 ID)"),
    (re.compile(r"MngEnvMCAP\d+", re.I), "테넌트 도메인"),
    (re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+"), "UPN·이메일 주소"),
    # Windows az.cmd drops inner double quotes from PowerShell arguments.
    (re.compile(r"--query\s+'[^']*\""), "PowerShell에서 깨지는 --query 인용('\"...\"')"),
]
LINK = re.compile(r"\]\(([^)\s]+)\)")
CODE_SPAN = re.compile(r"`[^`]*`")


def _unescaped_pipe_in_code(line: str) -> bool:
    return any(re.search(r"(?<!\\)\|", span) for span in CODE_SPAN.findall(line))


def check_file(path: Path) -> list[str]:
    errors = []
    in_fence = False
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        for pattern, label in FORBIDDEN:
            if pattern.search(line):
                errors.append(f"{path}:{no}: {label} 노출")
        if in_fence:
            continue
        if line.lstrip().startswith("|") and _unescaped_pipe_in_code(line):
            errors.append(f"{path}:{no}: 표 셀의 코드 안에 이스케이프되지 않은 '|'")
        for target in LINK.findall(line):
            if re.match(r"^[a-z]+:", target, re.I) or target.startswith("#"):
                continue
            rel = target.split("#", 1)[0]
            if rel and not (path.parent / rel).exists():
                errors.append(f"{path}:{no}: 깨진 링크 {target}")
    return errors


def _iter_files(targets):
    for t in targets:
        t = Path(t)
        if t.is_dir():
            yield from sorted(t.rglob("*.md"))
        elif t.exists():
            yield t


def main(argv) -> int:
    targets = argv or DEFAULT_TARGETS
    errors = [e for f in _iter_files(targets) for e in check_file(f)]
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
