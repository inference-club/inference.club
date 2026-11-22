#!/usr/bin/env bash
# Host hardening for the inference.club VPS. Idempotent: safe to re-run on
# every deploy. Shipped and executed by infra/deployment.ts ("harden-host").
#
#   1. sshd: key-only auth (no passwords, no keyboard-interactive)
#   2. fail2ban: ban IPs that brute-force sshd
#   3. ufw: host firewall allowing only 22/80/443 plus k3s-internal traffic
#      (defence in depth behind the Hetzner cloud firewall in server.ts)
#
# Package updates are left to unattended-upgrades. Note that it installs new
# kernels but does not reboot into them; that still needs a manual reboot.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# ---- 1. sshd ---------------------------------------------------------------
# Refuse to disable passwords if there is no key to log in with.
if ! grep -qE '^(ssh-|ecdsa-|sk-)' /root/.ssh/authorized_keys 2>/dev/null; then
    echo "harden: /root/.ssh/authorized_keys has no keys; refusing to continue" >&2
    exit 1
fi

# sshd uses the FIRST value it sees for each keyword and the Include line sits
# at the top of sshd_config, so this drop-in wins over the main file.
cat > /etc/ssh/sshd_config.d/00-hardening.conf <<'EOF'
# Managed by inference.club infra/templates/harden.sh -- do not edit by hand.
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
PermitRootLogin prohibit-password
PubkeyAuthentication yes
MaxAuthTries 3
LoginGraceTime 30
X11Forwarding no
EOF
chmod 0644 /etc/ssh/sshd_config.d/00-hardening.conf
sshd -t
systemctl reload ssh

# ---- packages --------------------------------------------------------------
need=""
for pkg in fail2ban ufw python3-systemd; do
    dpkg -s "$pkg" >/dev/null 2>&1 || need="$need $pkg"
done
if [ -n "$need" ]; then
    apt-get update -qq
    # shellcheck disable=SC2086
    apt-get install -y -qq --no-install-recommends $need
fi

# ---- 2. fail2ban -----------------------------------------------------------
# Debian 12 has no /var/log/auth.log by default, so read from the journal.
cat > /etc/fail2ban/jail.d/inference-club.local <<'EOF'
# Managed by inference.club infra/templates/harden.sh -- do not edit by hand.
[DEFAULT]
backend = systemd
bantime = 1h
findtime = 10m
maxretry = 5
# Repeat offenders get exponentially longer bans, capped at a week.
bantime.increment = true
bantime.maxtime = 1w

[sshd]
enabled = true
mode = aggressive
EOF
systemctl enable fail2ban >/dev/null 2>&1
systemctl restart fail2ban

# ---- 3. ufw ----------------------------------------------------------------
# 80/443 are served by the Traefik that k3s bundles.
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp comment 'ssh' >/dev/null
ufw allow 80/tcp comment 'http' >/dev/null
ufw allow 443/tcp comment 'https' >/dev/null
# k3s: pods and services must reach the node (kubelet, API server, DNS).
# These ranges only exist inside the node, so this opens nothing publicly.
ufw allow from 10.42.0.0/16 comment 'k3s pods' >/dev/null
ufw allow from 10.43.0.0/16 comment 'k3s services' >/dev/null
ufw --force enable >/dev/null

echo "harden: ok"
