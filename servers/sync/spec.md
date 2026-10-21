# Sync Server Specification

**Last Updated**: 2025-11-19
**Purpose**: Custom Go-based file synchronization server for multi-platform sync
**Status**: Active Development
**Language**: Go (Golang)

---

## 🌐 Infrastructure Overview

### Hosting Provider
- **Platform**: Oracle Cloud Infrastructure (OCI)
- **Tier**: Always Free Tier ✅
- **Region**: EU-Marseille-1 (France) - Same as Matomo server
- **Cost**: $0/month (permanent free tier)

### Instance Specifications
- **Instance Type**: VM.Standard.E2.1.Micro (Shared with Matomo & Email)
- **vCPUs**: 2 (AMD EPYC 7742)
- **RAM**: 1 GB (Shared across all services)
- **Storage**: 50 GB boot volume
- **OS**: Ubuntu 24.04 Minimal
- **Architecture**: x86_64

### Resource Allocation
Running on the same Oracle Cloud instance as Matomo and Email servers:
- **Sync Server RAM**: ~150 MB
- **Matomo**: ~300 MB
- **Email**: ~100 MB
- **MariaDB**: ~200 MB
- **Nginx Proxy**: ~50 MB
- **Total**: ~800 MB / 1 GB (80% utilization)

---

## 🖥️ Server Details

### Production Server
- **Public IP**: 130.110.251.193 (Shared with Matomo)
- **Private IP**: 10.0.1.x (Oracle VCN)
- **VCN**: matomo-vcn (10.0.0.0/16)
- **Subnet**: matomo-subnet (10.0.1.0/24)
- **Domain**: sync.diegonmarcos.com
- **SSH User**: ubuntu
- **SSH Key**: `~/.ssh/matomo_key`

---

## 🔄 Sync Services

### Architecture
- **Language**: Go 1.21+
- **Framework**: Custom REST API (using Gin or Echo)
- **Protocol**: HTTPS with custom binary protocol
- **Database**: SQLite3 (lightweight, embedded)
- **Storage**: Local filesystem with metadata tracking

### Synchronization Methods
- **Protocol**: Custom REST API + WebSocket for real-time sync
- **Encryption**: End-to-end AES-256 encryption
- **Versioning**: Last 5 versions per file
- **Conflict Resolution**: Last-write-wins with conflict markers
- **Compression**: gzip for transfers

### Supported Platforms
- [x] **Linux Desktop** - Native Go client daemon
- [x] **Mobile** - Android/iOS apps (REST API)
- [x] **Garmin Watch** - ConnectIQ widget (limited sync)
- [ ] Web Interface (Optional)

---

## 🐳 Docker Stack Architecture

### Container Setup
Custom Go sync server running in Docker Compose alongside Matomo and Email services.

#### Sync Server Container
- **Image**: Custom Go binary (multi-stage build)
- **Container Name**: sync-server
- **Internal Port**: 8090
- **Exposed Port**: 8090 (proxied via Nginx)
- **Purpose**: File synchronization service
- **Volumes**:
  - `./sync/data:/app/data` - Synced files storage
  - `./sync/db:/app/db` - SQLite database
  - `./sync/config:/app/config` - Configuration files
- **Resources**:
  - Memory limit: 200MB
  - CPU: 0.5 cores

#### Dockerfile (Multi-stage Build)
```dockerfile
# Build stage
FROM golang:1.21-alpine AS builder
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=1 GOOS=linux go build -a -installsuffix cgo -o sync-server ./cmd/server

# Runtime stage
FROM alpine:latest
RUN apk --no-cache add ca-certificates sqlite
WORKDIR /app
COPY --from=builder /build/sync-server .
EXPOSE 8090
CMD ["./sync-server"]
```

#### Docker Compose Integration
```yaml
version: '3'
services:
  sync-server:
    build: ./sync
    container_name: sync-server
    restart: unless-stopped
    ports:
      - "8090:8090"
    volumes:
      - ./sync/data:/app/data
      - ./sync/db:/app/db
      - ./sync/config:/app/config
    environment:
      - SYNC_PORT=8090
      - SYNC_DB_PATH=/app/db/sync.db
      - SYNC_DATA_PATH=/app/data
      - SYNC_LOG_LEVEL=info
    deploy:
      resources:
        limits:
          memory: 200M
    networks:
      - matomo-network
```

---

## 🔒 Security Configuration

### Firewall Rules (Oracle Security List)
| Port | Protocol | Source | Purpose |
|------|----------|--------|---------|
| 22 | TCP | Limited | SSH access (shared) |
| 80 | TCP | 0.0.0.0/0 | HTTP (redirect to HTTPS) |
| 443 | TCP | 0.0.0.0/0 | HTTPS (Nginx Proxy) |
| 8090 | TCP | Internal | Sync server (container-only) |

### SSL/TLS Configuration
- **Certificate Provider**: Let's Encrypt
- **Auto-Renewal**: Yes
- **Protocols**: TLS 1.2, TLS 1.3
- **Features**:
  - Force SSL redirect ✅
  - HTTP/2 enabled ✅
  - HSTS enabled ✅

### Encryption
- **At Rest**: AES-256
- **In Transit**: TLS 1.3
- **End-to-End**: Client-side encryption support

---

## 📂 File System Structure

```
~/sync/
├── Dockerfile                  # Multi-stage Go build
├── docker-compose.yml          # Container orchestration
├── go.mod                      # Go module dependencies
├── go.sum                      # Dependency checksums
├── cmd/
│   └── server/
│       └── main.go            # Server entry point
├── internal/
│   ├── api/                   # REST API handlers
│   ├── sync/                  # Sync engine
│   ├── storage/               # File storage
│   ├── db/                    # SQLite operations
│   └── auth/                  # Authentication
├── config/
│   └── config.yaml            # Server configuration
├── data/
│   └── [synced files]         # User file storage
├── db/
│   └── sync.db               # SQLite database
└── logs/
    └── sync.log              # Application logs
```

---

## 🔧 Go Server Implementation

### Core Components

#### 1. REST API Endpoints
```go
// File Operations
POST   /api/v1/files/upload      // Upload file
GET    /api/v1/files/download    // Download file
GET    /api/v1/files/list        // List files
DELETE /api/v1/files/:id         // Delete file
GET    /api/v1/files/:id/info    // File metadata

// Sync Operations
GET    /api/v1/sync/status       // Get sync status
POST   /api/v1/sync/push         // Push changes
GET    /api/v1/sync/pull         // Pull changes
GET    /api/v1/sync/delta        // Get file deltas

// Auth
POST   /api/v1/auth/login        // Device authentication
POST   /api/v1/auth/register     // Register device
POST   /api/v1/auth/refresh      // Refresh token

// Garmin-specific (lightweight)
GET    /api/v1/garmin/files      // List files (limited)
GET    /api/v1/garmin/download/:id  // Download single file
POST   /api/v1/garmin/upload     // Upload from watch
```

#### 2. Database Schema (SQLite)
```sql
CREATE TABLE devices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,  -- 'linux', 'mobile', 'garmin'
    last_sync DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE files (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    path TEXT NOT NULL,
    size INTEGER,
    hash TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    device_id TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices(id)
);

CREATE TABLE sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT,
    file_id TEXT,
    action TEXT,  -- 'upload', 'download', 'delete'
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices(id),
    FOREIGN KEY (file_id) REFERENCES files(id)
);
```

#### 3. Go Dependencies
```go
// go.mod
module github.com/diegonmarcos/sync-server

go 1.21

require (
    github.com/gin-gonic/gin v1.9.1      // Web framework
    github.com/mattn/go-sqlite3 v1.14.18 // SQLite driver
    github.com/golang-jwt/jwt/v5 v5.2.0  // JWT auth
    github.com/google/uuid v1.5.0        // UUID generation
    golang.org/x/crypto v0.17.0          // Encryption
)
```

---

## 🌍 Access URLs

| Service | URL | Purpose | Auth Required |
|---------|-----|---------|---------------|
| Sync API | https://sync.diegonmarcos.com/api/v1 | RESTful API | Yes (JWT) |
| Health Check | https://sync.diegonmarcos.com/health | Service status | No |
| Metrics | https://sync.diegonmarcos.com/metrics | Prometheus metrics | Limited |

---

## 📊 Resource Usage

### Estimated Requirements
- **Storage**: 100GB - 1TB (based on usage)
- **RAM**: 2-4GB minimum
- **CPU**: 2 cores minimum
- **Bandwidth**: 100GB/month minimum

---

## 🔄 Sync Configuration

### Sync Folders
- `/documents` - Personal documents
- `/photos` - Photo library
- `/backups` - Automated backups
- `/shared` - Shared collaboration space

### Retention Policy
- **Deleted Files**: 30 days in trash
- **Version History**: Last 10 versions or 30 days
- **Automatic Cleanup**: Old versions removed after retention period

---

## 🔗 Client Configuration

### 1. Linux Desktop Client (Go daemon)
```bash
# Installation
curl -L https://sync.diegonmarcos.com/install.sh | bash

# Or build from source
git clone https://github.com/diegonmarcos/sync-client
cd sync-client
go build -o sync-client ./cmd/client

# Configuration
./sync-client configure \
  --server https://sync.diegonmarcos.com \
  --device-name "MyLinuxPC" \
  --sync-dir ~/Sync

# Run as daemon
systemctl --user enable sync-client
systemctl --user start sync-client

# Manual sync
./sync-client sync
```

#### Linux Client Features
- Automatic file watching (inotify)
- Background daemon service
- Conflict resolution UI
- Bandwidth limiting
- Selective folder sync

---

### 2. Mobile App (Android/iOS)

#### Android
```bash
# React Native or Flutter app
# Features:
- Camera upload sync
- Background sync service
- Download on-demand
- Offline file access
- Share to sync
```

#### iOS
```bash
# Swift native app or Flutter
# Features:
- Photos library sync
- Background sync (limited)
- Files app integration
- iCloud Drive compatibility
```

#### Mobile API Integration
```kotlin
// Android Example (Kotlin)
val client = SyncClient("https://sync.diegonmarcos.com")
client.authenticate(deviceId, token)
client.uploadFile(file, "/photos/image.jpg")
val files = client.listFiles("/photos")
```

---

### 3. Garmin Watch Widget (ConnectIQ)

#### Overview
- **Platform**: Garmin ConnectIQ 4.0+
- **Language**: Monkey C
- **Widget Type**: Data field / Glance view
- **Supported Devices**:
  - Fenix 7/7S/7X
  - Forerunner 965/255/955
  - Epix Gen 2
  - Venu 2/3

#### Functionality (Limited by Watch Constraints)
Due to Garmin watch memory and connectivity limitations:
- **Upload**: Activity files (.FIT), workout logs
- **Download**: Lightweight config files, routes (GPX)
- **Max File Size**: 100KB per file
- **Sync Trigger**: Manual or post-activity

#### ConnectIQ Widget Spec
```javascript
// Monkey C pseudo-code
class SyncWidget extends WatchUi.DataField {
    function initialize() {
        serverUrl = "https://sync.diegonmarcos.com/api/v1/garmin";
        deviceId = System.getDeviceSettings().uniqueIdentifier;
    }

    function uploadActivity(fitFile) {
        // Upload .FIT file after workout
        Communications.makeWebRequest(
            serverUrl + "/upload",
            { "file": fitFile, "device": deviceId },
            { :method => Communications.HTTP_REQUEST_METHOD_POST }
        );
    }

    function downloadRoute() {
        // Download GPX route for navigation
        Communications.makeWebRequest(
            serverUrl + "/download/route.gpx",
            { "device": deviceId },
            { :method => Communications.HTTP_REQUEST_METHOD_GET }
        );
    }
}
```

#### Garmin Watch Limitations
- **Memory**: 128KB - 512KB app memory
- **Storage**: Limited persistent storage
- **Network**: Bluetooth (via phone) or WiFi only
- **API Calls**: Rate-limited, low bandwidth
- **File Types**: .FIT, .GPX, .TCX, .JSON only
- **No Background Sync**: Manual trigger required

#### Use Cases for Garmin Sync
1. **Activity Upload**: Auto-upload workout .FIT files post-activity
2. **Route Download**: Sync planned routes for navigation
3. **Config Sync**: Workout plans, training zones
4. **Data Backup**: Backup watch data to server

#### Widget Installation
```bash
# Development
1. Install Garmin ConnectIQ SDK
2. Clone widget source
3. Build .PRG file: monkeyc -o sync-widget.prg
4. Sideload to watch via Garmin Express

# Production
1. Submit to Garmin ConnectIQ Store
2. Download from watch's ConnectIQ store
3. Configure server URL in widget settings
```

#### Widget Glance View
```
┌─────────────────────┐
│ Sync Status         │
│ ─────────────────── │
│ Last Sync: 2h ago   │
│ Files: 3 pending    │
│ [Tap to Sync Now]   │
└─────────────────────┘
```

---

## 🛠️ Maintenance

### Daily Tasks
```bash
# Check sync status
./sync-manage.sh status

# View sync logs
./sync-manage.sh logs
```

### Weekly Tasks
```bash
# Create backup
./sync-manage.sh backup

# Check storage usage
./sync-manage.sh disk-usage
```

### Monthly Tasks
- Review storage quotas
- Check SSL certificate status
- Update server software
- Review sync logs for errors
- Clean up old versions

---

## 🐛 Troubleshooting

### Common Issues

**Sync conflicts:**
```bash
# View conflict files
find ~/sync/data -name "*conflict*"

# Check sync status
./sync-manage.sh conflicts
```

**Storage full:**
```bash
# Check disk usage
df -h

# Clean up old versions
./sync-manage.sh cleanup --older-than 30d
```

**Connection issues:**
```bash
# Check service status
docker-compose ps

# Test connectivity
curl -I https://sync.example.com
```

---

## 📦 Backup Strategy

### Automated Backups
- **Frequency**: Daily
- **Retention**: 30 days
- **Contents**:
  - User data
  - Database
  - Configuration files
- **Destination**: External storage / S3-compatible

### Manual Backup
```bash
./sync-manage.sh backup --full --output /backups/
```

---

## 🔄 Deployment History

| Date | Action | Version | Status |
|------|--------|---------|--------|
| 2025-11-19 | Specification created | 1.0 | Draft |

---

## 📝 Technical Notes

### Performance Optimization
- Enable file chunking for large files
- Configure caching for frequently accessed files
- Use CDN for static assets
- Enable compression for transfers

### Monitoring
- Sync success/failure rates
- Storage usage trends
- Bandwidth consumption
- User activity logs
- Error rates

---

## ✅ Checklist: Post-Deployment

- [ ] Server instance created
- [ ] Docker stack deployed
- [ ] SSL certificate configured
- [ ] DNS records updated
- [ ] User accounts created
- [ ] Client applications tested
- [ ] Backup system verified
- [ ] Monitoring configured
- [ ] Documentation updated

---

## 🔗 Related Documentation

### Sync Solutions
- **Nextcloud**: https://nextcloud.com/
- **Syncthing**: https://syncthing.net/
- **Seafile**: https://www.seafile.com/
- **ownCloud**: https://owncloud.com/

### Protocols
- **WebDAV**: https://en.wikipedia.org/wiki/WebDAV
- **rsync**: https://rsync.samba.org/

---

**Specification Version**: 1.0 (Draft)
**Created By**: Claude Code
**Creation Date**: 2025-11-19
