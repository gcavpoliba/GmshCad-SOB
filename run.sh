#!/usr/bin/env bash
# Avvio GmshCAD Studio con l'ambiente conda "gmshcad"
# (nome allineato a environment.yml; sovrascrivibile con GCS_ENV=nome ./run.sh)
# Uso: ./run.sh            (GUI)
#      ./run.sh --demo     (demo headless)
set -e
cd "$(dirname "$0")"
GCS_ENV="${GCS_ENV:-gmshcad}"

# attiva l'ambiente se non siamo già dentro
if [ -z "$CONDA_PREFIX" ] || ! python -c "import OCC" 2>/dev/null; then
  SOURCE="$(conda info --base 2>/dev/null)/etc/profile.d/conda.sh"
  [ -f "$SOURCE" ] && source "$SOURCE" && conda activate "$GCS_ENV"
fi

export QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-}
exec python main.py "$@"
