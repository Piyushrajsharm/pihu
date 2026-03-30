import ast
import os

def analyze_file(filepath):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        source = f.read()
    
    try:
        tree = ast.parse(source)
    except SyntaxError:
        print(f"[SyntaxError] {filepath}")
        return

    issues = []
    
    for node in ast.walk(tree):
        # Bare except clauses
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                issues.append(f"Line {node.lineno}: Bare 'except:' clause (catches SystemExit/KeyboardInterrupt)")
            elif isinstance(node.type, ast.Name) and node.type.id == "Exception":
                # Check if it logs or re-raises
                has_logging = False
                for stmt in node.body:
                    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                        if getattr(stmt.value.func, "id", "") in ["print", "log", "warning", "error", "critical"]:
                            has_logging = True
                            break
                        if isinstance(stmt.value.func, ast.Attribute) and getattr(stmt.value.func.value, "id", "") in ["log", "logger"]:
                            has_logging = True
                            break
                if not has_logging:
                    issues.append(f"Line {node.lineno}: 'except Exception:' without visible logging (silent failure risk)")

        # Unprotected json.loads
        if isinstance(node, ast.Call) and getattr(getattr(node.func, "value", None), "id", "") == "json" and getattr(node.func, "attr", "") == "loads":
            # Check if it's inside a try/except block catching JSONDecodeError
            in_try = False
            for pnode in ast.walk(tree):
                if isinstance(pnode, ast.Try):
                    for ex in pnode.handlers:
                        # naive check
                        pass # too complex for naive AST, but we flag ALL json.loads and review manually
            issues.append(f"Line {node.lineno}: json.loads() call (verify JSONDecodeError handling)")
            
        # Dangerous eval/exec
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") in ["eval", "exec"]:
            issues.append(f"Line {node.lineno}: use of {node.func.id}() (security risk)")

        # subprocess without timeout
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and getattr(node.func.value, "id", "") == "subprocess" and node.func.attr in ["run", "Popen", "check_output"]:
            has_timeout = any(kw.arg == "timeout" for kw in node.keywords)
            if not has_timeout:
                issues.append(f"Line {node.lineno}: subprocess.{node.func.attr} without explicit timeout parameter")

    if issues:
        print(f"\n--- {filepath} ---")
        for i in issues:
            print(f"  {i}")

def main():
    skip_dirs = ['__pycache__', 'node_modules', 'MiroFish', 'taskweaver', 'GodMode']
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                analyze_file(path)

if __name__ == "__main__":
    main()
