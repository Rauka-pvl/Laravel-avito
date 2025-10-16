# Trast Parser - Modular Web Scraper

A robust, modular web scraper designed for server environments with advanced proxy rotation, anti-detection measures, and adaptive learning capabilities.

## Features

- **Firefox-based scraping** - Uses Firefox with geckodriver for better Tor/WARP compatibility
- **Multi-proxy support** - WARP → Tor → Proxy pool fallback chain
- **Anti-detection measures** - Stealth browsing with fingerprint randomization
- **Adaptive learning** - Learns from successful strategies and IP performance
- **Session management** - Disposable browser pool with automatic cleanup
- **Data validation** - Comprehensive data quality checks and backup management

## Installation

### Prerequisites

```bash
# Install Firefox and geckodriver
sudo apt update
sudo apt install firefox firefox-geckodriver

# Install Python dependencies
pip install selenium requests beautifulsoup4 openpyxl pandas
```

### Proxy Setup

#### WARP (Recommended)
```bash
sudo ./install_warp.sh
```

#### Tor
```bash
sudo ./install_tor.sh
```

#### Proxy Pool
Place proxy files in the root directory:
- `proxies (1).json` - JSON format proxy list
- `68f0af05c9bf6.txt` - Text format proxy list (IP:PORT)

## Configuration

Edit `modules/config.py` to customize:

```python
# Browser settings
BROWSER_TYPE = "firefox"
HEADLESS = True

# Proxy priorities
WARP_ENABLED = True
TOR_SOCKS_PORT = 9050
WARP_PROXY_URL = "socks5://127.0.0.1:40000"

# Parsing parameters
PAGES_PER_SESSION = 20
MAX_EMPTY_PAGES = 10
```

## Usage

### Basic Usage
```bash
cd python_modules/trast
python main.py
```

### Testing
```bash
python test_modules.py
```

## Architecture

### Core Modules

- **browser_manager.py** - Firefox browser creation and session management
- **proxy_manager.py** - Hybrid proxy strategy (WARP/Tor/Proxy pool)
- **warp_manager.py** - Cloudflare WARP integration
- **anti_block.py** - Anti-detection and session establishment
- **parser_core.py** - Product extraction and page parsing
- **data_manager.py** - Data writing, validation, and backup
- **adaptive_learning.py** - Strategy optimization and IP tracking
- **ip_rotator.py** - Intelligent IP rotation strategies

### Proxy Strategy

1. **WARP** (Primary) - Cloudflare WARP proxy for speed and reliability
2. **Tor** (Fallback) - Tor network for maximum anonymity
3. **Proxy Pool** (Last resort) - Rotating proxy servers

### Anti-Detection Features

- Random user agents (Firefox-based)
- Dynamic viewport sizes
- Human-like behavior simulation
- Session establishment with cookies
- Request rate limiting
- IP rotation on failures

## File Structure

```
python_modules/trast/
├── main.py                 # Main entry point
├── modules/               # Core modules
│   ├── browser_manager.py # Firefox browser management
│   ├── proxy_manager.py   # Proxy strategy management
│   ├── warp_manager.py    # WARP integration
│   ├── config.py          # Configuration
│   └── ...
├── install_warp.sh        # WARP installation script
├── install_tor.sh         # Tor installation script
├── test_modules.py        # Module testing
└── learning_data.json    # Adaptive learning data
```

## Troubleshooting

### Firefox Issues
```bash
# Check Firefox installation
firefox --version

# Check geckodriver
geckodriver --version

# Install missing dependencies
sudo apt install firefox-geckodriver
```

### WARP Issues
```bash
# Check WARP status
warp-cli status

# Restart WARP
warp-cli disconnect
warp-cli connect
```

### Tor Issues
```bash
# Check Tor service
systemctl status tor-parser

# Restart Tor
sudo systemctl restart tor-parser
```

## Performance Optimization

- **Session pooling** - Reuses browser sessions efficiently
- **Smart IP rotation** - Rotates based on success rates and timing
- **Adaptive delays** - Adjusts delays based on response times
- **Bulk fetching** - Attempts to fetch all data in single request
- **Backup management** - Automatic backup creation and restoration

## Security Notes

- WARP runs in proxy-only mode to avoid SSH blocking
- Tor uses isolated data directory for security
- All proxy credentials are handled securely
- Browser sessions are properly disposed after use

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is for educational and research purposes only. Please respect website terms of service and robots.txt files.
