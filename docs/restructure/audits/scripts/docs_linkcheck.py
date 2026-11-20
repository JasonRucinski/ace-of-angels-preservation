import re, os, sys, subprocess
ROOT = sys.argv[1]
os.chdir(ROOT)
files = subprocess.run(['git','ls-files','*.md','.github/*'],capture_output=True,text=True).stdout.split()
files = [f for f in files if f.endswith(('.md','.yml'))]
ignored_dirs = ('work/','game/','builds/','wb/')
def slug(h):
    h = h.strip().lower()
    h = re.sub(r'`','',h)
    h = re.sub(r'[^\w\- ]','',h)
    return h.replace(' ','-')
anchors = {}
def get_anchors(path):
    if path in anchors: return anchors[path]
    s=set(); counts={}
    try:
        infence=False
        for line in open(path,encoding='utf-8'):
            if line.lstrip().startswith('```'): infence=not infence; continue
            if infence: continue
            m=re.match(r'^(#{1,6})\s+(.*?)\s*#*\s*$',line)
            if m:
                b=slug(re.sub(r'\[([^\]]*)\]\([^)]*\)',r'\1',m.group(2)))
                n=counts.get(b,0); counts[b]=n+1
                s.add(b if n==0 else f'{b}-{n}')
            for a in re.findall(r'<a (?:name|id)="([^"]+)"',line): s.add(a)
    except Exception: pass
    anchors[path]=s; return s
link_re = re.compile(r'(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)|!\[[^\]]*\]\(([^)\s]+)\)|^\[[^\]]+\]:\s*(\S+)')
broken=[]; ignored=[]; external=0; ok=0
for f in files:
    infence=False
    for i,line in enumerate(open(f,encoding='utf-8'),1):
        if line.lstrip().startswith('```'): infence=not infence; continue
        if infence: continue
        for m in link_re.finditer(line):
            t = m.group(1) or m.group(2) or m.group(3)
            if re.match(r'^[a-z]+:',t): external+=1; continue
            path,_,anc = t.partition('#')
            target = os.path.normpath(os.path.join(os.path.dirname(f), path)) if path else f
            rel = os.path.relpath(target)
            if rel.startswith(ignored_dirs) or any(('/'+d) in '/'+rel for d in ignored_dirs):
                ignored.append(f'{f}:{i}: {t}'); continue
            if path and not os.path.exists(target):
                broken.append(f'{f}:{i}: {t}  (missing {rel})'); continue
            if anc and target.endswith('.md'):
                if anc.lower() not in get_anchors(target):
                    broken.append(f'{f}:{i}: {t}  (no anchor #{anc} in {rel})'); continue
            ok+=1
print('files',len(files),'ok',ok,'external',external)
print('BROKEN',len(broken)); print('\n'.join(broken))
print('IGNORED-DIR LINKS',len(ignored)); print('\n'.join(ignored))
