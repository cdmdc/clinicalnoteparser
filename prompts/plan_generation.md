# Plan Generation Prompt

## Your Task
Generate a prioritized treatment plan from the clinical summary below. Extract information directly from the summary - use only what is explicitly stated.

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
      "diagnostics": {{"content": "...", "source": "..."}} or null,
      "therapeutics": {{"content": "...", "source": "..."}} or null,
      "risks_benefits": {{"content": "...", "source": "..."}} or null,
      "follow_ups": {{"content": "...", "source": "..."}} or null,
      "confidence": 0.9,
      "hallucination_guard_note": null or "..."
    }}
  ]
}}
```

## How to Extract Information

1. **Diagnostics**: Look in `concise_assessment` items for diagnosis text. Use the exact text from the summary. If no diagnosis mentioned, use null.

2. **Therapeutics**: Look in `concise_assessment` items for treatment recommendations (e.g., "Recommendations: Veramyst nasal spray, Medrol Dosepak, Clarinex 5 mg daily"). Extract the medication/treatment text exactly as written. Also check `medicines_allergies` for current medications. If no treatments mentioned, use null.

3. **Risks/Benefits**: If risks, benefits, side effects, or warnings are mentioned anywhere in the summary, extract exactly. Otherwise use null.

4. **Follow-ups**: Look in `concise_assessment` items for follow-up instructions, monitoring, appointments, or next steps. Extract exactly as written. If no follow-ups mentioned, use null.

## Source Citations
- Copy the `source` field directly from the summary item you're using
- Use ONLY section titles that appear in the "Valid Section Titles" list above
- Format: "SECTION_NAME section, chunk_X:Y-Z"
- Each field (diagnostics, therapeutics, risks_benefits, follow_ups) must have its own source citation

## Rules
- Extract text exactly as it appears in the summary - do not modify, add, or infer
- Use null if information is not in the summary
- Number recommendations 1, 2, 3... by urgency (1 = most urgent/important)
- Confidence: 1.0 if explicitly stated, 0.8-0.9 if strongly implied, lower if inferred
- Include hallucination_guard_note if confidence < 0.8 or evidence is weak
- If no recommendations can be made, return empty array: []
- Output ONLY valid JSON - no markdown, no explanatory text

## Summary
{summary_sections}
