---
description: Run the document gate — budgets, orphans, kb index, memory caps, intake cells, setup markers
---

Run `<venv python> scripts/check_docs.py --report` (`<venv python>` is defined in CLAUDE.md) and quote its output verbatim. If it fails, fix the write that caused it (trim the file where its `rule:` says, add the missing `doc_budgets.yaml` row, render the kb index with `--write-kb`, split the memory entry, or fill the setup marker) and run it again. Never raise a budget to make it pass.

$ARGUMENTS
