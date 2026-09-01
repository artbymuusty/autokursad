---
description: Show Agentic Empire system status and self-check results
---
Run `.ai/bin/empire status` and `.ai/bin/empire doctor`, then summarise for the
user: which backends are live, whether the test environment is usable, how many
decisions and roadmap items exist, and any failing invariant. If `doctor`
reports a problem, explain what it blocks and what would fix it. Do not
speculate about causes you have not verified.
