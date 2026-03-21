# Detailed Component Architecture Reference

## 1. Gateway Component Analysis

### OpenClaw Gateway Implementation Details

**Features Required:**
- WebSocket server on `localhost:18789`
- Session state persistence (activation modes)
- Multi-channel event routing with deduplication
- Tool execution with streaming responses
- Group mention detection and routing
- Reply tag association and tracking
- Presence status broadcasting
- Typing indicators
- Usage monitoring hooks

**Message Flow:**
```
Channel Adapter → Gateway Queue → Route to Session → Agent Runtime → Tool Execution → Format Response → Send to Channel
```

**Session Management:**
- `session_id`: Unique identifier
- `agent_id`: Associated agent
- `channel`: Source channel (telegram, slack, etc.)
- `user_id`: User identifier from channel
- `group_id`: (optional) Group identifier
- `activation_mode`: How agent activates (always-on, mention-only, reaction)
- `reply_tags`: Associated message threads
- `metadata`: Channel-specific data (thread_ts, message_id, etc.)

**Event System:**
- `message_received`: Incoming message
- `message_sent`: Outgoing response
- `tool_invoked`: Tool execution started
- `tool_completed`: Tool execution finished
- `tool_failed`: Tool execution error
- `session_created`: New session initialized
- `session_archived`: Session closed

---

### NemoClaw Gateway (OpenShell) Model

**Features:**
- Policy interception layer
- Request routing based on policies
- Hot-reload configuration updates
- Operator approval workflow for policy violations
- Audit logging of all requests
- Container orchestration hooks
- TUI for monitoring and debugging

**Policy Types:**
```python
NetworkPolicy = {
    "whitelist": ["*.example.com", "api.service.io"],
    "blacklist": [],
    "allow_localhost": True,
    "require_approval": ["unknown.domain"]
}

FilesystemPolicy = {
    "allowed_paths": ["/sandbox", "/tmp"],
    "readonly_paths": [],
    "forbidden_paths": ["*"]  # Everything else blocked
}

ProcessPolicy = {
    "allow_exec": True,
    "allow_fork": True,
    "forbidden_syscalls": ["ptrace", "execve", "prctl"],
}

InferencePolicy = {
    "allowed_models": ["nemotron-3-super-120b"],
    "endpoint": "https://api.nvidia.com/inference",
    "auth_required": True
}
```

---

### claw-python Recommended Gateway

**Minimum Implementation:**
```python
class ClawGateway:
    """
    WebSocket-based control plane for multi-channel agent routing.
    """

    async def connect_session(self, session_id: str, agent_id: str) -> None:
        """Initialize or resume a session"""

    async def route_message(
        self,
        session_id: str,
        content: str,
        metadata: dict
    ) -> AsyncIterator[str]:
        """
        Route message to agent, stream responses.
        Yields: chunks of response text
        """

    async def invoke_tool(
        self,
        session_id: str,
        tool_name: str,
        kwargs: dict
    ) -> Any:
        """
        Execute tool with permission checks.
        Returns: tool output
        """

    async def broadcast_event(
        self,
        event_type: str,
        session_id: str,
        data: dict
    ) -> None:
        """Broadcast event to listeners"""

    async def get_session(self, session_id: str) -> Session:
        """Retrieve session state"""

    async def archive_session(self, session_id: str) -> None:
        """Close and archive session"""
```

**Configuration:**
```yaml
gateway:
  host: "127.0.0.1"
  port: 18789
  max_connections: 100
  session_timeout_minutes: 1440

  security:
    require_auth: false  # For local development
    rate_limit_rps: 100

  logging:
    level: "INFO"
    log_file: "~/.claw/logs/gateway.log"

  storage:
    backend: "sqlite"  # or "postgresql"
    connection_string: "sqlite://~/.claw/sessions.db"
```

---

## 2. Channel Adapter Pattern

### OpenClaw Adapter Requirements

Each channel adapter must implement:

```python
class TelegramAdapter(ChannelAdapter):
    """
    Telegram messaging platform integration.
    Uses grammY library.
    """

    async def connect(self) -> None:
        """Connect to Telegram Bot API"""

    async def send_message(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        parse_mode: str = "markdown"
    ) -> str:
        """Send message, return message_id"""

    async def receive_messages(self) -> AsyncIterator[InboundMessage]:
        """Receive messages from Telegram"""
        # Yields: InboundMessage with user_id, group_id, content, attachments

    async def get_user_info(self, user_id: str) -> User:
        """Retrieve user profile information"""

    async def get_group_info(self, group_id: str) -> Group:
        """Retrieve group information"""

    async def edit_message(self, chat_id: str, message_id: str, content: str) -> None:
        """Edit existing message"""

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        """Delete message"""

    async def react_to_message(self, chat_id: str, message_id: str, emoji: str) -> None:
        """Add emoji reaction (if supported)"""
```

### Channel-Specific Considerations

**Telegram (grammY)**
- Message limit: 4096 characters
- Chunking strategy: Split on sentences respecting limit
- Threading: Via reply_to_message_id
- Rich formatting: Markdown with inline buttons
- File support: Document, photo, video, audio
- Webhook vs polling

**Slack (Bolt)**
- Message limit: 4000 characters (practical)
- Chunking strategy: Post multiple messages in thread
- Threading: Via thread_ts
- Rich formatting: Block Kit with interactive elements
- File support: File uploads API
- Token rotation and refresh
- Event subscription pattern

**Discord (discord.py)**
- Message limit: 2000 characters
- Chunking strategy: Post multiple embeds
- Threading: Conversation starters or replies
- Rich formatting: Embeds with fields
- File support: attachments
- Intent-based message filtering
- Rate limiting per guild

### Priority Adapter Implementation Order

**Priority 1: Telegram**
- Simplest API
- Large user base
- Good documentation (grammY)
- No OAuth complexity

**Priority 2: Slack**
- High enterprise value
- Rich interaction model
- Better formatting options
- Established OAuth patterns

**Priority 3: Discord**
- Community integration
- Webhook support
- Active library (discord.py)
- Growing user base

---

## 3. Tool System Architecture

### OpenClaw Tool Types

**Category 1: Execution Tools** (Run on Gateway host)
- `browser_control`: Chrome/Chromium via CDP
- `code_execute`: Python/JavaScript sandbox
- `file_read`: Read files with path restrictions
- `file_write`: Write files with path restrictions
- `http_request`: HTTP calls with proxy/auth

**Category 2: Device Tools** (Run on Node via RPC)
- `camera_snap`: Capture camera image
- `screen_record`: Record screen activity
- `system_run`: Execute shell commands
- `system_notify`: Send notifications
- `location_get`: Retrieve device location

**Category 3: Channel Tools** (Channel-specific)
- `channel_send_message`: Send message to channel
- `channel_send_file`: Upload file to channel
- `channel_react`: Add reaction
- `channel_thread_reply`: Reply in thread

**Category 4: Session Tools** (Agent coordination)
- `sessions_list`: List active sessions
- `sessions_history`: Retrieve session history
- `sessions_send`: Send message to another session

**Category 5: Automation Tools**
- `schedule_cron`: Schedule recurring task
- `webhook_register`: Register webhook handler
- `gmail_subscribe`: Subscribe to Gmail labels

---

### Tool Schema Generation

Each tool must export schema compatible with Claude API:

```python
@tool
def browser_screenshot(url: str, wait_ms: int = 0) -> str:
    """
    Take a screenshot of a webpage.

    Args:
        url: The URL to screenshot
        wait_ms: How long to wait before screenshot (milliseconds)

    Returns:
        Base64-encoded PNG image
    """
```

**Schema Output (Anthropic Format):**
```json
{
  "name": "browser_screenshot",
  "description": "Take a screenshot of a webpage.",
  "input_schema": {
    "type": "object",
    "properties": {
      "url": {
        "type": "string",
        "description": "The URL to screenshot"
      },
      "wait_ms": {
        "type": "integer",
        "description": "How long to wait before screenshot (milliseconds)",
        "default": 0
      }
    },
    "required": ["url"]
  }
}
```

### Tool Execution Model

**Flow:**
1. Agent outputs tool call in response
2. Gateway intercepts tool invocation
3. Permission check (can this agent use this tool?)
4. Tool execution with timeout
5. Stream results back to agent
6. Log execution event

**Execution Safety:**
```python
class ToolExecutor:
    async def execute(
        self,
        tool_name: str,
        kwargs: dict,
        session_id: str,
        timeout_seconds: int = 30
    ) -> Any:
        """
        Execute tool with safety checks.

        1. Check permissions (RBAC)
        2. Validate input schema
        3. Set resource limits (memory, CPU, network)
        4. Execute with timeout
        5. Log execution
        6. Return results
        """

    def _check_permission(self, session_id: str, tool: str) -> bool:
        """Check if session has permission for tool"""

    def _validate_input(self, tool_name: str, kwargs: dict) -> bool:
        """Validate against tool schema"""

    async def _set_limits(self, tool: Tool) -> None:
        """Apply resource limits via cgroups/ulimit"""

    async def _execute_with_timeout(self, func, timeout_seconds) -> Any:
        """Execute function with timeout"""

    async def _log_execution(self, tool_name: str, input, output, status) -> None:
        """Record execution in audit log"""
```

---

## 4. Memory and Vector Embedding System

### OpenClaw Memory Model

**Workspace-Level Configuration:**
- `AGENTS.md`: System prompts and agent definition
- `SOUL.md`: Agent personality, values, constraints
- `TOOLS.md`: Tool documentation for agent reference
- `skills/*/SKILL.md`: Individual skill documentation

**Session-Level Memory:**
- Message history (in-memory for active sessions)
- Conversation context (last N messages)
- User facts extracted from conversation
- Task state and progress tracking

### claw-python Recommended Architecture

**Multi-Layer Memory System:**

```python
class MemorySystem:
    """
    Hierarchical memory with semantic search.
    """

    async def store_message(
        self,
        session_id: str,
        role: str,  # 'user' | 'assistant' | 'system'
        content: str,
        embeddings: Optional[List[float]] = None
    ) -> None:
        """Store message and generate embeddings"""

    async def retrieve_context(
        self,
        session_id: str,
        query: str,
        k: int = 5
    ) -> List[Message]:
        """Semantic search in conversation history"""

    async def get_session_summary(
        self,
        session_id: str,
        max_tokens: int = 500
    ) -> str:
        """Generate summary of session for context window"""

    async def extract_facts(
        self,
        session_id: str,
        content: str
    ) -> Dict[str, Any]:
        """Extract structured facts from conversation"""

    async def get_relevant_skills(
        self,
        query: str,
        k: int = 3
    ) -> List[Skill]:
        """Find skills relevant to query"""

    async def get_relevant_tools(
        self,
        query: str,
        k: int = 5
    ) -> List[Tool]:
        """Find tools relevant to task description"""
```

**Storage Backend:**
```python
# Message Storage (Required)
class MessageStore:
    async def insert(self, session_id, role, content, timestamp) -> str
    async def get_recent(self, session_id, limit=20) -> List[Message]
    async def search(self, session_id, query, limit=10) -> List[Message]

# Embedding Storage (Optional but recommended)
class EmbeddingStore:
    async def store(self, content_id, embedding) -> None
    async def search_similar(self, embedding, k=5) -> List[Match]
    async def delete(self, content_id) -> None

# Fact Storage (Optional)
class FactStore:
    async def insert(self, session_id, entity, attribute, value) -> None
    async def get(self, session_id, entity, attribute) -> Optional[value]
    async def get_entity(self, session_id, entity) -> Dict[str, Any]
```

**Configuration:**
```yaml
memory:
  # Message history storage
  storage:
    backend: "sqlite"  # or "postgresql"
    path: "~/.claw/messages.db"

  # Vector embeddings (optional)
  embeddings:
    enabled: false  # Can enable later
    backend: "lancedb"  # or "pgvector"
    model: "all-MiniLM-L6-v2"
    dimension: 384

  # Session context management
  context:
    window_size: 20  # Messages to include
    use_summarization: false
    summary_model: "gpt-3.5-turbo"

  # Retention policies
  retention:
    keep_days: 90
    archive_after_days: 30
```

---

## 5. Security Implementation Tiers

### Tier 1: Basic (Recommended for v1)

```python
class BasicSecurityModel:
    """
    Suitable for single-user local deployment.
    """

    async def authenticate_session(self, session_id: str) -> bool:
        """Verify session is valid (stub for local dev)"""
        return True

    async def check_tool_permission(
        self,
        session_id: str,
        tool_name: str
    ) -> bool:
        """All tools allowed (permissive for local dev)"""
        return True

    async def audit_log(self, event: dict) -> None:
        """Log all important events"""
        # Write to ~/.claw/audit.log

    async def rate_limit(self, session_id: str) -> bool:
        """Basic rate limiting per session"""
```

### Tier 2: RBAC (Medium-term)

```python
class RBACSecurityModel:
    """
    Role-Based Access Control for multi-user deployments.
    """

    def __init__(self):
        self.roles = {
            "admin": {"tools": "*", "channels": "*"},
            "user": {"tools": ["web_search", "calculator"], "channels": ["telegram"]},
            "viewer": {"tools": [], "channels": ["read-only"]}
        }

    async def authenticate_user(self, api_key: str) -> Optional[User]:
        """Verify API key"""

    async def check_permission(
        self,
        user_id: str,
        resource: str,
        action: str
    ) -> bool:
        """RBAC permission check"""

    async def enforce_quota(
        self,
        user_id: str,
        resource: str
    ) -> bool:
        """Check usage quota (API calls, storage, etc.)"""
```

### Tier 3: Enterprise (Future)

```python
class EnterpriseSecurity:
    """
    Advanced security for enterprise deployments.
    """

    async def validate_mfa(self, user_id: str, code: str) -> bool:
        """Multi-factor authentication"""

    async def enforce_network_policy(self, request: HttpRequest) -> bool:
        """Outbound network whitelist/blacklist"""

    async def enforce_filesystem_policy(self, path: str) -> bool:
        """File access restrictions"""

    async def sandbox_tool_execution(
        self,
        tool_name: str,
        kwargs: dict
    ) -> Any:
        """Execute tool in restricted container"""

    async def validate_inference_endpoint(self, endpoint: str) -> bool:
        """Restrict inference to approved providers"""
```

---

## 6. Message Queue & Routing

### Inbound Queue

```python
class InboundMessageQueue:
    """
    Manage incoming messages from channels.
    """

    async def enqueue(
        self,
        channel: str,
        user_id: str,
        group_id: Optional[str],
        content: str,
        metadata: dict,
        priority: int = 0
    ) -> str:
        """
        Queue incoming message.
        Returns: message_id
        """

    async def dequeue(self, session_id: str) -> Optional[Message]:
        """Get next message for session"""

    async def get_pending(self, session_id: str) -> int:
        """Count pending messages"""

    async def deduplicate(self, message_id: str) -> bool:
        """Prevent duplicate processing"""
```

### Routing Logic

```python
class MessageRouter:
    """
    Route messages from channels to sessions/agents.
    """

    async def route(self, message: InboundMessage) -> str:
        """
        Determine target session for message.

        Logic:
        1. Check if session exists (user + channel)
        2. If not, create new session with agent
        3. If group message, check mention (@agent)
        4. If DM, check pairing status
        5. Return session_id
        """

    async def get_or_create_session(
        self,
        channel: str,
        user_id: str,
        group_id: Optional[str]
    ) -> str:
        """Get existing session or create new"""

    async def check_activation(
        self,
        session: Session,
        message: Message
    ) -> bool:
        """
        Check if agent should respond.

        Modes:
        - always-on: Always respond
        - mention-only: Respond if mentioned
        - reply-only: Respond if replying to agent message
        """
```

### Outbound Queue

```python
class OutboundMessageQueue:
    """
    Manage outgoing responses to channels.
    """

    async def enqueue_response(
        self,
        session_id: str,
        content: str,
        reply_to: Optional[str] = None
    ) -> None:
        """Queue agent response for delivery"""

    async def send_with_retry(
        self,
        channel_name: str,
        recipient_id: str,
        content: str,
        max_retries: int = 3
    ) -> bool:
        """
        Send message with retry logic.
        Handles channel rate limits and failures.
        """

    async def chunk_for_channel(
        self,
        channel_name: str,
        content: str
    ) -> List[str]:
        """
        Break message into channel-appropriate chunks.

        Telegram: 4096 chars
        Slack: 4000 chars (practical)
        Discord: 2000 chars
        """
```

---

## 7. Database Schema

### Core Session Management

```sql
-- Sessions table
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(id),
    channel TEXT NOT NULL,
    user_id TEXT NOT NULL,
    group_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    archived_at TIMESTAMP,
    last_message_at TIMESTAMP,
    metadata JSONB DEFAULT '{}',

    UNIQUE(agent_id, channel, user_id, group_id)
);

CREATE INDEX idx_sessions_agent ON sessions(agent_id);
CREATE INDEX idx_sessions_channel ON sessions(channel);
CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_sessions_archived ON sessions(archived_at) WHERE archived_at IS NULL;
```

### Message History

```sql
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL, -- 'user' | 'assistant' | 'system'
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    channel TEXT,
    channel_message_id TEXT,  -- For edit/delete tracking
    metadata JSONB DEFAULT '{}',

    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX idx_messages_session ON messages(session_id);
CREATE INDEX idx_messages_created ON messages(created_at);
CREATE INDEX idx_messages_role ON messages(session_id, role);
```

### Tool Execution Audit Log

```sql
CREATE TABLE tool_executions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    input JSONB NOT NULL,
    output JSONB,
    error TEXT,
    status TEXT NOT NULL, -- 'success' | 'error' | 'timeout'
    duration_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX idx_tool_executions_session ON tool_executions(session_id);
CREATE INDEX idx_tool_executions_tool ON tool_executions(tool_name);
CREATE INDEX idx_tool_executions_status ON tool_executions(status);
```

### Vector Embeddings (Optional)

```sql
CREATE TABLE embeddings (
    id TEXT PRIMARY KEY,
    message_id TEXT REFERENCES messages(id) ON DELETE CASCADE,
    embedding FLOAT8[] NOT NULL,  -- pgvector format
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_embeddings_message ON embeddings(message_id);
CREATE INDEX idx_embeddings_vector ON embeddings USING ivfflat (embedding vector_cosine_ops);
```

---

## 8. Configuration Management

### Workspace Configuration (YAML)

```yaml
# ~/.claw/workspace.yaml
workspace:
  name: "My AI Assistant"
  version: "1.0"

agents:
  default:
    name: "Claude"
    model: "claude-3-sonnet"
    temperature: 0.7
    max_tokens: 4096
    system_prompt_file: "prompts/system.md"
    tools:
      - "web_search"
      - "browser_control"
      - "file_read"
    disabled_tools:
      - "system_run"  # Disabled for this agent

channels:
  telegram:
    enabled: true
    api_token: "${TELEGRAM_BOT_TOKEN}"
    allowed_users: []  # Empty = all

  slack:
    enabled: false
    api_token: "${SLACK_BOT_TOKEN}"
    signing_secret: "${SLACK_SIGNING_SECRET}"

skills:
  enabled: true
  directories:
    - "~/.claw/skills"
    - "./local_skills"

memory:
  backend: "sqlite"
  path: "~/.claw/messages.db"

security:
  require_pairing: true  # Require DM pairing
  rate_limit_rps: 100
  audit_log: true
```

### Agent Configuration (YAML)

```yaml
# ~/.claw/agents/default.yaml
name: "Claude"
description: "General purpose AI assistant"

model:
  provider: "anthropic"
  name: "claude-3-sonnet"
  api_key: "${ANTHROPIC_API_KEY}"

behavior:
  temperature: 0.7
  max_tokens: 4096
  top_p: 1.0

tools:
  enabled:
    - "web_search"
    - "calculator"
    - "file_operations"
  disabled:
    - "system_run"
    - "camera_snap"

instructions:
  system: |
    You are a helpful AI assistant.
    Be concise, accurate, and friendly.

  constraints:
    - Do not execute system commands without user approval
    - Never store sensitive data in messages
    - Always explain what tools you're using

channels:
  telegram:
    enabled: true
    mention_prefix: "@"
    reply_in_thread: false
```

---

## 9. Configuration Load Order

When starting claw-python:

```
1. Load default configuration (built-in)
2. Load ~/.claw/config.yaml (global overrides)
3. Load environment variables (specific overrides)
4. Load workspace configuration
5. Load agent-specific configuration
6. Load channel credentials from secure storage/env
7. Initialize database connections
8. Start adapters and gateway
9. Load skills from workspace
```

This document provides the detailed architectural reference for implementing claw-python's core components.
