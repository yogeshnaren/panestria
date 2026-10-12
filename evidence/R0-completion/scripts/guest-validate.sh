set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
cd "$HOME/panestria"
make db-up
make db-migrate
export PANESTRIA_DATABASE_URL='postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:55432/panestria_synthetic'
export PANESTRIA_FRESH_HOST_REPORT="$HOME/r0-results/fresh-host.json"
uv run --frozen pytest -p no:cacheprovider tests/integration/test_aos_001.py::test_fresh_host_loopback --junitxml="$HOME/r0-results/fresh-host.xml" -q
make r0-demo > "$HOME/r0-results/demo.txt" 2>&1
uv run --frozen python - <<'PY'
from pathlib import Path
import json,platform,subprocess,hashlib
r=Path.home()/'r0-results'
manifest=json.loads((r/'fresh-host.json').read_text())
manifest.update({'os_release':Path('/etc/os-release').read_text(),'kernel':platform.release(),'uv':subprocess.check_output(['uv','--version'],text=True).strip(),'docker':subprocess.check_output(['docker','--version'],text=True).strip(),'compose':subprocess.check_output(['docker','compose','version'],text=True).strip(),'lock_sha256':hashlib.sha256(Path('uv.lock').read_bytes()).hexdigest(),'git_status':subprocess.check_output(['git','status','--short'],text=True).strip(),'bootstrap_log':'guest-bootstrap.log','provider_credentials_used':False})
(r/'environment-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
PY
make db-down
make reset-synthetic-data
printf '%s\n' 'FRESH_ACCEPTANCE_COMPLETE'
