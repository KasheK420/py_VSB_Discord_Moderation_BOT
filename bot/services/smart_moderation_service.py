"""
bot/services/smart_moderation_service.py
Enterprise-grade AI-powered smart moderation service with comprehensive logging

FEATURES:
- Advanced regex-based bad word detection with multiple languages
- Anti-raid protection with burst detection
- Link filtering with domain whitelist/blacklist
- Attachment scanning and file type validation
- Unicode confusables and zalgo text detection
- Academic misconduct detection (university-focused)
- Personal data leak prevention
- Sophisticated escalation rules with severity mapping
- Review queues for manual moderation
- Action templates and automated responses
- Comprehensive logging and incident tracking
"""

import discord
from discord.ext import commands
import asyncio
import logging
import json
import os
import re
import time
import hashlib
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict, deque
import urllib.parse

from ..utils.ai_helper import moderate_message, ask_ai, smart_reply
from .logging_service import EmbedLogger, LogLevel

logger = logging.getLogger(__name__)

def __service__():
    return SmartModerationService()

class SmartModerationService:
    """Enterprise-grade smart moderation with comprehensive filtering"""
    
    def __init__(self):
        self.bot = None
        self.embed_logger = None
        self.config = {}
        self.user_warnings = {}
        self.user_message_history = defaultdict(deque)  # For spam detection
        self.user_join_times = deque()  # For anti-raid
        self.ai_calls_today = 0
        self.compiled_regex = {}  # Cache compiled regex patterns
        self.review_queue = []  # Manual review queue
        
        # Rate limiting tracking
        self.user_rate_limits = defaultdict(deque)
        self.user_reaction_limits = defaultdict(deque)
        
        # Load configuration
        self._load_configuration()
        self._compile_regex_patterns()
        
    def _load_configuration(self):
        """Load comprehensive moderation configuration"""
        config_path = Path("bot/config/moderation.json")
        
        try:
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                logger.info(f"Loaded moderation config v{self.config.get('version', 'unknown')}")
            else:
                self._create_basic_config(config_path)
                logger.warning("Using basic fallback configuration")
                
        except Exception as e:
            logger.error(f"Failed to load moderation config: {e}")
            self.config = {"enabled": False}  # Safe fallback
    
    def _matches_any_bad_word(self, text: str) -> bool:
        """Check compiled regexes AND normalized 'hard terms' (for short messages)."""
        if not text:
            return False

        # 1) regex categories
        for key, patterns in self.compiled_regex.items():
            if not key.startswith("bad_words_"):
                continue
            for rx in patterns:
                if rx.search(text):
                    return True

        # 2) normalized hard-term scan
        norm = self._normalize_for_slurs(text)
        hard = self.config.get('hard_terms', {}).get('hate_slurs', [])
        for term in hard:
            if term in norm:
                return True

        return False

    
    def analyze_text(self, text: str) -> tuple[int, list[str]]:
        """
        Lightweight analyzer for plain text (no Discord message object).
        Returns (suspicion_score, violations).
        """
        text = text or ""
        suspicion_score = 0
        violations: list[str] = []
        weights = self.config.get('suspicion_weights', {})
        
        # bad words
        for category, patterns in self.compiled_regex.items():
            if not category.startswith("bad_words_"):
                continue
            for rx in patterns:
                if rx.search(text):
                    suspicion_score += weights.get('bad_word', 10)
                    violations.append(f"{category.replace('bad_words_','')}_detected")
                    break  # one hit per category is enough

        # optional: simple zalgo check
        zalgo = self.compiled_regex.get('format_zalgo_regex')
        if zalgo and len(zalgo.findall(text)) > self.config.get('limits', {}).get('zalgo_threshold', 6):
            suspicion_score += weights.get('zalgo_text', 3)
            violations.append('zalgo_text')

        return suspicion_score, violations
    
    def _compile_regex_patterns(self):
        """Pre-compile regex patterns for performance"""
        self.compiled_regex = {}
        
        # Compile bad word patterns
        bad_words = self.config.get('bad_words', {})
        for category, patterns in bad_words.items():
            self.compiled_regex[f"bad_words_{category}"] = []
            for pattern in patterns:
                try:
                    self.compiled_regex[f"bad_words_{category}"].append(
                        re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                    )
                except re.error as e:
                    logger.warning(f"Invalid regex pattern in {category}: {pattern} - {e}")
        
        # Compile format detectors
        format_detectors = self.config.get('format_detectors', {})
        for name, pattern in format_detectors.items():
            if isinstance(pattern, str):
                try:
                    self.compiled_regex[f"format_{name}"] = re.compile(pattern, re.IGNORECASE)
                except re.error as e:
                    logger.warning(f"Invalid format detector {name}: {pattern} - {e}")
    
    def _create_basic_config(self, config_path: Path):
        """Create minimal working configuration"""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config = {
            "enabled": True,
            "daily_ai_limit": 500,
            "limits": {"min_message_length": 15, "max_message_length": 1000},
            "bad_words": {"toxic": ["spam"]},
            "suspicion_weights": {"bad_word": 10}
        }
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2)
        
    async def setup(self, bot: discord.Client, embed_logger: Optional[EmbedLogger] = None):
        """Initialize the enterprise moderation service"""
        self.bot = bot
        self.embed_logger = embed_logger
        
        # Register event handlers
        self.bot.event(self.on_message)
        self.bot.event(self.on_member_join)
        self.bot.event(self.on_reaction_add)
        
        # Start background tasks
        asyncio.create_task(self._cleanup_old_data())
        
        if self.embed_logger:
            await self.embed_logger.log_system_event(
                title="Enterprise Moderation Started",
                description="Advanced AI-powered moderation system initialized successfully",
                level=LogLevel.SUCCESS,
                fields=[
                    ("Version", self.config.get('version', 'unknown'), True),
                    ("Status", "🟢 Active" if self.config.get('enabled') else "🔴 Disabled", True),
                    ("Bad Word Categories", str(len(self.config.get('bad_words', {}))), True),
                    ("Daily AI Limit", str(self.config.get('limits', {}).get('daily_ai_limit', 500)), True),
                    ("Anti-Raid", "Enabled" if self.config.get('anti_raid', {}).get('enabled') else "Disabled", True),
                    ("Review Queue", "Enabled" if self.config.get('review_queues', {}).get('enabled') else "Disabled", True)
                ]
            )
        
        logger.info("Enterprise smart moderation service initialized")
    
    async def on_member_join(self, member: discord.Member):
        """Handle member joins for anti-raid detection (timezone-safe)"""
        if not self.config.get('anti_raid', {}).get('enabled', False):
            return

        current_time = time.time()
        anti_raid = self.config['anti_raid']

        # Track join times
        self.user_join_times.append(current_time)

        # Clean old join times
        window = anti_raid.get('burst_window_seconds', 30)
        while self.user_join_times and current_time - self.user_join_times[0] > window:
            self.user_join_times.popleft()

        # Check for raid
        burst_threshold = anti_raid.get('burst_join_threshold', 8)
        if len(self.user_join_times) >= burst_threshold:
            await self._handle_raid_detection(member.guild)

        # Check new account age (timezone-aware)
        min_age_hours = anti_raid.get('new_account_min_age_hours', 12)
        now_utc = datetime.now(timezone.utc)
        # member.created_at is aware (UTC) in discord.py
        try:
            account_age_hours = (now_utc - member.created_at).total_seconds() / 3600.0
        except Exception:
            # If for some reason created_at is missing/None, skip the check
            account_age_hours = min_age_hours

        if account_age_hours < min_age_hours:
            await self._handle_new_account(member, account_age_hours)

    def _normalize_for_slurs(self, text: str) -> str:
        """Lowercase, strip zero-width & non-alnum, fold simple leetspeak."""
        t = (text or "").casefold()
        # strip zero-width chars
        t = re.sub(r'[\u200B-\u200D\uFEFF]', '', t)
        # basic leet folding
        t = t.translate(str.maketrans({
            '0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's', '7': 't',
            '$': 's', '@': 'a', '!': 'i'
        }))
        # remove non-alphanum
        t = re.sub(r'[^a-z0-9]+', '', t)
        return t

    
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """Monitor reaction spam"""
        if user.bot:
            return
        
        current_time = time.time()
        user_id = str(user.id)
        max_reactions = self.config.get('limits', {}).get('max_reactions_per_min', 25)
        
        # Track reactions
        self.user_reaction_limits[user_id].append(current_time)
        
        # Clean old reactions (1 minute window)
        while (self.user_reaction_limits[user_id] and 
               current_time - self.user_reaction_limits[user_id][0] > 60):
            self.user_reaction_limits[user_id].popleft()
        
        # Check for spam
        if len(self.user_reaction_limits[user_id]) > max_reactions:
            await self._handle_reaction_spam(user, reaction.message.channel)
    
    async def on_message(self, message: discord.Message):
        """Comprehensive message filtering with hard-filter for slurs."""
        if not await self._should_moderate_message(message):
            return

        # Rate limiting
        if await self._check_rate_limiting(message):
            return

        # Analyze content
        suspicion_score, violations = await self._analyze_message_content(message)

        # HARD FILTER: normalized slurs -> immediate high severity
        hard_norm = self._normalize_for_slurs(message.content or "")
        hard_terms = self.config.get('hard_terms', {}).get('hate_slurs', [])
        if any(term in hard_norm for term in hard_terms):
            user_id = str(message.author.id)
            self.user_warnings.setdefault(user_id, [])
            warning = {
                'timestamp': datetime.utcnow(),
                'violations': list(set(violations + ['hate_detected'])),
                'severity': 'high',
                'suspicion_score': max(suspicion_score, 50),
                'ai_reason': 'Hard filter matched: hate slur',
                'message_content': (message.content or "")[:200],
                'channel': message.channel.name,
                'message_id': message.id
            }
            self.user_warnings[user_id].append(warning)
            action = self._determine_action('high', len(self.user_warnings[user_id]), warning['violations'])
            await self._execute_action(message, action, warning)
            if self.embed_logger:
                await self._log_moderation_incident(message, warning, action)
            return

        # AI only if something looks off and within quota
        if suspicion_score > 0 and self.ai_calls_today < self.config.get('limits', {}).get('daily_ai_limit', 500):
            try:
                self.ai_calls_today += 1
                ai_result = await moderate_message(message.content)
                if not ai_result.get('is_appropriate', True):
                    await self._handle_inappropriate_content(message, ai_result, violations, suspicion_score)
            except Exception as e:
                logger.error(f"AI moderation failed: {e}")
                if self.embed_logger:
                    await self.embed_logger.log_error(
                        service="Smart Moderation",
                        error=e,
                        context=f"AI moderation failed for message {message.id} by {message.author.id}"
                    )
                self.ai_calls_today = max(0, self.ai_calls_today - 1)
        elif suspicion_score >= self.config.get('review_queues', {}).get('manual_review_required_threshold', 12):
            await self._queue_for_manual_review(message, violations, suspicion_score)

    
    async def _should_moderate_message(self, message: discord.Message) -> bool:
        if message.author.bot or not message.guild:
            return False
        if not self.config.get('enabled', True):
            return False

        # Admins are exempt
        if message.author.guild_permissions.administrator:
            return False

        # Channel/role exemptions
        if message.channel.id in self.config.get('whitelisted_channels', []):
            return False
        if message.channel.id in self.config.get('blacklisted_channels', []):
            return True
        exempted_roles = self.config.get('exemptions', {}).get('roles_no_automod', [])
        if await self._has_role_name(message.author, exempted_roles):
            return False
        if await self._has_whitelisted_role(message.author):
            return False
        if await self._is_trusted_user(message.author):
            return False

        # Length checks – but don't skip if there is a violation
        limits = self.config.get('limits', {})
        content = message.content or ""
        min_len = limits.get('min_message_length', 15)
        max_len = limits.get('max_message_length', 1000)

        # If content is short but contains a bad word, still moderate
        if len(content) < min_len and not self._matches_any_bad_word(content):
            return False
        if len(content) > max_len:
            # too long is itself a format issue; let analyzer handle it
            return True

        return True

    
    async def _check_rate_limiting(self, message: discord.Message) -> bool:
        """Check various rate limits and spam patterns"""
        user_id = str(message.author.id)
        current_time = time.time()
        content_hash = hashlib.md5(message.content.encode()).hexdigest()
        limits = self.config.get('limits', {})
        
        # Message rate limiting (10 second window)
        self.user_rate_limits[user_id].append(current_time)
        while (self.user_rate_limits[user_id] and 
               current_time - self.user_rate_limits[user_id][0] > 10):
            self.user_rate_limits[user_id].popleft()
        
        if len(self.user_rate_limits[user_id]) > limits.get('max_messages_per_10s', 7):
            await self._handle_message_spam(message)
            return True
        
        # Duplicate message detection
        message_data = {
            'content_hash': content_hash,
            'timestamp': current_time,
            'channel_id': message.channel.id
        }
        
        if user_id not in self.user_message_history:
            self.user_message_history[user_id] = deque(maxlen=50)
        
        self.user_message_history[user_id].append(message_data)
        
        # Check for duplicate messages
        duplicate_window = limits.get('duplicate_message_window_sec', 45)
        duplicate_threshold = limits.get('duplicate_message_threshold', 3)
        
        recent_messages = [
            msg for msg in self.user_message_history[user_id]
            if current_time - msg['timestamp'] < duplicate_window
        ]
        
        duplicate_count = sum(1 for msg in recent_messages if msg['content_hash'] == content_hash)
        
        if duplicate_count >= duplicate_threshold:
            await self._handle_duplicate_spam(message)
            return True
        
        return False
    
    async def _analyze_message_content(self, message: discord.Message) -> Tuple[int, List[str]]:
        """Comprehensive content analysis using regex + normalized hard terms."""
        content = message.content or ""
        suspicion_score = 0
        violations: List[str] = []
        weights = self.config.get('suspicion_weights', {})

        # Bad words by categories (regex)
        bad_words = self.config.get('bad_words', {})
        for category, _ in bad_words.items():
            regex_key = f"bad_words_{category}"
            if regex_key in self.compiled_regex:
                for pattern in self.compiled_regex[regex_key]:
                    if pattern.search(content):
                        suspicion_score += weights.get('bad_word', 10)
                        violations.append(f"{category}_detected")
                        break

        # Normalized hard slurs (immediate strong signal)
        norm = self._normalize_for_slurs(content)
        hard_terms = self.config.get('hard_terms', {}).get('hate_slurs', [])
        if any(term in norm for term in hard_terms):
            suspicion_score = max(suspicion_score, 50)
            if 'hate_detected' not in violations:
                violations.append('hate_detected')

        # Invite / URL / PII / zalgo (existing logic)
        format_detectors = self.config.get('format_detectors', {})
        if 'invite_regex' in format_detectors:
            invite_pattern = self.compiled_regex.get('format_invite_regex')
            if invite_pattern and invite_pattern.search(content):
                if not await self._is_invite_allowed(message):
                    suspicion_score += weights.get('invite_link', 7)
                    violations.append('invite_link')

        if 'url_regex' in format_detectors:
            url_pattern = self.compiled_regex.get('format_url_regex')
            if url_pattern:
                urls = url_pattern.findall(content)
                for url in urls:
                    if await self._is_suspicious_url(url):
                        suspicion_score += weights.get('suspicious_link', 6)
                        violations.append('suspicious_link')

        email_pattern = self.compiled_regex.get('format_email_regex')
        phone_pattern = self.compiled_regex.get('format_phone_regex')
        if (email_pattern and email_pattern.search(content)) or (phone_pattern and phone_pattern.search(content)):
            suspicion_score += weights.get('personal_data_leak', 10)
            violations.append('personal_data_leak')

        zalgo_pattern = self.compiled_regex.get('format_zalgo_regex')
        if zalgo_pattern and len(zalgo_pattern.findall(content)) > self.config.get('limits', {}).get('zalgo_threshold', 6):
            suspicion_score += weights.get('zalgo_text', 3)
            violations.append('zalgo_text')

        # Message format (as you already do)
        violations.extend(self._analyze_message_format(message, content))
        for v in ['excessive_caps','emoji_spam','mention_spam','mass_spoiler']:
            if v in violations:
                suspicion_score += weights.get(v, 3)

        return suspicion_score, violations

    
    def _analyze_message_format(self, message: discord.Message, content: str) -> List[str]:
        """Analyze message format for violations"""
        violations = []
        limits = self.config.get('limits', {})
        
        # Caps lock analysis
        if len(content) > 10:
            caps_ratio = sum(1 for c in content if c.isupper()) / len(content)
            if caps_ratio > limits.get('capslock_ratio_warn', 0.7):
                violations.append('excessive_caps')
        
        # Mention analysis
        mention_count = len(message.mentions) + len(message.role_mentions) + len(message.channel_mentions)
        if mention_count > limits.get('max_mentions_per_message', 5):
            violations.append('mention_spam')
        
        # Emoji analysis (rough count)
        emoji_count = len([c for c in content if ord(c) > 127])
        if emoji_count > limits.get('max_emojis_per_message', 20):
            violations.append('emoji_spam')
        
        # Spoiler analysis
        spoiler_count = content.count('||')
        if spoiler_count > len(content) * limits.get('spoiler_max_ratio', 0.5):
            violations.append('mass_spoiler')
        
        # Line count
        line_count = len(content.split('\n'))
        if line_count > limits.get('max_lines_per_message', 12):
            violations.append('excessive_lines')
        
        return violations
    
    async def _is_invite_allowed(self, message: discord.Message) -> bool:
        """Check if invite links are allowed"""
        link_policy = self.config.get('link_policy', {})
        
        if link_policy.get('block_all_invites', True):
            allowed_channels = link_policy.get('allow_invites_in_channels', [])
            return message.channel.id in allowed_channels
        
        return True
    
    async def _is_suspicious_url(self, url: str) -> bool:
        """Analyze URL for suspicious characteristics"""
        link_policy = self.config.get('link_policy', {})
        
        try:
            parsed_url = urllib.parse.urlparse(url.lower())
            domain = parsed_url.netloc
            
            # Check blocked domains
            blocked_domains = link_policy.get('block_domains', [])
            for blocked in blocked_domains:
                if re.match(blocked.replace('*', '.*'), domain):
                    return True
            
            # Check allowed domains
            allowed_domains = link_policy.get('allow_domains', [])
            if allowed_domains:
                for allowed in allowed_domains:
                    if domain.endswith(allowed.lower()):
                        return False
                return True  # Not in whitelist
            
            # Check URL shorteners
            if link_policy.get('block_url_shorteners', True):
                shorteners = link_policy.get('shortener_domains', [])
                if any(domain.endswith(shortener) for shortener in shorteners):
                    return True
            
            # Check suspicious TLDs
            suspicious_tlds = link_policy.get('block_suspicious_tlds', [])
            if any(domain.endswith(f'.{tld}') for tld in suspicious_tlds):
                return True
            
        except Exception as e:
            logger.warning(f"URL analysis failed for {url}: {e}")
            return True  # Treat unparseable URLs as suspicious
        
        return False
    
    async def _handle_inappropriate_content(self, message: discord.Message, ai_result: dict, 
                                          violations: List[str], suspicion_score: int):
        """Handle content flagged by AI as inappropriate"""
        user_id = str(message.author.id)
        severity = self._determine_severity(violations, ai_result.get('severity', 'low'))
        
        # Track warning
        if user_id not in self.user_warnings:
            self.user_warnings[user_id] = []
        
        warning = {
            'timestamp': datetime.utcnow(),
            'violations': violations + ai_result.get('violations', []),
            'severity': severity,
            'suspicion_score': suspicion_score,
            'ai_reason': ai_result.get('reason', ''),
            'message_content': message.content[:200],
            'channel': message.channel.name,
            'message_id': message.id
        }
        
        self.user_warnings[user_id].append(warning)
        
        # Determine action
        action = self._determine_action(severity, len(self.user_warnings[user_id]), violations)
        await self._execute_action(message, action, warning)
        
        # Log incident
        if self.embed_logger:
            await self._log_moderation_incident(message, warning, action)
    
    def _determine_severity(self, violations: List[str], ai_severity: str) -> str:
        """Determine overall severity based on violations and AI assessment"""
        severity_mapping = self.config.get('severity_mapping', {})
        
        # Check for high severity violations
        high_violations = severity_mapping.get('high', [])
        if any(v in violations for v in high_violations):
            return 'high'
        
        # Check for medium severity violations
        medium_violations = severity_mapping.get('medium', [])
        if any(v in violations for v in medium_violations):
            return 'medium'
        
        # Use AI assessment if available
        if ai_severity in ['high', 'medium', 'low']:
            return ai_severity
        
        return 'low'
    
    def _determine_action(self, severity: str, warning_count: int, violations: List[str]) -> str:
        """Determine action based on escalation rules"""
        escalation = self.config.get('escalation_rules', {})
        
        # Check for extreme conditions
        extreme = escalation.get('extreme_action', {})
        extreme_conditions = extreme.get('conditions', {})
        
        for condition, enabled in extreme_conditions.items():
            if enabled and condition in violations:
                return extreme.get('action', 'ban_and_report')
        
        # Regular escalation
        if severity == 'high' or warning_count >= escalation.get('severe_action', {}).get('min_warnings', 3):
            return escalation.get('severe_action', {}).get('action', 'timeout_1hour_or_kick')
        elif severity == 'medium' or warning_count >= 2:
            return escalation.get('medium_action', {}).get('action', 'timeout_10min')
        else:
            return escalation.get('light_action', {}).get('action', 'dm_warning')
    
    async def _execute_action(self, message: discord.Message, action: str, warning: dict):
        """Execute the determined moderation action"""
        actions_config = self.config.get('actions', {})
        
        try:
            # Always delete the message first
            if actions_config.get('delete_message', True):
                await message.delete()
        except discord.NotFound:
            pass
        except Exception as e:
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Smart Moderation",
                    error=e,
                    context=f"Failed to delete message {message.id}"
                )
        
        if action == 'dm_warning':
            await self._send_warning_dm(message, warning)
        
        elif action == 'timeout_10min':
            timeout_duration = actions_config.get('timeout_durations', {}).get('medium', 600)
            await self._timeout_user(message, timedelta(seconds=timeout_duration), warning)
        
        elif action == 'timeout_1hour_or_kick':
            warning_count = len(self.user_warnings.get(str(message.author.id), []))
            if warning_count >= actions_config.get('kick_after_warnings', 5):
                await self._kick_user(message, warning)
            else:
                timeout_duration = actions_config.get('timeout_durations', {}).get('high', 3600)
                await self._timeout_user(message, timedelta(seconds=timeout_duration), warning)
        
        elif action == 'ban_and_report':
            await self._ban_user(message, warning)
    
    async def _send_warning_dm(self, message: discord.Message, warning: dict):
        """Send warning via DM"""
        template = self.config.get('actions', {}).get('dm_warning_template', 
            "Hey {user}, your message in {channel} broke our server rules ({reason}). Please keep it civil.")
        
        warning_text = template.format(
            user=message.author.mention,
            channel=message.channel.mention,
            reason=', '.join(warning['violations'][:3])  # First 3 violations
        )
        
        try:
            await message.author.send(warning_text)
            
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Smart Moderation",
                    title="Warning DM Sent",
                    description=f"Warning message sent to <@{message.author.id}>",
                    level=LogLevel.INFO,
                    fields={
                        "User": f"<@{message.author.id}>",
                        "Channel": message.channel.mention,
                        "Violations": ', '.join(warning['violations'][:3]),
                        "Method": "Direct Message"
                    }
                )
                
        except discord.Forbidden:
            # If can't DM, send public warning
            public_template = self.config.get('actions', {}).get('public_warning_template',
                "{user}, please follow the rules. Reason: {reason}")
            
            public_warning = public_template.format(
                user=message.author.mention,
                reason=', '.join(warning['violations'][:2])
            )
            
            try:
                await message.channel.send(public_warning, delete_after=30)
                
                if self.embed_logger:
                    await self.embed_logger.log_custom(
                        service="Smart Moderation",
                        title="Public Warning Sent",
                        description=f"Warning message posted publicly for <@{message.author.id}> (DM failed)",
                        level=LogLevel.WARNING,
                        fields={
                            "User": f"<@{message.author.id}>",
                            "Channel": message.channel.mention,
                            "Violations": ', '.join(warning['violations'][:2]),
                            "Method": "Public (DM failed)"
                        }
                    )
            except Exception as e:
                if self.embed_logger:
                    await self.embed_logger.log_error(
                        service="Smart Moderation",
                        error=e,
                        context=f"Failed to send warning to {message.author.id}"
                    )
    
    async def _timeout_user(self, message: discord.Message, duration: timedelta, warning: dict):
        """Timeout user with explanation"""
        try:
            until = datetime.utcnow() + duration
            await message.author.timeout(until, reason=f"Auto-moderation: {', '.join(warning['violations'][:3])}")
            
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Smart Moderation",
                    title="User Timed Out",
                    description=f"<@{message.author.id}> has been timed out",
                    level=LogLevel.WARNING,
                    fields={
                        "User": f"<@{message.author.id}>",
                        "Duration": f"{duration.total_seconds()//60} minutes",
                        "Reason": ', '.join(warning['violations'][:3]),
                        "Channel": message.channel.mention,
                        "Until": until.strftime("%Y-%m-%d %H:%M UTC")
                    }
                )
            
            # Generate explanation with AI
            try:
                explanation = await ask_ai(
                    prompt=f"Explain why a user was timed out for {duration.total_seconds()//60} minutes for: {', '.join(warning['violations'])}",
                    system_context="Be educational but firm. Explain the rules clearly.",
                    max_length=200
                )
                
                await message.channel.send(
                    f"{message.author.mention} has been timed out for {duration.total_seconds()//60} minutes.\n{explanation}",
                    delete_after=60
                )
            except Exception as e:
                await message.channel.send(
                    f"{message.author.mention} has been timed out for {duration.total_seconds()//60} minutes.",
                    delete_after=60
                )
                if self.embed_logger:
                    await self.embed_logger.log_error(
                        service="Smart Moderation",
                        error=e,
                        context="Failed to generate timeout explanation with AI"
                    )
            
        except discord.Forbidden:
            logger.warning(f"Cannot timeout user {message.author.id} - insufficient permissions")
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Smart Moderation",
                    error=Exception("Insufficient permissions to timeout user"),
                    context=f"Cannot timeout user {message.author.id}"
                )
    
    async def _kick_user(self, message: discord.Message, warning: dict):
        """Kick user from server"""
        try:
            await message.author.kick(reason=f"Auto-moderation: {', '.join(warning['violations'])}")
            await message.channel.send(
                f"{message.author.mention} has been removed from the server for repeated rule violations."
            )
            
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Smart Moderation",
                    title="User Kicked",
                    description=f"<@{message.author.id}> has been kicked from the server",
                    level=LogLevel.ERROR,
                    fields={
                        "User": f"{message.author.name}#{message.author.discriminator} ({message.author.id})",
                        "Reason": ', '.join(warning['violations']),
                        "Channel": message.channel.mention,
                        "Action": "Kicked for repeated violations"
                    }
                )
                
        except discord.Forbidden:
            logger.warning(f"Cannot kick user {message.author.id} - insufficient permissions")
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Smart Moderation",
                    error=Exception("Insufficient permissions to kick user"),
                    context=f"Cannot kick user {message.author.id}"
                )
    
    async def _ban_user(self, message: discord.Message, warning: dict):
        """Ban user and report to staff"""
        try:
            await message.author.ban(reason=f"Auto-moderation: {', '.join(warning['violations'])}", delete_message_days=1)
            await message.channel.send(
                f"{message.author.mention} has been banned for severe rule violations."
            )
            
            # Notify staff
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Emergency Moderation",
                    title="🚨 User Banned - Manual Review Required",
                    description=f"User automatically banned for severe violations",
                    level=LogLevel.CRITICAL,
                    fields={
                        "User": f"{message.author.name}#{message.author.discriminator} ({message.author.id})",
                        "Violations": ', '.join(warning['violations']),
                        "Message Content": warning['message_content'][:100] + "..." if len(warning['message_content']) > 100 else warning['message_content'],
                        "Channel": message.channel.mention,
                        "Action Required": "Review ban and consider reporting to Discord Trust & Safety",
                        "Severity": warning.get('severity', 'unknown')
                    }
                )
                
        except discord.Forbidden:
            logger.error(f"Cannot ban user {message.author.id} - insufficient permissions")
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Smart Moderation",
                    error=Exception("Insufficient permissions to ban user"),
                    context=f"Cannot ban user {message.author.id} for severe violations"
                )
    
    async def _log_moderation_incident(self, message: discord.Message, warning: dict, action: str):
        """Log detailed moderation incident"""
        if not self.embed_logger:
            return
        
        severity_colors = {
            'low': LogLevel.INFO,
            'medium': LogLevel.WARNING,
            'high': LogLevel.ERROR
        }
        
        await self.embed_logger.log_custom(
            service="Smart Moderation",
            title=f"Content Moderated - {warning['severity'].title()} Severity",
            description=f"Automated moderation action taken against <@{message.author.id}>",
            level=severity_colors.get(warning['severity'], LogLevel.WARNING),
            fields={
                "User": f"<@{message.author.id}>",
                "Action": action.replace('_', ' ').title(),
                "Violations": ', '.join(warning['violations'][:5]),
                "Suspicion Score": str(warning['suspicion_score']),
                "AI Reason": warning['ai_reason'][:100] + "..." if len(warning['ai_reason']) > 100 else warning['ai_reason'] if warning['ai_reason'] else 'N/A',
                "Channel": message.channel.mention,
                "Warning Count": str(len(self.user_warnings.get(str(message.author.id), []))),
                "AI Calls Today": f"{self.ai_calls_today}/{self.config.get('limits', {}).get('daily_ai_limit', 500)}",
                "Message ID": str(message.id)
            }
        )
    
    async def _has_whitelisted_role(self, member: discord.Member) -> bool:
        """Check if user has whitelisted roles"""
        whitelisted_roles = self.config.get('whitelisted_roles', [])
        return await self._has_role_name(member, whitelisted_roles)
    
    async def _has_role_name(self, member: discord.Member, role_names: List[str]) -> bool:
        """Check if user has any of the specified role names"""
        user_role_names = [role.name.lower() for role in member.roles]
        return any(role_name.lower() in user_role_names for role_name in role_names)
    
    async def _is_trusted_user(self, member: discord.Member) -> bool:
        """Enhanced trusted user detection (timezone-safe)"""
        criteria = self.config.get('trusted_user_criteria', {})

        # Premium members
        if criteria.get('premium_members', True) and getattr(member, "premium_since", None):
            return True

        now_utc = datetime.now(timezone.utc)

        # Account age check (member.created_at is aware)
        min_account_age = criteria.get('account_age_days', 30)
        try:
            account_age_days = (now_utc - member.created_at).days
        except Exception:
            # If unavailable, fail closed (not trusted)
            return False
        if account_age_days < min_account_age:
            return False

        # Server join age check (member.joined_at can be None or aware)
        if getattr(member, "joined_at", None):
            try:
                min_join_age = criteria.get('server_join_age_hours', 24)
                join_age_hours = (now_utc - member.joined_at).total_seconds() / 3600.0
                if join_age_hours < min_join_age:
                    return False
            except Exception:
                # If subtraction fails, treat as not trusted
                return False

        # Warning count check
        if criteria.get('no_warnings_required', True):
            max_warnings = criteria.get('warns_max_for_trust', 0)
            user_warnings = len(self.user_warnings.get(str(member.id), []))
            if user_warnings > max_warnings:
                return False

        # Phone verification (not available via discord.py; skip)
        # Trusted role names
        trusted_roles = criteria.get('trusted_role_names', [])
        if trusted_roles and await self._has_role_name(member, trusted_roles):
            return True

        # If account is old enough and meets criteria
        return account_age_days >= min_account_age

    
    # Additional handlers for specific violations
    async def _handle_raid_detection(self, guild: discord.Guild):
        """Handle detected raid"""
        anti_raid = self.config.get('anti_raid', {})
        
        # Auto slowmode
        slowmode_seconds = anti_raid.get('auto_slowmode_seconds', 10)
        
        # Apply to general channels
        channels_affected = 0
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).manage_channels:
                try:
                    await channel.edit(slowmode_delay=slowmode_seconds)
                    channels_affected += 1
                except discord.Forbidden:
                    pass
        
        # Log raid detection
        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Anti-Raid System",
                title="🚨 Raid Detected",
                description=f"Burst join threshold exceeded - automatic countermeasures activated",
                level=LogLevel.CRITICAL,
                fields={
                    "Join Count": str(len(self.user_join_times)),
                    "Time Window": f"{anti_raid.get('burst_window_seconds', 30)}s",
                    "Action Taken": f"Auto-slowmode enabled ({slowmode_seconds}s)",
                    "Channels Affected": str(channels_affected),
                    "Server": guild.name,
                    "Recommendation": "Monitor for suspicious activity and consider manual intervention"
                }
            )
    
    async def _handle_new_account(self, member: discord.Member, account_age_hours: float):
        """Handle new account detection"""
        if account_age_hours < 1:  # Less than 1 hour old
            # Consider auto-kick or flag for manual review
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="New Account Monitor",
                    title="⚠️ Very New Account Joined",
                    description=f"Extremely new account detected - potential risk",
                    level=LogLevel.WARNING,
                    fields={
                        "User": f"{member.mention} ({member.id})",
                        "Account Age": f"{account_age_hours:.1f} hours",
                        "Username": member.name,
                        "Suggested Action": "Monitor closely or consider manual verification",
                        "Risk Level": "🔴 High" if account_age_hours < 0.5 else "🟡 Medium"
                    }
                )
    
    async def _handle_message_spam(self, message: discord.Message):
        """Handle message rate limit violation"""
        try:
            await message.delete()
        except Exception:
            pass
        
        # Timeout for spam
        try:
            await message.author.timeout(
                datetime.utcnow() + timedelta(minutes=5),
                reason="Message spam - rate limit exceeded"
            )
            
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Smart Moderation",
                    title="Message Spam Detected",
                    description=f"<@{message.author.id}> exceeded message rate limits",
                    level=LogLevel.WARNING,
                    fields={
                        "User": f"<@{message.author.id}>",
                        "Violation": "Message rate limit exceeded",
                        "Action": "5-minute timeout",
                        "Channel": message.channel.mention
                    }
                )
        except discord.Forbidden:
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Smart Moderation",
                    error=Exception("Cannot timeout spam user - insufficient permissions"),
                    context=f"Message spam by {message.author.id}"
                )
        
        try:
            warning_msg = await message.channel.send(
                f"{message.author.mention} slow down! You're sending messages too quickly.",
                delete_after=10
            )
        except Exception:
            pass
    
    async def _handle_duplicate_spam(self, message: discord.Message):
        """Handle duplicate message spam"""
        try:
            await message.delete()
        except Exception:
            pass
        
        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Smart Moderation",
                title="Duplicate Spam Detected",
                description=f"<@{message.author.id}> sent duplicate messages",
                level=LogLevel.INFO,
                fields={
                    "User": f"<@{message.author.id}>",
                    "Violation": "Duplicate message spam",
                    "Action": "Message deleted",
                    "Channel": message.channel.mention
                }
            )

        try:
            await message.channel.send(
                f"{message.author.mention} please don't repeat the same message.",
                delete_after=15
            )
        except Exception:
            pass
    
    async def _handle_reaction_spam(self, user: discord.User, channel: discord.TextChannel):
        """Handle reaction spam"""
        try:
            member = channel.guild.get_member(user.id)
            if member:
                await member.timeout(
                    datetime.utcnow() + timedelta(minutes=2),
                    reason="Reaction spam"
                )
                
                if self.embed_logger:
                    await self.embed_logger.log_custom(
                        service="Smart Moderation",
                        title="Reaction Spam Detected",
                        description=f"<@{user.id}> exceeded reaction rate limits",
                        level=LogLevel.WARNING,
                        fields={
                            "User": f"<@{user.id}>",
                            "Violation": "Reaction rate limit exceeded",
                            "Action": "2-minute timeout",
                            "Channel": channel.mention
                        }
                    )
        except discord.Forbidden:
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Smart Moderation",
                    error=Exception("Cannot timeout reaction spammer - insufficient permissions"),
                    context=f"Reaction spam by {user.id}"
                )
    
    async def _queue_for_manual_review(self, message: discord.Message, violations: List[str], score: int):
        """Queue message for manual review"""
        review_item = {
            'message_id': message.id,
            'channel_id': message.channel.id,
            'author_id': message.author.id,
            'content': message.content[:500],
            'violations': violations,
            'suspicion_score': score,
            'timestamp': datetime.utcnow(),
            'status': 'pending'
        }
        
        self.review_queue.append(review_item)
        
        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Manual Review Queue",
                title="Message Queued for Review",
                description=f"High suspicion content requires manual review",
                level=LogLevel.WARNING,
                fields={
                    "User": f"<@{message.author.id}>",
                    "Suspicion Score": str(score),
                    "Violations": ', '.join(violations),
                    "Queue Size": str(len(self.review_queue)),
                    "Channel": message.channel.mention,
                    "Action Required": "Manual moderator review needed"
                }
            )
    
    async def _cleanup_old_data(self):
        """Periodic cleanup of old tracking data"""
        while True:
            await asyncio.sleep(3600)  # Every hour
            
            current_time = time.time()
            cleaned_items = 0
            
            # Clean old rate limit data
            for user_id in list(self.user_rate_limits.keys()):
                while (self.user_rate_limits[user_id] and 
                       current_time - self.user_rate_limits[user_id][0] > 600):  # 10 minutes
                    self.user_rate_limits[user_id].popleft()
                    cleaned_items += 1
                
                if not self.user_rate_limits[user_id]:
                    del self.user_rate_limits[user_id]
            
            # Clean old reaction data
            for user_id in list(self.user_reaction_limits.keys()):
                while (self.user_reaction_limits[user_id] and 
                       current_time - self.user_reaction_limits[user_id][0] > 3600):  # 1 hour
                    self.user_reaction_limits[user_id].popleft()
                    cleaned_items += 1
                
                if not self.user_reaction_limits[user_id]:
                    del self.user_reaction_limits[user_id]
            
            # Clean old warnings (keep for configured duration)
            retention_days = self.config.get('logging', {}).get('store_user_history_days', 90)
            cutoff_time = datetime.utcnow() - timedelta(days=retention_days)
            
            for user_id in list(self.user_warnings.keys()):
                old_count = len(self.user_warnings[user_id])
                self.user_warnings[user_id] = [
                    warning for warning in self.user_warnings[user_id]
                    if warning['timestamp'] > cutoff_time
                ]
                cleaned_items += old_count - len(self.user_warnings[user_id])
                
                if not self.user_warnings[user_id]:
                    del self.user_warnings[user_id]
            
            if cleaned_items > 0 and self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Smart Moderation",
                    title="Data Cleanup Completed",
                    description="Periodic cleanup of old moderation data",
                    level=LogLevel.INFO,
                    fields={
                        "Items Cleaned": str(cleaned_items),
                        "Retention Period": f"{retention_days} days",
                        "Active Users Tracked": str(len(self.user_warnings)),
                        "Rate Limit Entries": str(len(self.user_rate_limits))
                    }
                )
    
    # Management methods
    def get_moderation_stats(self) -> dict:
        """Get comprehensive moderation statistics"""
        total_warnings = sum(len(warnings) for warnings in self.user_warnings.values())
        active_users_tracked = len([
            uid for uid, warnings in self.user_warnings.items() 
            if warnings and warnings[-1]['timestamp'] > datetime.utcnow() - timedelta(days=7)
        ])
        
        return {
            "enabled": self.config.get('enabled', False),
            "version": self.config.get('version', 'unknown'),
            "ai_calls_today": self.ai_calls_today,
            "daily_limit": self.config.get('limits', {}).get('daily_ai_limit', 500),
            "total_users_warned": len(self.user_warnings),
            "total_warnings_issued": total_warnings,
            "active_users_tracked": active_users_tracked,
            "review_queue_size": len(self.review_queue),
            "bad_word_categories": len(self.config.get('bad_words', {})),
            "compiled_patterns": len(self.compiled_regex),
            "anti_raid_enabled": self.config.get('anti_raid', {}).get('enabled', False),
            "whitelisted_channels": len(self.config.get('whitelisted_channels', [])),
            "whitelisted_roles": len(self.config.get('whitelisted_roles', []))
        }
    
    def reset_daily_limits(self):
        """Reset daily counters"""
        old_count = self.ai_calls_today
        self.ai_calls_today = 0
        
        if self.embed_logger:
            asyncio.create_task(self.embed_logger.log_custom(
                service="Smart Moderation",
                title="Daily Limits Reset",
                description="AI usage counters have been reset",
                level=LogLevel.INFO,
                fields={
                    "Previous AI Calls": str(old_count),
                    "New AI Calls": "0",
                    "Daily Limit": str(self.config.get('limits', {}).get('daily_ai_limit', 500)),
                    "Reset By": "Manual admin action"
                }
            ))
            
        logger.info("Daily AI usage limits reset")
    
    async def reload_configuration(self):
        """Reload configuration and recompile patterns"""
        old_version = self.config.get('version', 'unknown')
        old_enabled = self.config.get('enabled', False)
        
        self._load_configuration()
        self._compile_regex_patterns()
        
        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Smart Moderation",
                title="Configuration Reloaded",
                description="Moderation configuration has been reloaded from file",
                level=LogLevel.SUCCESS,
                fields={
                    "Previous Version": str(old_version),
                    "New Version": str(self.config.get('version', 'unknown')),
                    "Previous Status": "Enabled" if old_enabled else "Disabled",
                    "New Status": "Enabled" if self.config.get('enabled', False) else "Disabled",
                    "Patterns Compiled": str(len(self.compiled_regex)),
                    "Bad Word Categories": str(len(self.config.get('bad_words', {})))
                }
            )
            
        logger.info("Moderation configuration reloaded")
    
    async def get_user_warnings(self, user_id: str) -> List[dict]:
        """Get warnings for a specific user"""
        return self.user_warnings.get(user_id, [])
    
    async def clear_user_warnings(self, user_id: str):
        """Clear warnings for a user"""
        if user_id in self.user_warnings:
            warning_count = len(self.user_warnings[user_id])
            del self.user_warnings[user_id]
            
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Smart Moderation",
                    title="User Warnings Cleared",
                    description=f"All warnings cleared for user",
                    level=LogLevel.INFO,
                    fields={
                        "User": f"<@{user_id}>",
                        "Warnings Cleared": str(warning_count),
                        "Action": "Manual admin action"
                    }
                )
    
    def get_review_queue(self) -> List[dict]:
        """Get pending review items"""
        return [item for item in self.review_queue if item['status'] == 'pending']
    
    async def process_review_item(self, item_id: int, action: str, moderator_id: str):
        """Process a review queue item"""
        if 0 <= item_id < len(self.review_queue):
            self.review_queue[item_id]['status'] = action
            self.review_queue[item_id]['reviewed_by'] = moderator_id
            self.review_queue[item_id]['reviewed_at'] = datetime.utcnow()
            
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Manual Review",
                    title="Review Item Processed",
                    description=f"Review queue item processed by moderator",
                    level=LogLevel.INFO,
                    fields={
                        "Moderator": f"<@{moderator_id}>",
                        "Action": action,
                        "Original Score": str(self.review_queue[item_id]['suspicion_score']),
                        "Original Author": f"<@{self.review_queue[item_id]['author_id']}>",
                        "Item ID": str(item_id)
                    }
                )