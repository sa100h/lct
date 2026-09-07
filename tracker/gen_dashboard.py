"""NicePlan: генерирует kanban-сводку + burndown из tracker/tasks/*.md.

Использование:  python3 tracker/gen_dashboard.py
Переопределяет раздел между маркерами <!-- NICEPLAN:BOARD --> в README.md.

Задачи — markdown-файлы с TOML-подобным frontmatter:
    id; title; column; points; assignee; due; tags
Таблица разметки задаётся в COLUMNS (порядок колонок канбана).
"""
import re
import tomllib
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "tracker" / "config.toml"

# Порядок колонок канбана (Gitscrum-модель: Backlog → To Do → In Progress → Review → Done)
COLUMNS = ["Backlog", "To Do", "In Progress", "Review", "Done"]
STATUS_ICON = {
    "Done": "✅", "Review": "🔎", "In Progress": "🔨",
    "To Do": "📋", "Backlog": "🗃️",
}
COLUMN_LABEL = {
    "Backlog": "Backlog", "To Do": "To Do", "In Progress": "In Progress",
    "Review": "Review", "Done": "Done",
}

FM_RE = re.compile(r"^\s*id:\s*(?P<id>\S+?)\s*;\s*title:\s*(?P<title>.*?)\s*;\s*"
                   r"column:\s*(?P<column>.*?)\s*;\s*points:\s*(?P<points>\d+)\s*;\s*"
                   r"assignee:\s*(?P<assignee>.*?)\s*;\s*due:\s*(?P<due>.*?)\s*;\s*"
                   r"tags:\s*(?P<tags>.*?)\s*$", re.MULTILINE)


def load_tasks(tasks_path: Path):
    tasks = []
    for f in sorted(tasks_path.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        m = FM_RE.search(text)
        if not m:
            print(f"  ! без frontmatter: {f.name} — пропущен")
            continue
        t = m.groupdict()
        t["file"] = f.name
        t["points"] = int(t["points"])
        tasks.append(t)
    return tasks


def load_config():
    with open(CFG, "rb") as fh:
        return tomllib.load(fh)


def points_by_column(tasks, cols):
    agg = {c: 0 for c in cols}
    for t in tasks:
        c = t["column"]
        if c in agg:
            agg[c] += t["points"]
    return agg


def burndown(cfg, tasks, today=None):
    """Простой burndown по спринту: пройдено/осталось по дням таймбокса."""
    sp = cfg.get("sprint", {})
    if not sp:
        return ""
    start = datetime.date.fromisoformat(sp["start"])
    dur = int(sp.get("duration_days", 7))
    cap = int(sp.get("capacity_points", 0))
    if today is None:
        today = datetime.date.today()
    done = sum(t["points"] for t in tasks if t["column"] == "Done")
    total = sum(t["points"] for t in tasks)
    left = total - done
    elapsed = (today - start).days
    elapsed = max(0, min(elapsed, dur))
    ideal = cap * (1 - elapsed / dur) if dur else 0
    width = 16
    def bar(v):
        f = max(0, min(1, v))
        filled = round(f * width)
        return "█" * filled + "░" * (width - filled)
    lines = [
        f"**{sp['name']}** — {sp.get('state', '?')}",
        "",
        f"| День | Прошло дней | Осталось (факт) | Идеальный курс |",
        f"|---|---|---|---|",
        f"| | {elapsed}/{dur} | {left} pts {bar(left / cap if cap else 0)} | {bar(ideal / cap if cap else 0)} |",
        "",
        f"Готово: **{done}/{total}** pts из скоупа задач. Ёмкость спринта: {cap} pts.",
    ]
    return "\n".join(lines)


def render_board(tasks, cfg):
    out = ["<!-- NICEPLAN:BOARD -->", ""]
    out.append(f"# 📋 NicePlan — {cfg.get('project_name', 'планирование')}")
    out.append("")
    out.append("> Git-native планирование в стиле [GitScrum](https://docs.gitscrum.com/en): "
               "задачи — markdown-файлы, статусы — в `tracker/tasks/`, этот раздел "
               "автогенерируется из них. Сменил задачу → `gen_dashboard.py` → коммит.")
    out.append("")
    # Покопонная сводка
    agg = points_by_column(tasks, COLUMNS)
    chips = "  ".join(
        f"{STATUS_ICON[c]} **{COLUMN_LABEL[c]}** {agg[c]} pts"
        for c in COLUMNS
    )
    out.append(chips)
    out.append("")
    # Канбан-таблица
    out.append("| " + " | ".join(COLUMN_LABEL[c] for c in COLUMNS) + " |")
    out.append("|" + "---|" * len(COLUMNS))
    by_col = {c: [] for c in COLUMNS}
    for t in tasks:
        by_col.setdefault(t["column"], []).append(t)
    for c in COLUMNS:
        rows = sorted(by_col[c], key=lambda x: x["id"])
        cells = [f"{STATUS_ICON[x['column']]} `{x['id']}` {x['title']}  \n"
                 f"_{x['points']} pt · {x['assignee']} · {x['due']}_"
                 for x in rows] or ["_—_"]
        out.append("| " + " | ".join(cells) + " |")
    out.append("")
    # Burndown
    out.append("## ⏳ Burndown")
    out.append("")
    bd = burndown(cfg, tasks)
    out.append(bd if bd else "_Спринт не задан в `tracker/config.toml`._")
    out.append("")
    # Хакатон
    hh = cfg.get("hackathon", {})
    if hh:
        ddl = hh.get("deadline")
        left_days = (datetime.date.fromisoformat(ddl) - datetime.date.today()).days if ddl else "?"
        out.append(f"## 🏁 Хакатон: **{hh.get('event','')}**")
        out.append("")
        out.append(f"Дедлайн: {ddl} — осталось **{left_days}** дн. "
                   f"Продвижение отмечай в колонках и держи `LCT-12` живым.")
        out.append("")
    out.append("<!-- NICEPLAN:/BOARD -->")
    return "\n".join(out)


def main():
    cfg = load_config()
    tasks_path = ROOT / cfg.get("tasks_path", "tracker/tasks")
    tasks = load_tasks(tasks_path)
    board = render_board(tasks, cfg)

    readme = ROOT / "README.md"
    old = readme.read_text(encoding="utf-8") if readme.exists() else ""
    block_re = re.compile(
        r"<!-- NICEPLAN:BOARD -->.*?<!-- NICEPLAN:/BOARD -->", re.S)
    if block_re.search(old):
        new = block_re.sub(lambda _: board, old)
    else:
        new = (old.rstrip() + "\n\n" + board + "\n") if old else board + "\n"
    readme.write_text(new, encoding="utf-8")
    print(f"README.md обновлён: {len(tasks)} задач, {readme}")


if __name__ == "__main__":
    main()
