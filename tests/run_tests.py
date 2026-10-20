#!/usr/bin/env python3
"""Тесты kb-tools: фикстурная база с заведомо битыми заметками.
Запуск: python3 tests/run_tests.py  (exit 0 = все прошли)."""
import os, shutil, subprocess, sys, tempfile, json

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(HERE, "..", "bin")
FAILS = []


def check(name, cond, extra=""):
    print(("ok    " if cond else "FAIL  ") + name + (("  " + extra) if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def make_vault(d):
    for sub in ["reference/hubs", "journal", "skills", "profile", "templates",
                "inbox/telegram", "archive/_raw", "_maintenance", "bases"]:
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    W = lambda rel, s: open(os.path.join(d, rel), "w").write(s)
    W("AGENTS.md", "---\ncreated: 2026-08-02\nsource: system\nauthor: claude\ntags: [meta]\nstatus: active\n---\n# AGENTS\n")
    W("INDEX.md", "---\ncreated: 2026-08-02\nsource: system\nauthor: claude\ntags: [meta]\nstatus: active\n---\n# INDEX\n[[good-note]] [[hub-x]]\n")
    W("hot.md", "---\ncreated: 2026-08-02\nsource: system\nauthor: claude\ntags: [meta]\nstatus: active\n---\n# hot\n[[2026-08-02-episode-one]]\n")
    W("templates/note.md", "---\ncreated: {{date}}\nsource:\nauthor:\ntags: []\nstatus: active\n---\n# {{title}}\n")
    # валидные
    W("reference/good-note.md", "---\ncreated: 2026-08-01\nsource: test\nauthor: claude\ntags: [a]\nstatus: active\n---\n# ok\n[[hub-x]]\n")
    W("reference/hubs/hub-x.md", "---\ncreated: 2026-08-01\nsource: test\nauthor: claude\ntags: [hub]\nstatus: active\n---\n# hub\n[[good-note]]\n![[x.base]]\n")
    W("bases/x.base", "views: []\n")
    W("templates/review.md", "---\ncreated: {{date}}\nsource:\nauthor:\ntags: [review]\nstatus: active\nstage: review\nurl:\nhub:\n---\n# {{title}}\n")
    # канал Telegram: проверяется, но сиротство не считается
    W("inbox/telegram/good-review.md", "---\ncreated: 2026-10-21\nsource: telegram\nauthor: claude\ntags: [review]\nstatus: active\nbasis: web\nhub: \"[[hub-x]]\"\n---\n# r\n")
    W("journal/2026-08-02-episode-one.md", "---\ncreated: 2026-08-02\nsource: test\nauthor: claude\ntags: [episode]\nstatus: active\n---\n# ep\n[[hub-x]]\n")
    # inbox освобождён от проверок
    W("inbox/raw-garbage.md", "no frontmatter at all")
    return d


def main():
    tmp = tempfile.mkdtemp(prefix="kbtest-")
    try:
        d = make_vault(tmp)
        env = dict(os.environ, KB_ROOT=d)

        r = run([sys.executable, os.path.join(BIN, "kb-lint"), "--root", d, "--json"])
        check("чистая база: exit 0", r.returncode == 0, r.stdout + r.stderr)
        data = json.loads(r.stdout)
        check("чистая база: 0 ошибок", data["errors"] == [], str(data["errors"]))
        check("вложение ![[x.base]] резолвится", not any(e["code"] == "E6" for e in data["errors"]))
        check("inbox/telegram проверяется (7 заметок, сырьё inbox/ не в счёт)", data["checked"] == 7, str(data["checked"]))
        check("inbox/telegram: сирота без W1",
              not any(w["file"] == "inbox/telegram/good-review.md" and w["code"] == "W1" for w in data["warnings"]),
              str(data["warnings"]))

        # E1: нет шапки
        open(os.path.join(d, "reference/bad1.md"), "w").write("# без шапки\n[[hub-x]]\n")
        # E2/E4: нет поля + плохой статус
        open(os.path.join(d, "reference/bad2.md"), "w").write(
            "---\ncreated: 2026-08-01\nauthor: x\ntags: [a]\nstatus: wrong\n---\n[[hub-x]]\n")
        # E3: дата
        open(os.path.join(d, "reference/bad3.md"), "w").write(
            "---\ncreated: 01.08.2026\nsource: t\nauthor: x\ntags: [a]\nstatus: active\n---\n[[hub-x]]\n")
        # E6: битая ссылка
        open(os.path.join(d, "reference/bad4.md"), "w").write(
            "---\ncreated: 2026-08-01\nsource: t\nauthor: x\ntags: [a]\nstatus: active\n---\n[[net-takogo]]\n")
        # E7: имя в journal
        open(os.path.join(d, "journal/wrongname.md"), "w").write(
            "---\ncreated: 2026-08-01\nsource: t\nauthor: x\ntags: [a]\nstatus: active\n---\n[[hub-x]]\n")
        # E8: basis вне словаря; W5: basis model в reference/
        open(os.path.join(d, "reference/bad5.md"), "w").write(
            "---\ncreated: 2026-08-01\nsource: t\nauthor: x\ntags: [a]\nstatus: active\nbasis: guess\n---\n[[hub-x]]\n")
        open(os.path.join(d, "reference/model-note.md"), "w").write(
            "---\ncreated: 2026-08-01\nsource: t\nauthor: x\ntags: [a]\nstatus: active\nbasis: model\n---\n[[hub-x]]\n")

        # канал Telegram: битая шапка ловится, сырьё в корне inbox/ — нет
        open(os.path.join(d, "inbox/telegram/bad-review.md"), "w").write("без шапки\n[[hub-x]]\n")

        r = run([sys.executable, os.path.join(BIN, "kb-lint"), "--root", d, "--json"])
        data = json.loads(r.stdout)
        codes = {e["code"] for e in data["errors"]}
        check("битая база: exit 1", r.returncode == 1)
        check("inbox/telegram: ловит E1",
              any(e["file"] == "inbox/telegram/bad-review.md" and e["code"] == "E1" for e in data["errors"]))
        check("inbox/ (корень) по-прежнему освобождён",
              not any(e["file"].startswith("inbox/raw") for e in data["errors"]))
        for c in ["E1", "E2", "E3", "E4", "E6", "E7", "E8"]:
            check("ловит " + c, c in codes, str(sorted(codes)))
        wcodes = {w["code"] for w in data["warnings"]}
        check("ловит W5 (basis: model в reference/)", "W5" in wcodes, str(sorted(wcodes)))
        # --file проверяет только один файл
        r = run([sys.executable, os.path.join(BIN, "kb-lint"), "--root", d,
                 "--file", os.path.join(d, "reference/good-note.md"), "--json"])
        data = json.loads(r.stdout)
        check("--file: чистый файл в грязной базе -> 0 ошибок", r.returncode == 0, r.stdout)

        # kb-new
        r = run([sys.executable, os.path.join(BIN, "kb-new"), "note", "Тестовая заметка про сервер",
                 "--tags", "test,server", "--author", "claude", "--json"], env=env)
        check("kb-new: exit 0", r.returncode == 0, r.stderr)
        rel = json.loads(r.stdout)["created"]
        check("kb-new: транслит имени", rel == "reference/testovaya-zametka-pro-server.md", rel)
        text = open(os.path.join(d, rel)).read()
        check("kb-new: author заполнен", "author: claude" in text)
        check("kb-new: tags заполнены", "tags: [test, server]" in text)
        fm_ok = run([sys.executable, os.path.join(BIN, "kb-lint"), "--root", d,
                     "--file", os.path.join(d, rel), "--json"])
        errs = json.loads(fm_ok.stdout)["errors"]
        check("kb-new -> kb-lint: шапка валидна", errs == [], str(errs))
        # kb-new --basis вставляет поле
        r = run([sys.executable, os.path.join(BIN, "kb-new"), "note", "Basis check", "--basis", "web", "--json"], env=env)
        rel2 = json.loads(r.stdout)["created"]
        check("kb-new --basis вставляет поле", "basis: web" in open(os.path.join(d, rel2)).read())
        # автор по умолчанию: .kb.toml базы, если нет --author и $KB_AUTHOR
        open(os.path.join(d, ".kb.toml"), "w").write('author = "Owner Test"\n')
        env_noauthor = {k: v for k, v in env.items() if k != "KB_AUTHOR"}
        r = run([sys.executable, os.path.join(BIN, "kb-new"), "note", "Автор из конфига", "--json"], env=env_noauthor)
        rel4 = json.loads(r.stdout)["created"]
        check("kb-new: author из .kb.toml", "author: Owner Test" in open(os.path.join(d, rel4)).read())
        r = run([sys.executable, os.path.join(BIN, "kb-new"), "note", "Автор из окружения", "--json"],
                env=dict(env_noauthor, KB_AUTHOR="EnvAuthor"))
        rel5 = json.loads(r.stdout)["created"]
        check("kb-new: $KB_AUTHOR важнее .kb.toml", "author: EnvAuthor" in open(os.path.join(d, rel5)).read())
        # kb-new review -> inbox/telegram/, имя без даты (переезд в reference/ без переименования)
        r = run([sys.executable, os.path.join(BIN, "kb-new"), "review", "Проект some-agent",
                 "--author", "claude", "--basis", "web", "--source", "telegram", "--json"], env=env)
        rel3 = json.loads(r.stdout)["created"]
        check("kb-new review -> inbox/telegram/", rel3 == "inbox/telegram/proekt-some-agent.md", rel3)
        txt3 = open(os.path.join(d, rel3)).read()
        check("kb-new review: stage из шаблона", "stage: review" in txt3)
        # dry-run ничего не создаёт
        r = run([sys.executable, os.path.join(BIN, "kb-new"), "episode", "Проверка", "--dry-run", "--json"], env=env)
        would = json.loads(r.stdout)["would_create"]
        check("kb-new --dry-run не создаёт файл", not os.path.exists(os.path.join(d, would)), would)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n%s: %d провалов" % ("FAIL" if FAILS else "PASS", len(FAILS)))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
