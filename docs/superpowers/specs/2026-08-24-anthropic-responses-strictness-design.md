# Anthropic Responses API Strictness Default Design Spec

**Date**: 2026-08-24
**Component**: `litellm/llms/anthropic/experimental_pass_through/responses_adapters/transformation.py`
**Mapped Test**: `tests/test_litellm/llms/anthropic/experimental_pass_through/responses_adapters/test_responses_adapters_transformation.py`

## Problem Statement

The Anthropic experimental pass-through for Responses API currently hardcodes `strict: true` when translating structured output (JSON schema) requests. This prevents users from explicitly setting `strict: false` or omitting the field to use the OpenAI API default. The implementation should allow:

1. Explicit control over the strictness setting
2. Output format precedence over nested config
3. Preservation of schema and required fields
4. No mutation of input request data

## Design

### Strictness Default Behavior

- **Default (omitted `strict`)**: `false` — align with OpenAI's API default behavior
- **Explicit `true`**: Preserved as specified by user
- **Explicit `false`**: Preserved as specified by user

### Field Precedence

```
output_format.strict (if present)
  ↓ (precedence)
output_config.format.strict (if output_format absent)
  ↓ (fallback)
false (API default)
```

### Schema and Required List Preservation

All schema properties must be passed through unchanged:
- `schema.properties` — preserved exactly
- `schema.required` — preserved exactly
- `schema.additionalProperties` — preserved exactly
- All other schema fields — preserved unchanged

### Request Mutation

Input request objects must not be mutated. All reads are non-destructive.

## Implementation Location

**File**: `litellm/llms/anthropic/experimental_pass_through/responses_adapters/transformation.py`

**Method**: `LiteLLMAnthropicToResponsesAPIAdapter.translate_request()`

**Lines**: 357–374 (current; may shift after edit)

Current behavior (lines 364–374):
```python
if isinstance(output_format, dict) and output_format.get("type") == "json_schema":
    schema: Final = output_format.get("schema")
    if schema:
        responses_kwargs["text"] = {
            "format": {
                "type": "json_schema",
                "name": "structured_output",
                "schema": schema,
                "strict": True,  # HARDCODED
            }
        }
```

Expected behavior after fix:
- Read `output_format.strict` (if exists)
- Fall back to `output_config.format.strict` (if output_format absent and format exists)
- Default to `false` if neither is specified
- Preserve schema, required list, and all other fields unchanged

## Test Cases

### TC1: Omitted Strict (Default)
**Input**: `output_config={"format": {"type": "json_schema", "schema": {...}}}`

**Expected**: `text.format.strict = false`

**Verification**: Schema present, strict field absent from input, output has `strict: false`

### TC2: Explicit False
**Input**: `output_format={"type": "json_schema", "schema": {...}, "strict": false}`

**Expected**: `text.format.strict = false`

**Verification**: Strict explicitly false in input, output has `strict: false`

### TC3: Explicit True
**Input**: `output_format={"type": "json_schema", "schema": {...}, "strict": true}`

**Expected**: `text.format.strict = true`

**Verification**: Strict explicitly true in input, output has `strict: true`

### TC4: Nested Format with Strict
**Input**: `output_config={"format": {"type": "json_schema", "schema": {...}, "strict": false}}`

**Expected**: `text.format.strict = false`

**Verification**: Uses output_config when output_format absent, respects nested strict value

### TC5: Output Format Precedence
**Input**: 
```python
output_format={"type": "json_schema", "schema": schema_a, "strict": false}
output_config={"format": {"type": "json_schema", "schema": schema_b, "strict": true}}
```

**Expected**: 
- Uses `schema_a` (output_format schema)
- Uses `strict: false` (output_format strict)

**Verification**: output_format takes complete precedence; neither output_config.format nor its strict value are used

### TC6: Optional Properties Unchanged
**Input**: 
```python
output_format={
  "type": "json_schema",
  "schema": {
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"],
    "additionalProperties": False,
    "description": "Custom schema"
  }
}
```

**Expected**: All schema properties (including `description`, `additionalProperties`) preserved in output

**Verification**: `text.format.schema` matches input schema exactly

### TC7: No Input Mutation
**Input**: Request object with output_format and output_config

**Expected**: Input request object unchanged after translation

**Verification**: Original request dict unchanged; all operations are read-only

## Backward Compatibility

**Explicit `strict` values remain compatible**: Callers that explicitly set `strict: true` or `strict: false` are unaffected by this change.

**Implicit behavior changes**: The default when `strict` is omitted changes from the historical hardcoded `true` to `false` (aligning with OpenAI's API default). Callers relying on the implicit `strict: true` behavior must explicitly set it to maintain that behavior.

- **Existing tests** in `test_responses_adapters_transformation.py`:
  - Line 138: `assert fmt["strict"] is True` must be updated to reflect the new default
  - All other tests remain valid

- **External users**: Users who relied on implicit `strict: true` should explicitly set `strict: true` in their output_format to preserve that behavior
