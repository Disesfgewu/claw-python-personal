#!/bin/bash
# Jetson Orin Nano Super optimization script

echo "=== Jetson Orin Nano Optimization ==="

# 1. Set CPU governor to performance
if command -v sudo >/dev/null 2>&1; then
    echo "Setting CPU governor to performance..."
    echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor >/dev/null
else
    echo "sudo not available, skipping CPU governor change"
fi

# 2. Disable unnecessary services
if command -v sudo >/dev/null 2>&1; then
    echo "Disabling unnecessary services..."
    sudo systemctl disable --now cups.service 2>/dev/null || true
    sudo systemctl disable --now bluetooth.service 2>/dev/null || true
else
    echo "sudo not available, skipping service disable"
fi

# 3. Set swap
if command -v sudo >/dev/null 2>&1; then
    if [ ! -f /swapfile ]; then
        echo "Creating swap file..."
        sudo fallocate -l 2G /swapfile
        sudo chmod 600 /swapfile
        sudo mkswap /swapfile
        sudo swapon /swapfile
        echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab >/dev/null
    fi
else
    echo "sudo not available, skipping swap setup"
fi

# 4. Increase inotify watches
if command -v sudo >/dev/null 2>&1; then
    echo "Increasing inotify watches..."
    echo "fs.inotify.max_user_watches=524288" | sudo tee /etc/sysctl.d/40-inotify.conf >/dev/null
    sudo sysctl -p /etc/sysctl.d/40-inotify.conf
else
    echo "sudo not available, skipping inotify tuning"
fi

# 5. Set timezone
if command -v sudo >/dev/null 2>&1; then
    echo "Setting timezone to Asia/Taipei..."
    sudo timedatectl set-timezone Asia/Taipei
else
    echo "sudo not available, skipping timezone setup"
fi

echo "=== Optimization Complete ==="
