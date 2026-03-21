# Architecture Comparison: OpenClaw vs NemoClaw vs claw-python

## Executive Summary

This document provides a structured analysis of the architecture of OpenClaw and NemoClaw reference implementations, highlighting key design patterns that claw-python should consider implementing.

**OpenClaw** is a local-first, multi-channel personal AI assistant emphasizing user control and local deployment.
**NemoClaw** is an enterprise-focused, sandboxed implementation providing security-hardened agent execution.
**claw-python** should synthesize these approaches into a modular, extensible Python framework.

---

## 1. Core Architecture Patterns

### OpenClaw: Hub-and-Spoke Gateway Model
```
Messaging Platforms (20+ channels)
        ↓
Gateway (WebSocket @127.0.0.1:18789)
        ↓
Agent Runtime (Pi agent in RPC mode)
        ↓
├─ CLI Interface
├─ WebChat UI
├─ Node Devices (macOS/iOS/Android)
└─ Companion Apps
```

**Design Principles:**
- Local-first, self-hosted control plane
- WebSocket-based communication protocol
- Session isolation with multi-channel routing
- Support for agent-to-agent coordination

### NemoClaw: Containerized Security Model
```
Plugin Layer (TypeScript CLI)
        ↓
Blueprint (Versioned Python artifact)
        ↓
OpenShell Container
        ↓
OpenClaw + OpenShell Gateway
        ↓
├─ Sandbox (Policy-enforced execution)
├─ Inference Engine (NVIDIA backend routing)
└─ Security Layers (Network, Filesystem, Process)
```

**Design Principles:**
- Enterprise security with layered isolation
- Policy-as-code configuration
- Hot-reloadable network and inference policies
- Locked filesystem and process restrictions

### claw-python: Modular Framework Approach
Should implement:
- Pluggable gateway architecture (WebSocket-based)
- Channel adapter interface with standardized routing
- Tool system with exec/device separation
- Memory and session management
- Security layers (optional sandbox, auth, egress control)

---

## 2. Gateway Design Patterns

### OpenClaw Gateway
**Responsibilities:**
- Session persistence with activation modes
- Channel multiplexing (23+ platforms)
- Event routing and webhooks
- Tool execution and streaming
- Presence tracking and typing indicators
- Usage monitoring and cost estimation
- Group routing with mention gating
- Reply tag management

**Key Features:**
- WebSocket control plane
- Stateful session management
- Per-channel message chunking
- Multi-agent routing support

### NemoClaw Gateway (OpenShell)
**Responsibilities:**
- Policy enforcement at network and inference levels
- Request interception and routing
- Hot-reload configuration updates
- TUI-based operator approval workflows
- Audit logging and monitoring

**Key Features:**
- Policy-driven architecture
- Runtime-updateable network policies
- Inference call interception
- Sandbox resource management

### claw-python Gateway Implementation
**Minimum Viable Features:**
- WebSocket server for multi-client communication
- Session management (create, retrieve, route messages)
- Channel registration and multiplexing
- Tool invocation and streaming
- Event management (message queue)
- Authentication/authorization framework

---

## 3. Channel Adapter System

### OpenClaw Channel Support Matrix
| Platform | Adapter | Library | Type |
|----------|---------|---------|------|
| WhatsApp | Baileys | ws-based | Mobile |
| Telegram | grammY | API-based | Mobile |
| Slack | Bolt | API-based | Workspace |
| Discord | discord.js | WebSocket | Community |
| Google Chat | Native | API-based | Workspace |
| Signal | signal-cli | CLI-based | Mobile |
| iMessage/BlueBubbles | Native | Protocol | Apple |
| Microsoft Teams | Native | API-based | Workspace |
| Matrix | Native | Protocol | Federated |
| IRC | Native | Protocol | Legacy |
| Mattermost | API-based | API | Self-hosted |
| Nextcloud Talk | API-based | API | Self-hosted |
| Twitch | API-based | API | Streaming |
| And 10+ more... | Diverse | Various | Mixed |

### Adapter Pattern
Each adapter handles:
- **Group routing** with mention gating and reply tags
- **Per-channel chunking** for message streaming
- **Format translation** (text, media, rich formatting)
- **Security policies** (DM pairing, allowlists)
- **User identity mapping** (channel ID ↔ workspace user)

### claw-python Channel Architecture
**Interface required:**
```python
class ChannelAdapter(ABC):
    """Base adapter for messaging platform integration"""

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def send_message(self, recipient, content, **kwargs) -> None: ...
    async def receive_messages(self) -> AsyncIterator[Message]: ...
    async def get_user_info(self, user_id) -> User: ...
    async def get_group_info(self, group_id) -> Group: ...
```

**Initial Priority Channels:**
1. Telegram (API-based, widely used)
2. Slack (Workspace integration, rich features)
3. Discord (Community support, webhook-ready)

---

## 4. Memory & RAG System

### OpenClaw Memory Architecture
**Workspace Structure:**
- `~/.openclaw/workspace/`
  - `AGENTS.md` - Agent behavior prompting
  - `SOUL.md` - Personality and values
  - `TOOLS.md` - Tool catalog and documentation
  - `skills/` - Skill module directory
    - `<skill>/SKILL.md` - Skill documentation
    - `<skill>/` - Implementation files

**Session History:**
- `sessions_history` tool for transcript retrieval
- Session-level isolation with conversation tracking
- Agent-to-agent message passing via session tools

**Skills Platform (Three-Tier):**
1. **Bundled** - Core shipped skills
2. **Managed** - Registry-based (ClawHub) auto-discovery
3. **Workspace** - Local custom skills

### NemoClaw Memory Considerations
- Limited by sandbox filesystem restrictions
- Only `/sandbox` and `/tmp` accessible
- Policy-based access control to any persistent storage

### claw-python Memory Implementation
**Should include:**
- Workspace configuration (agent profiles, skills)
- Session history storage (SQLite/PostgreSQL)
- Vector embeddings for RAG (LanceDB/Pinecone)
- Conversation context management
- Long-term memory with semantic search
- Skill discovery and loading mechanism

**Proposed Structure:**
```
~/.claw/
├── workspace/
│   ├── agents.yaml
│   ├── skills/
│   │   └── <skill>/
│   │       ├── skill.yaml
│   │       └── __init__.py
│   └── memory/
├── sessions/
│   ├── session_<id>.db
│   └── embeddings/
└── config.yaml
```

---

## 5. Security Layers

### OpenClaw Security Model
**1. DM Pairing-Based Access Control**
- Unknown senders receive short pairing codes
- Requires explicit user approval
- `openclaw pairing approve <channel> <code>`
- Allowlist-based public inbound (requires `dmPolicy="open"`)

**2. Node Permissions (macOS TCC)**
- `system.run` → requires screen recording
- `system.notify` → requires notification permission
- Platform-specific permission checking
- Graceful degradation when permissions denied

**3. Tool Isolation**
- **Exec tools** (run on Gateway host)
- **Device tools** (run on paired nodes via `node.invoke`)
- Enables remote Gateway on Linux + local device capabilities

**4. Configuration Auditing**
- `openclaw doctor` command surfaces risky configs

### NemoClaw Security Layers
**1. Network Isolation**
- Namespace-based network segregation
- Whitelist-based outbound connection model
- Unauthorized requests trigger approval workflow
- Hot-reloadable network policies

**2. Filesystem Restriction**
- Access limited to `/sandbox` and `/tmp`
- Locked at sandbox creation (immutable)
- Seccomp filtering prevents syscalls

**3. Process Security**
- Privilege escalation blocking
- Dangerous syscall filtering
- Locked at creation time (immutable)
- Hardened execution environment

**4. Inference Control**
- All model calls intercepted
- Routed through OpenShell gateway
- Prevents direct API calls from sandbox
- Hot-reloadable routing policies

### claw-python Security Implementation
**Priority layers:**

1. **Authentication** (external auth integration)
   - API key-based for service access
   - OAuth support for user auth
   - JWT token validation

2. **Authorization** (capability-based access)
   - Per-user tool access control
   - Per-channel permission settings
   - Role-based access (user, admin, operator)

3. **Tool Sandboxing** (execution isolation)
   - Subprocess execution with timeouts
   - Resource limits (memory, CPU)
   - Network access control per tool

4. **Audit Logging**
   - All tool invocations logged
   - Session interaction tracking
   - Security event logging

5. **Optional Enterprise Features**
   - Network policy enforcement (egress control)
   - Filesystem access restrictions
   - Inference model access control

---

## 6. Tool System Architecture

### OpenClaw Tool Categories

**Browser Control**
- Dedicated Chrome/Chromium instance
- Chrome DevTools Protocol (CDP)
- Screenshot and interaction snapshots
- Actions: click, type, evaluate JavaScript

**Canvas & A2UI**
- Agent-driven visual workspace
- Push/Reset/Eval/Snapshot operations
- Web-based rendering system
- Real-time agent visualization

**Node Operations** (Device-specific)
- Camera snap/clip
- Screen recording
- Location retrieval
- Notification sending
- Respects platform permissions

**Automation Tools**
- Cron job scheduling
- Webhook management
- Gmail Pub/Sub integration
- Session-to-session communication

**Session Management Tools**
- `sessions_list` - List active sessions
- `sessions_history` - Retrieve transcripts
- `sessions_send` - Agent-to-agent messaging

**Discord/Slack Enhancements**
- Batch suggestion application
- Custom button generation
- Rich message formatting

### NemoClaw Tool Constraints
- Tools must respect sandbox restrictions
- Network calls routed through policy layer
- Filesystem operations limited to `/sandbox`
- Model calls intercepted through OpenShell

### claw-python Tool System
**Core Tool Interface:**
```python
class Tool(ABC):
    """Base tool for agent execution"""

    async def execute(self, **kwargs) -> Any: ...
    def get_schema(self) -> dict: ...
    def requires_permission(self, resource: str) -> bool: ...
```

**Essential Built-in Tools:**
1. Web search (with rate limiting)
2. Browser control (Playwright/Selenium)
3. File operations (with path restrictions)
4. Subprocess execution (with timeouts)
5. HTTP requests (with proxy support)
6. Scheduled tasks (APScheduler)
7. Channel-specific operations (send_message, etc.)

**Tool Categories:**
- **I/O Tools** (file, network, subprocess)
- **Utility Tools** (math, text, time)
- **Channel Tools** (send_message per platform)
- **Computation Tools** (code execution)
- **Memory Tools** (storage, retrieval)

---

## 7. Queue & Message Handling

### OpenClaw Message Flow
1. **Inbound**: Channel adapter receives message
2. **Routing**: Gateway routes to appropriate session/agent
3. **Processing**: Agent processes through tool invocations
4. **Tool Execution**: Streamed block-by-block responses
5. **Outbound**: Response formatted and sent via channel
6. **Archival**: Session history stored

**Key Features:**
- Per-channel message chunking (different limits per platform)
- Streaming responses with block streaming
- Group mention routing
- Reply tag association
- Presence and typing indicators

### NemoClaw Message Handling
- All messages pass through OpenShell container
- Policy-enforced routing
- Inference call interception
- Audit logging of all communications

### claw-python Queue Architecture
**Components:**
1. **Inbound Queue** (FIFO with priority)
   - Channel → Message → Session dispatcher
   - Deduplication for multi-channel routing
   - Priority levels (user, system, background)

2. **Processing Queue**
   - Agent processing state machine
   - Concurrent request handling
   - Timeout management
   - Error recovery with retry logic

3. **Outbound Queue**
   - Response formatting per channel
   - Rate limiting per channel adapter
   - Chunking for platform limits
   - Delivery confirmation tracking

**Proposed Implementation:**
```python
class MessageQueue:
    async def enqueue(self, message: Message, priority: int = 0) -> None: ...
    async def dequeue(self, session_id: str) -> Message: ...
    async def get_status(self, message_id: str) -> MessageStatus: ...
    async def mark_processed(self, message_id: str) -> None: ...

class ResponseFormatter:
    async def format_for_channel(
        self,
        response: str,
        channel: str,
        options: dict
    ) -> List[str]: ...  # Returns chunks respecting channel limits
```

---

## 8. Storage Patterns

### OpenClaw Storage Model
**Workspace Persistence:**
- File-based (`~/.openclaw/workspace/`)
- YAML/Markdown for configuration
- Git-friendly formats for version control
- Skill metadata in SKILL.md files

**Session Storage:**
- In-memory for active sessions
- Disk-backed for history retrieval
- Indexed for quick transcript access

**Configuration:**
- Per-workspace settings
- User preferences
- Channel-specific policies

### NemoClaw Storage Constraints
**Sandbox Restrictions:**
- `/sandbox` directory for persistent data
- `/tmp` for temporary files
- No direct filesystem access outside sandbox
- Policy-controlled blueprints

**Policy Storage:**
- Blueprint artifacts versioned
- Migration system for policy evolution
- Immutable baseline configurations

### claw-python Storage Design
**Recommended Multi-Layer Storage:**

1. **Configuration Layer** (File-based)
   - YAML for agent configuration
   - JSON for tool definitions
   - INI for environment settings

2. **Session Storage** (Database)
   - SQLite for development/local
   - PostgreSQL for production
   - Schema for sessions, messages, events

3. **Memory/Embedding Storage**
   - LanceDB for local vector storage
   - PostgreSQL with pgvector for production
   - Configurable embedding model

4. **Workspace Storage** (Hybrid)
   - File system for skills (Python packages)
   - Database for indexed metadata
   - Cloud storage support for media

**Database Schema (Essential):**
```sql
-- Sessions
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    user_id TEXT,
    created_at TIMESTAMP,
    archived_at TIMESTAMP,
    metadata JSONB
);

-- Messages
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT, -- 'user' | 'assistant' | 'system'
    content TEXT,
    timestamp TIMESTAMP,
    channel TEXT,
    metadata JSONB
);

-- Tools Execution Log
CREATE TABLE tool_executions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    tool_name TEXT,
    input JSONB,
    output JSONB,
    status TEXT, -- 'success' | 'error' | 'timeout'
    duration_ms INTEGER,
    timestamp TIMESTAMP
);

-- Vector Embeddings
CREATE TABLE embeddings (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    content TEXT,
    embedding FLOAT8[],
    timestamp TIMESTAMP
);
```

---

## 9. Architectural Recommendations for claw-python

### Phase 1: Foundation (Current)
- [x] Basic gateway structure (WebSocket server)
- [x] Session management
- [x] Message routing
- [x] Context system

### Phase 2: Channel Adapters
- [ ] Telegram adapter (grammY)
- [ ] Slack adapter (Bolt)
- [ ] Discord adapter (discord.py)
- [ ] Generic webhook adapter

### Phase 3: Tool System
- [ ] Core tool interface and registry
- [ ] Built-in tools (web, file, subprocess)
- [ ] Tool schema generation
- [ ] Permission system

### Phase 4: Memory & Storage
- [ ] Session persistence (SQLite)
- [ ] Message history and search
- [ ] Vector embedding support
- [ ] Workspace configuration system

### Phase 5: Security & Enterprise
- [ ] Authentication framework
- [ ] Authorization (RBAC)
- [ ] Audit logging
- [ ] Tool execution sandboxing

### Phase 6: Advanced Features
- [ ] Multi-channel routing with mention gating
- [ ] Agent-to-agent messaging
- [ ] Skills plugin system
- [ ] Network policy enforcement

### Phase 7: Production Hardening
- [ ] Containerization support
- [ ] Horizontal scaling
- [ ] High availability patterns
- [ ] Monitoring and observability

---

## 10. Design Pattern Summary

| Aspect | OpenClaw | NemoClaw | claw-python Target |
|--------|----------|----------|-------------------|
| **Deployment** | Local-first | Enterprise container | Flexible (both) |
| **Control Plane** | WebSocket Gateway | OpenShell + Plugin | WebSocket Gateway |
| **Security** | Pairing + Permissions | Sandbox + Policies | RBAC + Optional sandbox |
| **Channels** | 23+ adapters | Limited (sandbox) | 3-5 priority adapters |
| **Memory** | File + Workspace | Sandbox-limited | DB + Vector embeddings |
| **Tools** | Mixed exec/device | Sandboxed | Structured registry |
| **Storage** | File-based + History | Policy-controlled | Multi-layer (DB+Files) |
| **Scaling** | Single machine | Container-based | Database-backed |

---

## 11. Key Architectural Decisions for claw-python

### Decision 1: Gateway Architecture
**Chosen: WebSocket-based with Session Isolation**
- Rationale: Aligns with OpenClaw, simpler than full containerization
- Benefit: Flexible local and remote deployment
- Implementation: Use `websockets` library with async/await

### Decision 2: Channel Integration
**Chosen: Standardized Adapter Pattern**
- Rationale: Enables rapid addition of new channels
- Benefit: Decoupled channel implementations
- Implementation: Base `ChannelAdapter` class with interface contracts

### Decision 3: Tool Execution
**Chosen: Structured Tool Registry with Permissions**
- Rationale: Balances flexibility with security
- Benefit: Auditable, controllable tool invocation
- Implementation: Tool schema validation, execution tracking

### Decision 4: Storage Layer
**Chosen: Pluggable (SQLite default, PostgreSQL enterprise)**
- Rationale: Supports both local development and production
- Benefit: Scalability without complexity for simple deployments
- Implementation: SQLAlchemy ORM for database abstraction

### Decision 5: Security Model
**Chosen: Role-Based Access Control + Optional Sandboxing**
- Rationale: Meets security needs without over-engineering
- Benefit: Enterprise-ready without local deployment friction
- Implementation: Decorator-based permission checks, subprocess isolation

---

## Appendix: Reference URLs

- OpenClaw Repository: https://github.com/openclaw/openclaw
- NemoClaw Repository: https://github.com/NVIDIA/NemoClaw
- claw-python Repository: /home/martin/Desktop/claw-python-personal

## Document Metadata
- Created: 2026-03-21
- Analysis Period: Fetched live from GitHub
- OpenClaw Latest Commit: Main branch
- NemoClaw Latest Commit: Main branch (Alpha, since March 16, 2026)
