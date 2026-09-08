#!/bin/bash
# Install (or reinstall) the blinds daemon as a launchd user agent, so it
# starts at login and is restarted if it exits.
#
#   ./contrib/install-launchd.sh [config-path]
#
# Re-running this replaces an existing agent. With no argument it keeps the
# config file the installed agent already uses, falling back to
# <project>/config.yaml on a first install. Pass one to point it elsewhere.
set -euo pipefail

label="com.chriskillpack.bond-blinds"
project="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
uv="$(command -v uv)"
target="$HOME/Library/LaunchAgents/$label.plist"

config="${1:-}"
kept=""
if [[ -z $config && -f $target ]]; then
    # Scan for the flag rather than a fixed index so reordering the
    # template's ProgramArguments cannot make this read the wrong string.
    count="$(plutil -extract ProgramArguments raw -o - "$target" 2>/dev/null || echo 0)"
    for ((i = 0; i < count - 1; i++)); do
        if [[ "$(plutil -extract "ProgramArguments.$i" raw -o - "$target")" == --config ]]; then
            config="$(plutil -extract "ProgramArguments.$((i + 1))" raw -o - "$target")"
            kept="  (kept from the installed agent)"
        fi
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

mkdir -p "$(dirname "$target")"

sed -e "s|__UV__|$uv|g" \
    -e "s|__PROJECT__|$project|g" \
    -e "s|__CONFIG__|$config|g" \
    "$project/contrib/$label.plist" > "$target"

plutil -lint "$target" > /dev/null

# bootout first so a changed plist actually takes effect.
launchctl bootout "gui/$UID/$label" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$target"

echo "installed $target"
echo "  uv:      $uv"
echo "  project: $project"
echo "  config:  $config$kept"
echo
echo "restart it:  launchctl kickstart -k gui/$UID/$label"
echo "check it:    launchctl print gui/$UID/$label | head"
echo "logs:        tail -f $project/bond-blinds.log"
echo "             tail -f $project/launchd.log"
echo "remove it:   launchctl bootout gui/$UID/$label && rm $target"
