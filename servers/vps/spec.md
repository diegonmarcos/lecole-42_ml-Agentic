# VPS Infrastructure Specification

**Last Updated**: 2025-11-19
**Provider**: Oracle Cloud Infrastructure (OCI)
**Tier**: Always Free Tier
**Purpose**: Host Matomo, Email, and Sync servers
**Status**: Production

---

## 🌐 Oracle Cloud Free Tier Overview

### What is Always Free?
Oracle Cloud offers **permanently free** cloud resources (not a trial) with no time limits:
- ✅ 2 AMD-based Compute VMs
- ✅ Up to 4 Arm-based Ampere A1 cores (24GB RAM total)
- ✅ 200 GB Block Storage (total across all instances)
- ✅ 10 GB Object Storage
- ✅ 10 TB Outbound Data Transfer/month
- ✅ Load Balancer (10 Mbps)
- ✅ 2 Virtual Cloud Networks (VCNs)
- ✅ Autonomous Database (20GB)

### Current Usage
- **Active VMs**: 1 x VM.Standard.E2.1.Micro (AMD)
- **Block Storage**: 50 GB (boot volume)
- **VCNs**: 1 (matomo-vcn)
- **Remaining Free Tier**: 1 VM + 150GB storage available

---

## 🖥️ VPS Instance Specifications

### Primary Production Instance

#### Compute Details
- **Instance Name**: `matomo-server` (or user-defined)
- **Instance Type**: VM.Standard.E2.1.Micro
- **Instance OCID**: `ocid1.instance.oc1.eu-marseille-1.anwxeljruadvczacdbn762t6u3lc2a5ttdtjy6el235cehuu52uzmjuezucq`
- **Shape**: VM.Standard.E2.1.Micro (AMD-based)
- **Processor**: AMD EPYC 7742 (2 cores, 2.25 GHz base)
- **vCPUs**: 2 OCPUs (Oracle CPU Units)
- **RAM**: 1 GB DDR4
- **Network Bandwidth**: Up to 480 Mbps
- **Always Free Eligible**: ✅ Yes

#### Storage
- **Boot Volume**: 50 GB
- **Volume Type**: Block Storage (SSD)
- **IOPS**: Up to 3,000 IOPS
- **Throughput**: Up to 120 MB/s
- **Expandable**: Yes (up to 200 GB total in free tier)

#### Operating System
- **OS**: Ubuntu 24.04 LTS Minimal
- **Architecture**: x86_64 (amd64)
- **Kernel**: Linux 6.x
- **Initial User**: `ubuntu`
- **Package Manager**: apt

---

## 🌍 Network Configuration

### Virtual Cloud Network (VCN)
- **VCN Name**: matomo-vcn
- **CIDR Block**: 10.0.0.0/16
- **Region**: EU-Marseille-1 (France)
- **DNS Label**: matomo (auto-generated)
- **Internet Gateway**: Enabled ✅
- **NAT Gateway**: Not configured (free tier allows 1)
- **Service Gateway**: Not configured

### Subnet Configuration
- **Subnet Name**: matomo-subnet
- **CIDR Block**: 10.0.1.0/24
- **Subnet Type**: Public
- **Route Table**: Default Route Table
- **Security List**: Default Security List (custom rules)

### IP Addressing

#### Primary Instance IPs
- **Public IPv4**: 130.110.251.193
- **Private IPv4**: 10.0.1.x (assigned by DHCP)
- **Public IPv6**: Not assigned
- **Elastic IP**: No (ephemeral IP, may change on stop/start)

#### DNS Records
| Subdomain | Type | Value | TTL |
|-----------|------|-------|-----|
| analytics.diegonmarcos.com | A | 130.110.251.193 | 300 |
| sync.diegonmarcos.com | A | 130.110.251.193 | 300 |
| mail.diegonmarcos.com | A | 130.110.251.193 | 300 |

### Firewall Rules (Security List)

#### Ingress Rules
| Port | Protocol | Source CIDR | Description |
|------|----------|-------------|-------------|
| 22 | TCP | 0.0.0.0/0 | SSH access |
| 80 | TCP | 0.0.0.0/0 | HTTP (redirect to HTTPS) |
| 443 | TCP | 0.0.0.0/0 | HTTPS (Nginx Proxy) |
| 25 | TCP | 0.0.0.0/0 | SMTP (Email) |
| 587 | TCP | 0.0.0.0/0 | SMTP Submission (TLS) |
| 465 | TCP | 0.0.0.0/0 | SMTPS (SSL) |
| 993 | TCP | 0.0.0.0/0 | IMAPS (SSL) |
| ICMP | ICMP | 0.0.0.0/0 | Ping |

#### Egress Rules
| Port | Protocol | Destination | Description |
|------|----------|-------------|-------------|
| All | All | 0.0.0.0/0 | Allow all outbound |

---

## 🔐 Access & Authentication

### SSH Access

#### SSH Key Pair
- **Key Name**: `matomo_key`
- **Key Type**: RSA 4096-bit or ED25519
- **Local Path**: `~/.ssh/matomo_key` (private key)
- **Public Key**: Stored in OCI and instance `~/.ssh/authorized_keys`
- **Permissions**: `chmod 600 ~/.ssh/matomo_key`

#### SSH Connection
```bash
# Primary connection method
ssh -i ~/.ssh/matomo_key ubuntu@130.110.251.193

# With verbose debugging
ssh -v -i ~/.ssh/matomo_key ubuntu@130.110.251.193

# Using SSH config
# Add to ~/.ssh/config:
Host matomo-server
    HostName 130.110.251.193
    User ubuntu
    IdentityFile ~/.ssh/matomo_key
    IdentitiesOnly yes
    ServerAliveInterval 60
    ServerAliveCountMax 3

# Then connect with:
ssh matomo-server
```

#### SSH Configuration (Server-side)
```bash
# /etc/ssh/sshd_config
Port 22
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
ChallengeResponseAuthentication no
UsePAM yes
X11Forwarding no
PrintMotd no
AcceptEnv LANG LC_*
Subsystem sftp /usr/lib/openssh/sftp-server
```

### Oracle Cloud Console Access
- **Console URL**: https://cloud.oracle.com
- **Tenancy Name**: [User-specific]
- **User**: [User email]
- **Region**: EU (France - Marseille)
- **Compartment**: Default or custom

### Instance Console Access (Emergency)
If SSH fails, use OCI console:
1. Navigate to **Compute > Instances**
2. Click instance name
3. Click **Console Connection**
4. Launch cloud shell connection

---

## 📊 Resource Monitoring

### OCI Console Metrics
Available in **Compute > Instances > [Instance] > Metrics**:
- CPU Utilization %
- Memory Utilization %
- Network Bytes In/Out
- Disk Read/Write Bytes
- Disk IOPS

### Server-Side Monitoring

#### System Resources
```bash
# CPU usage
htop
top

# Memory usage
free -h
vmstat 1

# Disk usage
df -h
du -sh /var/lib/docker/*

# Network stats
netstat -tulnp
ss -tulnp

# Process monitoring
ps aux | grep -E 'docker|matomo|nginx'
```

#### Docker Stats
```bash
# Real-time container stats
docker stats

# Specific container
docker stats matomo-app

# Disk usage by Docker
docker system df
```

### Oracle Cloud Monitoring (Free)
- **Metric Retention**: 14 days (free tier)
- **Metric Interval**: 1 minute
- **Alarms**: 10 free alarms
- **Notifications**: Email/SMS (free tier limited)

---

## 🐳 Docker Infrastructure

### Docker Installation
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | bash
sudo usermod -aG docker ubuntu

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Verify installation
docker --version
docker compose version
```

### Docker Compose Stack
All services run on a single `docker-compose.yml`:

```yaml
version: '3'

services:
  # Matomo Analytics
  matomo-app:
    image: matomo:latest
    container_name: matomo-app
    restart: unless-stopped
    ports:
      - "8080:80"
    volumes:
      - ./matomo:/var/www/html
    environment:
      - MATOMO_DATABASE_HOST=matomo-db
      - MATOMO_DATABASE_DBNAME=matomo
      - MATOMO_DATABASE_USERNAME=matomo
      - MATOMO_DATABASE_PASSWORD=${MATOMO_DB_PASSWORD}
    depends_on:
      - matomo-db
    deploy:
      resources:
        limits:
          memory: 300M

  # MariaDB Database
  matomo-db:
    image: mariadb:10.11
    container_name: matomo-db
    restart: unless-stopped
    volumes:
      - ./mariadb:/var/lib/mysql
    environment:
      - MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD}
      - MYSQL_DATABASE=matomo
      - MYSQL_USER=matomo
      - MYSQL_PASSWORD=${MATOMO_DB_PASSWORD}
    deploy:
      resources:
        limits:
          memory: 200M

  # Nginx Proxy Manager
  nginx-proxy:
    image: nginxproxymanager/nginx-proxy-manager:latest
    container_name: nginx-proxy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "81:81"
    volumes:
      - ./nginx-proxy/data:/data
      - ./nginx-proxy/letsencrypt:/etc/letsencrypt
    deploy:
      resources:
        limits:
          memory: 50M

  # Sync Server (Go)
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
    deploy:
      resources:
        limits:
          memory: 150M

  # Email Server (TBD)
  # mail-server:
  #   image: mailserver/docker-mailserver:latest
  #   container_name: mail-server
  #   restart: unless-stopped
  #   ports:
  #     - "25:25"
  #     - "587:587"
  #     - "993:993"
  #   deploy:
  #     resources:
  #       limits:
  #         memory: 100M

networks:
  default:
    name: matomo-network
```

### Resource Allocation Summary
| Service | Memory Limit | CPU | Port(s) | Status |
|---------|--------------|-----|---------|--------|
| Matomo App | 300 MB | 0.5 | 8080 | Active |
| MariaDB | 200 MB | 0.5 | 3306 | Active |
| Nginx Proxy | 50 MB | 0.2 | 80/443/81 | Active |
| Sync Server | 150 MB | 0.3 | 8090 | Planned |
| Email Server | 100 MB | 0.5 | 25/587/993 | Planned |
| **Total** | **800 MB** | **2.0** | - | - |

---

## 🔧 Maintenance & Operations

### System Updates
```bash
# Update packages
sudo apt update
sudo apt upgrade -y

# Reboot if kernel updated
sudo reboot

# Docker updates
docker compose pull
docker compose up -d
```

### Backups

#### Manual Backup
```bash
# Create backup directory
mkdir -p ~/backups

# Backup all data
cd ~
tar -czf backups/full-backup-$(date +%Y%m%d).tar.gz \
  matomo/ sync/ mariadb/ nginx-proxy/ docker-compose.yml

# Download to local machine
scp -i ~/.ssh/matomo_key ubuntu@130.110.251.193:~/backups/*.tar.gz ./
```

#### Automated Backup Script
```bash
#!/bin/bash
# /home/ubuntu/backup.sh

BACKUP_DIR="/home/ubuntu/backups"
DATE=$(date +%Y%m%d)
RETENTION_DAYS=30

# Create backup
tar -czf $BACKUP_DIR/backup-$DATE.tar.gz \
  /home/ubuntu/matomo \
  /home/ubuntu/mariadb \
  /home/ubuntu/sync \
  /home/ubuntu/nginx-proxy

# Remove old backups
find $BACKUP_DIR -name "backup-*.tar.gz" -mtime +$RETENTION_DAYS -delete

# Add to crontab
# 0 3 * * * /home/ubuntu/backup.sh
```

### Monitoring Scripts

#### Health Check Script
```bash
#!/bin/bash
# /home/ubuntu/health-check.sh

echo "=== System Health Check ==="
echo "Date: $(date)"
echo ""

echo "CPU Usage:"
top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1"%"}'

echo ""
echo "Memory Usage:"
free -h

echo ""
echo "Disk Usage:"
df -h /

echo ""
echo "Docker Containers:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Size}}"

echo ""
echo "Docker Stats:"
docker stats --no-stream
```

---

## 🚨 Troubleshooting

### Common Issues

#### Instance Stopped/Terminated
Oracle may stop instances if:
- Account inactivity > 90 days
- Free tier abuse detection
- Region capacity issues

**Solution**: Restart from OCI console

#### SSH Connection Refused
```bash
# Check if port 22 is open
telnet 130.110.251.193 22

# Check OCI Security List rules
# Console > Networking > VCN > Security Lists

# Check instance status
# Console > Compute > Instances
```

#### Out of Memory
```bash
# Check memory usage
docker stats

# Restart containers
docker compose restart

# Add swap if needed (temporary)
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

#### Disk Full
```bash
# Check disk usage
df -h

# Clean Docker
docker system prune -a --volumes

# Clean apt cache
sudo apt clean
sudo apt autoclean
```

---

## 📋 Pre-Flight Checklist

### Before Deployment
- [ ] Oracle Cloud account created
- [ ] Always Free tier verified
- [ ] SSH key pair generated
- [ ] VCN and subnet created
- [ ] Security list rules configured
- [ ] Instance launched
- [ ] Domain DNS A records updated
- [ ] SSH access verified

### Initial Setup
- [ ] System packages updated
- [ ] Docker installed
- [ ] Docker Compose installed
- [ ] Firewall configured (if needed)
- [ ] Swap space configured (optional)
- [ ] Monitoring tools installed
- [ ] Backup script created
- [ ] Cron jobs configured

### Service Deployment
- [ ] Docker Compose file created
- [ ] Environment variables set
- [ ] Volumes created
- [ ] Services started
- [ ] Nginx Proxy configured
- [ ] SSL certificates installed
- [ ] Services tested
- [ ] Backups verified

---

## 📚 Reference Documentation

### Oracle Cloud
- **Free Tier**: https://www.oracle.com/cloud/free/
- **Documentation**: https://docs.oracle.com/en-us/iaas/
- **Compute**: https://docs.oracle.com/en-us/iaas/Content/Compute/home.htm
- **Networking**: https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/overview.htm

### Ubuntu
- **Ubuntu Server**: https://ubuntu.com/server/docs
- **Package Management**: https://ubuntu.com/server/docs/package-management

### Docker
- **Docker Docs**: https://docs.docker.com/
- **Docker Compose**: https://docs.docker.com/compose/
- **Best Practices**: https://docs.docker.com/develop/dev-best-practices/

---

## 🔄 Deployment History

| Date | Event | Details |
|------|-------|---------|
| 2025-11-18 | Initial VPS provisioned | Instance: 129.151.229.21 |
| 2025-11-19 | Current production VPS | Instance: 130.110.251.193 |
| 2025-11-19 | Matomo deployed | Docker Compose stack |
| TBD | Sync server deployment | Go-based sync service |
| TBD | Email server deployment | Mail server container |

---

## 📞 Support Contacts

### Oracle Cloud Support
- **Free Tier Support**: Community forums only
- **Community**: https://community.oracle.com/customerconnect/categories/oci
- **Documentation**: https://docs.oracle.com/

### Emergency Access
If locked out of instance:
1. Use OCI Console Instance Console
2. Create new SSH key via console
3. Recreate instance from boot volume backup
4. Contact Oracle Support (paid tiers only)

---

**Specification Version**: 1.0
**Created By**: Claude Code
**Creation Date**: 2025-11-19
**Last Verified**: 2025-11-19
