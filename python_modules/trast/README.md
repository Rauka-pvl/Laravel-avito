# Trast Parser

A modular, robust parser for trast-zapchast.ru with automatic connection testing and Cloudflare bypass capabilities.

## Features

- **Parallel Connection Testing**: Tests WARP, TOR, and public proxies simultaneously
- **Smart Fallback**: Uses httpx → requests → Selenium for maximum compatibility
- **Cloudflare Bypass**: Automatic detection and Selenium fallback
- **Comprehensive Logging**: Detailed logs with timestamps and connection info
- **Modular Architecture**: Clean separation of concerns for easy maintenance

## Quick Start

### Local Development

```bash
cd python_modules/trast
pip install -r requirements.txt
python test_parser.py
python main.py
```

### Server Deployment

#### Option 1: Quick Start (Python)
```bash
cd python_modules/trast
python quick_start.py
```

#### Option 2: Full Setup (Bash)
```bash
cd python_modules/trast
chmod +x server_setup.sh
./server_setup.sh
```

#### Option 3: Manual Installation
```bash
cd python_modules/trast
python install.py
python main.py
```

### Test Components

```bash
python test_parser.py
```

## Architecture

```
python_modules/trast/
├── main.py                 # Entry point
├── config.py               # Configuration
├── logger_setup.py         # Logging setup
├── connection_manager.py    # Connection testing
├── parser.py               # Page parsing
├── requirements.txt        # Dependencies
├── test_parser.py          # Test script
└── README.md              # This file
```

## Connection Strategy

The parser tests connections in this order of preference:

1. **WARP** (Cloudflare) - Fastest if available
2. **TOR** - Reliable anonymity
3. **Public Proxies** - Fallback option

All connections are tested in parallel, and the first successful one is used.

## Configuration

Key settings in `config.py`:

- **Target URL**: `https://trast-zapchast.ru/shop/`
- **TOR**: SOCKS5 on `127.0.0.1:9050`
- **WARP**: SOCKS5 on `127.0.0.1:40000`
- **Proxy Files**: `68f0af05c9bf6.txt`, `proxies (1).json`
- **Timeouts**: 5s connection, 30s request
- **Logs**: `storage/app/public/output/logs-trast/`

## Parsing Strategy

1. **Stage 1**: Try httpx (fastest)
2. **Stage 2**: Fallback to requests
3. **Stage 3**: Use Selenium for Cloudflare bypass

## Output

The parser extracts:
- Total page count from pagination
- First page content for analysis
- Connection details and performance metrics

## Logging

Logs are written to:
- Console (INFO level)
- File: `storage/app/public/output/logs-trast/trast_YYYYMMDD_HHMMSS.log` (DEBUG level)

## Error Handling

- Automatic retries with exponential backoff
- Connection switching on failure
- Detailed error logging with context
- Graceful degradation through fallback strategies

## Requirements

- Python 3.8+
- Chrome/Firefox browser (for Selenium fallback)
- TOR (optional, for anonymity)
- WARP (optional, for Cloudflare integration)

## Dependencies

- `httpx` - Modern HTTP client
- `aiohttp` - Async HTTP client
- `requests` - Traditional HTTP client
- `beautifulsoup4` - HTML parsing
- `selenium` - Web automation
- `stem` - TOR control
- `tenacity` - Retry logic

## Usage Examples

### Basic Usage
```bash
python main.py
```

### Test Components
```bash
python test_parser.py
```

### Custom Configuration
Edit `config.py` to modify:
- URLs and timeouts
- Proxy file paths
- User agents and headers
- Logging settings

## Troubleshooting

### No Working Connections
- Check if TOR is running: `tor-parser status`
- Check if WARP is connected: `warp-parser status`
- Verify proxy files exist and contain valid proxies

### Cloudflare Detection
- Parser automatically switches to Selenium
- Ensure Chrome/Firefox is installed
- Check logs for Cloudflare indicators

### Import Errors
- Run `python test_parser.py` to verify imports
- Check Python path and module structure
- Install missing dependencies

## Development

The parser is designed to be modular and extensible:

- Add new connection types in `connection_manager.py`
- Extend parsing logic in `parser.py`
- Modify configuration in `config.py`
- Add new logging features in `logger_setup.py`

## License

This parser is for educational and research purposes only. Please respect the website's terms of service and robots.txt.
