# Claude Code Hooks Research

Comprehensive analysis of practical Claude Code hook implementations from the community.

**Date**: 2026-01-06
**Sources**: GitHub repositories, blog posts, official documentation

---

## Table of Contents

1. [Hook Events Overview](#hook-events-overview)
2. [Safety & Guardrails Hooks](#safety--guardrails-hooks)
3. [Workflow Automation Hooks](#workflow-automation-hooks)
4. [Context Intelligence Hooks](#context-intelligence-hooks)
5. [Popular Implementations](#popular-implementations)
6. [Code Snippets](#code-snippets)
7. [Gaps & Opportunities](#gaps--opportunities)

---

## Hook Events Overview

Claude Code provides 8 lifecycle events for hooks:

| Event | Can Block | Can Inject Context | Purpose |
|-------|-----------|-------------------|---------|
| `UserPromptSubmit` | Yes (exit 2) | Yes (stdout) | Intercept prompts before processing |
| `PreToolUse` | Yes (exit 2) | No | Block dangerous operations |
| `PostToolUse` | No | Yes (stdout) | Validate results, run formatters |
| `Stop` | Yes | Yes | Enforce completion requirements |
| `SubagentStop` | Yes | Yes | Control subagent completion |
| `Notification` | No | No | Logging, alerts |
| `PreCompact` | No | No | Backup transcripts |
| `SessionStart` | No | No | Load context, initialize |

### Exit Code Semantics

- **0**: Success, continue normally
- **2**: Blocking error - stderr shown to Claude, action prevented
- **Other**: Non-blocking error - shown to user, continues

### JSON Response Format

```json
{
  "continue": true,
  "stopReason": "optional message",
  "suppressOutput": false,
  "decision": "approve|block|undefined",
  "reason": "explanation"
}
```

---

## Safety & Guardrails Hooks

### 1. Dangerous Command Blocker (PreToolUse)

**Source**: disler/claude-code-hooks-mastery, decider/claude-hooks
**Popularity**: High - most common hook implementation

Blocks dangerous shell commands before execution.

```python
#!/usr/bin/env python3
import json
import sys
import re

dangerous_patterns = [
    r'rm\s+.*-[rf]',           # rm -rf variants
    r'rm\s+--recursive',       # rm --recursive
    r'sudo\s+rm',              # privileged deletion
    r'chmod\s+777',            # world-writable permissions
    r'>\s*/etc/',              # system directory writes
    r'git\s+reset\s+--hard',   # destructive git
    r'git\s+push\s+--force',   # force push
]

data = json.loads(sys.stdin.read())
tool_name = data.get('tool_name', '')
command = data.get('tool_input', {}).get('command', '')

if tool_name == 'Bash':
    for pattern in dangerous_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            print(f"BLOCKED: Dangerous pattern '{pattern}' detected", file=sys.stderr)
            sys.exit(2)

sys.exit(0)
```

### 2. Environment File Protection (PreToolUse)

**Source**: disler/claude-code-hooks-mastery
**Popularity**: High

Prevents access to `.env` and credential files.

```python
#!/usr/bin/env python3
import json
import sys
import re

data = json.loads(sys.stdin.read())
tool_name = data.get('tool_name', '')
tool_input = data.get('tool_input', {})

# Check file-based tools
if tool_name in ['Read', 'Edit', 'Write']:
    file_path = tool_input.get('file_path', '')
    if re.search(r'\.env($|\.)', file_path) and '.env.sample' not in file_path:
        print("BLOCKED: Access to .env files is restricted", file=sys.stderr)
        sys.exit(2)

# Check bash commands for env access
if tool_name == 'Bash':
    command = tool_input.get('command', '')
    if re.search(r'(cat|less|head|tail|cp|mv)\s+.*\.env', command):
        print("BLOCKED: Indirect .env access detected", file=sys.stderr)
        sys.exit(2)

sys.exit(0)
```

### 3. Branch Protection Guard (PreToolUse)

**Source**: wangbooth/Claude-Code-Guardrails
**Popularity**: Medium

Prevents writes to protected branches (main, master, release).

```bash
#!/bin/bash
# guard-branch.sh
json_input=$(cat)

# Get current branch
current_branch=$(git branch --show-current 2>/dev/null)

# Protected branches pattern
protected="^(main|master|dev|release.*)$"

if [[ "$current_branch" =~ $protected ]]; then
    timestamp=$(date +%Y%m%d-%H%M%S)
    echo "BLOCKED: Cannot write to protected branch '$current_branch'" >&2
    echo "Suggestion: Create a feature branch with: git checkout -b vibe/$timestamp-claude" >&2
    exit 2
fi

exit 0
```

### 4. Secret Detection Hook (UserPromptSubmit)

**Source**: Official Claude Code docs
**Popularity**: Medium

Scans prompts for potential secrets before processing.

```python
#!/usr/bin/env python3
import json
import sys
import re

secret_patterns = [
    r'[A-Za-z0-9_-]{20,}',  # Long tokens
    r'sk-[A-Za-z0-9]{32,}', # OpenAI keys
    r'AKIA[A-Z0-9]{16}',    # AWS access keys
    r'ghp_[A-Za-z0-9]{36}', # GitHub tokens
    r'-----BEGIN.*KEY-----', # PEM keys
]

data = json.loads(sys.stdin.read())
prompt = data.get('prompt', '')

for pattern in secret_patterns:
    if re.search(pattern, prompt):
        print("WARNING: Potential secret detected in prompt", file=sys.stderr)
        # Could exit 2 to block, or just warn
        break

sys.exit(0)
```

### 5. Permission Auto-Handler (PreToolUse)

**Source**: claudelog.com
**Version**: Claude Code v2.0.45+

Auto-approve read-only tools, deny dangerous patterns.

```bash
#!/bin/bash
json_input=$(cat)
tool_name=$(echo "$json_input" | jq -r '.tool_name // empty')

# Auto-approve read-only tools
if [[ "$tool_name" =~ ^(Read|Glob|Grep|LS)$ ]]; then
    echo '{"decision": {"behavior": "allow"}}'
    exit 0
fi

# Deny dangerous patterns
if echo "$json_input" | jq -r '.tool_input.command // empty' | grep -q "rm -rf"; then
    echo '{"decision": {"behavior": "deny", "message": "Dangerous command blocked"}}'
    exit 0
fi

# Default: continue with normal permission flow
exit 0
```

---

## Workflow Automation Hooks

### 1. Auto-Format on Edit (PostToolUse)

**Source**: stevekinney.com, suiteinsider.com
**Popularity**: High

Runs Prettier/Black after file edits.

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/auto-format.sh"
          }
        ]
      }
    ]
  }
}
```

```bash
#!/bin/bash
# auto-format.sh
json_input=$(cat)
file_path=$(echo "$json_input" | jq -r '.tool_input.file_path // empty')

if [[ -z "$file_path" ]]; then
    exit 0
fi

case "$file_path" in
    *.py)
        black "$file_path" 2>/dev/null || ruff format "$file_path" 2>/dev/null
        ;;
    *.js|*.ts|*.jsx|*.tsx|*.json|*.md)
        prettier --write "$file_path" 2>/dev/null
        ;;
    *.go)
        gofmt -w "$file_path" 2>/dev/null
        ;;
esac

exit 0
```

### 2. Auto-Run Tests (PostToolUse)

**Source**: eesel.ai, suiteinsider.com
**Popularity**: High

Runs test suite after code modifications.

```bash
#!/bin/bash
# auto-test.sh
json_input=$(cat)
file_path=$(echo "$json_input" | jq -r '.tool_input.file_path // empty')

# Only run for source files
if [[ ! "$file_path" =~ \.(py|js|ts|tsx)$ ]]; then
    exit 0
fi

# Determine test command based on project
if [[ -f "package.json" ]]; then
    npm test 2>&1 | head -50
elif [[ -f "pyproject.toml" ]] || [[ -f "setup.py" ]]; then
    pytest -x -q 2>&1 | head -50
fi

# Don't block on test failure - just report
exit 0
```

### 3. Package Age Checker (PreToolUse)

**Source**: decider/claude-hooks
**Popularity**: Medium

Prevents installation of outdated npm packages.

```python
#!/usr/bin/env python3
import json
import sys
import re
import urllib.request
from datetime import datetime, timezone

MAX_AGE_DAYS = 180

def get_package_age(package_name):
    """Fetch package metadata from npm registry."""
    try:
        url = f"https://registry.npmjs.org/{package_name}"
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read())
            latest = data.get('dist-tags', {}).get('latest')
            if latest and latest in data.get('time', {}):
                pub_date = datetime.fromisoformat(
                    data['time'][latest].replace('Z', '+00:00')
                )
                age = (datetime.now(timezone.utc) - pub_date).days
                return age, latest
    except:
        pass
    return None, None

data = json.loads(sys.stdin.read())
command = data.get('tool_input', {}).get('command', '')

# Check for npm/yarn install commands
match = re.search(r'(npm|yarn)\s+(install|add|i)\s+(\S+)', command)
if match:
    package = match.group(3).split('@')[0]  # Remove version specifier
    age, version = get_package_age(package)

    if age and age > MAX_AGE_DAYS:
        print(f"BLOCKED: Package '{package}' is {age} days old (max: {MAX_AGE_DAYS})", file=sys.stderr)
        print(f"Latest version: {version}", file=sys.stderr)
        sys.exit(2)

sys.exit(0)
```

### 4. Auto-Commit After Edit (PostToolUse)

**Source**: stevekinney.com, wangbooth/Claude-Code-Guardrails
**Popularity**: Medium

Creates granular commits after each edit.

```bash
#!/bin/bash
# auto-commit.sh
json_input=$(cat)
file_path=$(echo "$json_input" | jq -r '.tool_input.file_path // empty')

if [[ -z "$file_path" ]] || [[ ! -f "$file_path" ]]; then
    exit 0
fi

# Only commit tracked files
if git ls-files --error-unmatch "$file_path" &>/dev/null; then
    git add "$file_path"
    git commit -m "chore(ai): apply Claude edit to $(basename "$file_path")" --no-verify 2>/dev/null
fi

exit 0
```

### 5. GitButler Integration (PreToolUse/PostToolUse/Stop)

**Source**: GitButler Docs
**Popularity**: Growing

Isolates Claude changes into virtual branches.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|MultiEdit|Write",
        "hooks": [{"type": "command", "command": "but claude pre-tool"}]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|MultiEdit|Write",
        "hooks": [{"type": "command", "command": "but claude post-tool"}]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [{"type": "command", "command": "but claude stop"}]
      }
    ]
  }
}
```

### 6. Desktop Notification (Stop)

**Source**: decider/claude-hooks, eesel.ai
**Popularity**: High

Sends notification when Claude finishes.

```python
#!/usr/bin/env python3
import json
import sys
import subprocess
import os

data = json.loads(sys.stdin.read())
project = os.path.basename(os.getcwd())

# macOS notification
try:
    subprocess.run([
        'osascript', '-e',
        f'display notification "Task completed in {project}" with title "Claude Code"'
    ], timeout=5)
except:
    pass

# Pushover (if configured)
user_key = os.environ.get('PUSHOVER_USER_KEY')
app_token = os.environ.get('PUSHOVER_APP_TOKEN')

if user_key and app_token:
    try:
        import urllib.request
        import urllib.parse

        data = urllib.parse.urlencode({
            'token': app_token,
            'user': user_key,
            'title': 'Claude Code Finished',
            'message': f'Task completed in {project}',
            'priority': 1
        }).encode()

        urllib.request.urlopen(
            'https://api.pushover.net/1/messages.json',
            data=data,
            timeout=5
        )
    except:
        pass

sys.exit(0)
```

---

## Context Intelligence Hooks

### 1. Session Context Loader (SessionStart)

**Source**: disler/claude-code-hooks-mastery
**Popularity**: Medium

Loads development context at session start.

```python
#!/usr/bin/env python3
import json
import sys
import subprocess
from pathlib import Path
from datetime import datetime

def get_git_status():
    """Get current git state."""
    try:
        branch = subprocess.run(
            ['git', 'branch', '--show-current'],
            capture_output=True, text=True
        ).stdout.strip()

        status = subprocess.run(
            ['git', 'status', '--porcelain'],
            capture_output=True, text=True
        ).stdout

        return {
            'branch': branch,
            'uncommitted_files': len(status.strip().split('\n')) if status.strip() else 0
        }
    except:
        return None

def get_recent_issues():
    """Fetch open GitHub issues."""
    try:
        result = subprocess.run(
            ['gh', 'issue', 'list', '--limit', '5', '--json', 'number,title'],
            capture_output=True, text=True
        )
        return json.loads(result.stdout) if result.returncode == 0 else None
    except:
        return None

def load_context_files():
    """Load project context files."""
    context = []
    for filename in ['.claude/CONTEXT.md', 'TODO.md', 'NOTES.md']:
        path = Path(filename)
        if path.exists():
            content = path.read_text()[:1000]  # Limit size
            context.append(f"## {filename}\n{content}")
    return '\n\n'.join(context)

# Main
data = json.loads(sys.stdin.read())

context = {
    'timestamp': datetime.now().isoformat(),
    'session_id': data.get('session_id'),
    'source': data.get('source'),  # startup, resume, clear
    'git': get_git_status(),
    'issues': get_recent_issues(),
}

# Output context for Claude to see
print(f"Development Context loaded at {context['timestamp']}")
if context['git']:
    print(f"Branch: {context['git']['branch']}, Uncommitted: {context['git']['uncommitted_files']}")

file_context = load_context_files()
if file_context:
    print(f"\n{file_context}")

sys.exit(0)
```

### 2. Smart Command Dispatcher (PreToolUse)

**Source**: claudelog.com
**Popularity**: Medium

Routes commands to specific validators based on content.

```bash
#!/bin/bash
json_input=$(cat)
command=$(echo "$json_input" | jq -r '.tool_input.command // empty')

if [ -z "$command" ]; then
    exit 0
fi

# Route to specific handlers
if echo "$command" | grep -q "npm run deploy"; then
    echo "Running pre-deployment validation..."
    ./scripts/pre-deployment-checks.sh <<< "$json_input"
fi

if echo "$command" | grep -q "npm run build"; then
    echo "Running build validation..."
    ./scripts/build-validator.sh <<< "$json_input"
fi

if echo "$command" | grep -q "docker"; then
    echo "Running Docker safety checks..."
    ./scripts/docker-validator.sh <<< "$json_input"
fi

exit 0
```

### 3. Prompt Context Injection (UserPromptSubmit)

**Source**: disler/claude-code-hooks-mastery
**Popularity**: Medium

Adds project standards context to prompts.

```python
#!/usr/bin/env python3
import json
import sys
from datetime import datetime

# Read project standards if available
standards = ""
try:
    with open('.claude/standards.md', 'r') as f:
        standards = f.read()[:500]
except:
    pass

# Inject context
context = f"""
---
Project Context (auto-injected)
Timestamp: {datetime.now().isoformat()}
Standards: {standards if standards else 'None defined'}
---
"""

print(context)
sys.exit(0)
```

### 4. Code Quality Validator (PostToolUse)

**Source**: decider/claude-hooks
**Popularity**: Medium

Enforces code quality standards after edits.

```python
#!/usr/bin/env python3
import json
import sys
import re
from pathlib import Path

# Configurable thresholds
MAX_FUNCTION_LINES = 30
MAX_FILE_LINES = 200
MAX_LINE_LENGTH = 100
MAX_NESTING = 4

def check_file_quality(file_path):
    """Check file against quality standards."""
    violations = []

    if not Path(file_path).exists():
        return violations

    with open(file_path, 'r') as f:
        lines = f.readlines()

    # File length
    if len(lines) > MAX_FILE_LINES:
        violations.append(f"File has {len(lines)} lines (max: {MAX_FILE_LINES})")

    # Line length
    for i, line in enumerate(lines, 1):
        if len(line.rstrip()) > MAX_LINE_LENGTH:
            violations.append(f"Line {i} exceeds {MAX_LINE_LENGTH} chars")

    # Function length (simple heuristic for Python)
    if file_path.endswith('.py'):
        in_function = False
        function_start = 0
        function_lines = 0

        for i, line in enumerate(lines, 1):
            if re.match(r'^\s*def\s+', line):
                if in_function and function_lines > MAX_FUNCTION_LINES:
                    violations.append(
                        f"Function at line {function_start} has {function_lines} lines"
                    )
                in_function = True
                function_start = i
                function_lines = 0
            elif in_function:
                function_lines += 1

    return violations

data = json.loads(sys.stdin.read())
file_path = data.get('tool_input', {}).get('file_path', '')

if file_path and file_path.endswith(('.py', '.js', '.ts')):
    violations = check_file_quality(file_path)
    if violations:
        print("Code quality warnings:", file=sys.stderr)
        for v in violations[:5]:  # Limit warnings
            print(f"  - {v}", file=sys.stderr)
        # Note: This doesn't block, just warns

sys.exit(0)
```

### 5. Transcript Backup (PreCompact)

**Source**: disler/claude-code-hooks-mastery
**Popularity**: Low

Creates backups before context compaction.

```python
#!/usr/bin/env python3
import json
import sys
import shutil
from pathlib import Path
from datetime import datetime

data = json.loads(sys.stdin.read())
transcript_path = data.get('transcript_path')
trigger = data.get('trigger', 'manual')

if transcript_path and Path(transcript_path).exists():
    backup_dir = Path('logs/transcript_backups')
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"transcript_{trigger}_{timestamp}.jsonl"

    shutil.copy(transcript_path, backup_dir / backup_name)
    print(f"Backup created: {backup_name}")

sys.exit(0)
```

### 6. TTS Completion Announcer (Stop)

**Source**: disler/claude-code-hooks-mastery
**Popularity**: Low

Speaks completion message using TTS.

```python
#!/usr/bin/env python3
import json
import sys
import subprocess
import os
import random

COMPLETION_MESSAGES = [
    "Work complete!",
    "All done!",
    "Task finished!",
    "Ready for review!",
]

def speak(text):
    """Use available TTS service."""
    # Try ElevenLabs
    if os.environ.get('ELEVENLABS_API_KEY'):
        # ... ElevenLabs API call
        pass

    # Try macOS say
    try:
        subprocess.run(['say', text], timeout=10)
        return
    except:
        pass

    # Try espeak (Linux)
    try:
        subprocess.run(['espeak', text], timeout=10)
        return
    except:
        pass

if '--notify' in sys.argv:
    message = random.choice(COMPLETION_MESSAGES)
    speak(message)

sys.exit(0)
```

---

## Popular Implementations

### Ranked by Community Adoption

1. **Dangerous Command Blocker** - Universal, high value
2. **Desktop Notifications** - Improves UX significantly
3. **Auto-Format on Edit** - Maintains code style
4. **Environment File Protection** - Security essential
5. **Auto-Run Tests** - Catches regressions early
6. **Branch Protection** - Prevents accidents
7. **Package Age Checker** - Dependency hygiene
8. **Session Context Loader** - Improves context quality
9. **Code Quality Validator** - Enforces standards
10. **Auto-Commit** - Granular history tracking

### SDK/Framework Options

| Name | Language | Notable Features |
|------|----------|------------------|
| **cchooks** | Python | Clean API, good docs |
| **claude-hooks** (johnlindquist) | TypeScript | Full type safety, Bun runtime |
| **claude-hooks-sdk** | PHP | Laravel-style fluent API |
| **claude-hook-comms (HCOM)** | CLI | Multi-agent collaboration |
| **Claude-Code-Guardrails** | Bash | Branch protection, snapshots |

### Notable Projects

- **TDD Guard** - Blocks changes violating TDD principles
- **TypeScript Quality Hooks** - Compilation, ESLint, Prettier pipeline
- **Britfix** - British English conversion (comments only)
- **CC Notify** - Desktop notifications with VS Code integration
- **Claudio** - OS-native sound feedback

---

## Code Snippets

### Minimal Hook Template (Python)

```python
#!/usr/bin/env python3
"""
Minimal Claude Code hook template.
Reads JSON from stdin, processes, exits with appropriate code.
"""
import json
import sys

def main():
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)  # Invalid input, don't block

    tool_name = data.get('tool_name', '')
    tool_input = data.get('tool_input', {})

    # Your logic here
    # ...

    # Exit codes:
    # 0 = success, continue
    # 2 = block action, show stderr to Claude
    # other = error, show to user, continue
    sys.exit(0)

if __name__ == '__main__':
    main()
```

### Minimal Hook Template (Bash)

```bash
#!/bin/bash
# Minimal Claude Code hook template

json_input=$(cat)
tool_name=$(echo "$json_input" | jq -r '.tool_name // empty')
command=$(echo "$json_input" | jq -r '.tool_input.command // empty')

# Your logic here
# ...

# Exit codes:
# 0 = success
# 2 = block (stderr shown to Claude)
exit 0
```

### Minimal Hook Template (TypeScript)

```typescript
#!/usr/bin/env bun
import { readFileSync } from 'fs';

interface HookPayload {
  tool_name: string;
  tool_input: Record<string, unknown>;
  tool_response?: unknown;
}

const input = readFileSync('/dev/stdin', 'utf-8');
const data: HookPayload = JSON.parse(input);

// Your logic here
// ...

process.exit(0);
```

### settings.json Configuration

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/block-dangerous.py"
          }
        ]
      },
      {
        "matcher": "Read|Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/protect-env.py"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/auto-format.sh"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/notify.py"
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/load-context.py"
          }
        ]
      }
    ]
  }
}
```

---

## Gaps & Opportunities

### Hooks That Don't Exist Yet (But Would Be Valuable)

#### 1. **Dependency License Checker**
Block installation of packages with incompatible licenses (GPL in commercial projects).

```python
# Concept: PreToolUse for npm/pip install
# Check license via npm view <pkg> license or PyPI API
# Block if license not in allowlist
```

#### 2. **Cost Estimator Hook**
Track and limit API/compute costs during sessions.

```python
# Concept: PostToolUse tracking
# Sum up costs based on tool usage
# Warn/block when budget threshold approached
```

#### 3. **Code Complexity Guard**
Block commits/edits that increase cyclomatic complexity beyond threshold.

```python
# Concept: PostToolUse for Write/Edit
# Run radon (Python) or escomplex (JS)
# Warn if complexity increases significantly
```

#### 4. **Breaking Change Detector**
Warn when changes might break downstream dependencies.

```python
# Concept: PostToolUse
# Parse AST diff, detect removed/changed public APIs
# Cross-reference with imports in other files
```

#### 5. **Documentation Drift Checker**
Ensure docs stay in sync with code changes.

```python
# Concept: PostToolUse
# When code changes, check if related docs need updates
# Warn if README/docs reference modified functions
```

#### 6. **Resource Cleanup Guard**
Ensure cloud resources created during session are tracked/cleaned.

```python
# Concept: PreToolUse + Stop
# Track terraform apply, aws/gcloud CLI creates
# On Stop, list orphaned resources
```

#### 7. **Accessibility Validator**
Check UI code for accessibility issues after edits.

```python
# Concept: PostToolUse for JSX/HTML
# Run axe-core or similar
# Warn on accessibility violations
```

#### 8. **Performance Regression Detector**
Catch performance regressions early.

```python
# Concept: PostToolUse
# Run lightweight benchmarks on changed code
# Compare against baseline
```

#### 9. **Internationalization Checker**
Ensure new strings are properly i18n-wrapped.

```python
# Concept: PostToolUse
# Scan for hardcoded user-facing strings
# Warn if not using i18n functions
```

#### 10. **AI Code Attribution Tracker**
Track which code was AI-generated for compliance.

```python
# Concept: PostToolUse
# Log all AI edits with timestamps and context
# Generate attribution report
```

### Architectural Gaps

1. **No visual workflow editor** - Hooks require shell/Python knowledge
2. **No hook marketplace** - Each team reinvents common patterns
3. **Limited hook composition** - No built-in way to chain/combine hooks
4. **No hook testing framework** - Hard to unit test hooks
5. **No hook metrics/dashboard** - Can't easily monitor hook performance
6. **No conditional hooks** - Can't enable/disable based on context
7. **No hook versioning** - Hard to upgrade hooks safely

### Integration Opportunities

1. **IDE Plugins** - VS Code extension for hook management
2. **CI/CD Integration** - Share hooks between local and CI
3. **Team Sync** - Centralized hook configuration repository
4. **Analytics** - Track which hooks block most often and why
5. **LLM-Powered Hooks** - Use smaller models for intelligent decisions

---

## References

### GitHub Repositories
- [disler/claude-code-hooks-mastery](https://github.com/disler/claude-code-hooks-mastery)
- [decider/claude-hooks](https://github.com/decider/claude-hooks)
- [johnlindquist/claude-hooks](https://github.com/johnlindquist/claude-hooks)
- [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code)
- [wangbooth/Claude-Code-Guardrails](https://github.com/wangbooth/Claude-Code-Guardrails)

### Articles & Documentation
- [GitButler: Automate Your AI Workflows with Claude Code Hooks](https://blog.gitbutler.com/automate-your-ai-workflows-with-claude-code-hooks)
- [eesel.ai: Hooks in Claude Code](https://www.eesel.ai/blog/hooks-in-claude-code)
- [claudelog.com: Hooks Reference](https://claudelog.com/mechanics/hooks/)
- [Steve Kinney: Claude Code Hook Examples](https://stevekinney.com/courses/ai-development/claude-code-hook-examples)
- [Suite Insider: Complete Guide Creating Claude Code Hooks](https://suiteinsider.com/complete-guide-creating-claude-code-hooks/)
- [GitButler Docs: Claude Code Hooks](https://docs.gitbutler.com/features/ai-integration/claude-code-hooks)
- [Codacy: Equipping Claude Code with Deterministic Security Guardrails](https://blog.codacy.com/equipping-claude-code-with-deterministic-security-guardrails)
- [The AI Stack: Deny Secrets to Agents](https://www.theaistack.dev/p/deny-secrets-to-agents)
- [Claude Code Docs: Hooks Reference](https://code.claude.com/docs/en/hooks)
