#!/bin/bash
# Install (or reinstall) the blinds daemon as a launchd system daemon, so it
# starts at boot and is restarted if it exits.
#
#   ./contrib/install-launchd.sh [config-path]
#
# Re-running this replaces an existing daemon. With no argument it keeps the
# config file the installed daemon already uses, falling back to
# <project>/config.yaml on a first install. Pass one to point it elsewhere.
#
# Needs root to write to /Library/LaunchDaemons, and re-runs itself under sudo
# if you did not. It installs a system daemon rather than a user agent so the
# blinds work after an unattended reboot, with no one logged in, and so macOS
# does not silently deny it access to the local network.
set -euo pipefail

label="com.chriskillpack.bond-blinds"
project="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="/Library/LaunchDaemons/$label.plist"

if [[ $EUID -ne 0 ]]; then
    exec sudo "${BASH_SOURCE[0]}" "$@"
fi

# The daemon drops root to whoever ran the install, so it keeps writing its
# logs and solar history as that user rather than leaving root-owned files.
run_user="${SUDO_USER:-$(id -un)}"
exec_path="$project/.venv/bin/bond-blinds"

if [[ ! -x $exec_path ]]; then
    echo "no entry point at $exec_path" >&2
    echo "run 'uv sync' in $project first" >&2
    exit 1
fi

# Where a previous install of the user agent would be, so we can migrate it.
old_agent="$(sudo -u "$run_user" -H printenv HOME)/Library/LaunchAgents/$label.plist"

config="${1:-}"
kept=""
if [[ -z $config ]]; then
    for source in "$target" "$old_agent"; do
        [[ -f $source ]] || continue
        # Scan for the flag rather than a fixed index so reordering the
        # template's ProgramArguments cannot make this read the wrong string.
        count="$(plutil -extract ProgramArguments raw -o - "$source" 2>/dev/null || echo 0)"
        for ((i = 0; i < count - 1; i++)); do
            if [[ "$(plutil -extract "ProgramArguments.$i" raw -o - "$source")" == --config ]]; then
                config="$(plutil -extract "ProgramArguments.$((i + 1))" raw -o - "$source")"
                kept="  (kept from the installed daemon)"
            fi
        done
        [[ -n $config ]] && break
    done
fi
config="${config:-$project/config.yaml}"

if [[ ! -f $config ]]; then
    # launchd would just restart the daemon into the same error every 30s.
    echo "no config file at $config" >&2
    echo "copy config.example.yaml to config.yaml and fill it in first" >&2
    exit 1
fi
config="$(cd "$(dirname "$config")" && pwd)/$(basename "$config")"  # launchd needs an absolute path

sed -e "s|__EXEC__|$exec_path|g" \
    -e "s|__PROJECT__|$project|g" \
    -e "s|__CONFIG__|$config|g" \
    -e "s|__USER__|$run_user|g" \
    "$project/contrib/$label.plist" > "$target"

# launchd ignores a system daemon plist that anyone but root can write.
chown root:wheel "$target"
chmod 644 "$target"
plutil -lint "$target" > /dev/null

# Retire the user agent this used to install, or the two fight over the port.
if [[ -f $old_agent ]]; then
    launchctl bootout "gui/$(id -u "$run_user")/$label" 2>/dev/null || true
    rm -f "$old_agent"
    echo "removed the old user agent at $old_agent"
fi

# bootout first so a changed plist actually takes effect.
launchctl bootout "system/$label" 2>/dev/null || true
launchctl bootstrap system "$target"

echo "installed $target"
echo "  exec:    $exec_path"
echo "  user:    $run_user"
echo "  project: $project"
echo "  config:  $config$kept"
echo
echo "restart it:  sudo launchctl kickstart -k system/$label"
echo "check it:    sudo launchctl print system/$label | head"
echo "logs:        tail -f $project/bond-blinds.log"
echo "             tail -f $project/launchd.log"
echo "remove it:   sudo launchctl bootout system/$label && sudo rm $target"
