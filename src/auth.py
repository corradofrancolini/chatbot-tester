"""
Authentication Module - Handles different authentication types for chatbot testing.

Supports:
- HTTP Basic Auth
- Form-based login (username/password)
- SSO (Microsoft, Google)
- No auth (public endpoints)

Configuration is read from project.yaml under the 'auth' section.
"""

import os
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Literal
from playwright.async_api import Page, BrowserContext


@dataclass
class AuthConfig:
    """Authentication configuration from project.yaml"""
    type: Literal["none", "basic", "form", "sso"] = "none"

    # Basic Auth
    basic_username_env: str = ""
    basic_password_env: str = ""

    # Form Auth
    form_username_selector: str = ""
    form_password_selector: str = ""
    form_submit_selector: str = ""
    form_username_env: str = ""
    form_password_env: str = ""
    form_success_selector: str = ""  # Element that appears after successful login

    # SSO Auth
    sso_provider: Literal["microsoft", "google", ""] = ""
    sso_email_env: str = ""
    sso_password_env: str = ""
    sso_success_selector: str = ""

    # Timeouts
    timeout_ms: int = 30000

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "AuthConfig":
        """Create AuthConfig from dictionary (project.yaml)"""
        if not data:
            return cls()

        return cls(
            type=data.get("type", "none"),
            basic_username_env=data.get("basic_username_env", ""),
            basic_password_env=data.get("basic_password_env", ""),
            form_username_selector=data.get("form_username_selector", ""),
            form_password_selector=data.get("form_password_selector", ""),
            form_submit_selector=data.get("form_submit_selector", ""),
            form_username_env=data.get("form_username_env", ""),
            form_password_env=data.get("form_password_env", ""),
            form_success_selector=data.get("form_success_selector", ""),
            sso_provider=data.get("sso_provider", ""),
            sso_email_env=data.get("sso_email_env", ""),
            sso_password_env=data.get("sso_password_env", ""),
            sso_success_selector=data.get("sso_success_selector", ""),
            timeout_ms=data.get("timeout_ms", 30000),
        )


class AuthHandler(ABC):
    """Abstract base class for authentication handlers"""

    def __init__(self, config: AuthConfig):
        self.config = config

    @abstractmethod
    async def authenticate(self, page: Page, url: str) -> bool:
        """
        Perform authentication.

        Args:
            page: Playwright page
            url: Target URL

        Returns:
            True if authentication successful
        """
        pass

    def _get_env(self, env_name: str) -> str:
        """Get environment variable value"""
        if not env_name:
            return ""
        return os.environ.get(env_name, "")


class NoAuthHandler(AuthHandler):
    """Handler for public endpoints (no auth needed)"""

    async def authenticate(self, page: Page, url: str) -> bool:
        return True


class BasicAuthHandler(AuthHandler):
    """Handler for HTTP Basic Authentication"""

    async def authenticate(self, page: Page, url: str) -> bool:
        username = self._get_env(self.config.basic_username_env)
        password = self._get_env(self.config.basic_password_env)

        if not username or not password:
            print(f"Warning: Basic auth credentials not found in env vars "
                  f"({self.config.basic_username_env}, {self.config.basic_password_env})")
            return False

        # Set HTTP credentials for Basic Auth
        context = page.context
        await context.set_extra_http_headers({
            "Authorization": f"Basic {self._encode_basic_auth(username, password)}"
        })

        return True

    def _encode_basic_auth(self, username: str, password: str) -> str:
        """Encode credentials for Basic Auth header"""
        import base64
        credentials = f"{username}:{password}"
        return base64.b64encode(credentials.encode()).decode()


class FormAuthHandler(AuthHandler):
    """Handler for form-based login (username/password form)"""

    async def authenticate(self, page: Page, url: str) -> bool:
        username = self._get_env(self.config.form_username_env)
        password = self._get_env(self.config.form_password_env)

        if not username or not password:
            print(f"Warning: Form auth credentials not found in env vars "
                  f"({self.config.form_username_env}, {self.config.form_password_env})")
            return False

        try:
            # Navigate to URL first
            await page.goto(url, wait_until='networkidle', timeout=self.config.timeout_ms)

            # Check if already logged in
            if self.config.form_success_selector:
                try:
                    await page.wait_for_selector(
                        self.config.form_success_selector,
                        timeout=2000
                    )
                    print("Already logged in")
                    return True
                except:
                    pass  # Not logged in, continue with login

            # Wait for login form
            await page.wait_for_selector(
                self.config.form_username_selector,
                timeout=self.config.timeout_ms
            )

            # Fill credentials
            await page.fill(self.config.form_username_selector, username)
            await page.fill(self.config.form_password_selector, password)

            # Submit
            await page.click(self.config.form_submit_selector)

            # Wait for success
            if self.config.form_success_selector:
                await page.wait_for_selector(
                    self.config.form_success_selector,
                    timeout=self.config.timeout_ms
                )
            else:
                await page.wait_for_load_state('networkidle')

            print("Form login successful")
            return True

        except Exception as e:
            print(f"Form login failed: {e}")
            return False


class SSOAuthHandler(AuthHandler):
    """Handler for SSO authentication (Microsoft, Google)"""

    async def authenticate(self, page: Page, url: str) -> bool:
        email = self._get_env(self.config.sso_email_env)
        password = self._get_env(self.config.sso_password_env)

        if not email or not password:
            print(f"Warning: SSO credentials not found in env vars "
                  f"({self.config.sso_email_env}, {self.config.sso_password_env})")
            return False

        try:
            # Navigate to URL first
            await page.goto(url, wait_until='networkidle', timeout=self.config.timeout_ms)

            # Check if already logged in
            if self.config.sso_success_selector:
                try:
                    await page.wait_for_selector(
                        self.config.sso_success_selector,
                        timeout=2000
                    )
                    print("Already logged in via SSO")
                    return True
                except:
                    pass

            if self.config.sso_provider == "microsoft":
                return await self._microsoft_login(page, email, password)
            elif self.config.sso_provider == "google":
                return await self._google_login(page, email, password)
            else:
                print(f"Unknown SSO provider: {self.config.sso_provider}")
                return False

        except Exception as e:
            print(f"SSO login failed: {e}")
            return False

    async def _microsoft_login(self, page: Page, email: str, password: str) -> bool:
        """Handle Microsoft/Azure AD login flow"""
        try:
            # Wait for email input (Microsoft login page)
            email_selector = 'input[type="email"], input[name="loginfmt"]'
            await page.wait_for_selector(email_selector, timeout=self.config.timeout_ms)

            # Enter email
            await page.fill(email_selector, email)
            await page.click('input[type="submit"], button[type="submit"]')

            # Wait for password input
            await asyncio.sleep(1)
            password_selector = 'input[type="password"], input[name="passwd"]'
            await page.wait_for_selector(password_selector, timeout=self.config.timeout_ms)

            # Enter password
            await page.fill(password_selector, password)
            await page.click('input[type="submit"], button[type="submit"]')

            # Handle "Stay signed in?" prompt if it appears
            await asyncio.sleep(2)
            try:
                stay_signed_in = await page.query_selector('input[id="idBtn_Back"], button:has-text("No")')
                if stay_signed_in:
                    await stay_signed_in.click()
            except:
                pass

            # Wait for redirect back to app
            if self.config.sso_success_selector:
                await page.wait_for_selector(
                    self.config.sso_success_selector,
                    timeout=self.config.timeout_ms
                )
            else:
                await page.wait_for_load_state('networkidle')

            print("Microsoft SSO login successful")
            return True

        except Exception as e:
            print(f"Microsoft login failed: {e}")
            return False

    async def _google_login(self, page: Page, email: str, password: str) -> bool:
        """Handle Google login flow"""
        try:
            # Wait for email input
            email_selector = 'input[type="email"]'
            await page.wait_for_selector(email_selector, timeout=self.config.timeout_ms)

            # Enter email
            await page.fill(email_selector, email)
            await page.click('#identifierNext, button:has-text("Next")')

            # Wait for password input
            await asyncio.sleep(2)
            password_selector = 'input[type="password"]'
            await page.wait_for_selector(password_selector, timeout=self.config.timeout_ms)

            # Enter password
            await page.fill(password_selector, password)
            await page.click('#passwordNext, button:has-text("Next")')

            # Wait for redirect back to app
            if self.config.sso_success_selector:
                await page.wait_for_selector(
                    self.config.sso_success_selector,
                    timeout=self.config.timeout_ms
                )
            else:
                await page.wait_for_load_state('networkidle')

            print("Google SSO login successful")
            return True

        except Exception as e:
            print(f"Google login failed: {e}")
            return False


def get_auth_handler(config: AuthConfig) -> AuthHandler:
    """Factory function to get appropriate auth handler"""
    handlers = {
        "none": NoAuthHandler,
        "basic": BasicAuthHandler,
        "form": FormAuthHandler,
        "sso": SSOAuthHandler,
    }

    handler_class = handlers.get(config.type, NoAuthHandler)
    return handler_class(config)


async def authenticate(page: Page, url: str, auth_config: Optional[Dict[str, Any]]) -> bool:
    """
    Main authentication function.

    Args:
        page: Playwright page
        url: Target URL
        auth_config: Auth configuration from project.yaml

    Returns:
        True if authentication successful (or no auth needed)
    """
    config = AuthConfig.from_dict(auth_config)
    handler = get_auth_handler(config)
    return await handler.authenticate(page, url)
