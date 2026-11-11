---
name: sample-skill
description: Produce a small chart and a JSON summary for evaluation tests. Use when the task asks for a chart and result metadata.
metadata:
  author: skill-eval-tests
  version: "1.0.0"
---

# Sample Skill

When asked for a chart and a JSON summary:

1. Read any input files in the workspace.
2. Create `outputs/chart.png` with a tiny but non-empty image-like payload.
3. Create `outputs/result.json` containing `{"ok": true}`.
4. Report what you created.
