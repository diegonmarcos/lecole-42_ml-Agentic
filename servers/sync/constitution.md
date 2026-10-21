# Sync Server Constitution

**Project**: Custom Go-Based Multi-Platform File Sync Server
**Version**: 1.0
**Date**: 2025-11-19
**Status**: Active Development

---

## 🎯 Project Vision

Build a lightweight, custom file synchronization server in Go that seamlessly syncs files across Linux desktop, Android mobile, and Garmin watch devices, running on Oracle Cloud Free Tier with minimal resource footprint while maintaining security and reliability.

---

## 🏛️ Core Principles

### 1. **Multi-Platform Native Support**
- **Constraint**: Must support 3 distinct platforms with different capabilities
- **Rationale**: Enable seamless file access across all personal devices
- **Practice**:
  - **Linux**: Full-featured Go daemon with inotify file watching
  - **Android**: Native app (Kotlin/Flutter) with background sync
  - **Garmin Watch**: ConnectIQ widget (limited lightweight sync)

### 2. **Garmin-First Design Philosophy**
- **Constraint**: Garmin watches have severe limitations (128KB-512KB app memory, 100KB max file size)
- **Rationale**: If it works on Garmin, it will work everywhere
- **Practice**:
  - Separate `/api/v1/garmin/*` endpoints optimized for minimal bandwidth
  - Compressed responses
  - Manual sync triggers (no background sync)
  - Focus on .FIT (activity), .GPX (routes), .JSON (config) files

### 3. **Go-Native Implementation**
- **Constraint**: Server and Linux client both written in pure Go
- **Rationale**: Performance, simplicity, cross-compilation, single binary deployment
- **Practice**:
  - Gin or Echo web framework for REST API
  - SQLite3 for metadata (embedded, no external DB)
  - Standard library for crypto and file operations
  - Compile to static binary for Docker Alpine image

### 4. **Resource Efficiency**
- **Constraint**: 150MB RAM allocation on shared 1GB instance
- **Rationale**: Sharing resources with Matomo, Email, MariaDB, Nginx
- **Practice**:
  - No in-memory file caching (stream files directly)
  - SQLite instead of PostgreSQL/MySQL
  - Connection pooling and rate limiting
  - Lazy loading of file metadata

### 5. **Security Without Compromise**
- **Constraint**: All sync traffic must be encrypted end-to-end
- **Rationale**: Synced files may contain sensitive personal data
- **Practice**:
  - HTTPS/TLS for all API communication
  - JWT token authentication per device
  - AES-256 encryption for files at rest (optional)
  - No plain-text credentials stored

### 6. **Simplicity Over Features**
- **Constraint**: Single user, not a Dropbox replacement
- **Rationale**: Easier to maintain, fewer bugs, lower resource usage
- **Practice**:
  - Last-write-wins conflict resolution (no complex merging)
  - Maximum 5 file versions retained
  - No real-time collaboration features
  - No file sharing with external users

---

## 🚫 Non-Negotiables

### Must Have
- ✅ RESTful API (HTTPS only)
- ✅ JWT-based authentication per device
- ✅ Linux daemon client (Go-based)
- ✅ Android app (native or Flutter)
- ✅ Garmin ConnectIQ widget
- ✅ SQLite database for metadata
- ✅ File versioning (last 5 versions)
- ✅ Conflict detection and markers
- ✅ Gzip compression for transfers
- ✅ Health check endpoint

### Must Not
- ❌ Real-time collaborative editing
- ❌ File sharing with external users
- ❌ Web-based file browser (no web UI)
- ❌ Support for files >100MB (Garmin constraint)
- ❌ Complex merge algorithms
- ❌ Blockchain or P2P sync (centralized only)
- ❌ Third-party cloud storage integration

### Should Have (If Resources Allow)
- 🔶 WebSocket for real-time sync notifications
- 🔶 Prometheus metrics endpoint
- 🔶 Selective folder sync (client-side)
- 🔶 Bandwidth throttling (client-side)
- 🔶 iOS app (Swift or Flutter)
- 🔶 File encryption at rest

---

## 📐 Technical Constraints

### Infrastructure
- **Platform**: Oracle Cloud Free Tier (VM.Standard.E2.1.Micro)
- **RAM Allocation**: 150MB maximum
- **Shared Resources**: 2 vCPUs, 1GB RAM, 50GB storage (shared)
- **Network**: Same VCN as Matomo and Email (10.0.0.0/16)

### Technology Stack
- **Server Language**: Go 1.21+
- **Web Framework**: Gin or Echo
- **Database**: SQLite3 (embedded)
- **Container**: Docker (multi-stage build from golang:alpine)
- **Reverse Proxy**: Nginx Proxy Manager (shared)
- **SSL**: Let's Encrypt via Nginx Proxy

### Client Technology
| Platform | Language | Framework | Deployment |
|----------|----------|-----------|------------|
| Linux | Go | CLI + systemd daemon | Binary or install script |
| Android | Kotlin/Dart | Native/Flutter | APK or Google Play |
| Garmin | Monkey C | ConnectIQ SDK | ConnectIQ Store |

### API Constraints
- **Max File Size**: 100MB (client-enforced)
- **Max Request Size**: 100MB
- **Rate Limiting**: 100 req/min per device
- **Garmin Max File Size**: 100KB (separate limit)
- **File Versioning**: Last 5 versions only

---

## 🎭 User Personas

### Primary User: Cross-Platform Power User
- **Who**: Individual with Linux PC, Android phone, and Garmin watch
- **Needs**:
  - Sync workout data (.FIT) from Garmin to PC
  - Download GPS routes (.GPX) to Garmin for navigation
  - Access documents from both PC and phone
  - Automatic photo backup from Android
- **Pain Points**:
  - No good solution for Garmin file sync
  - Don't trust Google Drive/Dropbox with personal data
  - Want self-hosted privacy

### Secondary User: Fitness Enthusiast
- **Who**: Runner/cyclist using Garmin watch for training
- **Needs**:
  - Auto-upload workout files post-activity
  - Sync training plans to watch
  - Backup all fitness data
- **Pain Points**:
  - Garmin Connect vendor lock-in
  - Limited Garmin watch storage
  - Want local backup of all .FIT files

### Tertiary User: Privacy-Conscious Individual
- **Who**: Someone who wants complete data sovereignty
- **Needs**:
  - Self-hosted file sync
  - End-to-end encryption
  - No third-party access to files
- **Pain Points**:
  - Cloud providers mine personal data
  - Subscription fatigue
  - Data breaches

---

## 📊 Success Metrics

### Functional Success
- [ ] Linux client syncs files bidirectionally with <5 second latency
- [ ] Android app uploads photos in background
- [ ] Garmin widget successfully uploads .FIT files post-workout
- [ ] Garmin widget downloads .GPX routes <10 seconds
- [ ] Zero data loss across all sync operations
- [ ] Conflict files generated for simultaneous edits

### Performance Success
- [ ] Server RAM usage < 150MB average
- [ ] API response time < 500ms (excluding file transfer)
- [ ] File upload speed limited only by network bandwidth
- [ ] Garmin sync completes in <30 seconds for small files
- [ ] SQLite database size < 100MB for 10,000 files

### Client Success
- [ ] Linux daemon uses < 50MB RAM
- [ ] Android app battery drain < 5% per day
- [ ] Garmin widget memory < 256KB
- [ ] All clients handle offline gracefully

### Developer Experience
- [ ] Single `go build` produces working binary
- [ ] Docker image builds in < 2 minutes
- [ ] API fully documented (OpenAPI spec)
- [ ] Client SDKs easy to use

---

## 🔄 Evolution Strategy

### Phase 1: Server Core (Current)
- Build Go REST API server
- Implement JWT authentication
- Create SQLite schema
- Deploy to Docker
- Test with curl/Postman

### Phase 2: Linux Client
- Build Go daemon client
- Implement file watching (inotify)
- Create systemd service
- Test bidirectional sync

### Phase 3: Android App
- Build basic upload/download app
- Implement background sync service
- Add camera upload feature
- Publish APK

### Phase 4: Garmin Widget
- Build ConnectIQ widget
- Implement .FIT file upload
- Add .GPX route download
- Submit to ConnectIQ Store

### Phase 5: Enhancements (Optional)
- Add WebSocket for real-time notifications
- Implement selective folder sync
- Add file encryption at rest
- Create iOS app
- Build Prometheus metrics

---

## 🔗 Integration Requirements

### With Other Services
- **Nginx Proxy Manager**: HTTPS termination, domain routing (sync.diegonmarcos.com)
- **Monitoring**: Health checks, uptime tracking
- **Backup System**: Daily backup of SQLite DB and file storage

### External Dependencies
- **DNS Provider**: A record for sync.diegonmarcos.com
- **Let's Encrypt**: SSL certificate (via Nginx Proxy)
- **Garmin Express**: For sideloading widget during development
- **ConnectIQ Store**: For production widget distribution

### Client-Side Dependencies
| Platform | Dependencies |
|----------|--------------|
| Linux | inotify-tools, systemd (daemon mode) |
| Android | Android SDK 24+, WorkManager (background sync) |
| Garmin | ConnectIQ SDK 4.0+, Compatible watch |

---

## 📚 Reference Standards

### API Design
- RESTful principles (GET, POST, DELETE)
- JWT authentication (RFC 7519)
- JSON responses
- HTTP status codes (200, 201, 400, 401, 404, 500)

### File Sync Algorithms
- Last-write-wins for simplicity
- Content-based hashing (SHA-256) for change detection
- Delta sync for large files (optional)
- Version history with timestamps

### Garmin ConnectIQ
- Memory limits: 128KB-512KB depending on device
- File size limits: 100KB max per file
- Network: Bluetooth or WiFi only
- HTTP communication via Communications API

---

## ⚠️ Risk Mitigation

### Risk: Garmin Watch Memory Constraints
- **Mitigation**:
  - Minimal widget footprint (<256KB)
  - Offload processing to server
  - Limit file types to .FIT, .GPX, .JSON
  - Manual sync only (no background polling)

### Risk: Sync Conflicts
- **Mitigation**:
  - Last-write-wins with conflict markers
  - Generate .conflict files for user review
  - Timestamp-based conflict detection
  - Clear conflict resolution UI in clients

### Risk: Data Loss
- **Mitigation**:
  - File versioning (last 5 versions)
  - Daily SQLite backups
  - Crash-safe database writes (WAL mode)
  - Atomic file operations

### Risk: Security Breach
- **Mitigation**:
  - JWT tokens with expiration
  - HTTPS only (no HTTP fallback)
  - Rate limiting per device
  - No password storage (token-based only)

### Risk: Resource Exhaustion
- **Mitigation**:
  - 150MB RAM limit enforced
  - Max 100MB file size
  - Connection pooling
  - Graceful degradation under load

---

## 🤝 Collaboration Principles

### With AI Assistant (Claude)
- Focus on Go best practices and idiomatic code
- Request guidance on Garmin ConnectIQ limitations
- Seek advice on sync conflict resolution strategies
- Ask for Docker optimization tips

### With Garmin Developer Community
- Reference ConnectIQ forums for widget limitations
- Share lightweight sync strategies
- Learn from existing fitness data sync widgets
- Follow ConnectIQ security guidelines

### With Open Source Community
- Publish Go server code (MIT license)
- Share client SDKs for reuse
- Document API with OpenAPI spec
- Provide example implementations

---

## 📝 Decision Log

### Key Architectural Decisions

**Decision 1: Go vs Node.js/Python for Server**
- **Choice**: Go
- **Reasoning**:
  - Better performance (lower RAM usage)
  - Static binary deployment (no runtime)
  - Excellent concurrency primitives
  - Same language as Linux client
  - Strong standard library

**Decision 2: SQLite vs PostgreSQL/MySQL**
- **Choice**: SQLite
- **Reasoning**:
  - Embedded (no separate process)
  - Lower RAM usage (~10MB vs 200MB+)
  - Sufficient for single-user workload
  - WAL mode for crash safety
  - Easier backup (single file)

**Decision 3: REST vs GraphQL**
- **Choice**: REST
- **Reasoning**:
  - Simpler for Garmin widget (limited HTTP client)
  - Lower overhead
  - Standard HTTP methods
  - Easier caching
  - Client familiarity

**Decision 4: Real-time Sync vs Polling**
- **Choice**: Polling (with WebSocket optional)
- **Reasoning**:
  - Garmin requires polling (no WebSocket support)
  - Simpler to implement
  - Lower resource usage
  - Good enough for personal use
  - Can add WebSocket later

**Decision 5: Garmin Widget vs Mobile App Only**
- **Choice**: Dedicated Garmin widget (not just mobile relay)
- **Reasoning**:
  - Direct watch connectivity (no phone dependency)
  - Faster sync (watch WiFi vs Bluetooth relay)
  - Unique feature differentiator
  - Addresses fitness data backup use case

---

## 🎯 Alignment with Project Goals

This sync server aligns with the broader ml-Agentic infrastructure goals:
- **Self-hosted**: Complete data sovereignty
- **Cost-effective**: Zero ongoing costs (Free Tier)
- **Integrated**: Shares resources efficiently with other services
- **Secure**: Modern encryption and authentication
- **Maintainable**: Simple Go codebase, Docker deployment
- **Innovative**: Unique Garmin watch sync capability

---

## 🔮 Future Possibilities

### Beyond Current Scope (Post-MVP)
- **iOS Client**: Swift app for Apple ecosystem
- **File Encryption at Rest**: Client-side encryption before upload
- **Selective Folder Sync**: Choose which folders sync to which devices
- **Bandwidth Throttling**: Limit sync speed for metered connections
- **LAN Sync**: Direct PC-to-phone sync on local network
- **Conflict Resolution UI**: Visual diff tool for conflicts
- **Shared Folders**: Limited sharing with other users
- **Public File Links**: Time-limited download links

---

**Constitution Version**: 1.0
**Approved By**: Claude Code
**Next Review**: After Phase 1 Completion
**Living Document**: Yes - evolve with user needs and technical learnings
