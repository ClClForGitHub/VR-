# Agent LLM Provider Notes

Last updated: 2026-06-27

## Local Credential Source

Runtime tests should load local credentials from:

```bash
source /home/team/zouzhiyuan/image23D_Agent/.env.agent_llm.local
```

The local env file is ignored by `/home/team/zouzhiyuan/image23D_Agent/.gitignore` and should not be committed or copied into logs.

## Provider Priority

Use Qwen first for agent LLM testing, then DeepSeek as fallback/comparison:

1. Qwen
2. DeepSeek

## User-Supplied Model Aliases

| Provider | Model alias from user | Env model value | Key record |
| --- | --- | --- | --- |
| Qwen | QWEN 3.7max | `QWEN_MODEL=qwen3.7-max` | present locally, suffix `eeef` |
| DeepSeek | DeepSeek V4 flash | `DEEPSEEK_MODEL` | present locally, suffix `9c68` |

## Use Boundary

- These keys are for later agent-provider integration and heavier close-out testing.
- Do not hard-code keys into Python modules, tests, progress docs, or generated artifacts.
- Qwen text agent calls use `QWEN_MODEL`; Qwen visual QA calls should use `QWEN_VISION_MODEL` because the current Qwen3.7-Max line is text-only while Qwen3.7-Plus is the visual/multimodal option.
- Before live provider testing, verify account region/workspace details for the Qwen base URL. The env file currently uses the legacy DashScope compatible-mode URL because no workspace-specific domain was supplied.
