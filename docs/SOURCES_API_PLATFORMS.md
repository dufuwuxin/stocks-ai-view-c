import glob
import html
import re

out = []
for p in sorted(glob.glob('/tmp/mm*.html'), key=lambda x: int(re.findall(r'\d+', x)[0])):
    s = open(p, encoding='utf-8', errors='ignore').read()
    s = re.sub(r'(?s)<script.*?</script>', '', s)
    s = re.sub(r'(?s)<style.*?</style>', '', s)
    s = re.sub(r'(?s)<br\s*/?>', '\n', s)
    s = re.sub(r'(?s)</(p|div|li|tr|h1|h2|h3|h4|td|th|table|section|pre|span|a|b)>', '\n', s)
    t = re.sub(r'(?s)<[^>]+>', ' ', s)
    t = html.unescape(t)
    t = re.sub(r'[ \t\xa0]+', ' ', t)
    t = re.sub(r'\n\s*\n+', '\n', t)
    i = t.find('接口文档\n')
    seg = t[i:i + 400] if i >= 0 else ''
    name = ''
    addr = ''
    freq = ''
    lines = [x.strip() for x in seg.split('\n') if x.strip()]
    if len(lines) > 1:
        name = lines[1]
    m = re.search(r'接口地址：(\S+)', seg)
    if m:
        addr = m.group(1)
    m2 = re.search(r'请求频率[:：]\s*([^\n]+)', seg)
    if m2:
        freq = m2.group(1).strip()
    out.append('%s | %s | %s | %s' % (p.split('/')[-1], name, addr, freq))

print('\n'.join(out))
