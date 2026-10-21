# Servers Infrastructure Documentation

**Last Updated**: 2025-11-19
**Infrastructure**: Oracle Cloud Free Tier
**Methodology**: Spec-Driven Development (GitHub Spec Kit)

---

## 📁 Directory Structure

```
servers/
├── README.md                    # This file
├── vps/                         # VPS Infrastructure
│   └── spec.md                  # Oracle Cloud Free Tier specs
├── webserver/                   # Matomo Analytics
│   └── spec.md                  # Webserver configuration
├── email/                       # Email Server
│   ├── spec.md                  # Technical specifications
│   ├── constitution.md          # Project principles
│   └── .speckit/               # Spec-kit artifacts (future)
├── sync/                        # File Sync Server
│   ├── spec.md                  # Technical specifications
│   ├── constitution.md          # Project principles
│   └── .speckit/               # Spec-kit artifacts (future)
└── llm-orchestration/          # LLM Orchestration (planned)
    └── (future)
```

---

## 🌐 Infrastructure Overview

All services run on a **single Oracle Cloud VM** (Free Tier):

### Hardware
- **Instance**: VM.Standard.E2.1.Micro
- **vCPUs**: 2 (AMD EPYC 7742)
- **RAM**: 1 GB (shared across all services)
- **Storage**: 50 GB
- **OS**: Ubuntu 24.04 Minimal
- **Region**: EU-Marseille-1 (France)
- **Cost**: $0/month ✅

### IP & DNS
- **Public IP**: 130.110.251.193
- **Domains**:
  - `analytics.diegonmarcos.com` → Matomo
  - `sync.diegonmarcos.com` → Sync Server
  - `mail.diegonmarcos.com` → Email Server

---

## 🐳 Docker Compose Stack

### Resource Allocation

| Service | RAM | Port(s) | Status | Purpose |
|---------|-----|---------|--------|---------|
| **Nginx Proxy Manager** | 50 MB | 80/443/81 | ✅ Active | Reverse proxy + SSL |
| **Matomo Analytics** | 300 MB | 8080 | ✅ Active | Website analytics |
| **MariaDB** | 200 MB | 3306 | ✅ Active | Matomo database |
| **Sync Server** | 150 MB | 8090 | 🔶 Planned | File synchronization |
| **Email Server** | 100 MB | 25/587/993 | 🔶 Planned | SMTP/IMAP + Webmail |
| **LLM Orchestration** | TBD | TBD | 🔶 Planned | N8N workflows + backend |
| **Total Used** | ~800 MB | - | - | 80% utilization |
| **Available** | ~200 MB | - | - | Reserved for overhead |

---

## 📖 Server Documentation

### 1. VPS Infrastructure (`vps/`)

**Purpose**: Complete Oracle Cloud Free Tier VPS documentation

**Contents**:
- Instance specifications and access details
- Network configuration (VCN, subnets, firewall rules)
- SSH access and security
- Docker infrastructure setup
- Monitoring and maintenance procedures
- Backup strategies
- Troubleshooting guides

**Status**: ✅ Complete and deployed

**Read**: [servers/vps/spec.md](./vps/spec.md)

---

### 2. Webserver - Matomo Analytics (`webserver/`)

**Purpose**: Self-hosted web analytics for diegonmarcos.github.io

**Tech Stack**:
- **Application**: Matomo (latest)
- **Database**: MariaDB 10.11
- **Proxy**: Nginx Proxy Manager
- **SSL**: Let's Encrypt (auto-renewal)

**Features**:
- GDPR-compliant analytics
- Google Tag Manager integration
- Event tracking (page views, scroll depth, downloads)
- Cookie consent management

**Status**: ✅ Deployed and active

**Read**: [servers/webserver/spec.md](./webserver/spec.md)

---

### 3. Email Server (`email/`)

**Purpose**: Self-hosted email server with simple webmail UI

**Tech Stack**:
- **MTA**: Postfix (SMTP)
- **MDA**: Dovecot (IMAP/POP3)
- **Webmail**: SnappyMail or minimal Roundcube (read/reply only)
- **Container**: docker-mailserver
- **SSL**: Let's Encrypt via Nginx Proxy

**Features**:
- Full email send/receive capability
- IMAP support for desktop/mobile clients
- Simple webmail interface (read and reply)
- SPF, DKIM, DMARC authentication
- Basic spam filtering
- Daily automated backups

**Status**: 🔶 Specification complete, awaiting deployment

**Read**:
- [servers/email/spec.md](./email/spec.md) - Technical specifications
- [servers/email/constitution.md](./email/constitution.md) - Project principles

---

### 4. Sync Server (`sync/`)

**Purpose**: Custom Go-based file synchronization across Linux, Android, and Garmin watch

**Tech Stack**:
- **Language**: Go 1.21+
- **Framework**: Gin or Echo (REST API)
- **Database**: SQLite3 (embedded)
- **Container**: Docker (multi-stage build)
- **Clients**:
  - Linux: Go daemon (systemd service)
  - Android: Kotlin/Flutter app
  - Garmin: ConnectIQ widget (Monkey C)

**Features**:
- RESTful API with JWT authentication
- File versioning (last 5 versions)
- Conflict detection and resolution
- Gzip compression for transfers
- Specialized Garmin endpoints for fitness data (.FIT files, GPS routes)
- Offline-first design

**Status**: 🔶 Specification complete, awaiting development

**Read**:
- [servers/sync/spec.md](./sync/spec.md) - Technical specifications
- [servers/sync/constitution.md](./sync/constitution.md) - Project principles

**Unique Features**:
- **Garmin Watch Sync**: First-class support for Garmin wearables
- **ConnectIQ Widget**: Upload workouts (.FIT), download routes (.GPX)
- **Multi-platform**: Seamless sync across desktop, mobile, watch

---

### 5. LLM Orchestration (`llm-orchestration/`)

**Purpose**: LLM workflow orchestration with web chat interface

**Tech Stack** (Planned):
- **Orchestration**: N8N workflows
- **Backend**: Custom web chat API
- **Integration**: Claude, GPT, Gemini, local LLMs

**Status**: 🔶 Planning phase

**Read**: [servers/llm-orchestration/](./llm-orchestration/) (coming soon)

---

## 📋 Spec-Kit Methodology

This project follows **Spec-Driven Development** using GitHub Spec Kit:

### Spec-Kit Artifacts

For each server component, we maintain:

1. **`constitution.md`** - Core principles, constraints, and values
2. **`specification.md`** - Detailed requirements and scope (future)
3. **`plan.md`** - Technical implementation plan (future)
4. **`tasks.md`** - Actionable task breakdown (future)

### Current Status

| Server | constitution.md | specification.md | plan.md | tasks.md |
|--------|----------------|------------------|---------|----------|
| VPS | N/A | ✅ (spec.md) | N/A | N/A |
| Webserver | N/A | ✅ (spec.md) | N/A | N/A |
| Email | ✅ | ✅ (spec.md) | 🔶 | 🔶 |
| Sync | ✅ | ✅ (spec.md) | 🔶 | 🔶 |
| LLM Orch | 🔶 | 🔶 | 🔶 | 🔶 |

### Spec-Kit Commands (Future)

```bash
# Constitution: Establish project principles
/speckit.constitution

# Specification: Create baseline specification
/speckit.specify

# Planning: Create implementation plan
/speckit.plan

# Tasks: Generate actionable tasks
/speckit.tasks

# Implementation: Execute implementation
/speckit.implement
```

---

## 🚀 Deployment Status

### ✅ Production (Active)
1. **VPS Infrastructure** - Oracle Cloud instance running
2. **Webserver (Matomo)** - Analytics collecting data
3. **MariaDB** - Database operational
4. **Nginx Proxy Manager** - Reverse proxy with SSL

### 🔶 Planned (Spec Complete)
1. **Email Server** - Awaiting deployment
2. **Sync Server** - Awaiting development
3. **LLM Orchestration** - Awaiting specification

---

## 📊 Resource Monitoring

### Current Usage
```bash
# SSH into VPS
ssh -i ~/.ssh/matomo_key ubuntu@130.110.251.193

# Check Docker stats
docker stats

# Check disk usage
df -h

# Check memory
free -h
```

### Oracle Free Tier Limits
- ✅ 2 AMD VMs (using 1)
- ✅ 200 GB Block Storage (using 50 GB)
- ✅ 10 GB Object Storage (using 0 GB)
- ✅ 10 TB Outbound Transfer/month
- ✅ Always Free (no time limit)

---

## 🔒 Security

### SSL/TLS
- **Provider**: Let's Encrypt
- **Management**: Nginx Proxy Manager (auto-renewal)
- **Protocols**: TLS 1.2, TLS 1.3
- **Features**: Force SSL, HTTP/2, HSTS

### Firewall (Oracle Security List)
| Port | Service | Access |
|------|---------|--------|
| 22 | SSH | Key-based only |
| 80 | HTTP | Redirect to HTTPS |
| 443 | HTTPS | Public |
| 25/587/465 | SMTP | Public (email) |
| 993 | IMAPS | Public (email) |
| 8080/8090 | Internal | Container-only |

### Authentication
- **SSH**: RSA 4096-bit key (`~/.ssh/matomo_key`)
- **Services**: JWT tokens or strong passwords
- **No Root Login**: Disabled
- **No Password Auth**: SSH key only

---

## 🛠️ Maintenance

### Daily
```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs -f --tail=100
```

### Weekly
```bash
# Create backups
./backup.sh

# Check for updates
docker-compose pull
```

### Monthly
```bash
# System updates
sudo apt update && sudo apt upgrade -y

# Check disk usage
du -sh /var/lib/docker/*

# Review logs for anomalies
journalctl -p err -n 50
```

---

## 📞 Access & Management

### SSH Access
```bash
# Quick login
ssh -i ~/.ssh/matomo_key ubuntu@130.110.251.193

# With SSH config (~/.ssh/config)
Host matomo-server
    HostName 130.110.251.193
    User ubuntu
    IdentityFile ~/.ssh/matomo_key

# Then
ssh matomo-server
```

### Service URLs
- **Analytics**: https://analytics.diegonmarcos.com
- **Sync API**: https://sync.diegonmarcos.com/api/v1 (planned)
- **Webmail**: https://mail.diegonmarcos.com (planned)
- **Nginx Admin**: http://130.110.251.193:81

### Oracle Cloud Console
- **URL**: https://cloud.oracle.com
- **Region**: EU (France - Marseille)
- **Compartment**: Default

---

## 🔗 Related Documentation

### Project Root
- [0.constitution_v4.2.md](../0.constitution_v4.2.md) - Project constitution
- [01-spec_v4.2.md](../01-spec_v4.2.md) - Main specification
- [02-plan_v4.2.md](../02-plan_v4.2.md) - Implementation plan
- [04-tasks_v4.2.md](../04-tasks_v4.2.md) - Task breakdown

### Infrastructure
- [docker-compose.yml](../docker-compose.yml) - Main compose file
- [prometheus.yml](../prometheus.yml) - Monitoring config

### Orchestrators
- [langgraph-llm-orchestrator/](../langgraph-llm-orchestrator/) - LangGraph workflows
- [n8n-llm-orchestrator/](../n8n-llm-orchestrator/) - N8N workflows

---

## 🎯 Next Steps

### Immediate (Priority 1)
1. Deploy email server (constitution complete)
2. Test email deliverability (SPF/DKIM/DMARC)
3. Configure simple webmail interface

### Short-term (Priority 2)
1. Develop sync server Go backend
2. Build Linux client daemon
3. Test bidirectional file sync

### Medium-term (Priority 3)
1. Create Android sync app
2. Develop Garmin ConnectIQ widget
3. Test cross-platform sync

### Long-term (Priority 4)
1. Implement LLM orchestration server
2. Add N8N workflows
3. Build web chat interface

---

## 📚 References

### Oracle Cloud
- **Free Tier**: https://www.oracle.com/cloud/free/
- **Docs**: https://docs.oracle.com/en-us/iaas/

### Docker
- **Docker Docs**: https://docs.docker.com/
- **Docker Compose**: https://docs.docker.com/compose/

### Spec-Kit
- **GitHub Spec Kit**: https://github.com/github/spec-kit
- **Spec-Driven Development**: Documentation in langgraph-llm-orchestrator/spec.md

### Email Server
- **docker-mailserver**: https://docker-mailserver.github.io/docker-mailserver/
- **SnappyMail**: https://snappymail.eu/

### Sync Server
- **Garmin ConnectIQ**: https://developer.garmin.com/connect-iq/
- **Go Web Frameworks**: https://echo.labstack.com/, https://gin-gonic.com/

---

**Documentation Version**: 1.0
**Maintained By**: Claude Code
**Last Verified**: 2025-11-19
