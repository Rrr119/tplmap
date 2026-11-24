#!/usr/bin/env bash
# Provision the real Jinja2 / Twig / FreeMarker runtimes used by the local
# ranges and the detection-rate benchmark without touching the system.
#
# Everything is downloaded into .runtimes/ next to the repository root.
# Jinja2 itself is expected in the active Python (pip install jinja2).
#
# Usage:  bash ranges/setup_runtimes.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RT="$ROOT/.runtimes"
mkdir -p "$RT"

PHP_VERSION="${PHP_VERSION:-8.4.23}"
JDK_URL="${JDK_URL:-https://api.adoptium.net/v3/binary/latest/21/ga/linux/x64/jdk/hotspot/normal/eclipse}"
FREEMARKER_VERSION="${FREEMARKER_VERSION:-2.3.34}"

# --- PHP (static CLI build) + Twig ---------------------------------------
if [ ! -x "$RT/php" ]; then
  echo "[*] Downloading static PHP $PHP_VERSION"
  curl -fL --retry 3 -o "$RT/php.tar.gz" \
    "https://dl.static-php.dev/static-php-cli/common/php-${PHP_VERSION}-cli-linux-x86_64.tar.gz"
  tar -xzf "$RT/php.tar.gz" -C "$RT" php
  chmod +x "$RT/php"
fi

if [ ! -f "$ROOT/ranges/twig_range/vendor/autoload.php" ]; then
  echo "[*] Installing Twig 3 via Composer"
  curl -fL --retry 3 -o "$RT/composer.phar" \
    "https://getcomposer.org/download/latest-stable/composer.phar"
  (
    cd "$ROOT/ranges/twig_range"
    "$RT/php" "$RT/composer.phar" require twig/twig:^3.20 --no-interaction
  )
fi

# --- Java (full JDK, needed to compile the FreeMarker range) + FreeMarker -
if [ -z "${TPLMAP_JAVA:-}" ] && [ -z "$(ls -d "$RT"/jdk*/bin/javac 2>/dev/null | head -1)" ]; then
  echo "[*] Downloading Temurin JDK 21"
  curl -fL --retry 3 -o "$RT/jdk.tar.gz" "$JDK_URL"
  tar -xzf "$RT/jdk.tar.gz" -C "$RT"
fi

if [ ! -f "$RT/freemarker.jar" ]; then
  echo "[*] Downloading FreeMarker $FREEMARKER_VERSION"
  curl -fL --retry 3 -o "$RT/freemarker.jar" \
    "https://repo1.maven.org/maven2/org/freemarker/freemarker/${FREEMARKER_VERSION}/freemarker-${FREEMARKER_VERSION}.jar"
fi

# --- Jinja2 for the active Python ----------------------------------------
if ! python3 -c 'import jinja2' >/dev/null 2>&1; then
  echo "[*] Installing jinja2 for the active Python"
  python3 -m pip install --user 'jinja2>=3'
fi

echo "[+] Runtimes ready. Run: python3 benchmarks/run_comparison.py"
