---
name: healthcheck
description: "Performs security hardening and risk-tolerance configuration for claw-python deployments. Use when: running a security audit, hardening firewall or SSH settings, or checking for available updates. NOT for: application-level debugging or runtime monitoring."
metadata:
  { "openclaw": { "emoji": "🛡️", "os": ["darwin", "linux"], "requires": {} } }
---

# Host Hardening

Assess and improve the security posture of the host running claw-python.

## Audit commands

Start with a read-only snapshot:

```bash
uname -a
ss -ltnup                                        # open ports
systemctl list-units --state=failed              # failed services
apt list --upgradable 2>/dev/null | head -20     # pending updates
Area	Command
SSH config	sshd -T | grep -E 'permitrootlogin|passwordauth'
Firewall (Linux)	ufw status verbose
Firewall (macOS)	pfctl -sr
Hardening steps
Apply only after reviewing output and confirming with the user:


# Disable root SSH login
sudo sed -i 's/^PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl reload sshd

# Enable UFW with deny-by-default
sudo ufw default deny incoming
sudo ufw allow ssh
sudo ufw enable
Notes
Always preview changes before applying.
Confirm with the user before modifying any system configuration.


---
