#!/usr/bin/env bash
# Assemble a self-contained Hugging Face Space (Streamlit SDK) in dist/hf_space/.
# Usage:  bash scripts/build_hf_space.sh
#         huggingface-cli upload <hf-user>/<space-name> dist/hf_space . --repo-type=space
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
out="$here/dist/hf_space"
rm -rf "$out" && mkdir -p "$out/src"
cp "$here/app.py" "$out/"
cp -r "$here/src/geowell_tea" "$out/src/"
cp -r "$here/configs" "$out/"
find "$out" -name "__pycache__" -prune -exec rm -rf {} +
cat > "$out/requirements.txt" <<'REQ'
numpy>=2.0
scipy>=1.13
pandas>=2.2
pyyaml>=6.0
REQ
cat > "$out/README.md" <<'MD'
---
title: Thermosiphon heat from reused wells
emoji: 🔥
colorFrom: yellow
colorTo: red
sdk: streamlit
app_file: app.py
python_version: "3.12"
pinned: false
short_description: Cost of heat from an ammonia thermosiphon in a reused oil & gas well
---

Fast calculator from the `geowell_tea` techno-economic model
(https://github.com/mallorysnowden/Thermosyphon-Moonshot). Costs are assumptions, not quotes;
see MODEL_LIMITATIONS.md in the repo before using any number.
MD
echo "Space files written to $out"
