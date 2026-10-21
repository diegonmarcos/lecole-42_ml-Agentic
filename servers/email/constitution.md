# Email Server Constitution

**Project**: Self-Hosted Email Server
**Version**: 1.0
**Date**: 2025-11-19
**Status**: Active Development

---

## 🎯 Project Vision

Build a secure, lightweight, and reliable self-hosted email server running on Oracle Cloud Free Tier infrastructure, providing full email functionality (SMTP, IMAP) with modern security standards while sharing resources with Matomo and Sync services.

---

## 🏛️ Core Principles

### 1. **Resource Efficiency First**
- **Constraint**: Must operate within 100MB RAM allocation
- **Rationale**: Sharing 1GB instance with multiple services
- **Practice**: Use lightweight mail server solutions (Postfix + Dovecot or docker-mailserver)

### 2. **Security by Default**
- **Constraint**: All email traffic must be encrypted (TLS/SSL)
- **Rationale**: Email contains sensitive personal information
- **Practice**:
  - Force TLS for SMTP submission (port 587)
  - SSL for IMAP (port 993)
  - SPF, DKIM, DMARC configured
  - Fail2ban for brute force protection

### 3. **Deliverability Over Features**
- **Constraint**: Email must reliably reach inbox, not spam folder
- **Rationale**: Primary goal is functional email communication
- **Practice**:
  - Proper DNS records (MX, SPF, DKIM, DMARC, PTR)
  - Reputation monitoring
  - Rate limiting to prevent blacklisting
  - No mass mailing features

### 4. **Simplicity and Maintainability**
- **Constraint**: Single-user or small family use only
- **Rationale**: Easier to maintain, lower resource usage
- **Practice**:
  - Docker-based deployment
  - Minimal custom configuration
  - Clear documentation
  - Automated backups

### 5. **Cost Zero Commitment**
- **Constraint**: Must stay within Oracle Free Tier limits
- **Rationale**: No ongoing operational costs
- **Practice**:
  - Monitor resource usage
  - Optimize storage (email retention policies)
  - Share infrastructure with other services

---

## 🚫 Non-Negotiables

### Must Have
- ✅ End-to-end encryption (TLS/SSL)
- ✅ SPF, DKIM, DMARC authentication
- ✅ Spam filtering (basic)
- ✅ Automated SSL renewal
- ✅ IMAP support for mobile/desktop clients
- ✅ Daily backups of mailboxes
- ✅ **Simple Webmail UI** (Read and reply only - SnappyMail or minimal Roundcube)

### Must Not
- ❌ Support for mass mailing or newsletters
- ❌ Complex multi-domain setup
- ❌ Advanced spam filtering (SpamAssassin consumes too much RAM)
- ❌ Built-in antivirus (ClamAV too resource-heavy for 1GB instance)

### Should Have (If Resources Allow)
- 🔶 SMTP relay for sending via Gmail (as fallback)
- 🔶 Sieve filters for server-side rules
- 🔶 Quota management per mailbox
- 🔶 Contact management in webmail
- 🔶 Calendar integration (optional)

---

## 📐 Technical Constraints

### Infrastructure
- **Platform**: Oracle Cloud Free Tier (VM.Standard.E2.1.Micro)
- **RAM Allocation**: 100MB maximum
- **Shared Resources**: 2 vCPUs, 1GB RAM, 50GB storage (shared with Matomo, Sync, MariaDB)
- **Network**: Same VCN as other services (10.0.0.0/16)

### Technology Stack
- **Container**: Docker (docker-mailserver or Postfix+Dovecot)
- **SMTP**: Postfix (MTA)
- **IMAP/POP3**: Dovecot
- **Database**: None (file-based storage) or shared MariaDB (if needed)
- **Reverse Proxy**: Nginx Proxy Manager (shared)
- **SSL**: Let's Encrypt (automated via Nginx Proxy)

### Security Requirements
- **Ports**: 25 (SMTP), 587 (Submission), 465 (SMTPS), 993 (IMAPS)
- **Authentication**: Strong passwords or certificate-based
- **Encryption**: TLS 1.2+ only
- **Firewall**: Oracle Security List rules

---

## 🎭 User Personas

### Primary User: Personal Email User
- **Who**: Single individual or family (1-5 mailboxes)
- **Needs**:
  - Reliable email sending/receiving
  - Access from multiple devices (phone, laptop, tablet)
  - Privacy from big tech providers
- **Pain Points**:
  - Gmail/Outlook privacy concerns
  - Vendor lock-in
  - Data ownership

### Secondary User: System Administrator
- **Who**: You (the deployer/maintainer)
- **Needs**:
  - Easy deployment and maintenance
  - Clear logs for troubleshooting
  - Minimal manual intervention
- **Pain Points**:
  - Email deliverability issues
  - Spam/blacklist management
  - Resource constraints

---

## 📊 Success Metrics

### Functional Success
- [ ] Send and receive emails reliably (>99% success rate)
- [ ] Zero emails landing in spam folder (proper DNS config)
- [ ] IMAP sync works across all devices
- [ ] SSL certificates auto-renew without intervention

### Performance Success
- [ ] RAM usage < 100MB average
- [ ] Email delivery latency < 10 seconds
- [ ] IMAP response time < 1 second
- [ ] No service crashes for 30+ days

### Security Success
- [ ] All DNS security records pass (SPF, DKIM, DMARC)
- [ ] SSL Labs A+ rating
- [ ] Zero successful brute force attempts
- [ ] No open relay vulnerabilities

---

## 🔄 Evolution Strategy

### Phase 1: Core Email (Current)
- Deploy basic SMTP + IMAP server
- Configure DNS records
- Set up SSL certificates
- Create initial mailbox

### Phase 2: Reliability Enhancement
- Implement automated backups
- Add monitoring and alerts
- Configure Fail2ban
- Test disaster recovery

### Phase 3: User Experience (Optional)
- Add minimal webmail interface
- Implement server-side filtering (Sieve)
- Add email aliases
- Configure auto-responders

### Phase 4: Advanced Features (If Resources Allow)
- SMTP relay for better deliverability
- Calendar/Contacts sync (CalDAV/CardDAV)
- Email retention policies
- Advanced logging

---

## 🔗 Integration Requirements

### With Other Services
- **Nginx Proxy Manager**: SSL termination for webmail (if implemented)
- **Sync Server**: Potential email attachment sync
- **Monitoring**: Email delivery status in shared monitoring dashboard

### External Dependencies
- **DNS Provider**: MX, SPF, DKIM, DMARC, PTR records
- **Email Clients**: Thunderbird, Outlook, Apple Mail, K-9 Mail, etc.
- **Oracle Cloud**: Port forwarding, Security Lists

---

## 📚 Reference Standards

### Email Standards
- RFC 5321 (SMTP)
- RFC 3501 (IMAP4rev1)
- RFC 6376 (DKIM)
- RFC 7208 (SPF)
- RFC 7489 (DMARC)

### Security Standards
- TLS 1.2+ (RFC 5246, RFC 8446)
- Perfect Forward Secrecy
- Strong cipher suites only
- STARTTLS enforcement

---

## ⚠️ Risk Mitigation

### Risk: IP Reputation/Blacklisting
- **Mitigation**:
  - Start with low sending volume
  - Monitor blacklists (MXToolbox)
  - Configure SPF/DKIM/DMARC correctly
  - Use SMTP relay as backup

### Risk: Resource Exhaustion
- **Mitigation**:
  - Strict memory limits (100MB)
  - Email size limits (10MB)
  - Mailbox quotas (1GB per user)
  - Regular cleanup of old emails

### Risk: Security Breach
- **Mitigation**:
  - Fail2ban for brute force protection
  - Strong password policy
  - Regular security updates
  - Minimal exposed ports

### Risk: Data Loss
- **Mitigation**:
  - Daily automated backups
  - Backup retention (30 days)
  - Off-instance backup storage
  - Tested recovery procedures

---

## 🤝 Collaboration Principles

### With AI Assistant (Claude)
- Prioritize security and reliability over features
- Ask for clarification on email delivery best practices
- Request validation of DNS configurations
- Seek guidance on troubleshooting delivery issues

### With Community
- Reference established email server guides (docker-mailserver docs)
- Follow Oracle Cloud community best practices
- Consult mail-tester.com for deliverability testing
- Use MXToolbox for DNS verification

---

## 📝 Decision Log

### Key Architectural Decisions

**Decision 1: Docker-based vs Manual Installation**
- **Choice**: Docker (docker-mailserver image)
- **Reasoning**:
  - Pre-configured for best practices
  - Easier to maintain and update
  - Resource isolation
  - Well-documented

**Decision 2: Webmail Yes/No**
- **Choice**: Optional (Phase 3)
- **Reasoning**:
  - Nice-to-have, not essential
  - Resource intensive
  - Most users prefer native email clients
  - Can add later if resources allow

**Decision 3: Anti-spam/Anti-virus**
- **Choice**: Basic spam filtering only (no ClamAV, no SpamAssassin)
- **Reasoning**:
  - Both are RAM-intensive (200-400MB each)
  - Would exceed 100MB allocation
  - Client-side spam filtering is sufficient for personal use

**Decision 4: Single vs Multi-domain**
- **Choice**: Single domain only
- **Reasoning**:
  - Simpler configuration
  - Lower resource usage
  - Sufficient for personal/family use

---

## 🎯 Alignment with Project Goals

This email server aligns with the broader ml-Agentic infrastructure goals:
- **Self-hosted**: Full control and privacy
- **Cost-effective**: Zero ongoing costs (Free Tier)
- **Integrated**: Shares resources with Matomo and Sync services
- **Secure**: Modern encryption and authentication standards
- **Maintainable**: Docker-based, automated operations

---

**Constitution Version**: 1.0
**Approved By**: Claude Code
**Next Review**: After Phase 1 Deployment
**Living Document**: Yes - update as requirements evolve
