
import sys
try:
    with open('modules/signature.py', 'r', encoding='utf-8') as f:
        content = f.read()
    count = content.count('"""')
    print(f"Triple quotes count: {count}")
    
    # Check for GAP-011 and its context
    idx = content.find("GAP-011")
    if idx != -1:
        print(f"Context around GAP-011: {content[idx-50:idx+50]}")
except Exception as e:
    print(f"Error: {e}")
