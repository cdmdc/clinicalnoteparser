# Prompt Engineering Documentation

This directory contains prompt templates used by the clinical note parser pipeline. This document explains the design decisions, reasoning, and best practices for each prompt.

## Overview

The pipeline uses three main prompts:
1. **section_inference.md**: Optional LLM-based section detection (fallback when regex fails)
2. **summary_extraction.md**: Extract structured facts from text chunks
3. **plan_generation.md**: Generate problem-oriented recommendations

## Design Principles

### 1. PHI Protection
All prompts include explicit instructions to:
- Not add, infer, or fabricate Protected Health Information (PHI)
- Only extract information explicitly present in source text
- Not infer patient names, dates of birth, addresses, or identifiers

**Why**: Clinical notes contain sensitive patient data. Preventing hallucination of PHI is critical for privacy and legal compliance.

### 2. Anti-Fabrication
All prompts emphasize:
- Do not invent facts, diagnoses, or recommendations
- Only extract/generate what is clearly stated in the text
- If evidence is missing, do not include the claim

**Why**: Medical decisions rely on accurate information. Fabricated facts could lead to incorrect diagnoses or treatments.

### 3. Citation Requirements
Every fact and recommendation must:
- Be tied to specific source text spans
- Include character offsets (local for chunks, global for final output)
- Have at least one citation

**Why**: Citations enable traceability and verification. Users can check the source text to validate extracted information.

### 4. Uncertainty Handling
Prompts instruct the LLM to:
- Use confidence scores [0, 1]
- Include uncertainty notes for low-confidence claims
- Exclude very uncertain claims (<0.5 confidence)

**Why**: Medical information often has varying degrees of certainty. Explicit uncertainty helps users make informed decisions.

## Prompt Details

### section_inference.md

**Purpose**: Identify section headers when automatic regex detection fails.

**When Used**: 
- Fallback when regex finds < min_sections_for_success sections
- When no section headers are detected after Overview

**Key Features**:
- Simple JSON output format
- Focus on common clinical section patterns
- Character position tracking for section boundaries

**Design Decisions**:
- Minimal prompt to avoid over-engineering (regex should handle most cases)
- Focus on common patterns (HISTORY, PHYSICAL EXAMINATION, etc.)
- Global character positions for consistency with regex output

### summary_extraction.md

**Purpose**: Extract structured facts from individual text chunks.

**When Used**: For every chunk in the document.

**Key Features**:
- Local character spans (within chunk) for easier validation
- Category classification (problem, medication, allergy, etc.)
- Confidence scoring
- Multiple citations per fact (if fact appears multiple times)

**Design Decisions**:
- **Local spans**: Using local character positions (0-based within chunk) makes validation easier and reduces errors from global offset calculations
- **Category system**: Predefined categories help organize facts and enable structured output
- **Multiple citations**: A fact can appear multiple times in a chunk (e.g., "diabetes" mentioned twice), so multiple citations are allowed
- **Confidence thresholds**: Clear guidance on when to use different confidence levels helps the LLM make consistent decisions

**Example Effective Pattern**:
```
Input: "Patient has diabetes and hypertension. Current medications: metformin, lisinopril."
Output: 
- Fact: "diabetes" (category: problem, confidence: 1.0)
- Fact: "hypertension" (category: problem, confidence: 1.0)
- Fact: "metformin" (category: medication, confidence: 1.0)
- Fact: "lisinopril" (category: medication, confidence: 1.0)
```

**Example Ineffective Pattern**:
```
Input: "Patient has diabetes"
Output: 
- Fact: "Patient likely has type 2 diabetes based on age" (WRONG - inferring information not in text)
```

### plan_generation.md

**Purpose**: Generate problem-oriented recommendations based on extracted facts.

**When Used**: After all facts are extracted and aggregated.

**Key Features**:
- Fact ID system for citation linking
- Problem-oriented structure (recommendations grouped by problem)
- Global followup recommendations
- Rationale for each recommendation

**Design Decisions**:
- **Fact IDs**: Using fact IDs (fact_001, fact_002, etc.) enables precise citation linking without text matching ambiguity
- **Problem-oriented**: Grouping recommendations by problem matches clinical workflow (problem → plan)
- **Rationale**: Including rationale helps users understand why recommendations are made
- **Global followup**: Some recommendations apply to the overall case, not specific problems (e.g., "schedule follow-up")

**Example Effective Pattern**:
```
Facts:
- fact_001: HbA1c is 8.5%
- fact_002: Patient on metformin

Output:
Problem: Diabetes
Recommendation: "Consider intensifying diabetes management"
Rationale: "HbA1c above target, current medication may need adjustment"
Citations: [fact_001, fact_002]
```

**Example Ineffective Pattern**:
```
Facts:
- fact_001: Patient has diabetes

Output:
Recommendation: "Start insulin therapy" (WRONG - no evidence for this specific recommendation)
```

## Prompt Hardening

All prompts include "hardening" instructions to prevent common LLM failures:

1. **PHI Protection**: Explicitly prevents hallucination of patient identifiers
2. **Anti-Fabrication**: Prevents invention of facts not in source
3. **Citation Requirements**: Ensures every claim is traceable
4. **Uncertainty Handling**: Encourages appropriate confidence scoring

These instructions are repeated in each prompt to ensure consistency across the pipeline.

## Testing and Iteration

Prompts should be tested with:
- Various clinical note formats
- Edge cases (empty sections, ambiguous text, missing information)
- Different LLM models (if switching from default)

When iterating on prompts:
1. Test with real clinical notes
2. Measure citation coverage and validity
3. Check for hallucination (facts without citations)
4. Verify confidence scores are appropriate
5. Ensure output format is consistently parseable

## Future Improvements

Potential enhancements:
- Few-shot examples in prompts (currently zero-shot)
- Model-specific optimizations (if using different models)
- Dynamic prompt adjustment based on document type
- Multi-language support (if needed)

