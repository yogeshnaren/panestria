set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
cloud-init status --wait
sudo apt-get update
sudo apt-get install -y make git curl ca-certificates docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu
curl -fLsS https://astral.sh/uv/0.12.3/install.sh -o /tmp/uv-install.sh
sh /tmp/uv-install.sh
export PATH="$HOME/.local/bin:$PATH"
uv --version
uv python install 3.12
git clone "$HOME/repo.bundle" "$HOME/panestria"
cd "$HOME/panestria"
git checkout d457242e9e6ee2c54fbd99db99cb35319b1c8783
test ! -e .venv
make bootstrap
uv run --frozen python -c 'import panestria; print(panestria.package_version())'
rm -rf .venv
uv sync --frozen --group dev --offline
uv run --frozen --offline python -c 'import panestria; print(panestria.package_version())'
mkdir -p "$HOME/r0-results"
uv run --frozen python "$HOME/hwprobe.py" --json "$HOME/r0-results/guest-hardware.json" > "$HOME/r0-results/guest-hardware.txt"
uv run --frozen python - <<'PY'
from pathlib import Path
import json,sys,subprocess,uuid
r=Path.home()/'r0-results'; boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
report={'boot_id':boot,'venv_created_this_boot':True,'host_kind':'fresh-qemu-vm','offline_cache_reinstall_passed':True,'python':sys.version,'candidate_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'instance_id':Path('/var/lib/cloud/data/instance-id').read_text().strip()}
(r/'fresh-host.json').write_text(json.dumps(report,indent=2)+'\n')
PY
printf '%s\n' 'FRESH_BOOTSTRAP_COMPLETE'
