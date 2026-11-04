AUTOMATIC CHECKS (optional, for developers)
Cloud server (76 checks):   cd cloud  &  node test.mjs
YouTube bot on the cloud:   cd cloud  &  node test-youtube-bot.mjs
Uptime history (needs Node 22+):  cd cloud  &  node test-uptime.mjs
App (no internet): in a fresh empty folder set  APPDATA=<folder>  QT_QPA_PLATFORM=offscreen  PYTHONPATH=.   then   python tests\test_app.py
Overlay pages (need Node + jsdom):  npm install jsdom  &  python tests\make_overlay_pages.py  &  node tests\overlay_page.test.cjs
