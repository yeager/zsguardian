# ZSGuardian — Zero Trust Security Dashboard

A modern macOS menubar + dashboard application that connects to the [Zscaler MCP Server](https://github.com/zscaler/zscaler-mcp-server) and provides real-time visibility into your entire Zscaler Zero Trust environment.

## Features

- **Security Posture Score** — Gamified radial gauge (0–100) computed from your live environment
- **MCP Tools Explorer** — Browse and search 110+ read-only Zscaler tools
- **Policy Flow Map** — Visual mapping of access policies, app segments, and URL categories
- **Connector Health** — Real-time connector status monitoring
- **Application Segments** — View and inspect all ZPA application segments
- **System Tray** — Persistent menubar icon with quick actions
- **Glassmorphism UI** — Dark/light mode with animated gradients and glass effects
- **Secure Credentials** — All secrets stored in macOS Keychain, never on disk

## Prerequisites

- macOS 12+
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (for `uvx zscaler-mcp`)
- Zscaler API credentials (Client ID, Client Secret, Customer ID, Vanity Domain, ZIA Cloud)

## Installation

```bash
# Clone
git clone <this-repo>
cd zscaler-guardian

# Install dependencies
pip install -r requirements.txt

# (Optional) Store credentials in Keychain ahead of time
security add-generic-password -s "zscaler-mcp-client-id" -a "zsguardian" -w "YOUR_CLIENT_ID" -U
security add-generic-password -s "zscaler-mcp-client-secret" -a "zsguardian" -w "YOUR_SECRET" -U
security add-generic-password -s "zscaler-mcp-customer-id" -a "zsguardian" -w "YOUR_CUSTOMER_ID" -U
security add-generic-password -s "zscaler-mcp-vanity-domain" -a "zsguardian" -w "YOUR_DOMAIN" -U
security add-generic-password -s "zscaler-mcp-zia-cloud" -a "zsguardian" -w "YOUR_ZIA_CLOUD" -U
```

## Usage

```bash
python src/main.py
```

If credentials are not found in Keychain, the Settings dialog opens automatically. Enter your Zscaler API credentials and they will be securely stored in macOS Keychain.

## Architecture

```
src/
├── main.py           # Entry point — PySide6 app + qasync event loop
├── mcp_client.py     # MCP JSON-RPC client (spawns uvx zscaler-mcp via stdio)
├── keychain.py       # macOS Keychain read/write via security CLI
├── dashboard.py      # Main window + settings dialog
├── tray.py           # System tray icon + menu
├── widgets/
│   ├── score_gauge.py   # Animated radial security score
│   ├── status_cards.py  # Glass-morphism metric cards
│   └── policy_map.py    # Policy flow visualization
└── styles/
    └── theme.py         # Dark/light glassmorphism themes
```

## How It Works

1. **Credentials** are loaded from macOS Keychain at runtime
2. **MCP Client** spawns `uvx zscaler-mcp` as a subprocess with credentials as env vars
3. **JSON-RPC** communication over stdio (MCP protocol 2024-11-05)
4. **Tool discovery** via `tools/list` — typically 110+ read-only tools
5. **Dashboard** calls tools like `list_access_policies`, `list_connectors`, etc.
6. **Security Score** is computed from the number and health of policies, connectors, segments, DLP engines, and IdPs

## License

MIT
