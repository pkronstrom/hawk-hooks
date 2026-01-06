# Captain-Hook: Planned Hooks

Missing hooks to implement, ranked by community adoption and value.

---

## High Priority (Popular + High Value)

### 1. Auto-Run Tests (`post_tool_use/auto-test.py`)

**Problem:** Claude edits code but doesn't always run tests, leading to regressions that aren't caught until later.

**How it works:**
- Triggers on `PostToolUse` for `Write`, `Edit`, `MultiEdit`
- Detects project type (package.json → npm test, pyproject.toml → pytest, etc.)
- Runs test suite (with timeout, limited output)
- Outputs test summary to stderr for Claude to see
- Non-blocking (warns, doesn't prevent edits)

**Implementation notes:**
```python
# Detect test runner
if Path("package.json").exists():
    cmd = ["npm", "test"]
elif Path("pyproject.toml").exists():
    cmd = ["pytest", "-x", "-q", "--tb=short"]
elif Path("Cargo.toml").exists():
    cmd = ["cargo", "test", "--", "--nocapture"]

# Run with timeout, capture output
result = subprocess.run(cmd, capture_output=True, timeout=60)
if result.returncode != 0:
    print(f"Tests failed:\n{result.stdout[:500]}", file=sys.stderr)
```

---

### 2. Branch Protection (`pre_tool_use/branch-guard.sh`)

**Problem:** Claude can accidentally write to protected branches (main, master, release), causing issues in shared repos.

**How it works:**
- Triggers on `PreToolUse` for `Write`, `Edit`, `MultiEdit`, `Bash(git commit)`
- Checks current git branch against protected patterns
- Blocks with exit 2 and suggests creating a feature branch
- Configurable protected branch patterns via env var

**Implementation notes:**
```bash
current_branch=$(git branch --show-current 2>/dev/null)
protected="^(main|master|dev|release.*)$"

if [[ "$current_branch" =~ $protected ]]; then
    echo "BLOCKED: Cannot write to protected branch '$current_branch'" >&2
    echo "Create a feature branch: git checkout -b feature/$(date +%Y%m%d)-description" >&2
    exit 2
fi
```

---

### 3. Code Complexity Guard (`post_tool_use/complexity-check.py`)

**Problem:** AI-generated code can introduce complex, hard-to-maintain functions without warning.

**How it works:**
- Triggers on `PostToolUse` for `Write`, `Edit` on `.py`, `.js`, `.ts` files
- Calculates cyclomatic complexity using `radon` (Python) or `escomplex` (JS)
- Warns if complexity exceeds threshold (default: 10)
- Warns if function length exceeds threshold (default: 30 lines)
- Non-blocking, outputs warnings to stderr

**Implementation notes:**
```python
# Python: use radon
from radon.complexity import cc_visit

with open(file_path) as f:
    results = cc_visit(f.read())

for item in results:
    if item.complexity > MAX_COMPLEXITY:
        print(f"Warning: {item.name} has complexity {item.complexity} (max: {MAX_COMPLEXITY})", file=sys.stderr)
```

**Dependencies:** `radon` (Python), `escomplex` (Node)

---

### 4. TDD Guard (`pre_tool_use/tdd-guard.py` + `stop/tdd-check.py`)

**Problem:** Claude may write implementation before tests, violating TDD principles.

**How it works:**
- `PreToolUse`: When editing implementation files, checks if corresponding test file exists
- `Stop`: Before stopping, verifies tests pass for any modified code
- Configurable test file patterns (e.g., `test_*.py`, `*.test.ts`)
- Can block or just warn based on config

**Implementation notes:**
```python
# Map implementation to test file
def get_test_file(impl_path):
    # src/foo.py → tests/test_foo.py
    # src/components/Bar.tsx → src/components/Bar.test.tsx
    patterns = [
        (r'src/(.+)\.py$', r'tests/test_\1.py'),
        (r'(.+)\.tsx?$', r'\1.test.tsx'),
    ]
    for pattern, replacement in patterns:
        if re.match(pattern, impl_path):
            return re.sub(pattern, replacement, impl_path)
    return None

# Check test exists before allowing impl edit
test_file = get_test_file(file_path)
if test_file and not Path(test_file).exists():
    print(f"Warning: No test file found at {test_file}", file=sys.stderr)
```

---

## Medium Priority (Valuable but Less Common)

### 5. Breaking Change Detector (`post_tool_use/breaking-change.py`)

**Problem:** Changes to public APIs can break downstream code without warning.

**How it works:**
- Triggers on `PostToolUse` for `Write`, `Edit` on source files
- Parses AST to detect removed/renamed public functions, classes, exports
- Cross-references with imports in other project files
- Warns about potential breaking changes

**Implementation notes:**
```python
# Compare AST before/after
import ast

def get_public_symbols(code):
    tree = ast.parse(code)
    symbols = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            if not node.name.startswith('_'):
                symbols.add(node.name)
    return symbols

# Detect removed symbols
removed = old_symbols - new_symbols
if removed:
    # Check if any other files import these
    for other_file in glob.glob("**/*.py"):
        content = Path(other_file).read_text()
        for symbol in removed:
            if f"from {module} import {symbol}" in content:
                print(f"Breaking: {symbol} removed but imported in {other_file}", file=sys.stderr)
```

---

### 6. Documentation Drift Checker (`post_tool_use/doc-drift.py`)

**Problem:** Code changes but documentation (README, docstrings, CLAUDE.md) becomes stale.

**How it works:**
- Triggers on `PostToolUse` for source file edits
- Extracts function/class names that were modified
- Searches README.md, docs/, docstrings for references
- Warns if docs reference modified code and may need updates

**Implementation notes:**
```python
# Get modified function names from git diff
modified_symbols = extract_modified_symbols(file_path)

# Check docs for references
doc_files = glob.glob("**/*.md") + glob.glob("docs/**/*")
for doc in doc_files:
    content = Path(doc).read_text()
    for symbol in modified_symbols:
        if symbol in content:
            print(f"Doc drift: {doc} references modified '{symbol}'", file=sys.stderr)
```

---

### 7. Accessibility Validator (`post_tool_use/a11y-check.py`)

**Problem:** UI code may have accessibility issues (missing alt text, poor contrast, no ARIA labels).

**How it works:**
- Triggers on `PostToolUse` for `.jsx`, `.tsx`, `.html`, `.vue` files
- Runs `eslint-plugin-jsx-a11y` or `axe-core` checks
- Reports accessibility violations
- Non-blocking warnings

**Implementation notes:**
```python
# For React/JSX files
if file_path.endswith(('.jsx', '.tsx')):
    result = subprocess.run(
        ["npx", "eslint", "--plugin", "jsx-a11y", "--rule", "jsx-a11y/recommended: error", file_path],
        capture_output=True
    )
    if result.returncode != 0:
        print(f"Accessibility issues:\n{result.stdout}", file=sys.stderr)
```

**Dependencies:** `eslint-plugin-jsx-a11y` or `axe-core`

---

### 8. Package Age Checker (`pre_tool_use/package-age.py`)

**Problem:** Installing outdated or abandoned packages introduces security risks and technical debt.

**How it works:**
- Triggers on `PreToolUse` for `Bash` with `npm install`, `pip install`, etc.
- Queries npm registry / PyPI for package metadata
- Blocks if package hasn't been updated in X days (default: 180)
- Configurable age threshold

**Implementation notes:**
```python
# Extract package name from command
match = re.search(r'(npm|yarn) (install|add) (\S+)', command)
package = match.group(3).split('@')[0]

# Query npm registry
response = urllib.request.urlopen(f"https://registry.npmjs.org/{package}")
data = json.loads(response.read())
latest_date = data['time'][data['dist-tags']['latest']]
age_days = (datetime.now() - parse_date(latest_date)).days

if age_days > MAX_AGE_DAYS:
    print(f"BLOCKED: {package} is {age_days} days old", file=sys.stderr)
    sys.exit(2)
```

---

## Lower Priority (Nice to Have)

### 9. Auto-Commit (`post_tool_use/auto-commit.sh`)

**Problem:** Want granular commit history of AI changes for easy rollback.

**How it works:**
- Triggers on `PostToolUse` for `Write`, `Edit`
- Stages and commits the changed file with auto-generated message
- Uses `--no-verify` to skip pre-commit hooks
- Creates atomic commits per edit

**Trade-off:** Creates many small commits, may clutter history.

---

### 10. TypeScript/ESLint Pipeline (`post_tool_use/ts-quality.sh`)

**Problem:** TypeScript errors and lint issues not caught immediately.

**How it works:**
- Triggers on `PostToolUse` for `.ts`, `.tsx` files
- Runs `tsc --noEmit` for type checking
- Runs `eslint --fix` for auto-fixable issues
- Reports remaining errors

---

### 11. AI Code Attribution (`post_tool_use/ai-attribution.py`)

**Problem:** Need to track which code was AI-generated for compliance/auditing.

**How it works:**
- Logs all AI edits with timestamps, file paths, session IDs
- Writes to `.claude/ai-edits.log`
- Can generate attribution reports

---

## Implementation Order Suggestion

1. **Branch Protection** - Simple, high value, prevents accidents
2. **Auto-Run Tests** - High adoption, catches regressions
3. **Code Complexity Guard** - Quality enforcement
4. **TDD Guard** - For test-driven workflows
5. **Breaking Change Detector** - Stability for larger projects
6. **Doc Drift Checker** - Keep docs in sync
7. Others as needed

---

## Notes

- All hooks should be **non-blocking by default** (warn, don't prevent)
- Add `# Env: HOOK_NAME_BLOCK=true` to enable blocking mode
- Follow existing patterns in `~/.config/captain-hook/hooks/`
- Test manually with: `echo '{"tool_name": "...", "tool_input": {...}}' | python hook.py`
