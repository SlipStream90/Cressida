# API Contract — mission_20260709_092044

## Summary

No API. This is a CLI script with stdout output.

## Output Contract

| Field | Value |
|---|---|
| Channel | stdout |
| Encoding | UTF-8 |
| Content | `Hello from Cressida` |
| Trailing newline | Yes (print default) |
| Exit code | `0` |

## Verification

```bash
python hello_cressida.py
# Expected: Hello from Cressida
# Exit: 0
```
