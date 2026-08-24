# Anthropic Responses Adapter Strictness Fix - Implementation Plan

## Overview

Fix the Responses adapter's hardcoded `strict=True` bug to respect caller-supplied values with `False` as default.

## Files to Modify

### Test File
- `tests/test_litellm/llms/anthropic/experimental_pass_through/responses_adapters/test_responses_adapters_transformation.py`

### Source File
- `litellm/llms/anthropic/experimental_pass_through/responses_adapters/transformation.py`

## Test Strategy

Add regression tests covering:

1. **Omitted strict parameter** - verify default is `False`
2. **Explicit False** - verify caller's `False` value is preserved
3. **Explicit True** - verify caller's `True` value is preserved
4. **Nested output_config precedence** - test nested format with various strictness levels
5. **Optional required field** - verify required field handling is not mutated by strictness changes
6. **No mutation** - confirm no unintended changes to schema reference, other config fields

Each test case exercises the translate_request function with different input combinations and asserts the output_format/output_config.format.strict field matches expectations.

## Implementation Steps

1. Write tests first (TDD approach)
2. Identify translate_request call sites in transformation.py
3. Update logic to preserve explicit strict values and default to False
4. Run tests to confirm they pass
5. Run full lint, format, and type checks
6. Verify no test regressions

## Acceptance Criteria

- All new tests pass
- No existing tests broken
- Strictness value preserved when explicitly provided
- Default strictness is False when omitted
- No changes to schema reference or required field logic
- Lint, format, and type checks pass
