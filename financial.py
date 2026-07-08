import json, os

DATA_PATH = os.path.join(os.path.dirname(__file__), 'data', 'companies_data.json')

def load_data():
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def query_financial(name):
    data = load_data()
    # 模糊比對
    found = next((c for c in data if name.lower() in c['name'].lower()), None)
    if not found:
        names = ', '.join(c['name'] for c in data[:10]) + '...'
        return f'找不到「{name}」\n範例：查VIS、查UMC、查ADI\n共 {len(data)} 家公司可查'

    qs = found['quarters'][-4:]
    rv = found['revenue'][-4:]
    gm = found['grossMargin'][-4:]
    ep = found['eps'][-4:]
    cur = found['currency']

    lines = [f'📊 {found["name"]}（{found["market"]}）\n']
    for i, q in enumerate(qs):
        lines.append(f'▌{q}')
        lines.append(f'  營收  {f"{rv[i]:,.0f} {cur}" if rv[i] is not None else "—"}')
        lines.append(f'  毛利率 {f"{gm[i]:.1f}%" if gm[i] is not None else "—"}')
        lines.append(f'  EPS   {ep[i] if ep[i] is not None else "—"}')
    return '\n'.join(lines)

def get_summary():
    data = load_data()
    # 取毛利率最高/最低的最新一季
    valid = [(c['name'], c['grossMargin'][-1]) for c in data if c['grossMargin'] and c['grossMargin'][-1] is not None]
    if not valid:
        return '暫無摘要資料'
    valid.sort(key=lambda x: x[1], reverse=True)
    top3 = valid[:3]
    bot3 = valid[-3:]

    lines = ['📊 本週半導體財報摘要\n',
             '🏆 毛利率最高（最新季）']
    for name, gm in top3:
        lines.append(f'  {name}：{gm:.1f}%')
    lines.append('\n⚠️ 毛利率最低（最新季）')
    for name, gm in bot3:
        lines.append(f'  {name}：{gm:.1f}%')
    lines.append(f'\n共追蹤 {len(data)} 家公司')
    return '\n'.join(lines)
