# Model Card: Clinical Note Parser

## Model Details

**Model Name**: Clinical Note Parser Pipeline  
**Version**: 1.0  
**Date**: November 2024  
**Developers**: Clinical Note Parser Team  
**Repository**: https://github.com/cdmdc/clinicalnoteparser

### Model Architecture

The Clinical Note Parser is a multi-stage pipeline that combines deterministic text processing with local Large Language Models (LLMs) via Ollama. The system processes unstructured clinical notes through:

1. **Ingestion**: PDF/text extraction with character offset tracking
2. **Section Detection**: Rule-based section header identification
3. **Chunking**: Section-based text segmentation
4. **Summarization**: LLM-powered structured information extraction
5. **Planning**: LLM-generated treatment recommendations
6. **Evaluation**: Automated quality assessment with citation validation

**Base LLM**: Qwen2.5:7b (default, configurable)  
**Processing**: Local inference via Ollama (no cloud API calls)  
**Hardware**: CPU or GPU-accelerated (MPS on Apple Silicon)

---

## Intended Use

### Primary Use Cases

✅ **Intended**:
- **Clinical Documentation Analysis**: Extract structured information from unstructured clinical notes
- **Care Plan Generation**: Generate prioritized treatment recommendations from clinical documentation
- **Information Retrieval**: Enable traceable fact extraction with source citations
- **Research & Analysis**: Support clinical research by structuring narrative notes
- **Documentation Review**: Assist healthcare providers in reviewing and organizing clinical notes

### Out-of-Scope Use Cases

❌ **Not Intended**:
- **Direct Clinical Decision-Making**: Outputs should not be used as the sole basis for patient care decisions
- **Real-Time Patient Monitoring**: System is designed for document analysis, not live patient data
- **Diagnostic Assistance**: Does not provide diagnostic recommendations or interpretations
- **Regulatory Compliance**: Not certified for regulatory submissions or legal documentation
- **Multi-Language Support**: Optimized for English-language clinical notes only

---

## Limitations

### Pre-Processing Limitations

1. **OCR Support**
   - No OCR support for scanned PDFs or image-based documents
   - Requires text-based PDFs or text files as input
   - Multimodal inputs (images, tables, diagrams) not supported

2. **Text Encoding & Validation**
   - Limited encoding error handling
   - Limited text validation and normalization
   - May struggle with corrupted or malformed text

3. **Section Detection**
   - Relies primarily on regex pattern matching for section headers
   - Limited LLM fallback for regex failures
   - Non-standard document formats may cause issues (e.g., autopsy reports)
   - May require more complex LLM fallback for edge cases

4. **Chunking Strategy**
   - Fixed chunk size may not be optimal for all document types
   - Section-based chunking may not handle very long sections well
   - No adaptive chunking based on document characteristics

5. **Document Length**
   - Exceptionally long documents may exceed LLM context window limits
   - No automatic document splitting or summarization for very long documents
   - Processing time scales significantly with document length

### Reasoning Limitations

1. **Document Type Performance**
   - **Autopsy Reports**: Low performance - requires a separate specialized pipeline
   - Good mean performance across standard clinical notes, but high variability
   - Performance degrades on highly unstructured or narrative-only documents

2. **Information Extraction Quality**
   - Variability in citation validity and semantic accuracy suggests occasional hallucinations
   - No distinction between "information not present" and "information not extracted"
   - Empty fields (`[]`) may indicate either missing information or extraction failure
   - May miss implicit or inferred information

3. **Conflicting Information**
   - No alerts or resolution mechanisms for conflicting information within documents
   - Cannot identify or reconcile contradictory statements
   - May extract conflicting facts without flagging them

4. **Temporal Awareness**
   - No temporal awareness or time-based reasoning
   - Cannot track changes over time within a document
   - No understanding of temporal relationships between events

5. **Cross-Document Intelligence**
   - No cross-document analysis capabilities
   - Cannot track information across multiple visits or documents
   - No cross-document summary or longitudinal tracking
   - Cannot incorporate patient history from other sources

6. **Medical Knowledge Validation**
   - No validation against external medical knowledge bases
   - No access to medical guidelines or best practices
   - Cannot verify medical accuracy of extracted information
   - Recommendations based solely on provided document content

### LLM Response Handling

1. **Retry Mechanisms**
   - Automatic retry mechanism (up to 2 retries for JSON parsing, 2 for validation)
   - Beyond retry limits: error logging and graceful degradation
   - Some edge cases may still cause failures after all retries

2. **Citation Validation Issues**
   - Occasional section name mismatches in citations
   - Character span out-of-bounds errors
   - Missing chunk ID references
   - Current citation validity: ~79% (based on evaluation of 501 documents)

3. **Response Quality**
   - Response quality depends on base LLM capabilities
   - May require multiple retries for complex documents
   - Large documents (50+ sections) may take several minutes to process

### Evaluation Limitations

1. **Semantic Accuracy Validation**
   - Need to validate semantic accuracy thresholds with golden answers
   - Current evaluation metrics may not capture all quality aspects
   - No standardized benchmark for comparison

2. **Human Validation**
   - No tooling for human reviewers to validate outputs
   - Limited human-in-the-loop validation infrastructure
   - Evaluation primarily automated with limited human oversight

3. **Evaluation Coverage**
   - Evaluation based on 501 documents from MTSamples dataset
   - May not represent all document types or edge cases
   - Limited evaluation on autopsy reports and forensic documents

### Testing Limitations

1. **Unit Test Coverage**
   - Need comprehensive unit tests for edge cases:
     - Documents with 100+ sections
     - Very long sections
     - Tables and structured data
     - Malformed or corrupted documents
   - Additional unit tests needed for LLM failure edge cases

2. **Performance Testing**
   - Limited performance testing infrastructure
   - Need comprehensive testing for:
     - Processing time across document sizes
     - Memory usage and optimization
     - Latency and response times
     - Scalability for batch processing

3. **Regression Testing**
   - No golden file tests for output comparison
   - Limited version comparison testing
   - Need automated testing for prompt changes
   - No systematic regression testing framework

4. **Integration Testing**
   - Limited complex integration testing
   - Need end-to-end testing across all pipeline stages
   - Limited testing of error handling and recovery scenarios

---

## Safety Considerations

### Medical Safety

⚠️ **Critical Warnings**:

1. **Not for Direct Clinical Use**
   - This system is a documentation analysis tool, not a clinical decision support system
   - All outputs must be reviewed by qualified healthcare professionals
   - Do not use outputs as the sole basis for patient care decisions

2. **No Medical Advice**
   - The system extracts and structures information; it does not provide medical advice
   - Treatment recommendations are based on document content only
   - No validation against current medical guidelines or best practices

3. **Error Propagation**
   - Errors in source documents will be reflected in outputs
   - Hallucination rate: 0.04% (very low, but not zero)
   - Always verify critical information against original source

### Data Privacy & Security

✅ **Privacy Features**:
- **Local Processing**: All LLM inference runs locally via Ollama (no cloud API calls)
- **No Data Transmission**: Documents never leave the local machine
- **HIPAA Considerations**: Local processing reduces data breach risk
- **PHI Handling**: Users responsible for proper PHI handling and storage

⚠️ **Security Considerations**:
- Ensure proper access controls on processed documents
- Follow institutional data security policies
- Consider encryption for stored outputs containing PHI

### System Reliability

1. **Error Handling**
   - Multi-layer retry mechanism for LLM failures
   - Graceful degradation on parsing errors
   - Comprehensive logging for debugging

2. **Output Validation**
   - Citation validation against source text
   - Pydantic schema validation for structured outputs
   - Hallucination detection via orphan claim identification

---

## Bias Considerations

### Dataset Bias

1. **Training/Evaluation Data**
   - Primary evaluation on MTSamples dataset (English-language, US healthcare system)
   - May not generalize to other healthcare systems or languages
   - Specialty distribution may not reflect real-world clinical practice

2. **Demographic Representation**
   - No explicit demographic information in evaluation dataset
   - Cannot assess performance across different patient populations
   - Potential for implicit bias in language patterns

### Model Bias

1. **Language Patterns**
   - Trained/evaluated on English-language clinical notes
   - May reflect biases in medical documentation practices
   - Could perpetuate documentation style biases

2. **Specialty Bias**
   - Performance varies across medical specialties
   - May favor common specialties over rare ones
   - Autopsy/forensic documents show lower accuracy

3. **Information Extraction Bias**
   - May prioritize certain types of information over others
   - Could miss information in non-standard formats
   - May reflect biases in what information is typically documented

### Mitigation Strategies

1. **Citation Traceability**: All extracted information includes source citations for verification
2. **Human Review**: Designed for human-in-the-loop workflows
3. **Transparency**: Open-source codebase enables bias auditing
4. **Evaluation Metrics**: Comprehensive evaluation framework to identify performance gaps

---

## Performance Metrics

### Evaluation Dataset

- **Size**: 501 clinical notes from MTSamples dataset
- **Specialties**: 40+ medical specialties
- **Document Length**: Average ~3,400 characters (range: 1,300-5,500)

### Key Metrics

| Metric | Value | Description |
|:-------|:------|:------------|
| **Hallucination Rate** | 0.04% | Percentage of facts not traceable to source |
| **Citation Coverage** | 99.16% | Percentage of facts with source citations |
| **Citation Validity** | 79.39% | Percentage of citations with valid references |
| **Semantic Accuracy** | 68.40% | Jaccard similarity between recommendations and source |
| **Span Consistency** | 99.80% | Consistency of character span references |

### Performance by Document Type

- **Standard Clinical Notes**: High accuracy (citation validity >80%)
- **Autopsy Reports**: Lower accuracy (citation validity ~60-70%)
- **Forensic Documents**: Variable performance
- **Long Documents (50+ sections)**: May require multiple retries

---

## Ethical Considerations

### Transparency

- **Open Source**: Full codebase available for review and audit
- **Documentation**: Comprehensive documentation of methods and limitations
- **Evaluation**: Public evaluation metrics and methodology

### Accountability

- **Human Oversight**: Designed for human review, not autonomous operation
- **Traceability**: All outputs include source citations for verification
- **Error Reporting**: Comprehensive logging for error analysis

### Fairness

- **Accessibility**: Local processing reduces cost barriers
- **Privacy**: Local processing protects patient privacy
- **Bias Awareness**: Acknowledgment of potential biases and limitations

---

## Recommendations for Use

### Best Practices

1. **Always Review Outputs**: Never use outputs without human review
2. **Verify Critical Information**: Cross-check important facts against source documents
3. **Understand Limitations**: Be aware of system limitations for your use case
4. **Monitor Performance**: Track accuracy metrics for your specific document types
5. **Maintain Privacy**: Follow institutional policies for PHI handling

### When to Use

✅ **Appropriate**:
- Documentation analysis and organization
- Research and data extraction
- Care plan drafting (with review)
- Information retrieval from clinical notes

❌ **Inappropriate**:
- Direct patient care decisions
- Real-time clinical monitoring
- Regulatory submissions
- Legal documentation

---

## Contact & Support

**Repository**: https://github.com/cdmdc/clinicalnoteparser  
**Issues**: Report issues via GitHub Issues  
**Documentation**: See README.md and docs/overview.md

---

## Citation

If you use this system in your research, please cite:

```
Clinical Note Parser. (2024). 
https://github.com/cdmdc/clinicalnoteparser
```

---

**Last Updated**: November 2024  
**Version**: 1.0

