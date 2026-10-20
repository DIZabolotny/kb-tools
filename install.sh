#!/bin/sh
# Установка kb-tools: chmod +x, симлинки в ~/.local/bin, подсказка про KB_ROOT.
# Использование: ./install.sh [путь-к-папке-базы]
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/.local/bin"
chmod +x "$HERE"/bin/*
for f in "$HERE"/bin/*; do
  ln -sf "$f" "$HOME/.local/bin/$(basename "$f")"
  echo "симлинк: ~/.local/bin/$(basename "$f") -> $f"
done
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) echo "ВНИМАНИЕ: ~/.local/bin не в PATH — добавьте в ~/.zshrc:";
     echo '  export PATH="$HOME/.local/bin:$PATH"';;
esac
if [ -n "$1" ]; then
  echo "Добавьте в ~/.zshrc, чтобы инструменты находили базу из любой папки:"
  echo "  export KB_ROOT=\"$1\""
fi
command -v python3 >/dev/null || echo "ВНИМАНИЕ: python3 не найден — нужен для работы команд"
echo "Проверка: kb-lint --brief"
