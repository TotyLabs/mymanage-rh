import json
import re

with open("src_to_audit.txt") as f:
    files = f.read().splitlines()

findings = []

RULES = [
    (r"except Exception:\s*pass", "Silent Exception Ignored (Dangerous)"),
    (r"open\([^,]+,\s*['\"]w['\"]\)", "File opened for writing without explicit encoding"),
    (r"print\(", "Print statement instead of structured logger"),
    (r"text\(f['\"].*?{.*?}.*?['\"]\)", "Raw f-string SQL injection risk in SQLAlchemy text()"),
    (r"__pycache__|os\.environ\.get\(['\"]SECRET_KEY['\"],\s*['\"]test.*['\"]\)", "Insecure default secret key or token"),
    (r"innerHTML", "Potential XSS via innerHTML (Frontend)"),
    (r"LocalStorage\.getItem\(['\"]token['\"]\)", "Token retrieved from LocalStorage (Frontend Auth Risk)"),
]

for file_path in files:
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
            lines = content.split('\n')
            
            for i, line in enumerate(lines):
                for pattern, title in RULES:
                    if re.search(pattern, line):
                        findings.append({
                            "severity": "Medium",
                            "title": title,
                            "file": file_path,
                            "line": i + 1,
                            "snippet": line.strip(),
                            "risk": "security issue" if "XSS" in title or "SQL" in title else "maintainability/runtime risk"
                        })
    except Exception as e:
        pass

with open("audit_findings_auto.json", "w") as f:
    json.dump(findings, f, indent=2)

print(f"Auto-analyzer complete. Found {len(findings)} potential issues.")
