#!/usr/bin/env python3
import hashlib, sys
from pathlib import Path
path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config/blueprint.yaml")
digest = hashlib.sha256(path.read_bytes()).hexdigest()
print(f"sha256: {digest}")
