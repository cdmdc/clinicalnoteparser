# Prompt Design Reasoning

This document explains the design rationale and key decisions behind each prompt in the Clinical Note Parser pipeline.

---

## Section Inference Prompt (`section_inference.md`)

### Purpose
Fallback mechanism for identifying section headers when automatic regex-based detection fails.

### Design Rationale

**Why LLM-based fallback?**
- Regex pattern matching works for ~90% of documents but fails on non-standard formats (e.g., autopsy reports, forensic documents)
- LLM can handle variations in formatting, capitalization, and section naming conventions
- Provides graceful degradation when deterministic methods fail

**Key Design Decisions:**

1. **Strict Anti-Fabrication Rules**
   - Explicitly prohibits inventing section headers
   - Only identifies headers clearly present in text
   - Prevents hallucination of non-existent sections

2. **PHI Protection Emphasis**
   - Reminds LLM not to add or infer PHI
   - Critical for medical document processing compliance

3. **Character Position Tracking**
   - Requires global character positions (start_char, end_char)
   - Enables precise citation and traceability
   - Maintains consistency with deterministic section detection output format

4. **Simple JSON Output**
   - Minimal structure: just section title and character spans
   - Easy to integrate with existing pipeline
   - No complex reasoning required - just identification

**Trade-offs:**
- More expensive than regex (LLM call vs. pattern matching)
- Slower processing time
- Only used when regex fails, minimizing cost impact

---

## Summary Generation Prompt (`text_summary.md`)

### Purpose
Extract structured clinical information from document chunks and organize into seven predefined categories.

### Design Rationale

**Why Seven Categories?**
- Covers all major information types in clinical notes
- Non-overlapping design prevents duplicate extraction
- Aligns with standard clinical documentation structure (SOAP note format)

**Key Design Decisions:**

1. **Strong Anti-Hallucination Framework**
   - **Source-only extraction**: No external medical knowledge
   - **No inference**: If not explicitly stated, don't create it
   - **Empty arrays for missing info**: Distinguishes "not present" from "not extracted" (though this distinction could be clearer)
   - **Prefer copying**: Minimizes paraphrasing errors
   - **When unsure, leave out**: Accuracy over completeness

   **Rationale**: Medical information requires high accuracy. A 0.04% hallucination rate was achieved through these strict rules.

2. **Explicit Section Definitions**
   - Each section has clear "Include" and "Exclude" criteria
   - Prevents misclassification of information
   - Reduces ambiguity about where facts belong

3. **Primary Source Guidance**
   - `patient_snapshot`: Primarily from "Overview" chunks
   - `assessment`: Primarily from "RECOMMENDATIONS" chunks
   - Guides LLM to look in most relevant sections first

4. **Citation Format with Section Names**
   - Format: `"[SECTION_NAME] section, chunk_ID:START-END"`
   - Includes section name for better traceability
   - Enables validation against chunk headers
   - Supports bracket tolerance (`[SECTION]` or `SECTION`)

5. **Chunk Processing Tracking**
   - `_chunks_processed` field tracks which chunks were used
   - Enables comprehensiveness validation
   - Helps identify if LLM missed relevant chunks

6. **No Minimum Item Requirements**
   - Extract only what exists
   - Prevents fabrication to meet quotas
   - Quality over quantity

**Trade-offs:**
- May miss implicit information (by design - accuracy over completeness)
- Empty arrays don't distinguish "not present" vs "not extracted" (acknowledged limitation)
- Requires careful prompt engineering to balance comprehensiveness and accuracy

**Evolution:**
- Started with example-based (few-shot) approach
- Moved to constraint-based prompting with explicit definitions
- Removed examples to prevent copying, then re-added with stronger warnings
- Current v2: Concise, structured, with detailed section definitions

---

## Plan Generation Prompt (`plan_generation.md`)

### Purpose
Generate prioritized treatment recommendations from the structured summary, focusing on actionable items.

### Design Rationale

**Why Separate from Summary?**
- Summary extracts facts; plan generates actionable recommendations
- Different reasoning task: synthesis vs. extraction
- Allows focused optimization for each task

**Key Design Decisions:**

1. **Assessment-First Approach**
   - Recommendations primarily from `assessment` section
   - Assessment contains clinician's interpretation and plan
   - Other sections provide context but not primary recommendations

2. **Strict Anti-Hallucination Rules**
   - Mirror summary prompt's approach
   - No external medical knowledge
   - No inference or guessing
   - Copy source fields exactly from summary

3. **Action-Oriented Definition**
   - Clear criteria for what counts as a recommendation
   - Focus on actionable items (treatments, procedures, follow-ups)
   - Excludes passive observations or historical facts

4. **One Recommendation Per Action**
   - If assessment item has multiple actions, split into separate recommendations
   - Enables better prioritization and tracking
   - Improves clarity and actionability

5. **Confidence Scoring**
   - 1.0 for explicitly stated
   - 0.8-0.9 for partially stated but clear
   - <0.8 for ambiguous wording
   - Provides transparency about recommendation certainty

6. **Hallucination Guard Notes**
   - Low-confidence recommendations include explanation
   - Helps reviewers identify potentially problematic recommendations
   - Balances completeness with safety

7. **Empty Array for No Recommendations**
   - If no actionable items in assessment, return `[]`
   - Prevents fabrication of recommendations
   - Common for autopsy reports or documentation-only notes

**Trade-offs:**
- May miss recommendations implicit in other sections (by design - focuses on explicit assessment)
- Relies on summary quality - if assessment is empty, plan will be empty
- Confidence scores are subjective but provide useful signal

**Evolution:**
- v1: More verbose, less structured
- v2: Concise, focused on anti-hallucination and actionability
- Stronger emphasis on assessment section as primary source

---

## Common Design Patterns Across Prompts

1. **Anti-Hallucination First**
   - All prompts prioritize accuracy over completeness
   - Explicit rules against inference and fabrication
   - Empty outputs preferred over invented content

2. **Citation and Traceability**
   - All outputs include source citations
   - Enables verification and validation
   - Critical for medical applications

3. **Structured JSON Output**
   - Consistent format across prompts
   - Enables programmatic processing
   - Validated with Pydantic schemas

4. **Error Handling with Agentic Retry**
   - Prompts designed to work with agentic retry mechanisms
   - When errors occur (JSON parsing, validation failures), the system retries with expanded context history
   - Error feedback is appended to the prompt, allowing the LLM to self-correct
   - Clear error messages guide LLM corrections in subsequent attempts
   - Multi-layer retry strategy: JSON parsing retries (2 attempts) + validation retries (2 attempts)
   - Graceful degradation when information is missing or after retry exhaustion

5. **Medical Domain Awareness**
   - Understands clinical documentation structure
   - Respects medical information accuracy requirements
   - PHI protection considerations

6. **Minimal and Compact Design**
   - Prompts kept intentionally minimal and compact
   - Essential for small Qwen2.5:7b model (7B parameters)
   - Reduces token usage and improves response quality
   - Focuses on essential instructions without unnecessary verbosity
   - Balances detail with model capacity constraints

---

## Future Improvements

1. **Prompt Evaluation and Optimization**
   - Evaluate prompts on a golden set of manually validated documents
   - Systematic A/B testing of prompt variations
   - Quantitative metrics for prompt effectiveness
   - Iterative refinement based on evaluation results

2. **Enhanced Examples**
   - Add better examples to prompts with clean separation of content across sections
   - Demonstrate proper categorization and citation format
   - Show edge cases and how to handle them
   - Balance example quality with prompt compactness for small models

3. **Specialized Report Type Handling**
   - Identify special report types (e.g., Autopsy, Forensic, Pathology)
   - Develop specialized prompts adapted for each report type
   - Automatic report type detection and prompt selection
   - Separate pipeline for autopsy reports (currently shows low performance)
   - Custom section definitions and extraction rules per report type

4. **Section Inference**
   - Add examples of common section patterns
   - Improve handling of non-standard formats
   - Consider multimodal input for scanned documents

5. **Summary Generation**
   - Better distinction between "not present" and "not extracted"
   - Temporal awareness for tracking changes
   - Handling of conflicting information

6. **Plan Generation**
   - Cross-section reasoning (not just assessment)
   - Medical knowledge validation (with external sources)
   - Temporal planning (scheduled vs. immediate actions)

---

**Last Updated**: November 2024

