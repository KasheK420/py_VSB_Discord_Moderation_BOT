"""
bot/utils/webserver.py
CAS callback web server for VSB Discord Bot with comprehensive logging
Handles CAS callbacks with beautiful success page
"""

from aiohttp import web
import aiohttp
import asyncio
import logging
from typing import Optional
from pathlib import Path
from ..services.logging_service import LogLevel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OAuthWebServer:
    def __init__(self, auth_service, host='0.0.0.0', port=80):
        self.auth_service = auth_service
        self.host = host
        self.port = port
        self.app = web.Application()
        self.request_count = 0
        self.setup_routes()
        
    def setup_routes(self):
        """Setup web server routes"""
        self.app.router.add_get('/', self.handle_root)
        self.app.router.add_get('/callback', self.handle_callback)
        self.app.router.add_get('/health', self.handle_health)
        
    async def handle_root(self, request: web.Request) -> web.Response:
        """Root endpoint - redirects to CAS if Discord ID provided"""
        self.request_count += 1
        discord_id = request.query.get('_')
        client_ip = request.remote
        
        # Log root access
        if self.auth_service.embed_logger:
            await self.auth_service.embed_logger.log_custom(
                service="Web Server",
                title="Root Endpoint Accessed",
                description="User accessed web server root endpoint",
                level=LogLevel.INFO,
                fields={
                    "Endpoint": "/",
                    "Client IP": client_ip,
                    "Discord ID": discord_id if discord_id else "Missing",
                    "Request Count": str(self.request_count),
                    "User Agent": request.headers.get('User-Agent', 'Unknown')[:100]
                }
            )
        
        if not discord_id:
            if self.auth_service.embed_logger:
                await self.auth_service.embed_logger.log_custom(
                    service="Web Server",
                    title="Bad Request - Missing Discord ID",
                    description="Root endpoint accessed without Discord ID parameter",
                    level=LogLevel.WARNING,
                    fields={
                        "Client IP": client_ip,
                        "Request Count": str(self.request_count),
                        "Error": "Missing Discord ID parameter (_)"
                    }
                )
            
            return web.Response(
                text="Missing Discord ID parameter",
                status=400,
                headers={'Content-Type': 'text/plain'}
            )
        
        # Generate state for OAuth flow
        state = f"discord_{discord_id}"
        self.auth_service.pending_auths[state] = {
            'discord_id': discord_id,
            'timestamp': asyncio.get_event_loop().time()
        }
        
        # Build CAS login URL
        cas_params = {
            'service': self.auth_service.service_url,
            'state': state
        }
        
        import urllib.parse
        cas_login_url = f"{self.auth_service.cas_login_url}?" + urllib.parse.urlencode(cas_params)
        
        # Log redirect
        if self.auth_service.embed_logger:
            await self.auth_service.embed_logger.log_custom(
                service="Web Server",
                title="CAS Redirect Initiated",
                description="Redirecting user to CAS authentication",
                level=LogLevel.INFO,
                fields={
                    "Discord ID": discord_id,
                    "State": state,
                    "CAS URL": self.auth_service.cas_login_url,
                    "Service URL": self.auth_service.service_url
                }
            )
        
        # Redirect to CAS
        return web.Response(
            status=302,
            headers={'Location': cas_login_url}
        )
        
    async def handle_callback(self, request: web.Request) -> web.Response:
        """Handle CAS callback"""
        self.request_count += 1
        ticket = request.query.get('ticket')
        state = request.query.get('state', request.query.get('_'))
        client_ip = request.remote
        
        # Log callback attempt
        if self.auth_service.embed_logger:
            await self.auth_service.embed_logger.log_custom(
                service="Web Server",
                title="CAS Callback Received",
                description="Processing CAS authentication callback",
                level=LogLevel.INFO,
                fields={
                    "Endpoint": "/callback",
                    "Client IP": client_ip,
                    "Has Ticket": "Yes" if ticket else "No",
                    "State": state if state else "Missing",
                    "Request Count": str(self.request_count)
                }
            )
        
        if not ticket:
            if self.auth_service.embed_logger:
                await self.auth_service.embed_logger.log_custom(
                    service="Web Server",
                    title="Callback Error - Missing Ticket",
                    description="CAS callback received without required ticket parameter",
                    level=LogLevel.ERROR,
                    fields={
                        "Client IP": client_ip,
                        "State": state if state else "None",
                        "Error": "Missing CAS ticket parameter"
                    }
                )
            
            return web.Response(
                text="Authentication failed: Missing ticket",
                status=400,
                headers={'Content-Type': 'text/plain'}
            )
        
        if not state or not state.startswith('discord_'):
            if self.auth_service.embed_logger:
                await self.auth_service.embed_logger.log_custom(
                    service="Web Server",
                    title="Callback Error - Invalid State",
                    description="CAS callback received with invalid state parameter",
                    level=LogLevel.ERROR,
                    fields={
                        "Client IP": client_ip,
                        "State": state if state else "None",
                        "Ticket": "Present" if ticket else "Missing",
                        "Error": "Invalid or missing state parameter"
                    }
                )
            
            return web.Response(
                text="Authentication failed: Invalid state",
                status=400,
                headers={'Content-Type': 'text/plain'}
            )
        
        # Process the authentication
        try:
            result = await self.auth_service.process_cas_callback(ticket, state)
            
            if result['success']:
                # Success page
                html_content = self.generate_success_page(result['user'])
                return web.Response(
                    text=html_content,
                    status=200,
                    headers={'Content-Type': 'text/html; charset=utf-8'}
                )
            else:
                # Error page
                html_content = self.generate_error_page(result.get('error', 'Authentication failed'))
                return web.Response(
                    text=html_content,
                    status=400,
                    headers={'Content-Type': 'text/html; charset=utf-8'}
                )
                
        except Exception as e:
            logger.error(f"Error processing CAS callback: {e}")
            
            if self.auth_service.embed_logger:
                await self.auth_service.embed_logger.log_error(
                    service="Web Server",
                    error=e,
                    context=f"Error processing CAS callback for state: {state}"
                )
            
            html_content = self.generate_error_page("Internal server error during authentication")
            return web.Response(
                text=html_content,
                status=500,
                headers={'Content-Type': 'text/html; charset=utf-8'}
            )
        
    async def handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint"""
        self.request_count += 1
        
        uptime_info = {
            "status": "healthy",
            "service": "VSB Discord OAuth Server",
            "requests_served": self.request_count,
            "auth_service": "connected" if self.auth_service else "disconnected"
        }
        
        # Log health check (but only occasionally to avoid spam)
        if self.request_count % 100 == 0 and self.auth_service.embed_logger:
            await self.auth_service.embed_logger.log_custom(
                service="Web Server",
                title="Health Check",
                description="Health endpoint accessed - system status",
                level=LogLevel.INFO,
                fields={
                    "Status": "✅ Healthy",
                    "Total Requests": str(self.request_count),
                    "Server": f"{self.host}:{self.port}",
                    "Auth Service": "Connected" if self.auth_service else "Disconnected"
                }
            )
        
        return web.json_response(uptime_info)
        
    async def start(self):
        """Start the web server"""
        try:
            runner = web.AppRunner(self.app)
            await runner.setup()
            site = web.TCPSite(runner, self.host, self.port)
            await site.start()
            
            logger.info(f"OAuth web server started on {self.host}:{self.port}")
            
            if self.auth_service.embed_logger:
                await self.auth_service.embed_logger.log_custom(
                    service="Web Server",
                    title="Web Server Started",
                    description="OAuth callback web server is now running",
                    level=LogLevel.SUCCESS,
                    fields={
                        "Host": self.host,
                        "Port": str(self.port),
                        "Endpoints": "/, /callback, /health",
                        "Status": "🟢 Running",
                        "Auth Service": "Connected" if self.auth_service else "Disconnected"
                    }
                )
        except Exception as e:
            logger.error(f"Failed to start web server: {e}")
            if self.auth_service.embed_logger:
                await self.auth_service.embed_logger.log_error(
                    service="Web Server",
                    error=e,
                    context=f"Failed to start web server on {self.host}:{self.port}"
                )
            raise

    async def stop(self):
        """Stop the web server"""
        if self.auth_service.embed_logger:
            await self.auth_service.embed_logger.log_custom(
                service="Web Server",
                title="Web Server Stopping",
                description="OAuth callback web server is shutting down",
                level=LogLevel.WARNING,
                fields={
                    "Total Requests Served": str(self.request_count),
                    "Host": self.host,
                    "Port": str(self.port),
                    "Status": "🔴 Shutting down"
                }
            )
        logger.info(f"OAuth web server on {self.host}:{self.port} shutting down")

    def generate_success_page(self, user_info: dict) -> str:
        """Generate beautiful success page"""
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Authentication Successful - VSB Discord</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #333;
        }}
        
        .success-container {{
            background: white;
            padding: 3rem;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            text-align: center;
            max-width: 500px;
            width: 90%;
        }}
        
        .success-icon {{
            width: 80px;
            height: 80px;
            background: #4CAF50;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 2rem;
            font-size: 2.5rem;
        }}
        
        .success-title {{
            font-size: 2rem;
            color: #2c3e50;
            margin-bottom: 1rem;
            font-weight: 600;
        }}
        
        .success-message {{
            font-size: 1.1rem;
            color: #666;
            margin-bottom: 2rem;
            line-height: 1.6;
        }}
        
        .user-info {{
            background: #f8f9fa;
            padding: 1.5rem;
            border-radius: 12px;
            margin-bottom: 2rem;
        }}
        
        .user-detail {{
            margin-bottom: 0.5rem;
            font-size: 1rem;
        }}
        
        .user-detail strong {{
            color: #2c3e50;
        }}
        
        .close-instruction {{
            color: #666;
            font-style: italic;
            font-size: 0.9rem;
        }}
        
        .vsb-logo {{
            width: 100px;
            opacity: 0.7;
            margin-top: 2rem;
        }}
    </style>
</head>
<body>
    <div class="success-container">
        <div class="success-icon">
            ✅
        </div>
        
        <h1 class="success-title">Authentication Successful!</h1>
        
        <div class="success-message">
            Your VSB account has been successfully linked to Discord. You now have access to all verified features in the VSB Discord server.
        </div>
        
        <div class="user-info">
            <div class="user-detail"><strong>Name:</strong> {user_info.get('display_name', 'Not provided')}</div>
            <div class="user-detail"><strong>Login:</strong> {user_info.get('login', 'Not provided')}</div>
            <div class="user-detail"><strong>Status:</strong> Verified ✅</div>
            <div class="user-detail"><strong>Linked:</strong> {user_info.get('linked_at', 'Just now')}</div>
        </div>
        
        <p class="close-instruction">
            You can safely close this window and return to Discord.
        </p>
        
        <div class="vsb-logo">
            🎓 VSB-TUO
        </div>
    </div>
</body>
</html>
        """

    def generate_error_page(self, error_message: str) -> str:
        """Generate beautiful error page"""
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Authentication Error - VSB Discord</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #ff7b7b 0%, #f06292 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #333;
        }}
        
        .error-container {{
            background: white;
            padding: 3rem;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            text-align: center;
            max-width: 500px;
            width: 90%;
        }}
        
        .error-icon {{
            width: 80px;
            height: 80px;
            background: #f44336;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 2rem;
            font-size: 2.5rem;
        }}
        
        .error-title {{
            font-size: 2rem;
            color: #2c3e50;
            margin-bottom: 1rem;
            font-weight: 600;
        }}
        
        .error-message {{
            font-size: 1.1rem;
            color: #666;
            margin-bottom: 2rem;
            line-height: 1.6;
            background: #fff3cd;
            padding: 1rem;
            border-radius: 8px;
            border-left: 4px solid #ffc107;
        }}
        
        .help-text {{
            color: #666;
            font-size: 0.95rem;
            line-height: 1.5;
            margin-bottom: 2rem;
        }}
        
        .contact-info {{
            background: #f8f9fa;
            padding: 1.5rem;
            border-radius: 12px;
            margin-bottom: 1rem;
            font-size: 0.9rem;
        }}
        
        .retry-instruction {{
            color: #666;
            font-style: italic;
            font-size: 0.9rem;
        }}
    </style>
</head>
<body>
    <div class="error-container">
        <div class="error-icon">
            ❌
        </div>
        
        <h1 class="error-title">Authentication Failed</h1>
        
        <div class="error-message">
            {error_message}
        </div>
        
        <div class="help-text">
            This error typically occurs when:<br>
            • The authentication link has expired<br>
            • Your VSB account credentials are invalid<br>
            • There was a temporary server issue
        </div>
        
        <div class="contact-info">
            <strong>Need help?</strong><br>
            Contact the Discord server administrators or try the authentication process again.
        </div>
        
        <p class="retry-instruction">
            You can close this window and try linking your account again from Discord.
        </p>
    </div>
</body>
</html>
        """