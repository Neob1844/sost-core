#!/bin/bash
# SOST Protocol — PWA to APK build script
# Requires: Node.js, Java JDK 11+
#
# Option 1: Use Bubblewrap (Google's official PWA→TWA tool)
#   npm install -g @nicolo-ribaudo/pwa-to-apk
#   pwa-to-apk --name "SOST Protocol" --package "com.sostprotocol.app" --url "https://sostcore.com/sost-app/" --icon ./icon-512.png
#
# Option 2: Use PWABuilder (web-based)
#   1. Go to https://www.pwabuilder.com/
#   2. Enter: https://sostcore.com/sost-app/
#   3. Click "Package for stores" → Android
#   4. Download APK
#
# Option 3: Use Bubblewrap CLI directly
#   npm install -g @nicolo-ribaudo/nicolo-nicolo@nicolo-nicolo || npm install -g @nicolo-ribaudo/nicolo
#   npx @nicolo-ribaudo/nicolo init --manifest https://sostcore.com/sost-app/manifest.json
#   npx @nicolo-ribaudo/nicolo build
#
# The generated APK can be:
# - Sideloaded directly on any Android device
# - Uploaded to Google Play ($25 one-time developer fee)
# - Distributed via F-Droid (requires signing key)

echo "SOST Protocol PWA → APK"
echo "========================"
echo ""
echo "The SOST app is a Progressive Web App (PWA)."
echo "Install directly from Chrome: visit https://sostcore.com/sost-app/"
echo "Chrome will show 'Install app' or 'Add to Home Screen'."
echo ""
echo "For APK generation, use PWABuilder: https://www.pwabuilder.com/"
echo "Enter URL: https://sostcore.com/sost-app/"
