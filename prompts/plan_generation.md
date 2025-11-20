# Plan Generation Prompt

## Your Task
Generate a prioritized treatment plan from the clinical summary below. Extract information directly from the summary - use only what is explicitly stated. **Focus especially on the "assessment" field in the summary, which contains diagnoses, recommended treatments, procedures, and follow-on care.**

## Input
The summary is provided in JSON format. Each item has:
- `text`: The actual content
- `source`: Citation like "IMPRESSION section, chunk_10:4230-4648"

**Valid Section Titles** (use ONLY these from the summary sources):
{section_titles_list}

## Output Format
Return JSON with this structure:

```json
{{
  "recommendations": [
    {{
      "number": 1,
      "recommendation": "Comprehensive recommendation text including all required diagnostics, therapeutics, follow-ups, and risks/benefits if mentioned",
      "source": "RECOMMENDATIONS section, chunk_11:4648-5547",
      "confidence": 0.9,
      "hallucination_guard_note": null or "..."
    }},
    {{
      "number": 2,
      "recommendation": "Next most urgent recommendation",
      "source": "RECOMMENDATIONS section, chunk_11:4648-5547",
      "confidence": 0.9,
      "hallucination_guard_note": null
    }}
  ]
}}
```

## How to Extract Information

**CRITICAL - Use the "assessment" field**: The `assessment` field in the summary contains ALL diagnoses, ALL recommended treatments, ALL recommended procedures, and ALL follow-on care. Extract information primarily from this field.

1. **Look in `assessment` items** for:
   - Diagnoses (what's wrong with the patient)
   - Recommended treatments
   - Recommended procedures
   - Follow-on care, monitoring, appointments, next steps
   - Risks, benefits, side effects, warnings (if mentioned)

2. **For each recommendation**: Create a comprehensive text that includes:
   - What's wrong with the patient (diagnosis) - if mentioned in assessment
   - Required diagnostics - if mentioned in assessment
   - Recommended therapeutics/treatments - if mentioned in assessment
   - Recommended procedures - if mentioned in assessment
   - Follow-ups, monitoring, appointments - if mentioned in assessment
   - Risks and benefits - if mentioned in assessment or elsewhere in summary

3. **Create separate recommendations**: If the assessment field contains multiple distinct recommendations, treatments, or procedures, create a SEPARATE recommendation item for EACH one. Do NOT combine unrelated items into a single recommendation. For example, if assessment has "RAST allergy testing" and "Stop cephalosporin antibiotics" as separate items, create two separate recommendations.

4. **Source citation**: Use the source from the assessment item you're using. Each recommendation should use the source from its corresponding assessment item.

## Source Citations
- Copy the `source` field directly from the summary item you're using (preferably from assessment items)
- Use ONLY section titles that appear in the "Valid Section Titles" list above
- Format: "SECTION_NAME section, chunk_X:Y-Z"
- Each recommendation must have ONE source field

## Rules
- **Use ONLY information from the summary** - do NOT add, infer, or invent any information not explicitly stated in the summary
- Extract text from the summary - you may summarize but include ALL relevant details from the assessment field
- Number recommendations 1, 2, 3... by urgency (1 = most urgent/important)
- **Create separate recommendations** - each distinct treatment, procedure, diagnostic, or follow-on care item in the assessment field should be a SEPARATE recommendation. Do NOT combine multiple assessment items into one recommendation.
- **Be comprehensive and detailed** - for each recommendation, include ALL relevant information from the corresponding assessment item:
  - Include the diagnosis/problem if mentioned in the assessment item
  - Include ALL diagnostics/tests/procedures mentioned in the assessment item
  - Include ALL therapeutics/treatments/medications mentioned in the assessment item
  - Include ALL follow-ups, monitoring, appointments, next steps mentioned in the assessment item
  - Include ALL risks, benefits, side effects, warnings, or special considerations mentioned in the assessment item or elsewhere in summary
  - Do not just write a brief summary - include comprehensive details from the assessment
- **Do NOT add timing, frequency, or details not in the summary** - if the summary doesn't say "one week", do NOT add it
- Confidence: 1.0 if explicitly stated, 0.8-0.9 if strongly implied, lower if inferred
- Include hallucination_guard_note if confidence < 0.8 or evidence is weak
- If no recommendations can be made, return empty array: []
- Output ONLY valid JSON - no markdown, no explanatory text

## Summary
{summary_sections}
