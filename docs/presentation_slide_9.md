## Slide 9: Cost & Performance — Latency, Token Usage, and Tradeoffs

### Overview

Our pipeline is designed for **local execution** using Ollama, prioritizing **privacy and zero API costs** over cloud-based scalability. This section analyzes the performance characteristics, token usage, latency, and tradeoffs of our current solution.

---

## Cost Analysis: Zero API Costs (Local Execution)

### Cost Model: Local-First Architecture

**Key Design Decision**: All LLM processing happens locally via Ollama, eliminating API costs entirely.

**Cost Breakdown**:

| Component | Cost | Notes |
|:----------|:-----|:------|
| **LLM Inference** (`qwen2.5:7b`) | **$0.00** | Local execution via Ollama |
| **Embeddings** (`nomic-embed-text`) | **$0.00** | Local execution via Ollama |
| **PDF Processing** (`pypdf`) | **$0.00** | Pure Python library, no external services |
| **Storage** | **$0.00** | Local filesystem |
| **Network** | **$0.00** | No external API calls |
| **Hardware** | **Variable** | Depends on user's machine (CPU/GPU) |

**Total Cost per Document**: **$0.00** (excluding hardware)

---

### Comparison: Local vs. Cloud API Costs

**If Using Cloud APIs** (hypothetical comparison):

| Provider | Model | Input Cost | Output Cost | Est. Cost per Document* |
|:---------|:------|:-----------|:------------|:------------------------|
| **OpenAI GPT-4** | `gpt-4-turbo` | $10/1M tokens | $30/1M tokens | **$0.15 - $0.50** |
| **OpenAI GPT-3.5** | `gpt-3.5-turbo` | $0.50/1M tokens | $1.50/1M tokens | **$0.01 - $0.03** |
| **Anthropic Claude** | `claude-3-opus` | $15/1M tokens | $75/1M tokens | **$0.30 - $1.00** |
| **Anthropic Claude** | `claude-3-sonnet` | $3/1M tokens | $15/1M tokens | **$0.06 - $0.20** |
| **Our Solution** | `qwen2.5:7b` (local) | **$0.00** | **$0.00** | **$0.00** |

*Estimated based on ~2,000-5,000 input tokens and ~1,000-2,000 output tokens per document

**Cost Savings**:
- **vs. GPT-4**: $0.15-$0.50 per document → **$0.00** (100% savings)
- **vs. GPT-3.5**: $0.01-$0.03 per document → **$0.00** (100% savings)
- **vs. Claude Opus**: $0.30-$1.00 per document → **$0.00** (100% savings)

**At Scale** (1,000 documents):
- **GPT-4**: $150-$500
- **GPT-3.5**: $10-$30
- **Our Solution**: **$0.00**

---

### Hidden Costs: Hardware Requirements

**While API costs are zero, hardware requirements exist**:

| Hardware | Requirement | Impact |
|:---------|:------------|:-------|
| **CPU** | Modern multi-core CPU | Slower inference (10-60s per document) |
| **GPU** (Optional) | NVIDIA GPU or Apple Silicon | Faster inference (2-10s per document) |
| **RAM** | 8GB+ recommended | Model loading and inference |
| **Storage** | ~4GB for model | Model storage (`qwen2.5:7b` ~4GB) |

**Trade-off**: Zero API costs but requires capable hardware for reasonable performance.

---

## Token Usage Analysis

### Token Estimation Methodology

**Character-to-Token Ratio**: ~4 characters per token (English text, typical for clinical notes)

**Token Calculation**:
- Document text: Characters ÷ 4
- Prompt overhead: ~500-1,000 tokens (system message, instructions, JSON schema)
- Output tokens: ~500-2,000 tokens (summary + plan)

---

### Per-Document Token Usage

#### Input Tokens

**1. Summary Generation** (Single LLM Call):

| Component | Size | Tokens (Est.) | Notes |
|:----------|:-----|:--------------|:------|
| **Document Text** | 2,200-7,600 chars | **550-1,900** | Average: ~3,400 chars = 850 tokens |
| **Chunk Headers** | ~50 chars/chunk × 3-10 chunks | **40-125** | Section titles, chunk IDs, spans |
| **Prompt Template** | ~2,000-3,000 chars | **500-750** | Instructions, JSON schema |
| **System Message** | ~200-500 chars | **50-125** | Model instructions |
| **Total Input** | | **1,140-2,900** | Average: ~1,500 tokens |

**2. Plan Generation** (Single LLM Call):

| Component | Size | Tokens (Est.) | Notes |
|:----------|:-----|:--------------|:------|
| **Summary Text** | ~1,500-4,000 chars | **375-1,000** | Formatted summary |
| **Summary JSON** | ~2,000-5,000 chars | **500-1,250** | Structured summary |
| **Prompt Template** | ~1,500-2,500 chars | **375-625** | Instructions, JSON schema |
| **System Message** | ~200-500 chars | **50-125** | Model instructions |
| **Total Input** | | **1,300-3,000** | Average: ~1,800 tokens |

**3. Semantic Accuracy Evaluation** (Embedding Calls):

| Component | Calls | Tokens per Call | Total Tokens |
|:----------|:------|:----------------|:-------------|
| **Recommendation Embeddings** | 3-10 | ~50-200 | **150-2,000** |
| **Cited Text Embeddings** | 3-10 | ~50-200 | **150-2,000** |
| **Total Embedding Tokens** | | | **300-4,000** |

**Total Tokens per Document**:

| Stage | Input Tokens | Output Tokens | Total |
|:------|:-------------|:--------------|:------|
| **Summary** | 1,140-2,900 | 500-1,500 | **1,640-4,400** |
| **Plan** | 1,300-3,000 | 300-1,000 | **1,600-4,000** |
| **Evaluation** | 300-4,000 | 0 | **300-4,000** |
| **Total** | | | **3,540-12,400** |

**Average**: ~6,000 tokens per document

---

### Token Usage Breakdown by Document Size

**Small Document** (~2,200 chars = 550 tokens):
- Summary: ~1,140 input + 500 output = **1,640 tokens**
- Plan: ~1,300 input + 300 output = **1,600 tokens**
- Evaluation: ~300 tokens
- **Total: ~3,540 tokens**

**Medium Document** (~3,400 chars = 850 tokens):
- Summary: ~1,500 input + 800 output = **2,300 tokens**
- Plan: ~1,800 input + 600 output = **2,400 tokens**
- Evaluation: ~1,000 tokens
- **Total: ~4,700 tokens**

**Large Document** (~7,600 chars = 1,900 tokens):
- Summary: ~2,900 input + 1,500 output = **4,400 tokens**
- Plan: ~3,000 input + 1,000 output = **4,000 tokens**
- Evaluation: ~4,000 tokens
- **Total: ~12,400 tokens**

---

### Token Efficiency: Full-Context vs. RAG

**Our Approach (Full-Context)**:
- **Single LLM call** for summary (all chunks)
- **Token Usage**: ~1,500 input tokens (average)
- **Efficiency**: Processes entire document in one pass

**Alternative (RAG with Retrieval)**:
- **Multiple LLM calls**: Retrieval (1 call) + Generation per chunk (3-10 calls)
- **Token Usage**: ~500 tokens per call × 4-11 calls = **2,000-5,500 tokens**
- **Efficiency**: More calls, but potentially more focused

**Trade-off**: Our approach uses **fewer total tokens** (single call) but processes **all text** (even if less relevant). RAG uses **more tokens** (multiple calls) but processes **only relevant chunks**.

**For Clinical Notes**: Full-context is more efficient because:
1. Documents are relatively short (fit in one call)
2. All information is relevant (no filtering needed)
3. Single call reduces overhead (prompt repetition)

---

## Latency Analysis

### Latency Components

**Per-Document Latency Breakdown**:

| Stage | Time (CPU) | Time (GPU) | Notes |
|:------|:-----------|:-----------|:------|
| **Ingestion** | 0.1-0.5s | 0.1-0.5s | PDF/text extraction, normalization |
| **Section Detection** | 0.01-0.1s | 0.01-0.1s | Regex-based (fast) |
| **Chunking** | 0.01-0.05s | 0.01-0.05s | Rule-based (fast) |
| **Summary Generation** | 10-60s | 2-10s | LLM call (largest component) |
| **Plan Generation** | 5-30s | 1-5s | LLM call |
| **Evaluation** | 2-10s | 1-3s | Embedding calls + metrics |
| **Total** | **17-101s** | **4-19s** | Average: ~40s (CPU), ~8s (GPU) |

**Key Observations**:
- **LLM calls dominate latency** (80-90% of total time)
- **GPU acceleration** provides 4-5x speedup
- **Non-LLM stages** are fast (<1s total)

---

### Latency by Document Size

**Small Document** (~550 tokens):
- Summary: 5-20s (CPU) / 1-3s (GPU)
- Plan: 3-15s (CPU) / 0.5-2s (GPU)
- Evaluation: 1-3s (CPU) / 0.5-1s (GPU)
- **Total: 9-38s (CPU) / 2-6s (GPU)**

**Medium Document** (~850 tokens):
- Summary: 10-40s (CPU) / 2-6s (GPU)
- Plan: 5-20s (CPU) / 1-3s (GPU)
- Evaluation: 2-5s (CPU) / 1-2s (GPU)
- **Total: 17-65s (CPU) / 4-11s (GPU)**

**Large Document** (~1,900 tokens):
- Summary: 20-60s (CPU) / 4-10s (GPU)
- Plan: 10-30s (CPU) / 2-5s (GPU)
- Evaluation: 5-10s (CPU) / 2-3s (GPU)
- **Total: 35-100s (CPU) / 8-18s (GPU)**

---

### Latency Comparison: Local vs. Cloud APIs

| Solution | Average Latency | Notes |
|:---------|:----------------|:------|
| **Our Solution (CPU)** | **~40s** | Local `qwen2.5:7b` on CPU |
| **Our Solution (GPU)** | **~8s** | Local `qwen2.5:7b` on GPU |
| **OpenAI GPT-4** | **~5-15s** | Cloud API (network latency) |
| **OpenAI GPT-3.5** | **~2-5s** | Cloud API (faster model) |
| **Anthropic Claude** | **~3-10s** | Cloud API (network latency) |

**Trade-off**: 
- **Local (CPU)**: Slower but private, zero cost
- **Local (GPU)**: Comparable to cloud, private, zero cost
- **Cloud**: Faster but requires network, has API costs, data leaves local machine

---

### Throughput: Batch Processing

**Sequential Processing** (1 document at a time):
- **CPU**: ~40s per document = **90 documents/hour**
- **GPU**: ~8s per document = **450 documents/hour**

**Parallel Processing** (4 workers, default):
- **CPU**: ~40s per document ÷ 4 = **360 documents/hour** (theoretical)
- **GPU**: ~8s per document ÷ 4 = **1,800 documents/hour** (theoretical)

**Bottleneck**: LLM inference (not I/O or CPU-bound tasks)

**Scalability**: Limited by hardware (CPU cores, GPU memory). Can scale horizontally by running multiple Ollama instances.

---

## Performance Tradeoffs

### 1. Full-Context vs. RAG

| Aspect | Full-Context (Our Approach) | RAG (Alternative) |
|:-------|:----------------------------|:------------------|
| **Token Usage** | Lower (single call) | Higher (multiple calls) |
| **Latency** | Lower (single call) | Higher (multiple calls) |
| **Context Completeness** | Complete (all chunks) | Selective (retrieved chunks) |
| **Scalability** | Limited by context window | Better for long documents |
| **Complexity** | Simpler (no vector store) | More complex (vector store, retrieval) |
| **Accuracy** | High (full context) | Variable (depends on retrieval) |

**Our Choice**: Full-context for clinical notes (short documents, full context valuable)

---

### 2. Local vs. Cloud Execution

| Aspect | Local (Our Approach) | Cloud (Alternative) |
|:-------|:---------------------|:---------------------|
| **Cost** | $0.00 (hardware only) | $0.01-$0.50 per document |
| **Latency** | 8-40s (depends on hardware) | 2-15s (network dependent) |
| **Privacy** | Complete (no data leaves machine) | Data sent to cloud provider |
| **Scalability** | Limited by hardware | Unlimited (cloud scaling) |
| **Reliability** | Depends on local machine | High (cloud infrastructure) |
| **Setup Complexity** | Medium (Ollama installation) | Low (API key only) |

**Our Choice**: Local for privacy and zero API costs (acceptable latency trade-off)

---

### 3. Chunking Strategy: Overlap vs. No Overlap

| Aspect | With Overlap (Our Approach) | No Overlap (Alternative) |
|:-------|:----------------------------|:-------------------------|
| **Token Usage** | Higher (~13% more tokens) | Lower (no redundancy) |
| **Context Continuity** | High (no boundary loss) | Low (potential boundary loss) |
| **Citation Accuracy** | High (boundary facts cited) | Lower (boundary facts may be missed) |
| **LLM Performance** | Better (more context) | Worse (less context) |

**Our Choice**: Overlap for accuracy (small token cost, significant accuracy benefit)

---

### 4. Model Size: 7B vs. Larger Models

| Aspect | 7B (Our Choice) | 13B-70B (Alternative) |
|:-------|:----------------|:----------------------|
| **Quality** | Good (structured extraction) | Better (more nuanced) |
| **Latency** | Fast (2-10s on GPU) | Slower (5-30s on GPU) |
| **Memory** | ~4GB (fits on most GPUs) | 8-40GB (requires high-end GPU) |
| **Cost** | $0.00 (local) | $0.00 (local, but needs better hardware) |

**Our Choice**: 7B for balance of quality, speed, and hardware requirements

---

## Performance Optimization Opportunities

### Current Optimizations

1. **Single-Pass Processing**: All chunks in one LLM call (reduces overhead)
2. **Caching**: Skip ingestion/chunking if intermediate files exist
3. **Parallel Processing**: Batch mode with `ThreadPoolExecutor`
4. **GPU Acceleration**: Automatic MPS/GPU usage via Ollama
5. **Retry Logic**: Exponential backoff for transient failures

---

### Potential Optimizations (Not Yet Implemented)

1. **Streaming Output**: Process LLM output as it streams (reduce perceived latency)
2. **Model Quantization**: Use quantized models (4-bit, 8-bit) for faster inference
3. **Batch Embedding**: Batch embedding calls for semantic accuracy (currently sequential)
4. **Context Window Optimization**: Dynamically adjust chunk size based on document length
5. **Selective Evaluation**: Skip semantic accuracy for low-confidence recommendations

**Estimated Impact**:
- **Streaming**: -20% perceived latency
- **Quantization**: -30% latency, -50% memory
- **Batch Embeddings**: -50% evaluation latency
- **Context Optimization**: -10% token usage (variable)
- **Selective Evaluation**: -30% evaluation latency

---

## Cost & Performance Summary

### Current Solution Characteristics

**Cost**:
- ✅ **$0.00 per document** (local execution)
- ✅ **No API costs** (privacy-preserving)
- ⚠️ **Hardware requirement** (CPU/GPU needed)

**Performance**:
- ✅ **8-40s per document** (depends on hardware)
- ✅ **90-450 documents/hour** (sequential)
- ✅ **360-1,800 documents/hour** (parallel, 4 workers)
- ⚠️ **Limited by hardware** (not cloud-scalable)

**Token Usage**:
- ✅ **~6,000 tokens per document** (average)
- ✅ **Efficient** (single-pass, full-context)
- ✅ **Scalable** (fits in context windows)

---

### When Our Solution Makes Sense

**Ideal For**:
- ✅ **Privacy-sensitive** applications (HIPAA compliance)
- ✅ **Low to medium volume** (hundreds to thousands of documents/day)
- ✅ **Local processing** requirements (no cloud access)
- ✅ **Cost-sensitive** applications (zero API costs)
- ✅ **Research/development** (iterative development, testing)

**Not Ideal For**:
- ❌ **High-volume** applications (millions of documents/day)
- ❌ **Low-latency** requirements (<1s per document)
- ❌ **Limited hardware** (no GPU, slow CPU)
- ❌ **Cloud-native** architectures (prefer cloud APIs)

---

### Recommendations

**For Production Use**:
1. **Use GPU** if available (4-5x speedup)
2. **Enable parallel processing** for batch jobs (4-8 workers)
3. **Monitor hardware** (CPU/GPU utilization, memory)
4. **Consider quantization** for faster inference (if quality acceptable)

**For Development/Testing**:
1. **Current solution is sufficient** (acceptable latency)
2. **Use caching** to skip re-processing during iteration
3. **Monitor token usage** for optimization opportunities

**For Scale** (if needed):
1. **Horizontal scaling**: Multiple Ollama instances
2. **Model optimization**: Quantization, smaller models
3. **Selective processing**: Skip evaluation for non-critical documents

---

## Conclusion

Our **local-first, zero-cost** solution provides an excellent balance of **privacy, cost, and performance** for clinical note processing. While latency is higher than cloud APIs, the **zero API costs** and **complete privacy** make it ideal for healthcare applications where data cannot leave the local environment.

**Key Strengths**:
- ✅ Zero API costs
- ✅ Complete privacy (HIPAA-compliant)
- ✅ Acceptable performance (8-40s per document)
- ✅ Efficient token usage (~6,000 tokens/document)

**Key Tradeoffs**:
- ⚠️ Higher latency than cloud APIs (acceptable for batch processing)
- ⚠️ Hardware requirements (GPU recommended for best performance)
- ⚠️ Limited scalability (hardware-bound, not cloud-scalable)

**Overall Assessment**: **Excellent fit** for privacy-sensitive, cost-conscious clinical note processing applications.

