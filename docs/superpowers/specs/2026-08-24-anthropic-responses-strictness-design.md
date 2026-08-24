# Anthropic Responses Adapter Strictness Bug - Design Doc

## Problem Statement

The Responses adapter's `translate_request` function hardcodes `strict=True` when setting `output_format` or nested `output_config.format`, regardless of whether the caller provided an explicit strictness value.

## Root Cause

In `litellm/llms/anthropic/experimental_pass_through/responses_adapters/transformation.py`, the logic that builds output configuration unconditionally sets `strict=True` for any output format translation, overwriting caller-supplied values.

## Desired Behavior

- When `strict` is omitted, default to `False`
- When `strict` is explicitly set (to `True` or `False`), preserve that value
- Schema reference and required fields remain unchanged
- Chat Completions and tool strictness handling out of scope

## Solution Scope

Fix the translate_request function to:
1. Check if strict was explicitly provided by the caller
2. If omitted, use `False` as default
3. If provided, preserve the caller's value in output configuration

This applies to both `output_format` and nested `output_config.format` cases.

## Non-Goals

- Chat Completions API strictness behavior
- Tool strictness handling
- Changes to schema validation or required field handling
