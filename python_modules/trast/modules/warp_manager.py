"""
WARP manager module for Trast parser.

Handles Cloudflare WARP integration for enhanced privacy and IP rotation.
"""

import os
import subprocess
import logging
import requests
import time
from typing import Optional, Dict, List, Tuple
from .config import TrastConfig

logger = logging.getLogger("trast.warp_manager")


class WARPManager:
    """Manages Cloudflare WARP connections and proxy configuration."""
    
    def __init__(self):
        self.warp_enabled = TrastConfig.WARP_ENABLED
        self.proxy_urls = self._get_warp_proxy_urls()
        self.current_proxy = None
        self.is_connected = False
        
    def _get_warp_proxy_urls(self) -> List[str]:
        """Get list of WARP proxy URLs."""
        urls = []
        for port in TrastConfig.WARP_ALTERNATIVE_PORTS:
            urls.append(f"socks5://127.0.0.1:{port}")
        return urls
    
    def is_available(self) -> bool:
        """Check if WARP is available and running."""
        if not self.warp_enabled:
            return False
            
        try:
            # Check if WARP is installed
            result = subprocess.run(
                ["warp-cli", "--help"], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            
            if result.returncode != 0:
                logger.debug("WARP CLI not found")
                return False
            
            # Check WARP status
            status_result = subprocess.run(
                ["warp-cli", "status"], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            
            if "Connected" in status_result.stdout:
                logger.info("✅ WARP is connected")
                return True
            else:
                logger.debug("WARP is not connected")
                return False
                
        except Exception as e:
            logger.debug(f"Error checking WARP availability: {e}")
            return False
    
    def connect(self) -> bool:
        """Connect to WARP."""
        try:
            logger.info("🔗 Connecting to WARP...")
            
            # Try to connect
            result = subprocess.run(
                ["warp-cli", "connect"], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            
            if result.returncode == 0:
                # Wait for connection
                time.sleep(3)
                
                # Verify connection
                if self.is_available():
                    logger.info("✅ WARP connected successfully")
                    self.is_connected = True
                    return True
                else:
                    logger.warning("⚠️ WARP connection failed")
                    return False
            else:
                logger.error(f"❌ WARP connection error: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error connecting to WARP: {e}")
            return False
    
    def disconnect(self) -> bool:
        """Disconnect from WARP."""
        try:
            logger.info("🔌 Disconnecting from WARP...")
            
            result = subprocess.run(
                ["warp-cli", "disconnect"], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            
            if result.returncode == 0:
                logger.info("✅ WARP disconnected")
                self.is_connected = False
                return True
            else:
                logger.warning(f"⚠️ WARP disconnect warning: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error disconnecting from WARP: {e}")
            return False
    
    def get_proxy_config(self) -> Optional[Dict[str, str]]:
        """Get WARP proxy configuration."""
        if not self.is_available():
            return None
            
        # Test available proxy ports
        for proxy_url in self.proxy_urls:
            if self._test_proxy_port(proxy_url):
                self.current_proxy = proxy_url
                logger.info(f"🔗 Using WARP proxy: {proxy_url}")
                return {
                    'http': proxy_url,
                    'https': proxy_url
                }
        
        logger.warning("⚠️ No working WARP proxy ports found")
        return None
    
    def _test_proxy_port(self, proxy_url: str) -> bool:
        """Test if a proxy port is working."""
        try:
            # Extract port from URL
            port = int(proxy_url.split(":")[-1])
            
            # Test with a simple request
            proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            
            response = requests.get(
                "https://httpbin.org/ip", 
                proxies=proxies, 
                timeout=5
            )
            
            if response.status_code == 200:
                logger.debug(f"✅ WARP proxy port {port} is working")
                return True
            else:
                logger.debug(f"❌ WARP proxy port {port} failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.debug(f"❌ WARP proxy port test failed: {e}")
            return False
    
    def get_current_ip(self) -> Optional[str]:
        """Get current IP address through WARP."""
        try:
            proxy_config = self.get_proxy_config()
            if not proxy_config:
                return None
            
            response = requests.get(
                "https://httpbin.org/ip", 
                proxies=proxy_config, 
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                ip = data.get('origin', '').split(',')[0].strip()
                logger.debug(f"🌍 Current WARP IP: {ip}")
                return ip
            else:
                logger.warning(f"⚠️ Failed to get WARP IP: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error getting WARP IP: {e}")
            return None
    
    def rotate_ip(self) -> bool:
        """Rotate WARP IP by reconnecting."""
        try:
            logger.info("🔄 Rotating WARP IP...")
            
            # Disconnect and reconnect
            self.disconnect()
            time.sleep(2)
            
            if self.connect():
                # Get new IP
                new_ip = self.get_current_ip()
                if new_ip:
                    logger.info(f"✅ WARP IP rotated to: {new_ip}")
                    return True
                else:
                    logger.warning("⚠️ WARP IP rotation completed but couldn't get new IP")
                    return True
            else:
                logger.error("❌ Failed to rotate WARP IP")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error rotating WARP IP: {e}")
            return False
    
    def get_stats(self) -> Dict[str, any]:
        """Get WARP statistics."""
        return {
            'warp_enabled': self.warp_enabled,
            'is_connected': self.is_connected,
            'is_available': self.is_available(),
            'current_proxy': self.current_proxy,
            'available_proxies': len(self.proxy_urls),
            'current_ip': self.get_current_ip()
        }
    
    def install_warp(self) -> bool:
        """Install WARP CLI (Linux only)."""
        try:
            logger.info("📦 Installing WARP CLI...")
            
            # Check if running on Linux
            if os.name != 'posix':
                logger.error("❌ WARP installation only supported on Linux")
                return False
            
            # Install WARP
            commands = [
                "curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | sudo gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg",
                "echo 'deb [arch=amd64 signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(lsb_release -cs) main' | sudo tee /etc/apt/sources.list.d/cloudflare-client.list",
                "sudo apt update",
                "sudo apt install -y cloudflare-warp"
            ]
            
            for cmd in commands:
                result = subprocess.run(
                    cmd.split(), 
                    capture_output=True, 
                    text=True, 
                    timeout=60
                )
                
                if result.returncode != 0:
                    logger.error(f"❌ WARP installation failed at: {cmd}")
                    logger.error(f"Error: {result.stderr}")
                    return False
            
            logger.info("✅ WARP CLI installed successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error installing WARP: {e}")
            return False
    
    def register_warp(self) -> bool:
        """Register WARP (first-time setup)."""
        try:
            logger.info("📝 Registering WARP...")
            
            result = subprocess.run(
                ["warp-cli", "register"], 
                capture_output=True, 
                text=True, 
                timeout=30
            )
            
            if result.returncode == 0:
                logger.info("✅ WARP registered successfully")
                return True
            else:
                logger.error(f"❌ WARP registration failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error registering WARP: {e}")
            return False
