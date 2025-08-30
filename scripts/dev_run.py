#!/usr/bin/env python3
"""
scripts/dev_run.py
Development script with auto-reload for VSB Discord Bot
Enhanced for Docker compatibility on Windows
"""

import sys
import os
import subprocess
import time
import signal
from pathlib import Path
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver  # Better for Docker
from watchdog.events import FileSystemEventHandler
import threading
import logging
from datetime import datetime

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [DEV] - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

class BotReloader(FileSystemEventHandler):
    """Handles file system events and triggers bot restart"""
    
    def __init__(self):
        self.bot_process = None
        self.restart_lock = threading.Lock()
        self.last_restart = 0
        self.restart_cooldown = 2  # Increased cooldown for Docker
        
        # File patterns to watch
        self.watch_patterns = {'.py', '.json', '.yml', '.yaml', '.env'}
        self.ignore_patterns = {
            '__pycache__', '.git', '.pytest_cache', 'logs',
            '.pyc', '.pyo', '.pyd', '.db', '.log', '.tmp'
        }
        
    def should_restart(self, event_path: str) -> bool:
        """Check if file change should trigger restart"""
        path = Path(event_path)
        
        # Check if file has watched extension
        if not any(str(path).endswith(ext) for ext in self.watch_patterns):
            return False
            
        # Check if path contains ignored patterns
        if any(ignored in str(path) for ignored in self.ignore_patterns):
            return False
            
        # Check cooldown
        current_time = time.time()
        if current_time - self.last_restart < self.restart_cooldown:
            return False
            
        return True
        
    def on_modified(self, event):
        """Handle file modification events"""
        if event.is_directory:
            return
            
        if not self.should_restart(event.src_path):
            return
            
        logger.info(f"File changed: {os.path.relpath(event.src_path)}")
        self.restart_bot()
        
    def on_created(self, event):
        """Handle file creation events"""
        if event.is_directory:
            return
            
        if not self.should_restart(event.src_path):
            return
            
        logger.info(f"File created: {os.path.relpath(event.src_path)}")
        self.restart_bot()
        
    def start_bot(self):
        """Start the bot process"""
        with self.restart_lock:
            logger.info("Starting bot...")
            
            # Kill existing process if running
            if self.bot_process and self.bot_process.poll() is None:
                self.stop_bot()
                
            # Start new bot process
            env = os.environ.copy()
            
            # Set Python path to include current directory
            current_dir = str(Path.cwd())
            python_path = env.get('PYTHONPATH', '')
            if python_path:
                env['PYTHONPATH'] = f"{current_dir}:{python_path}"
            else:
                env['PYTHONPATH'] = current_dir
            
            # Add development environment variables if .env.dev exists
            dev_env_path = Path('.env.dev')
            if dev_env_path.exists():
                logger.info("Loading .env.dev")
                with open(dev_env_path) as f:
                    for line in f:
                        if '=' in line and not line.startswith('#'):
                            key, value = line.strip().split('=', 1)
                            env[key] = value
            
            try:
                # Try different ways to start the bot
                start_commands = [
                    [sys.executable, '-m', 'bot.main'],
                    [sys.executable, 'bot/main.py'],
                    [sys.executable, '-c', 'import sys; sys.path.append("."); import bot.main']
                ]
                
                for cmd in start_commands:
                    try:
                        logger.info(f"Attempting to start with: {' '.join(cmd)}")
                        self.bot_process = subprocess.Popen(
                            cmd,
                            env=env,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            universal_newlines=True,
                            bufsize=1,
                            cwd=current_dir
                        )
                        
                        # Wait a moment to see if it starts successfully
                        time.sleep(1)
                        if self.bot_process.poll() is None:
                            # Process is still running, success!
                            break
                        else:
                            # Process exited immediately, capture error output
                            try:
                                output, _ = self.bot_process.communicate(timeout=2)
                                logger.error(f"Start failed with output: {output}")
                            except subprocess.TimeoutExpired:
                                self.bot_process.kill()
                                output, _ = self.bot_process.communicate()
                                logger.error(f"Start failed (timeout): {output}")
                            continue
                            
                    except Exception as e:
                        logger.error(f"Command failed with exception: {e}")
                        continue
                
                if self.bot_process and self.bot_process.poll() is None:
                    # Start thread to read bot output
                    output_thread = threading.Thread(
                        target=self.read_bot_output,
                        daemon=True
                    )
                    output_thread.start()
                    
                    self.last_restart = time.time()
                    logger.info("Bot started successfully (PID: %d)", self.bot_process.pid)
                else:
                    logger.error("All start attempts failed")
                    
            except Exception as e:
                logger.error(f"Failed to start bot: {e}")
                
    def read_bot_output(self):
        """Read and display bot output"""
        if not self.bot_process:
            return
            
        try:
            for line in self.bot_process.stdout:
                if line:
                    print(f"  [BOT] {line.rstrip()}")
        except Exception:
            pass  # Process ended
            
    def stop_bot(self):
        """Stop the bot process gracefully"""
        if not self.bot_process:
            return
            
        logger.info("Stopping bot...")
        
        # Try graceful shutdown first
        self.bot_process.terminate()
        
        # Wait up to 5 seconds for graceful shutdown
        try:
            self.bot_process.wait(timeout=5)
            logger.info("Bot stopped gracefully")
        except subprocess.TimeoutExpired:
            # Force kill if graceful shutdown failed
            logger.warning("Forcing bot shutdown...")
            self.bot_process.kill()
            self.bot_process.wait()
            logger.info("Bot forcefully stopped")
            
    def restart_bot(self):
        """Restart the bot process"""
        logger.info("Restarting bot...")
        self.start_bot()

class DevRunner:
    """Main development runner with file watching"""
    
    def __init__(self):
        # Use PollingObserver for better Docker compatibility
        self.observer = PollingObserver()
        self.handler = BotReloader()
        self.running = True
        
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info("\nShutdown signal received")
        self.shutdown()
        
    def shutdown(self):
        """Shutdown the development runner"""
        self.running = False
        logger.info("Stopping file watcher...")
        self.observer.stop()
        self.handler.stop_bot()
        logger.info("Development runner stopped")
        sys.exit(0)
        
    def run(self):
        """Start the development runner"""
        print("""
╔══════════════════════════════════════════════╗
║     VSB Discord Bot - Development Mode       ║
║                                               ║
║  Watching for file changes...                ║
║  Auto-reload enabled (Polling mode)          ║
║  Press Ctrl+C to stop                        ║
╚══════════════════════════════════════════════╝
        """)
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Setup file watching
        watch_paths = []
        
        # Watch bot directory
        if Path('bot').exists():
            watch_paths.append(Path('bot'))
        
        # Watch webserver.py if it exists (as file, not directory)
        if Path('webserver.py').exists():
            watch_paths.append(Path('webserver.py').parent)  # Watch parent dir
        
        # Watch config files
        config_files = [
            Path('config.json'),
            Path('auth.json'),
            Path('.env'),
            Path('.env.dev')
        ]
        
        for config_file in config_files:
            if config_file.exists():
                watch_paths.append(config_file.parent)
        
        # Remove duplicates and schedule observers
        unique_paths = list(set(watch_paths))
        
        for path in unique_paths:
            if path.exists():
                self.observer.schedule(
                    self.handler,
                    str(path),
                    recursive=True
                )
                logger.info(f"Watching: {path}/")
        
        # Start bot
        self.handler.start_bot()
        
        # Start file observer
        self.observer.start()
        logger.info("File watcher started (polling every 1 second)")
        
        # Keep running
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.shutdown()
            
        self.observer.join()

def main():
    """Main entry point"""
    # Check if we're in the project root
    if not Path('bot').exists():
        logger.error("Error: Must run from project root directory")
        logger.error("   Usage: python scripts/dev_run.py")
        sys.exit(1)
        
    # Check dependencies
    try:
        import watchdog
    except ImportError:
        logger.error("Error: watchdog not installed")
        logger.error("   Install: pip install watchdog")
        sys.exit(1)
        
    # Show current working directory
    logger.info(f"Working directory: {Path.cwd()}")
    logger.info(f"Python path: {sys.path[:3]}...")  # Show first 3 entries
        
    # Run development server
    runner = DevRunner()
    runner.run()

if __name__ == '__main__':
    main()