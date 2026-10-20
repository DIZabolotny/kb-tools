"""kbcore — общий парсер и правила базы знаний (KnowledgeBase).

Единственное место, где закодировано «понимание» формата заметки:
YAML-шапка, wiki-ссылки, конвенции имён, области проверки.
"""
import os
import re
import sys
import datetime

REQUIRED_FIELDS = ["created", "source", "author", "tags", "status"]
VALID_STATUS = {"active", "outdated", "archived"}
VALID_BASIS = {"base", "web", "document", "capture", "model"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTH_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")
JOURNAL_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md$")
LATIN_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
WIKILINK_RE = re.compile(r"!?\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")

# Папки/файлы, освобождённые от проверок (сырьё, шаблоны, служебное)
EXEMPT_DIRS = {"inbox", "templates", "_to_delete", ".git", ".obsidian", ".trash", "bases"}
EXEMPT_UNDER = [os.path.join("archive", "_raw")]
EXEMPT_FILES = {"_about.md", "CLAUDE.md", "GEMINI.md", ".gitignore"}
# Мета-файлы корня: шапка проверяется, сиротство — нет
META_FILES = {"AGENTS.md", "INDEX.md", "hot.md", "friction.md", "gaps.md"}
# Подпапки освобождённых папок, которые всё же проверяются: автоматические
# каналы пишут туда готовые заметки (канал Telegram). Сиротство здесь не
# проверяется — это зона «на изучении», хаб показывает её через Base.
LINTED_SUBDIRS = ["inbox/telegram"]


def in_linted_subdir(relpath):
    rel = relpath.replace("\\", "/")
    return any(rel.startswith(sub + "/") for sub in LINTED_SUBDIRS)


CONFIG_FILE = ".kb.toml"


def read_config(root):
    """Настройки базы из <root>/.kb.toml (например, author = "Имя"). Нет файла -> {}."""
    path = os.path.join(root, CONFIG_FILE)
    if not os.path.isfile(path):
        return {}
    with open(path, "rb") as f:
        raw = f.read()
    try:
        import tomllib
        return tomllib.loads(raw.decode("utf-8"))
    except ImportError:  # Python < 3.11: только плоские строки key = "value"
        out = {}
        for ln in raw.decode("utf-8").splitlines():
            m = re.match(r'^\s*([A-Za-z_][\w-]*)\s*=\s*"([^"]*)"\s*$', ln)
            if m:
                out[m.group(1)] = m.group(2)
        return out


def find_root(start=None):
    """Корень базы: --root > $KB_ROOT > подъём от start/cwd до папки с AGENTS.md."""
    env = os.environ.get("KB_ROOT")
    if env and os.path.isfile(os.path.join(env, "AGENTS.md")):
        return os.path.abspath(env)
    d = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isfile(os.path.join(d, "AGENTS.md")) and os.path.isdir(os.path.join(d, "reference")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def is_exempt(relpath):
    parts = relpath.replace("\\", "/").split("/")
    if os.path.basename(relpath) in EXEMPT_FILES:
        return True
    if in_linted_subdir(relpath):
        return False
    if parts[0] in EXEMPT_DIRS:
        return True
    for ex in EXEMPT_UNDER:
        if relpath.startswith(ex.replace("\\", "/")):
            return True
    if os.path.basename(relpath) in EXEMPT_FILES:
        return True
    if os.path.basename(relpath).startswith(".tmp"):
        return True
    return False


def _keep_dir(parts, d):
    """Спускаться ли в папку d: освобождённые пропускаем, кроме путей к LINTED_SUBDIRS."""
    path = "/".join(parts + [d])
    if any(sub == path or sub.startswith(path + "/") or path.startswith(sub + "/") for sub in LINTED_SUBDIRS):
        return True
    return d not in EXEMPT_DIRS and not (parts == ["archive"] and d == "_raw")


def iter_notes(root):
    """Все .md базы, подлежащие проверке. -> [(relpath, abspath)]"""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        parts = [] if rel_dir == "." else rel_dir.replace("\\", "/").split("/")
        dirnames[:] = [d for d in dirnames if _keep_dir(parts, d)]
        for fn in filenames:
            if not fn.endswith(".md"):
                continue
            rel = fn if rel_dir == "." else rel_dir.replace("\\", "/") + "/" + fn
            if is_exempt(rel):
                continue
            out.append((rel, os.path.join(dirpath, fn)))
    return sorted(out)


def parse_frontmatter(text):
    """Мини-парсер плоской YAML-шапки (без внешних зависимостей).
    -> (dict | None, error | None). Поддержка: строки, списки [a, b], кавычки."""
    if not text.startswith("---"):
        return None, "нет YAML-шапки (файл должен начинаться с ---)"
    end = text.find("\n---", 3)
    if end == -1:
        return None, "шапка не закрыта (нет второго ---)"
    body = text[3:end]
    data = {}
    for ln in body.splitlines():
        if not ln.strip() or ln.strip().startswith("#"):
            continue
        if ln.startswith((" ", "\t")):
            return None, "вложенный YAML не поддерживается схемой: %r" % ln.strip()
        if ":" not in ln:
            return None, "строка шапки без двоеточия: %r" % ln.strip()
        key, _, val = ln.partition(":")
        key = key.strip()
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            items = [v.strip().strip('"\'') for v in inner.split(",")] if inner else []
            data[key] = [i for i in items if i]
        else:
            data[key] = val.strip('"\'')
    return data, None


FENCED_RE = re.compile(r"```.*?```", re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def strip_code(text):
    """Убирает fenced-блоки и inline-код: ссылки-примеры в документации — не ссылки."""
    return INLINE_CODE_RE.sub("", FENCED_RE.sub("", text))


def extract_wikilinks(text):
    """Цели wiki-ссылок без секций и алиасов; хвост .md отрезается.
    Код-блоки игнорируются."""
    targets = []
    for m in WIKILINK_RE.finditer(strip_code(text)):
        t = m.group(1).strip()
        if t.endswith(".md"):
            t = t[:-3]
        if t:
            targets.append(t)
    return targets


def build_stem_index(notes):
    """Индексы для резолва ссылок: точный стем и нижний регистр."""
    exact, lower = {}, {}
    for rel, _ in notes:
        stem = os.path.basename(rel)[:-3]
        exact.setdefault(stem, rel)
        lower.setdefault(stem.lower(), rel)
        rel_noext = rel[:-3]
        exact.setdefault(rel_noext, rel)
        lower.setdefault(rel_noext.lower(), rel)
    return exact, lower


def build_file_index(root):
    """Не-.md файлы базы (картинки, PDF, .base, .canvas) для резолва вложений:
    полный относительный путь и имя файла, в нижнем регистре."""
    names = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {".git", ".obsidian", ".trash"}]
        for fn in filenames:
            if fn.endswith(".md"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), root).replace("\\", "/")
            names.add(rel.lower())
            names.add(fn.lower())
    return names


def resolve_link(target, exact, lower, files=None):
    base = target.split("/")[-1]
    if files is not None and "." in base:
        if target.lower() in files or base.lower() in files:
            return True
    return (target in exact or base in exact
            or target.lower() in lower or base.lower() in lower)


def today():
    return datetime.date.today().isoformat()
