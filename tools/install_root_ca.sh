#!/usr/bin/env bash
set -e

CERT="certs/root_ca.crt"

if [ ! -f "$CERT" ]; then
  echo "❌ Root CA not found at $CERT"
  exit 1
fi

OS="$(uname)"

if [[ "$OS" == "Darwin" ]]; then
  echo "Installing on macOS..."
  sudo security add-trusted-cert -d -r trustRoot \
    -k /Library/Keychains/System.keychain "$CERT"

elif [[ "$OS" == "Linux" ]]; then
  echo "Installing on Linux..."
  # Ubuntu/Debian common path
  sudo cp "$CERT" /usr/local/share/ca-certificates/mymanagerh.crt
  sudo update-ca-certificates

else
  echo "Windows detected:"
  echo "Run manually:"
  echo "certutil -addstore Root certs\\root_ca.crt"
  exit 0
fi

echo "✅ Root CA installed"
