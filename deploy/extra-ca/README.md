# Optional extra trusted root certificates

Place PEM certificates (`*.crt`) here **only** if your network or antivirus performs TLS
inspection (for example a corporate proxy or "AVG/Avast Web Shield"). They are added to the
backend and frontend build images' trust store so `pip`, `npm`, and runtime calls to Yahoo /
AI providers keep **full certificate verification** instead of failing.

* Leave this folder empty on a normal VPS.
* `*.crt` files are git-ignored; never commit them.
* Export a root on Windows: `certmgr.msc` → Trusted Root Certification Authorities → export as Base-64 `.cer`, rename to `.crt`.
