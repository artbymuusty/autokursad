#!/usr/bin/env python3
"""Agentic Empire enforcement hook — interactive-session layer.

Wired as a PreToolUse hook in `.claude/settings.json`. Exit code 2 blocks the
tool call and shows stderr to the model.

WHAT THIS IS, PRECISELY
-----------------------
This governs the **interactive Claude Code session**, which acts with the
user's authority. It enforces Constitution Articles 2 (scope), 14
(safety-critical) and 15 (Git) at tool-call time.

It is **NOT** the control on the Empire's Coder. The Coder is a `codex exec`
subprocess and this hook does not see it at all. The Coder is bounded by
`security.assert_coder_change_allowed` (which inspects what was *actually*
written, including renames), by `security.assert_audit_append_only` (the audit
trail is gitignored, so git cannot report a write to it), and by the sandbox
mode passed on its command line.

It is **NOT a sandbox**. Shell text can be obfuscated arbitrarily; a determined
command will get through. Adversarial verification on 2026-08-19 demonstrated
bypasses via `python3 -c`, heredocs, `perl -pi`, variable expansion, `cd` into
the target directory, and `xargs`/`find -exec`. This version closes the ones
that can be closed by inspection and refuses conservatively when a
write-capable command mentions safety-critical material it cannot resolve.
Anything counting on this as a complete barrier is counting wrong.

FAILURE MODE
------------
Fails CLOSED when the safety policy cannot be read — "cannot tell" is not
"allowed". Fails OPEN on any other internal error, so a bug here does not brick
the repository.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
AI = REPO / ".ai"

BLOCK = 2
ALLOW = 0

# Tools whose contract this guard understands. Anything else carrying a path
# or a command is refused (DEC-002 required change 2).
_KNOWN_TOOLS = {
    "Bash", "Write", "Edit", "NotebookEdit", "Read", "Glob", "Grep",
    "WebFetch", "WebSearch", "Task", "Agent", "TodoWrite", "SlashCommand",
    "Skill", "AskUserQuestion", "ExitPlanMode", "EnterPlanMode", "Artifact",
    "Monitor", "ListAgents", "SendMessage", "TaskOutput", "TaskStop",
}
# Tool calls that can mutate the repository. An internal error while checking
# one of these BLOCKS; an internal error on a read-only tool does not.
_WRITE_CAPABLE = {"Bash", "Write", "Edit", "NotebookEdit"}


def die(message: str) -> None:
    print(f"\n[AGENTIC EMPIRE — BLOCKED]\n{message}\n", file=sys.stderr)
    sys.exit(BLOCK)


# A policy file that PARSES but has the wrong shape is worse than one that
# fails to parse: `_matches` iterates a string character by character and
# quietly matches nothing, so every glob list silently becomes empty.
# DEC-002 required change 2 — verified as a real bypass, not a hypothetical.
_POLICY_SHAPE = {
    "safety_critical": {"path_globs": list, "symbol_patterns": list},
    "git": {"writable_path_globs": list, "protected_branches": list,
            "prohibited_commands": list},
}


def load_policy(name: str) -> dict:
    data = json.loads((AI / "policy" / f"{name}.json").read_text(encoding="utf-8"))
    for key, kind in _POLICY_SHAPE.get(name, {}).items():
        value = data.get(key)
        if not isinstance(value, kind) or not value or \
                not all(isinstance(x, str) for x in value):
            die(f"Policy `{name}.json` is malformed: `{key}` must be a "
                f"non-empty list of strings, got "
                f"{type(value).__name__}.\n\n"
                f"The file parses, so nothing raised — but every glob check "
                f"against it would silently match nothing. Refusing rather "
                f"than running with a safety policy that means nothing.")
    return data


def current_branch() -> str:
    try:
        r = subprocess.run(["git", "branch", "--show-current"], cwd=str(REPO),
                           capture_output=True, text=True, timeout=15)
        return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _matches(rel: str, globs: list[str]) -> bool:
    for glob in globs:
        base = glob.rstrip("*/")
        if fnmatch.fnmatch(rel, glob) or (base and rel.startswith(base)):
            return True
    return False


# ---------------------------------------------------------------- git

def check_git_command(command: str) -> None:
    git_policy = load_policy("git")
    lowered = " ".join(command.split())

    if "git " not in lowered:
        return

    for banned in git_policy["prohibited_commands"]:
        if f"git {banned}" in lowered or (f" {banned}" in lowered and "git" in lowered):
            notes = git_policy.get("prohibition_notes", {})
            key = banned.split()[0].lstrip("-")
            hint = notes.get(key, "")
            die(f"Prohibited Git operation: `{banned}`\n"
                f"Constitution Article 15 / DEC-013.\n{hint}")

    branch = current_branch()
    if branch in git_policy["protected_branches"]:
        for verb in ("commit", "merge", "rebase", "cherry-pick", "revert"):
            if f"git {verb}" in lowered:
                die(f"Refusing `git {verb}` on protected branch '{branch}'.\n"
                    f"Constitution Article 15: implementation happens on "
                    f"'{git_policy['task_branch_prefix']}<task-id>'.\n"
                    f"Create one first:  git checkout -b "
                    f"{git_policy['task_branch_prefix']}<task-id>")

    if "git push" in lowered:
        die("Refusing `git push`.\n"
            "Constitution Article 15 / DEC-013: pushing to the remote is the "
            "user's action alone. The Empire never pushes.")


# ---------------------------------------------------------------- writes

def check_write(path_str: str, *, via: str = "file tool") -> None:
    git_policy = load_policy("git")
    safety = load_policy("safety_critical")

    try:
        rel = str(Path(path_str).resolve().relative_to(REPO)).replace("\\", "/")
    except (ValueError, OSError):
        return  # outside the repository; not this guard's concern

    if not _matches(rel, git_policy["writable_path_globs"]):
        die(f"Refusing to write `{rel}` (via {via}).\n"
            f"Constitution Article 2 / DEC-001: outside the writable set.\n"
            f"The vendored PX4 tree (src/, platforms/, ROMFS/, boards/, msg/, "
            f"docs/) is read-only reference — roughly 45,000 files.")

    if _matches(rel, safety["path_globs"]):
        die(f"Refusing to write `{rel}` (via {via}).\n"
            f"Constitution Article 14 / DEC-006: SAFETY-CRITICAL PATH.\n\n"
            f"KURSAD40 is a real aircraft with a physical payload release. "
            f"Changes to arming, geofence, failsafe, flight modes, control "
            f"gains, takeoff, landing, return-to-home, payload release or "
            f"actuator logic require explicit USER approval — no decision, "
            f"Jury verdict or agent authority substitutes for it.\n\n"
            f"You may analyse this file and recommend a change. You may not "
            f"write it.")

    branch = current_branch()
    if branch in git_policy["protected_branches"]:
        # No carve-out. Adversarial verification 2026-08-19 found `.ai/state/`
        # whitelisted here — which is precisely the audit trail.
        die(f"Refusing to modify `{rel}` while on protected branch "
            f"'{branch}'.\nConstitution Article 15: work on "
            f"'{git_policy['task_branch_prefix']}<task-id>'.")


# ---------------------------------------------------------------- bash

_WRITE_COMMANDS = {
    "tee", "cp", "mv", "rm", "shred", "truncate", "dd", "install", "ln",
    "touch", "chmod", "chown", "mkdir", "rmdir", "rsync", "patch", "unzip",
    "tar", "gunzip", "zip", "split", "sponge",
}
_INTERPRETERS = {
    "python", "python3", "perl", "ruby", "node", "php", "awk", "gawk",
    "ed", "ex", "vim", "vi", "emacs", "sed", "gsed", "tcl", "lua",
}
_INPLACE = re.compile(r"(?:^|\s)-{1,2}[a-zA-Z.]*i[a-zA-Z.]*(?:\s|$)")
_REDIRECT = re.compile(r"(?<![0-9<>])>{1,2}\|?\s*(\S+)")
_DD_OF = re.compile(r"\bof=(\S+)")
# `open(path)` for reading must not trip this. Require a write mode or an
# explicit mutating call — otherwise `python3 -c "print(open(f).read())"`,
# a perfectly ordinary read, is refused.
_INLINE_WRITE = re.compile(
    r"""open\s*\([^)]*['"][rbt]*[wax]\+?[rbt]*['"]"""   # open(p, 'w'/'a'/'x')
    r"""|\.write(?:lines)?\s*\("""                       # f.write(...)
    r"""|\.write_(?:text|bytes)\s*\("""                  # Path(p).write_text()
    r"""|shutil\.(?:copy|copy2|copyfile|move|rmtree)"""
    r"""|os\.(?:remove|unlink|rename|replace|makedirs|mkdir|truncate)"""
    r"""|\bFile\.(?:write|delete|rename)"""
    r"""|\bIO\.write"""
    r"""|fopen\s*\([^)]*['"][wax]""")

# Wrappers that execute another command; the real command follows.
_WRAPPERS = {"xargs", "env", "nohup", "time", "nice", "sudo", "doas",
             "timeout", "stdbuf", "command", "exec", "find"}


def _expand(token: str) -> str | None:
    token = token.strip().strip("'\"")
    if not token or token.startswith("-"):
        return None
    if token in ("{}", "$@", "$*"):
        return None
    if token.startswith("~"):
        token = os.path.expanduser(token)
    if "$" in token or "`" in token:
        return None          # unresolvable; the conservative rule handles it
    return token


def _repo_path(token: str, cwd: Path) -> str | None:
    path = Path(token)
    if not path.is_absolute():
        path = cwd / token
    try:
        path.resolve().relative_to(REPO)
    except (ValueError, OSError):
        return None
    return str(path.resolve())


def _safety_tokens() -> list[str]:
    """Distinctive fragments of safety-critical paths, for the fallback rule."""
    generic = {"scripts", "olds", "Tools", "config", "simulation"}
    out = set()
    for glob in load_policy("safety_critical")["path_globs"]:
        for part in glob.replace("**", "").replace("*", "").split("/"):
            part = part.strip()
            if len(part) > 3 and part not in generic:
                out.add(part)
    return sorted(out)


def check_bash_writes(command: str, cwd: Path) -> None:
    """Best-effort detection of writes that bypass the file tools.

    Two layers:
      1. Resolve concrete targets where the token is unambiguous, and check
         each one — relative to the command's own cwd, tracking `cd`.
      2. When a write-capable construct has an UNRESOLVABLE target (variable
         expansion, command substitution, an inline program, an xargs
         placeholder) and the command text mentions safety-critical material,
         refuse rather than guess. Article 14 is not a place to assume.
    """
    unresolvable_write = False
    segment_cwd = cwd

    for segment in re.split(r"\|\||&&|[|;&\n]", command):
        segment = segment.strip()
        if not segment:
            continue
        try:
            words = shlex.split(segment)
        except ValueError:
            words = segment.split()
        if not words:
            continue

        # `cd X && echo > f` used to resolve f against REPO, not X.
        if words[0] == "cd" and len(words) > 1:
            target = _expand(words[1])
            if target:
                nxt = Path(target)
                segment_cwd = nxt if nxt.is_absolute() else (segment_cwd / target)
            continue

        head = Path(words[0]).name
        # Peel wrappers so `xargs -I{} sed -i ... {}` and `find -exec sed -i`
        # are examined as the write they are, not as an unknown outer command.
        wrapped = False
        while head in _WRAPPERS and len(words) > 1:
            wrapped = True
            rest_words = words[1:]
            # Skip the wrapper's own flags and their inline arguments.
            idx = 0
            while idx < len(rest_words) and (
                    rest_words[idx].startswith("-") or
                    (head == "find" and not Path(rest_words[idx]).name
                     in (_WRITE_COMMANDS | _INTERPRETERS))):
                idx += 1
            if idx >= len(rest_words):
                break
            words = rest_words[idx:]
            head = Path(words[0]).name
        if wrapped:
            unresolvable_write = True

        rest = " ".join(words[1:])
        writes = head in _WRITE_COMMANDS
        interp = head in _INTERPRETERS
        inplace = interp and bool(_INPLACE.search(" " + rest))

        candidates: list[str] = []
        for m in _REDIRECT.finditer(segment):
            candidates.append(m.group(1))
        for m in _DD_OF.finditer(segment):
            candidates.append(m.group(1))

        if writes or inplace:
            positional = [w for w in words[1:] if not w.startswith("-")]
            if inplace:
                candidates.extend(positional[1:] or positional)
            elif head in ("cp", "mv", "install", "rsync", "ln"):
                if positional:
                    candidates.append(positional[-1])
            else:
                candidates.extend(positional)

        # An interpreter running an inline program can write anything.
        if interp and not inplace and _INLINE_WRITE.search(rest):
            unresolvable_write = True
        # A heredoc fed to an interpreter is the same case.
        if interp and "<<" in segment:
            unresolvable_write = True

        for raw in candidates:
            token = _expand(raw)
            if token is None:
                if raw and ("$" in raw or "`" in raw or raw == "{}"):
                    unresolvable_write = True
                continue
            resolved = _repo_path(token, segment_cwd)
            if resolved:
                check_write(resolved, via=f"Bash ({head})")

        if (writes or inplace) and re.search(r"\bxargs\b|-exec\b", command):
            unresolvable_write = True

    # Segment splitting is naive about separators inside quotes: a `;` in a
    # python one-liner splits the command mid-string and the write disappears.
    # Re-check the whole command whenever an interpreter is present.
    if not unresolvable_write:
        words_all = re.findall(r"[\w.\-/]+", command)
        if any(Path(w).name in _INTERPRETERS for w in words_all) and \
                _INLINE_WRITE.search(command):
            unresolvable_write = True

    if unresolvable_write:
        hits = [tok for tok in _safety_tokens() if tok in command]
        if hits:
            die("Refusing this command.\n"
                "It can write a file, its target could not be resolved "
                "statically (variable expansion, command substitution, an "
                "inline program, a heredoc or a placeholder), and the command "
                f"text mentions safety-critical material: {hits}.\n\n"
                "Constitution Article 14: when the guard cannot tell what "
                "would be written, it refuses. Use an explicit literal path, "
                "or ask the user.")


# ---------------------------------------------------------------- main

def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return ALLOW

    if (AI / "state" / "STOP").exists():
        die("EMERGENCY STOP is active (.ai/state/STOP exists).\n"
            "Constitution Article 25: no tool call proceeds while it is set.\n"
            "Clear with:  .ai/bin/empire stop --clear")

    tool = payload.get("tool_name", "")
    args = payload.get("tool_input", {}) or {}

    # DEC-002 required change 2: default-deny posture. An unrecognised tool
    # that carries a file path or a command is treated as write-capable, so a
    # new tool does not arrive pre-approved.
    if tool not in _KNOWN_TOOLS and (
            args.get("file_path") or args.get("path") or args.get("command")):
        die(f"Unrecognised tool '{tool}' carrying a path or command.\n"
            f"This guard enumerates the tools it knows how to check. An "
            f"unknown write-capable tool is refused rather than allowed by "
            f"default. Add it to _KNOWN_TOOLS once its contract is understood.")

    if tool == "Bash":
        command = args.get("command", "") or ""
        check_git_command(command)
        cwd = Path(payload.get("cwd") or args.get("cwd") or REPO)
        check_bash_writes(command, cwd)
    elif tool in ("Write", "Edit", "NotebookEdit"):
        target = args.get("file_path") or args.get("notebook_path")
        if target:
            check_write(str(target))

    return ALLOW


def _tool_name_from_stdin(raw: str) -> str:
    try:
        return json.loads(raw).get("tool_name", "")
    except Exception:                                           # noqa: BLE001
        return ""


if __name__ == "__main__":
    _raw = sys.stdin.read()
    sys.stdin = __import__("io").StringIO(_raw)
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:                                    # noqa: BLE001
        # DEC-002 required change 2: the previous handler exited ALLOW whenever
        # the policy file merely PARSED, so an internal error inside
        # check_write turned into a permitted write — contradicting this
        # module's own "fails closed" claim. Any unhandled error on a
        # write-capable tool now BLOCKS.
        tool = _tool_name_from_stdin(_raw)
        if tool in _WRITE_CAPABLE or not tool:
            print("\n[AGENTIC EMPIRE — BLOCKED]\n"
                  f"The guard hit an internal error while checking a "
                  f"write-capable call ({tool or 'unknown tool'}), so it could "
                  f"not verify this against Constitution Articles 2, 14 and 15."
                  f"\nGuard error: {exc}\n\n"
                  "Refusing rather than assuming. Fix the guard, or make the "
                  "change through a path that is checkable.\n",
                  file=sys.stderr)
            sys.exit(BLOCK)
        print(f"[empire guard] internal error on read-only tool "
              f"'{tool}', allowing: {exc}", file=sys.stderr)
        sys.exit(ALLOW)
