"""
Pihu — Network Guard
Default-deny egress policy enforcement for sandboxes and tool calls.

Controls which domains/IPs the agent can reach, enforces download
validation, blocks localhost/private-network access, and logs all egress.
"""

import re
import ipaddress
from enum import Enum
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from logger import get_logger

log = get_logger("NET-GUARD")


class NetworkClass(Enum):
    """Network access classes for different trust contexts."""
    NONE = "none"                        # No network access at all
    APPROVED_APIS_ONLY = "approved_apis" # Only allowlisted API endpoints
    BROWSER_WITH_WINDOW = "browser"      # Browser with user-visible window
    FULL_WITH_APPROVAL = "full"          # Full network, requires explicit approval


@dataclass
class EgressAssessment:
    """Result of network egress evaluation."""
    url: str
    domain: str
    is_allowed: bool
    network_class: NetworkClass
    reasons: list[str]
    is_private_network: bool
    is_localhost: bool
    blocked: bool
    requires_approval: bool


# ──────────────────────────────────────────────
# PRIVATE NETWORK RANGES
# ──────────────────────────────────────────────

PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fe80::/10"),        # IPv6 link-local
    ipaddress.ip_network("fc00::/7"),         # IPv6 ULA
]

LOCALHOST_PATTERNS = {
    "localhost", "127.0.0.1", "::1",
    "0.0.0.0", "[::1]", "local",
}

# Dangerous MIME types for downloads
BLOCKED_MIME_TYPES = {
    "application/x-exe", "application/x-executable",
    "application/x-msdos-program", "application/x-msdownload",
    "application/x-batch", "application/x-sh",
    "application/vnd.microsoft.portable-executable",
    "application/x-dosexec",
}

# Maximum download size (50MB default)
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024

# Maximum redirects
MAX_REDIRECTS = 5


class NetworkGuard:
    """Deterministic network egress policy enforcer."""

    def __init__(
        self,
        allowed_domains: list[str] = None,
        blocked_domains: list[str] = None,
        default_class: NetworkClass = NetworkClass.NONE,
        allow_localhost: bool = False,
        allow_private_network: bool = False,
        max_download_bytes: int = MAX_DOWNLOAD_BYTES,
    ):
        self.allowed_domains = set(d.lower() for d in (allowed_domains or []))
        self.blocked_domains = set(d.lower() for d in (blocked_domains or []))
        self.default_class = default_class
        self.allow_localhost = allow_localhost
        self.allow_private_network = allow_private_network
        self.max_download_bytes = max_download_bytes
        
        # Log access for forensics
        self._egress_log: list[dict] = []
        
        log.info("🌐 NetworkGuard initialized | default=%s | allowed_domains=%d | localhost=%s",
                 default_class.value, len(self.allowed_domains), allow_localhost)

    def assess(self, url: str, network_class: NetworkClass = None) -> EgressAssessment:
        """Evaluate whether a URL is allowed under current network policy."""
        reasons = []
        active_class = network_class or self.default_class
        
        # Parse URL
        try:
            parsed = urlparse(url)
            domain = (parsed.hostname or "").lower()
            port = parsed.port
        except Exception as e:
            return EgressAssessment(
                url=url, domain="", is_allowed=False,
                network_class=active_class, reasons=[f"URL parse failed: {e}"],
                is_private_network=False, is_localhost=False,
                blocked=True, requires_approval=False,
            )
        
        # 1. No-network mode — deny everything
        if active_class == NetworkClass.NONE:
            reasons.append("Network class is NONE — all egress blocked")
            return EgressAssessment(
                url=url, domain=domain, is_allowed=False,
                network_class=active_class, reasons=reasons,
                is_private_network=False, is_localhost=False,
                blocked=True, requires_approval=False,
            )
        
        # 2. Localhost/loopback check
        is_localhost = domain in LOCALHOST_PATTERNS
        if not is_localhost and domain:
            try:
                ip = ipaddress.ip_address(domain)
                is_localhost = ip.is_loopback
            except ValueError:
                pass
        
        if is_localhost and not self.allow_localhost:
            reasons.append(f"Localhost access blocked: '{domain}'")
            return EgressAssessment(
                url=url, domain=domain, is_allowed=False,
                network_class=active_class, reasons=reasons,
                is_private_network=False, is_localhost=True,
                blocked=True, requires_approval=False,
            )
        
        # 3. Private network check
        is_private = False
        if domain:
            try:
                ip = ipaddress.ip_address(domain)
                is_private = any(ip in net for net in PRIVATE_NETWORKS)
            except ValueError:
                pass
        
        if is_private and not self.allow_private_network:
            reasons.append(f"Private network access blocked: '{domain}'")
            return EgressAssessment(
                url=url, domain=domain, is_allowed=False,
                network_class=active_class, reasons=reasons,
                is_private_network=True, is_localhost=is_localhost,
                blocked=True, requires_approval=False,
            )
        
        # 4. Blocked domain check
        if self._matches_domain_list(domain, self.blocked_domains):
            reasons.append(f"Domain '{domain}' is in blocked list")
            return EgressAssessment(
                url=url, domain=domain, is_allowed=False,
                network_class=active_class, reasons=reasons,
                is_private_network=is_private, is_localhost=is_localhost,
                blocked=True, requires_approval=False,
            )
        
        # 5. Allowlist enforcement (if we have an allowlist)
        if active_class == NetworkClass.APPROVED_APIS_ONLY:
            if self.allowed_domains and not self._matches_domain_list(domain, self.allowed_domains):
                reasons.append(f"Domain '{domain}' not in approved allowlist")
                return EgressAssessment(
                    url=url, domain=domain, is_allowed=False,
                    network_class=active_class, reasons=reasons,
                    is_private_network=is_private, is_localhost=is_localhost,
                    blocked=True, requires_approval=False,
                )
            reasons.append(f"Domain '{domain}' approved")
        
        # 6. Full access mode — allowed but requires approval
        if active_class == NetworkClass.FULL_WITH_APPROVAL:
            reasons.append("Full network access — requires user approval")
            return EgressAssessment(
                url=url, domain=domain, is_allowed=True,
                network_class=active_class, reasons=reasons,
                is_private_network=is_private, is_localhost=is_localhost,
                blocked=False, requires_approval=True,
            )
        
        # 7. Log egress
        self._log_egress(url, domain, active_class, allowed=True)
        
        return EgressAssessment(
            url=url, domain=domain, is_allowed=True,
            network_class=active_class, reasons=reasons,
            is_private_network=is_private, is_localhost=is_localhost,
            blocked=False, requires_approval=False,
        )

    @staticmethod
    def _matches_domain_list(domain: str, domain_list: set[str]) -> bool:
        """Check if domain matches any entry in the list (supports subdomain matching)."""
        if domain in domain_list:
            return True
        # Check if domain is a subdomain of any allowed domain
        for allowed in domain_list:
            if domain.endswith("." + allowed):
                return True
        return False

    def validate_download(self, content_length: Optional[int] = None,
                          content_type: Optional[str] = None,
                          redirect_count: int = 0) -> tuple[bool, str]:
        """Validate download before accepting content."""
        if content_length and content_length > self.max_download_bytes:
            return False, f"Download too large: {content_length} bytes (max: {self.max_download_bytes})"
        
        if content_type and content_type.lower() in BLOCKED_MIME_TYPES:
            return False, f"Blocked MIME type: {content_type}"
        
        if redirect_count > MAX_REDIRECTS:
            return False, f"Too many redirects: {redirect_count} (max: {MAX_REDIRECTS})"
        
        return True, "OK"

    def _log_egress(self, url: str, domain: str, network_class: NetworkClass, allowed: bool):
        """Record egress for forensic review."""
        import time
        entry = {
            "timestamp": time.time(),
            "url": url[:200],
            "domain": domain,
            "network_class": network_class.value,
            "allowed": allowed,
        }
        self._egress_log.append(entry)
        
        # Keep last 500
        if len(self._egress_log) > 500:
            self._egress_log = self._egress_log[-300:]

    def get_egress_log(self, limit: int = 50) -> list[dict]:
        """Return recent egress events."""
        return self._egress_log[-limit:]
