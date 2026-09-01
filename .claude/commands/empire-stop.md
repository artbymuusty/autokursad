---
description: Engage or clear the Agentic Empire emergency stop
argument-hint: [--clear]
---
Constitution Article 25.

With no argument, run `.ai/bin/empire stop --reason "requested by user"`. This
creates `.ai/state/STOP`; every backend call, state transition and guarded tool
call then aborts cleanly with state preserved.

With `--clear`, run `.ai/bin/empire stop --clear`. Tell the user the runtime
will not auto-resume — an interrupted workflow must be restarted explicitly.
