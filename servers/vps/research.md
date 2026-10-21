# VPS Provider Research & Pricing

**Last Updated**: 2025-11-19
**Purpose**: Compare VPS providers for cost-effectiveness and LLM deployment
**Focus Areas**: Free tiers, cheap options, GPU/VRAM availability, LLM-native platforms

---

## 🎯 Research Criteria

### Must-Have
- Low cost or free tier
- Linux support (Ubuntu/Debian preferred)
- Sufficient RAM (1GB minimum)
- Reliable uptime (>99%)
- Docker support

### Nice-to-Have
- GPU/VRAM access for LLMs
- Pay-as-you-use billing
- LLM-native infrastructure
- API access
- S3-compatible storage

---

## 💰 Free Tier Providers

### 1. Oracle Cloud (Current Choice)

**Always Free Tier** ⭐ BEST FREE OPTION
- **Compute**: 2x VM.Standard.E2.1.Micro (AMD) - 1GB RAM, 2 vCPUs each
- **OR**: 4x ARM Ampere A1 cores + 24GB RAM (configurable)
- **Storage**: 200 GB Block Storage
- **Transfer**: 10 TB outbound/month
- **Duration**: **Permanent** (no time limit)
- **Cost**: $0/month forever

**Pros**:
- ✅ Best free tier (no expiration)
- ✅ ARM option excellent for LLM inference
- ✅ Generous bandwidth (10 TB)
- ✅ Multiple regions (EU, US, Asia)
- ✅ Full VCN with load balancer

**Cons**:
- ❌ Account creation can be challenging
- ❌ Free tier resources can be reclaimed if inactive
- ❌ Limited support (community only)
- ❌ No GPU in free tier

**LLM Capability**:
- ARM A1 instance (4 cores, 24GB) can run small LLMs (7B models with quantization)
- Sufficient for llama.cpp, Ollama with GGUF models

**Current Status**: ✅ Active (using AMD instance)

---

### 2. Google Cloud Platform (GCP)

**Free Tier**
- **Compute**: 1x e2-micro (0.25-0.5 vCPU, 1GB RAM)
- **Storage**: 30 GB HDD
- **Transfer**: 1 GB North America egress/month
- **Duration**: Permanent + $300 credit (90 days)
- **Cost**: $0/month (with limits)

**Pros**:
- ✅ $300 free credit for 90 days
- ✅ Excellent documentation
- ✅ TPU access (paid)
- ✅ Vertex AI for LLMs

**Cons**:
- ❌ Very limited free tier compute
- ❌ 1 GB bandwidth is restrictive
- ❌ TPU/GPU very expensive
- ❌ Can be complex to configure

**LLM Capability**:
- e2-micro too small for LLM hosting
- Vertex AI charges per-request (expensive)
- TPU Pods for training (starting $4.50/hour)

---

### 3. AWS (Amazon Web Services)

**Free Tier** (12 months)
- **Compute**: 750 hours/month t2.micro (1 vCPU, 1GB RAM)
- **Storage**: 30 GB EBS
- **Transfer**: 15 GB outbound
- **Duration**: 12 months only
- **Cost**: $0/month (first year), then ~$10/month

**Pros**:
- ✅ Industry standard
- ✅ Extensive service catalog
- ✅ SageMaker for LLMs
- ✅ Bedrock for managed LLMs

**Cons**:
- ❌ Only 12 months free
- ❌ Complex pricing (easy to overspend)
- ❌ GPU instances very expensive (p3.2xlarge ~$3/hour)
- ❌ Limited free tier

**LLM Capability**:
- AWS Bedrock: Pay-per-token (Claude, Llama2)
- SageMaker: Custom model deployment ($0.05/hour minimum)
- EC2 GPU: p3 instances starting $3.06/hour

---

### 4. Azure (Microsoft)

**Free Tier** (12 months)
- **Compute**: 750 hours/month B1S (1 vCPU, 1GB RAM)
- **Storage**: 64 GB + 5 GB blob
- **Transfer**: 15 GB outbound
- **Duration**: 12 months + $200 credit (30 days)
- **Cost**: $0/month (first year)

**Pros**:
- ✅ $200 credit for experimentation
- ✅ Azure OpenAI Service
- ✅ Good Windows support
- ✅ Strong enterprise features

**Cons**:
- ❌ Only 12 months free
- ❌ Complex portal
- ❌ GPU very expensive
- ❌ Limited free tier post-trial

**LLM Capability**:
- Azure OpenAI: Pay-per-token (GPT-4, GPT-3.5)
- Azure ML: Custom models ($0.10/hour minimum)
- NC-series GPU: Starting $0.90/hour (cheapest GPU option)

---

## 💵 Ultra-Cheap VPS Providers (No GPU)

### 5. Hetzner

**Cloud VPS**
- **Instance**: CX11 (1 vCPU, 2GB RAM, 20GB SSD)
- **Cost**: **€4.15/month** (~$4.50)
- **Transfer**: 20 TB included
- **Location**: Germany, Finland, USA

**Pros**:
- ✅ Excellent price/performance
- ✅ High bandwidth
- ✅ IPv6 included
- ✅ Good reputation
- ✅ Simple pricing

**Cons**:
- ❌ No free tier
- ❌ No GPU options
- ❌ EU-focused (GDPR strict)

**LLM Capability**:
- Dedicated GPU servers available (not VPS)
- GPU server starting €39/month (older GPUs)
- Can run small LLMs (7B quantized) on CX21 (2GB RAM)

---

### 6. Contabo

**VPS S SSD**
- **Instance**: 4 vCPUs, 8GB RAM, 200GB SSD
- **Cost**: **€5.99/month** (~$6.50)
- **Transfer**: 32 TB included
- **Location**: EU, USA, Asia

**Pros**:
- ✅ Incredible RAM for price
- ✅ Huge bandwidth
- ✅ Multiple locations
- ✅ Simple setup

**Cons**:
- ❌ Shared resources (oversubscribed)
- ❌ No GPU
- ❌ Mixed reviews on support
- ❌ Performance can vary

**LLM Capability**:
- 8GB RAM can run 7B models with quantization
- Good for Ollama, llama.cpp
- CPU-only inference (slow)

---

### 7. Vultr

**Regular Performance**
- **Instance**: 1 vCPU, 1GB RAM, 25GB SSD
- **Cost**: **$6/month**
- **Transfer**: 2 TB included
- **Location**: 25+ locations worldwide

**Cloud GPU** (Pay-as-you-use)
- **Instance**: 1x A100 (80GB VRAM)
- **Cost**: **$2.50/hour** (pay-as-you-use)
- **Also**: RTX 6000 Ada ($1.25/hour), A40 ($1.50/hour)

**Pros**:
- ✅ Hourly GPU billing (no long commitment)
- ✅ A100 available
- ✅ Simple pricing
- ✅ Good global coverage
- ✅ Instant deployment

**Cons**:
- ❌ GPU expensive for 24/7 usage
- ❌ CPU VPS pricier than competitors
- ❌ Lower specs for price

**LLM Capability**: ⭐ EXCELLENT
- A100 80GB can run 70B models
- RTX 6000 Ada (48GB) for 33B models
- Pay-as-you-use perfect for inference spikes
- Pre-installed CUDA drivers

---

## 🚀 LLM-Native Platforms (Pay-as-you-use VRAM)

### 8. RunPod ⭐ BEST FOR LLMS

**Serverless GPU**
- **Pricing**: Pay per second of GPU usage
- **GPUs Available**:
  - RTX 4090 (24GB): **$0.69/hour**
  - RTX 4080 (16GB): **$0.49/hour**
  - RTX A6000 (48GB): **$0.89/hour**
  - A100 80GB: **$2.29/hour**
  - H100 80GB: **$4.89/hour**
- **Billing**: Per-second (minimum 5 seconds)
- **Autoscale**: 0 to 100+ GPUs instantly

**Pros**:
- ✅ TRUE pay-per-second (sleep = $0)
- ✅ Cheapest GPU pricing
- ✅ LLM-optimized templates (vLLM, Text Generation Inference)
- ✅ Jupyter, SSH, HTTP endpoints
- ✅ Huge GPU selection
- ✅ Automatic scaling

**Cons**:
- ❌ Cold start latency (5-30 seconds)
- ❌ Limited CPU-only options
- ❌ Network storage costs extra

**LLM Capability**: ⭐⭐⭐ EXCEPTIONAL
- Pre-built templates for Llama2, Mistral, Falcon
- vLLM for fast inference
- Can run 70B models on A100
- Autoscale based on demand

**Best Use Case**: Inference spikes, development, fine-tuning

**Cost Example**:
- Run 7B model 24/7 on RTX 4080: $354/month
- Run 7B model 8 hours/day: $118/month
- On-demand usage: $0.50/hour only when active

---

### 9. Vast.ai ⭐ CHEAPEST GPU

**Peer-to-Peer GPU Marketplace**
- **Pricing**: Varies by provider (auction-style)
- **Typical Prices**:
  - RTX 3090 (24GB): **$0.20-0.35/hour**
  - RTX 4090 (24GB): **$0.40-0.60/hour**
  - A100 40GB: **$0.80-1.20/hour**
  - A100 80GB: **$1.50-2.00/hour**
- **Billing**: Per hour (can stop anytime)

**Pros**:
- ✅ CHEAPEST GPU prices (50-70% cheaper than clouds)
- ✅ Huge GPU selection (consumer + data center)
- ✅ Pay-as-you-go
- ✅ Jupyter, SSH access
- ✅ Docker support

**Cons**:
- ❌ Variable reliability (peer-hosted)
- ❌ Some hosts may disconnect
- ❌ No SLA/uptime guarantee
- ❌ Data transfer costs variable
- ❌ Need to find available instances

**LLM Capability**: ⭐⭐⭐ EXCELLENT (if reliable host)
- Can run 70B models on cheap A100
- RTX 3090 great for 13B-30B models
- Popular for ML training/inference

**Best Use Case**: Batch processing, experimentation, fine-tuning

---

### 10. Together.ai

**Serverless LLM Inference**
- **Pricing**: Per-token, not per-second
- **Models**:
  - Llama-2-70B: **$0.90/million tokens**
  - Mistral-7B: **$0.20/million tokens**
  - Llama-2-13B: **$0.23/million tokens**
- **Custom Models**: Bring your own (BYOM)
- **Fine-tuning**: Available

**Pros**:
- ✅ No infrastructure management
- ✅ Pay per token (very granular)
- ✅ Fast inference (vLLM backend)
- ✅ Can deploy custom models
- ✅ API-first

**Cons**:
- ❌ No direct GPU access
- ❌ Limited to supported models
- ❌ Can be expensive for high volume

**LLM Capability**: ⭐⭐⭐ Serverless
- Optimized for inference
- No cold start
- Good for API-based applications

---

### 11. Lambda Labs

**On-Demand GPU Cloud**
- **Pricing**:
  - RTX 6000 Ada (48GB): **$0.80/hour**
  - A100 40GB: **$1.10/hour**
  - A100 80GB: **$1.99/hour**
  - H100 80GB: **$2.99/hour**
- **Billing**: Hourly, can stop anytime
- **Location**: USA primarily

**Pros**:
- ✅ ML/AI focused
- ✅ Pre-installed ML frameworks (PyTorch, TensorFlow)
- ✅ Jupyter pre-configured
- ✅ NVMe storage included
- ✅ Good performance

**Cons**:
- ❌ Limited availability (popular GPUs often sold out)
- ❌ USA-focused
- ❌ No serverless autoscaling

**LLM Capability**: ⭐⭐⭐ Great for training
- Optimized for ML workloads
- Fast NVMe storage
- Multi-GPU support

---

### 12. Modal

**Serverless Python Functions + GPU**
- **Pricing**:
  - CPU: $0.0001/second
  - GPU (A100): **$0.0035/second** ($1.26/hour)
  - GPU (T4): **$0.0006/second** ($0.216/hour)
- **Billing**: Per-second of actual usage
- **Autoscale**: Automatic (0 to thousands)

**Pros**:
- ✅ TRUE serverless (pay only when running)
- ✅ Python-native (decorator-based)
- ✅ Autoscaling to zero
- ✅ Container-based
- ✅ Great for API endpoints

**Cons**:
- ❌ Python only
- ❌ Not for long-running processes
- ❌ Cold start latency

**LLM Capability**: ⭐⭐⭐ Perfect for API inference
- Deploy LLM as API endpoint
- Auto-scale based on demand
- Sleep when idle (save $)

---

## 📊 Comparison Tables

### Free Tier Comparison

| Provider | vCPUs | RAM | Storage | Bandwidth | Duration | Cost |
|----------|-------|-----|---------|-----------|----------|------|
| **Oracle Cloud** | 2 (or 4 ARM) | 1-24 GB | 200 GB | 10 TB | ∞ | $0 |
| Google Cloud | 0.5 | 1 GB | 30 GB | 1 GB | ∞ | $0 |
| AWS | 1 | 1 GB | 30 GB | 15 GB | 12mo | $0 |
| Azure | 1 | 1 GB | 64 GB | 15 GB | 12mo | $0 |

**Winner**: Oracle Cloud (no contest)

---

### Cheap CPU VPS Comparison

| Provider | vCPUs | RAM | Storage | Bandwidth | Cost/month |
|----------|-------|-----|---------|-----------|------------|
| Hetzner CX11 | 1 | 2 GB | 20 GB | 20 TB | **$4.50** |
| Contabo VPS S | 4 | 8 GB | 200 GB | 32 TB | **$6.50** |
| Vultr | 1 | 1 GB | 25 GB | 2 TB | $6 |
| DigitalOcean | 1 | 1 GB | 25 GB | 1 TB | $6 |
| Linode | 1 | 1 GB | 25 GB | 1 TB | $5 |

**Winner**: Contabo (most RAM/storage) or Hetzner (best reputation)

---

### Pay-as-you-use GPU Comparison (per hour)

| Provider | RTX 4090 (24GB) | A100 80GB | H100 80GB | Billing |
|----------|-----------------|-----------|-----------|---------|
| **RunPod** | **$0.69** | **$2.29** | **$4.89** | Per-second |
| **Vast.ai** | **$0.40-0.60** | **$1.50-2.00** | N/A | Per-hour |
| Lambda Labs | N/A | $1.99 | $2.99 | Per-hour |
| Vultr | N/A | $2.50 | N/A | Per-hour |
| Modal | N/A | $1.26 | N/A | Per-second |
| AWS (p4d) | N/A | ~$32* | N/A | Per-hour |

*AWS A100 = p4d.24xlarge (8x A100) = $32.77/hour

**Winner**: Vast.ai (cheapest) or RunPod (best reliability + per-second billing)

---

### LLM-Native Platform Comparison

| Provider | Model Size | Pricing Model | Cold Start | Best For |
|----------|-----------|---------------|------------|----------|
| RunPod | Up to 70B | Per-second GPU | 5-30s | Inference API |
| Vast.ai | Up to 70B | Per-hour GPU | 1-5min | Batch jobs |
| Together.ai | Hosted models | Per-token | None | API-only |
| Modal | Up to 70B | Per-second | 5-20s | Python functions |
| Replicate | Hosted models | Per-second | None | No-code inference |

---

## 💡 Recommendations

### For Current Setup (Email + Sync + Matomo)
✅ **Stick with Oracle Cloud Free Tier**
- Already deployed
- Sufficient resources
- No cost
- Can upgrade to ARM A1 for LLM later

---

### For LLM Development/Testing
🚀 **RunPod or Modal**

**RunPod**:
- Best for self-hosted open source LLMs
- Pay per-second (sleep = $0)
- Easy to deploy (Docker templates)
- RTX 4090 at $0.69/hour

**Modal**:
- Best for Python-based LLM APIs
- Serverless autoscaling
- Deploy with `@app.function(gpu="a100")`
- Great for occasional inference

---

### For Production LLM Inference (24/7)
💰 **Cheap CPU VPS (Hetzner) + API calls (Together.ai)**

**Why**:
- Run orchestration on Hetzner ($4.50/month)
- Call Together.ai API for LLM inference ($0.20-0.90/million tokens)
- Much cheaper than 24/7 GPU server
- No infrastructure management

**Cost Example**:
- Hetzner VPS: $4.50/month
- 10M tokens/month: $9 (Together.ai Mistral-7B)
- **Total**: ~$13.50/month

**vs. 24/7 GPU**:
- RunPod RTX 4090 24/7: $497/month
- Vast.ai RTX 3090 24/7: ~$172/month

---

### For Heavy LLM Training/Fine-tuning
⚡ **Vast.ai (cheapest) or Lambda Labs (reliability)**

**Vast.ai**:
- RTX 3090 at $0.20-0.35/hour
- A100 80GB at $1.50-2.00/hour
- Perfect for batch jobs
- Save 50-70% vs. AWS/Azure

**Lambda Labs**:
- More reliable than Vast.ai
- Better support
- A100 80GB at $1.99/hour
- Good for multi-day training runs

---

### For Experimentation (Learning LLMs)
🆓 **Oracle Cloud ARM A1 + Ollama**

**Setup**:
1. Create ARM A1 instance (4 cores, 24GB RAM) - FREE
2. Install Ollama
3. Run Llama-2-7B or Mistral-7B with quantization (GGUF)

**Pros**:
- Completely free
- Learn LLM inference
- Enough RAM for 7B models
- No time limit

**Performance**:
- CPU inference (slow but works)
- ~1-3 tokens/second on ARM
- Fine for experimentation

---

## 🎯 Cost Optimization Strategies

### Strategy 1: Hybrid Cloud
- **Static services** (email, sync, web) → Oracle Free Tier ($0)
- **LLM orchestration** → Hetzner CX11 ($4.50/month)
- **LLM inference** → Together.ai API (pay-per-token)
- **Occasional GPU** → RunPod (per-second billing)

**Monthly Cost**: $5-20 depending on usage

---

### Strategy 2: All-In Oracle + API
- **Everything** → Oracle Free Tier ARM A1 ($0)
- **Heavy LLM tasks** → Together.ai or OpenRouter API
- **No GPU** (use external APIs)

**Monthly Cost**: $0-50 (API usage only)

---

### Strategy 3: GPU On-Demand
- **Base services** → Oracle Free Tier ($0)
- **LLM inference** → RunPod Serverless (per-second)
- **Autoscale to zero** when not in use

**Monthly Cost**: $0-100 (depending on inference load)

---

## 📝 Provider Quick Links

### Free Tiers
- **Oracle Cloud**: https://www.oracle.com/cloud/free/
- **Google Cloud**: https://cloud.google.com/free
- **AWS**: https://aws.amazon.com/free/
- **Azure**: https://azure.microsoft.com/free/

### Cheap VPS
- **Hetzner**: https://www.hetzner.com/cloud
- **Contabo**: https://contabo.com/
- **Vultr**: https://www.vultr.com/pricing/
- **DigitalOcean**: https://www.digitalocean.com/pricing

### GPU Providers
- **RunPod**: https://www.runpod.io/pricing
- **Vast.ai**: https://vast.ai/pricing
- **Lambda Labs**: https://lambdalabs.com/service/gpu-cloud
- **Modal**: https://modal.com/pricing
- **Together.ai**: https://www.together.ai/pricing

---

## ⚠️ Important Notes

### Oracle Cloud Free Tier
- **Reclamation Risk**: Oracle may reclaim free tier resources if:
  - Account inactive for 90+ days
  - CPU utilization consistently <10%
  - Suspected abuse
- **Mitigation**: Run background cron job to keep CPU active

### Vast.ai Reliability
- Peer-to-peer marketplace = variable quality
- Check host reliability score (>98%)
- Use interruptible instances for batch jobs only
- Consider Lambda/RunPod for production

### GPU Pricing Volatility
- Prices change based on demand
- RunPod/Vast.ai prices fluctuate
- Lock in reserved instances for 24/7 workloads
- Monitor spot pricing for savings

---

**Research Version**: 1.0
**Next Update**: When significant pricing changes occur
**Maintained By**: Claude Code
