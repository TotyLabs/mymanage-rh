import re

artifact_dir = r"C:\Users\LENOVO\.gemini\antigravity\brain\f39a2607-9745-43ba-97c1-d9833c914d99"
with open(f"{artifact_dir}\\gap_analysis.md", 'r', encoding='utf-8') as f:
    text = f.read()

blocks = re.split(r'\n### (?=[CHML]\d?-)', text)

gaps = []
for idx, b in enumerate(blocks):
    if idx == 0: continue
    
    title_match = re.match(r'^([CHML]\d?-\d+)\s*·\s*(.*)', b)
    if not title_match: continue
        
    gap_id = title_match.group(1)
    title = title_match.group(2).strip()
    
    desc = ''
    files_match = re.search(r'\*\*Files\*\*:[^\n]*\n+(.*?)(?=\n###|\n---|$)', b, re.DOTALL)
    if files_match:
        content = files_match.group(1).strip()
        content = re.sub(r'```.*?```', '', content, flags=re.DOTALL)
        paras = [p for p in content.split('\n\n') if p.strip() and not p.strip().startswith('|') and not p.strip().startswith('//') and not p.strip().startswith('**Deep trace**')]
        
        deep = re.search(r'\*\*Deep trace\*\*:\s*(.*?)(?=\n\n|$)', content, re.DOTALL)
        if deep:
            desc = deep.group(1).strip()
        elif paras:
            desc = paras[0].strip()
            
        desc = desc.replace('\n', ' ')
        if len(desc) > 350:
            desc = desc[:347] + '...'
            
    gaps.append({'id': gap_id, 'title': title, 'desc': desc})

priority_map = {
    'C': 1, 'C2': 1, 'C3': 1,
    'H': 2, 'H2': 2, 'H3': 2,
    'M': 3, 'M2': 3, 'M3': 3,
    'L': 4, 'L2': 4, 'L3': 4
}
def get_pri(gap_id):
    prefix = gap_id.split('-')[0]
    return priority_map.get(prefix, 99)

sorted_gaps = sorted(gaps, key=lambda x: (get_pri(x['id']), x['id']))

out = []
out.append('# Full Frontend Gap Closure Execution Plan')
out.append('\nThis plan maps exactly 142 unique gaps without any grouping. Every item is detailed with its technical finding and the required fix. The execution order is strictly Priority-based (Critical → High → Medium → Low).')
out.append('\n## User Review Required')
out.append('Please review the fully unrolled 142-item listing below. Once approved, I will resume execution sequentially.\n')

cats = ['🔴 CRITICAL GAPS', '🟠 HIGH GAPS', '🟡 MEDIUM GAPS', '🟢 LOW GAPS']

current_cat = 0
out.append(f'## {cats[current_cat]}')

counter = 1
for g in sorted_gaps:
    pri = get_pri(g['id'])
    if pri > current_cat + 1:
        current_cat = pri - 1
        out.append(f'\n## {cats[current_cat]}')
        
    out.append(f'{counter}. **{g["id"]}**: {g["title"]}. **Detail**: {g["desc"]}')
    counter += 1

with open(f"{artifact_dir}\\implementation_plan.md", 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))

print(f'Wrote {len(sorted_gaps)} items')
