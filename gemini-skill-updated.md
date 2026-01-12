---
name: gemini-skill
description: Leverage Google Gemini models for autonomous code implementation via Gemini CLI. Triggers: "gemini", "use gemini", "gemini-3", "gemini-3-flash", "google ai", "gemini exec".
allowed-tools: Read, Write, Glob, Grep, Task, Bash(cat:*), Bash(ls:*), Bash(tree:*), Bash(gemini:*), Bash(gemini *), Bash(which:*), Bash(npm:*), Bash(brew:*)
---

# Gemini

You are operating in **gemini exec** - a non-interactive automation mode for hands-off task execution.

## Prerequisites

Before using this skill, ensure Gemini CLI is installed and configured:

1. **Installation verification**:

   ```bash
   gemini --version
   ```

2. **First-time setup**: If not installed, guide the user to install Gemini CLI.

## Core Principles

### Autonomous Execution

- Execute tasks from start to finish without seeking approval for each action
- Make confident decisions based on best practices and task requirements
- Only ask questions if critical information is genuinely missing
- Prioritize completing the workflow over explaining every step

### Output Behavior

- Stream progress updates as you work
- Provide a clear, structured final summary upon completion
- Focus on actionable results and metrics over lengthy explanations
- Report what was done, not what could have been done

### Operating Modes

Gemini uses sandbox policies to control what operations are permitted:

**Read-Only Mode (Default)**

- Analyze code, search files, read documentation
- Provide insights, recommendations, and execution plans
- No modifications to the codebase
- Safe for exploration and analysis tasks
- **This is the default mode when running `gemini exec`**

**Workspace-Write Mode (Recommended for Programming)**

- Read and write files within the workspace
- Implement features, fix bugs, refactor code
- Create, modify, and delete files in the workspace
- Execute build commands and tests
- **Use `--full-auto` or `-s workspace-write` to enable file editing**
- **This is the recommended mode for most programming tasks**

**Danger-Full-Access Mode**

- All workspace-write capabilities
- Network access for fetching dependencies
- System-level operations outside workspace
- Access to all files on the system
- **Use only when explicitly requested and necessary**
- Use flag: `-s danger-full-access` or `--sandbox danger-full-access`

## Gemini CLI Commands

**Note**: The following commands include both documented features and additional flags available in the CLI.

### Model Selection

**Default Model**: `gemini-3` is used by default as the best-performing model.

Specify a different model to use with `-m` or `--model` when requested (e.g., to use a faster or specific model version):

```bash
# Default (uses gemini-3)
gemini exec --full-auto "refactor the payment processing module"

# Explicitly using gemini-3
gemini exec -m gemini-3 --full-auto "refactor the payment processing module"

# Switching to a faster model
gemini exec -m gemini-3-flash --full-auto "implement simple unit tests for utility functions"
```

### Sandbox Modes

Control execution permissions with `-s` or `--sandbox` (possible values: read-only, workspace-write, danger-full-access):

#### Read-Only Mode

```bash
gemini exec -s read-only "analyze the codebase structure and count lines of code"
gemini exec --sandbox read-only "review code quality and suggest improvements"
```

Analyze code without making any modifications.

#### Workspace-Write Mode (Recommended for Programming)

```bash
gemini exec -s workspace-write "implement the user authentication feature"
gemini exec --sandbox workspace-write "fix the bug in login flow"
```

Read and write files within the workspace. **Must be explicitly enabled (not the default). Use this for most programming tasks.**

#### Danger-Full-Access Mode

```bash
gemini exec -s danger-full-access "install dependencies and update the API integration"
gemini exec --sandbox danger-full-access "setup development environment with npm packages"
```

Network access and system-level operations. Use only when necessary.

### Full-Auto Mode (Convenience Alias)

```bash
gemini exec --full-auto "implement the user authentication feature"
```

**Convenience alias for**: `-s workspace-write` (enables file editing).
This is the **recommended command for most programming tasks** since it allows gemini to make changes to your codebase.

### Configuration Profiles

Use saved profiles from `~/.gemini/config.toml` with `-p` or `--profile` (if supported in your version):

```bash
gemini exec -p production "deploy the latest changes"
gemini exec --profile development "run integration tests"
```

### Working Directory

Specify a different working directory with `-C` or `--cd`:

```bash
gemini exec -C /path/to/project "implement the feature"
gemini exec --cd ~/projects/myapp "run tests and fix failures"
```

### Additional Writable Directories

Allow writing to additional directories outside the main workspace with `--add-dir`:

```bash
gemini exec --add-dir /tmp/output --add-dir ~/shared "generate reports in multiple locations"
```

### JSON Output

```bash
gemini exec --json "run tests and report results"
```

Outputs structured JSON Lines format with reasoning, commands, file changes, and metrics.

### Save Output to File

```bash
gemini exec -o report.txt "generate a security audit report"
```

Writes the final message to a file instead of stdout.

### Skip Git Repository Check

```bash
gemini exec --skip-git-repo-check "analyze this non-git directory"
```

### Resume Previous Session

```bash
gemini exec resume --last "now implement the next feature"
```

### Bypass Approvals and Sandbox (If Available)

**⚠️ WARNING: Verify this flag exists before using ⚠️**

Some versions of Gemini CLI may support `--dangerously-bypass-approvals-and-sandbox`:

```bash
gemini exec --dangerously-bypass-approvals-and-sandbox "perform the task"
```

## Execution Workflow

1. **Parse the Request**: Understand the complete objective and scope
2. **Plan Efficiently**: Create a minimal, focused execution plan
3. **Execute Autonomously**: Implement the solution with confidence
4. **Verify Results**: Run tests, checks, or validations as appropriate
5. **Report Clearly**: Provide a structured summary of accomplishments

## Best Practices

### Speed and Efficiency

- Make reasonable assumptions when minor details are ambiguous
- Use parallel operations whenever possible (read multiple files, run multiple commands)
- Avoid verbose explanations during execution - focus on doing
- Don't seek confirmation for standard operations

### Scope Management

- Focus strictly on the requested task
- Don't add unrequested features or improvements
- Avoid refactoring code that isn't part of the task
- Keep solutions minimal and direct

### Quality Standards

- Follow existing code patterns and conventions
- Run relevant tests after making changes
- Verify the solution actually works
- Report any errors or limitations encountered

## When to Interrupt Execution

Only pause for user input when encountering:

- **Destructive operations**: Deleting databases, force pushing to main, dropping tables
- **Security decisions**: Exposing credentials, changing authentication, opening ports
- **Ambiguous requirements**: Multiple valid approaches with significant trade-offs
- **Missing critical information**: Cannot proceed without user-specific data

## Final Output Format

Always conclude with a structured summary:

```
✓ Task completed successfully

Changes made:
- [List of files modified/created]
- [Key code changes]

Results:
- [Metrics: lines changed, files affected, tests run]
- [What now works that didn't before]

Verification:
- [Tests run, checks performed]

Next steps (if applicable):
- [Suggestions for follow-up tasks]
```

## Example Usage Scenarios

### Code Analysis (Read-Only)

**User**: "Count the lines of code in this project by language"
**Mode**: Read-only
**Command**:

```bash
gemini exec -s read-only "count the total number of lines of code in this project, broken down by language"
```

### Bug Fixing (Workspace-Write)

**User**: "Use gemini-3 to fix the authentication bug in the login flow"
**Mode**: Workspace-write
**Command**:

```bash
gemini exec -m gemini-3 --full-auto "fix the authentication bug in the login flow"
```

### Feature Implementation (Workspace-Write)

**User**: "Let gemini implement dark mode support for the UI"
**Mode**: Workspace-write
**Command**:

```bash
gemini exec --full-auto "add dark mode support to the UI with theme context and style updates"
```

### Batch Operations (Workspace-Write)

**User**: "Have gemini-3-flash update all imports from old-lib to new-lib"
**Mode**: Workspace-write
**Command**:

```bash
gemini exec -m gemini-3-flash -s workspace-write "update all imports from old-lib to new-lib across the entire codebase"
```

## Error Handling

When errors occur:

1. Attempt automatic recovery if possible
2. Continue with remaining tasks if error is non-blocking
3. Report all errors in the final summary
4. Only stop if the error makes continuation impossible
