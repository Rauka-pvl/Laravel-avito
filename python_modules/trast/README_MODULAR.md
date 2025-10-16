# Modular Trast Parser v2.0

## Overview

The Trast parser has been completely refactored from a monolithic 1145-line script into a modular, maintainable architecture with 8 focused modules. This new architecture provides better separation of concerns, improved testability, and enhanced reliability.

## Architecture

### Module Structure

```
python_modules/trast/
├── modules/
│   ├── __init__.py              # Module exports
│   ├── config.py                # Centralized configuration
│   ├── proxy_manager.py         # Proxy & Tor management
│   ├── browser_manager.py       # Browser lifecycle management
│   ├── anti_block.py           # Anti-blocking strategies
│   ├── parser_core.py          # Core parsing logic
│   ├── data_manager.py         # Data output & backup
│   ├── ip_rotator.py           # IP rotation strategies
│   └── adaptive_learning.py    # Learning & optimization
├── main_refactored.py          # New modular main script
├── main_legacy.py              # Original script (backup)
└── test_modules.py             # Module validation tests
```

## Key Improvements

### 1. **Separation of Concerns**
- Each module has a single, well-defined responsibility
- Easy to modify one aspect without affecting others
- Clear interfaces between modules

### 2. **Enhanced Anti-Blocking**
- **Hybrid Strategy**: Tor primary + proxy pool fallback
- **Aggressive IP Rotation**: Multiple rotation strategies (time-based, request-based, error-based)
- **Adaptive Learning**: Tracks success/failure patterns and optimizes strategies
- **Human Behavior Simulation**: Random scrolling, mouse movements, reading delays
- **Cloudflare-Safe Delays**: Intelligent timing to avoid detection

### 3. **Improved Reliability**
- **Disposable Browsers**: Clean slate on failures, no state contamination
- **Smart Backup System**: Incremental backups with metadata and auto-restore
- **Data Validation**: Quality checks and filtering of invalid products
- **Comprehensive Error Handling**: Graceful degradation and recovery

### 4. **Better Monitoring**
- **Detailed Statistics**: Track performance across all modules
- **Learning Analytics**: Monitor strategy effectiveness
- **Proxy Health Monitoring**: Track success rates and burned IPs
- **Session Management**: Monitor browser session performance

## Module Details

### `config.py` - Configuration Management
- Centralized settings and constants
- File paths and URLs
- Timing parameters and thresholds
- User agent rotation
- Easy configuration updates

### `proxy_manager.py` - Proxy & Tor Management
- **ProxyPool**: Load, test, and manage proxy servers
- **TorManager**: Tor circuit management and IP rotation
- **HybridProxyStrategy**: Combines Tor and proxy pool with fallback
- Automatic protocol detection (HTTP/HTTPS/SOCKS4/SOCKS5)
- Health monitoring and adaptive selection

### `browser_manager.py` - Browser Lifecycle
- **BrowserFactory**: Create stealth browsers with anti-detection
- **BrowserSession**: Track session metrics and lifecycle
- **DisposableBrowserPool**: Manage browser instances
- Automatic cleanup and resource management

### `anti_block.py` - Anti-Blocking Strategies
- **BlockDetector**: Detect CAPTCHA, Cloudflare, rate limits
- **HumanBehaviorSimulator**: Random scrolling, mouse movements, reading
- **DelayStrategy**: Smart delays based on context
- **SessionEstablisher**: Legitimate session establishment
- **FingerprintRandomizer**: Randomize browser fingerprints

### `parser_core.py` - Core Parsing Logic
- **ProductExtractor**: Extract products from HTML
- **PageFetcher**: Fetch pages with retry logic
- **ParsingOrchestrator**: Coordinate parsing sessions
- Bulk fetch optimization
- Session-based parsing for rate limiting

### `data_manager.py` - Data Management
- **DataWriter**: Excel/CSV operations
- **BackupManager**: Incremental backups with metadata
- **DataValidator**: Product validation and quality checks
- Smart restore from backups
- Automatic cleanup of old backups

### `ip_rotator.py` - IP Rotation Strategies
- **IPRotationStrategy**: Base class for rotation strategies
- **TimeBasedRotation**: Rotate every N minutes
- **RequestBasedRotation**: Rotate every N requests
- **ErrorBasedRotation**: Rotate after N errors
- **AggressiveRotation**: Rotate on every request
- **AdaptiveRotator**: Learn and optimize rotation strategies

### `adaptive_learning.py` - Learning & Optimization
- **AdaptiveLearningEngine**: Track strategy performance
- **StrategyPerformance**: Monitor strategy success rates
- **IPPerformance**: Track IP reliability
- Persistent learning data
- Strategy recommendations

## Usage

### Running the Modular Parser

```bash
cd python_modules/trast
python main_refactored.py
```

### Testing Modules

```bash
cd python_modules/trast
python test_modules.py
```

### Configuration

All configuration is centralized in `modules/config.py`. Key settings:

```python
# Timing parameters
CLOUDFLARE_DELAY_RANGE = (15, 45)
SMART_DELAY_RANGE = (5, 10)
PAGES_PER_SESSION = 20

# Anti-blocking thresholds
MAX_EMPTY_PAGES = 10
MAX_CONSECUTIVE_SPARSE = 20
SUCCESS_THRESHOLD_PERCENT = 80

# IP rotation
TOR_SOCKS_PORT = 9050
TOR_CONTROL_PORT = 9051
```

## Key Features

### 1. **Hybrid Proxy Strategy**
- Primary: Tor with automatic circuit rotation
- Fallback: Proxy pool with health monitoring
- Automatic failover and recovery

### 2. **Aggressive IP Rotation**
- Multiple rotation strategies
- Adaptive learning from success/failure patterns
- Burned IP detection and avoidance

### 3. **Cloudflare Bypass**
- Human behavior simulation
- Cloudflare-safe delays
- Session establishment with legitimacy checks
- Fingerprint randomization

### 4. **Smart Backup System**
- Incremental backups with metadata
- Auto-restore if current result is below threshold
- Backup cleanup and management

### 5. **Adaptive Learning**
- Track strategy performance
- Learn from success/failure patterns
- Optimize rotation and anti-block strategies
- Persistent learning data

## Migration from Legacy

The original `main.py` has been preserved as `main_legacy.py`. The new modular version provides:

- **Better Reliability**: Modular error handling and recovery
- **Enhanced Anti-Blocking**: More sophisticated bypass strategies
- **Improved Performance**: Optimized parsing and resource management
- **Better Monitoring**: Comprehensive statistics and learning analytics
- **Easier Maintenance**: Clear separation of concerns

## Performance Comparison

| Aspect | Legacy | Modular |
|--------|--------|---------|
| Lines of Code | 1145 | ~300 (main) + 8 modules |
| Error Recovery | Basic | Advanced with learning |
| IP Rotation | Manual | Automatic with strategies |
| Anti-Blocking | Basic | Advanced with simulation |
| Monitoring | Limited | Comprehensive |
| Testability | Difficult | Easy (unit tests) |
| Maintainability | Hard | Easy (modular) |

## Future Enhancements

- **Parallel Processing**: Multi-threaded parsing
- **Machine Learning**: Advanced pattern recognition
- **Proxy Sources**: Integration with more proxy providers
- **Browser Pooling**: Multiple browser instances
- **API Integration**: REST API for remote control

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure all dependencies are installed
2. **Proxy Failures**: Check proxy files and Tor installation
3. **Browser Issues**: Verify Chrome and ChromeDriver versions
4. **Learning Data**: Check `learning_data.json` permissions

### Debug Mode

Enable debug logging by modifying the logging level in `main_refactored.py`:

```python
logging.basicConfig(level=logging.DEBUG, ...)
```

## Support

For issues or questions about the modular parser, check:

1. Module test results: `python test_modules.py`
2. Learning data: `learning_data.json`
3. Backup files: `backups/` directory
4. Log files: `logs-trast/` directory

The modular architecture makes debugging and maintenance much easier than the original monolithic approach.
