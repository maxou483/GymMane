#!/usr/bin/env python3
"""Génère docs/seances/data.js à partir des sources de GymMane.

Usage : python3 docs/seances/build.py [--bundle DOSSIER]

--bundle écrit aussi des paquets autonomes (dessins d'exercices, photos
d'aliments, médailles) pour héberger la page ailleurs que dans le dépôt.
Sans paquets, la page lit directement les fichiers de ../../assets/.
"""
import base64, csv, json, os, re, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
HERE = os.path.dirname(os.path.abspath(__file__))
ART_CHUNK = 50
FOOD_CHUNK = 100


def read(p):
    with open(os.path.join(ROOT, p), encoding='utf-8') as f:
        return f.read()


STR = re.compile(r"""r'([^']*)'|r"([^"]*)"|'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)\"""")


def unescape(s):
    return re.sub(r"\\(.)", lambda m: {'n': '\n', 't': '\t'}.get(m.group(1), m.group(1)), s).replace('\\$', '$')


def strings(src):
    out = []
    for m in STR.finditer(src):
        if m.group(1) is not None: out.append(m.group(1))
        elif m.group(2) is not None: out.append(m.group(2))
        elif m.group(3) is not None: out.append(unescape(m.group(3)))
        else: out.append(unescape(m.group(4)))
    return out


def const_block(src, name):
    i = src.index(name)
    j = src.index('=', i)
    k = j
    depth = 0
    while True:
        c = src[k]
        if c in '[{(':
            depth += 1
        elif c in ']})':
            depth -= 1
            if depth == 0:
                return src[j + 1:k + 1]
        elif c in "'\"":
            m = STR.match(src, k if src[k - 1] != 'r' else k - 1)
            if m:
                k = m.end() - 1
        k += 1


def field(block, key):
    m = re.search(r"\n    %s: (.*?)(?=,\n    \w+: |,\n?$)" % key, block, re.S)
    return m.group(1) if m else None


def exercises():
    src = read('lib/catalog/exercise_catalog.dart')
    body = src[:src.index('const List<ToolMeta>')]
    out = []
    for b in re.findall(r"Exercise\((.*?)\n  \),", body, re.S):
        b = b.rstrip()
        b = b if b.endswith(',') else b + ','
        def one(k):
            v = field(b, k)
            return strings(v)[0] if v else ''
        def many(k):
            v = field(b, k)
            return strings(v) if v else []
        out.append({
            'id': one('id'), 'en': one('name'), 'p': one('primary'), 's': many('secondary'),
            'eq': one('equipment'), 'd': one('difficulty'), 'art': one('art'),
            'kind': one('kind'), 'al': many('aliases'), 'st': many('steps'),
        })
    return out, src


def sets_and_maps(src):
    def lst(name):
        return strings(const_block(src, name))
    modes = dict(re.findall(r"'([^']+)': '(cardio|time)'", const_block(src, 'kExerciseModes')))
    prog_src = const_block(src, 'kProgressions')
    progs = [strings(x) for x in re.findall(r"\[([^\[\]]+)\]", prog_src)]
    return {
        'modes': modes, 'warmup': lst('kWarmupIds'), 'stretch': lst('kStretchIds'),
        'cardioExtras': lst('kCardioExtras'), 'needsKit': lst('kNeedsKit'), 'progressions': progs,
    }


def programs():
    src = read('lib/catalog/program_templates.dart')
    src = src[src.index('kProgramTemplates'):]
    out = []
    for m in re.finditer(r"ProgramTemplate\('([^']+)', '([^']+)', \[(.*?)\n  \]\),", src, re.S):
        days = []
        for d in re.finditer(r"ProgramDay\('([^']+)', \[(.*?)\](?:, weekday: (\d))?\)", m.group(3), re.S):
            ex = [(n, int(s)) for n, s in re.findall(r"\('([^']+)', (\d+)\)", d.group(2))]
            days.append({'name': d.group(1), 'wd': int(d.group(3) or 0), 'ex': ex})
        out.append({'id': m.group(1), 'name': m.group(2), 'days': days})
    return out


# Noms des modèles de programme qui ne correspondent pas mot pour mot à un exercice du catalogue.
PROGRAM_NAMES = {
    'Lat Pulldown': 'Cable Pulldown', 'Front Squat': 'Barbell Front Squat', 'Cable Fly': 'Cable Crossover',
    'Leg Curl': 'Lying Leg Curl', 'Standing Calf Raise': 'Lever Standing Calf Raise',
    'Barbell Row': 'Barbell Bent Over Row', 'Deadlift': 'Barbell Deadlift', 'Lateral Raise': 'Dumbbell Lateral Raise',
    'Romanian Deadlift': 'Barbell Romanian Deadlift', 'Pull Up': 'Pull-up', 'Push Up': 'Push-up',
    'Seated Cable Row': 'Cable Seated Row', 'Triceps Pushdown': 'Cable Pushdown', 'Chin Up': 'Chin-up',
    'Incline Dumbbell Press': 'Dumbbell Incline Bench Press', 'Skull Crushers': 'Barbell Lying Triceps Extension',
    'Overhead Press': 'Barbell Standing Wide Military Press', 'Lunge': 'Reverse Lunge',
    'Hammer Curl': 'Dumbbell Hammer Curl', 'Barbell Squat': 'Barbell Full Squat',
}


def resolve_programs(progs, ex):
    by = {e['en']: e['id'] for e in ex}
    for p in progs:
        for d in p['days']:
            out = []
            for n, sets in d['ex']:
                eid = by.get(PROGRAM_NAMES.get(n, n))
                if not eid:
                    raise SystemExit('Exercice introuvable dans le catalogue : ' + n)
                out.append([eid, sets])
            d['ex'] = out
    return progs


def body(path, prefix):
    src = read(path)
    def lst(name):
        return strings(const_block(src, name))
    def mp(name):
        blk = const_block(src, name)
        return {k: strings(v) for k, v in re.findall(r"'(\w+)': \[(.*?)\n  \]", blk, re.S)}
    out = {'base': lst(prefix + 'BaseMain' if prefix != 'body' else 'bodyBaseMain'),
           'lite': lst(prefix + 'BaseLite' if prefix != 'body' else 'bodyBaseLite')}
    if prefix == 'body':
        out['fills'] = mp('muscleFills')
        out['hits'] = mp('muscleHits')
    else:
        out['fills'] = mp(prefix + 'Fills')
        out['hits'] = mp(prefix + 'Hits')
        out['head'] = lst(prefix + 'Head')
        out['headInner'] = lst(prefix + 'HeadInner')
        out['headCut'] = float(re.search(prefix + r'HeadCut = ([\d.]+)', src).group(1))
    return out


def foods():
    rows = list(csv.DictReader(open(os.path.join(ROOT, 'assets/data/foods.tsv'), encoding='utf-8'), delimiter='\t'))
    out = []
    photos = set(os.listdir(os.path.join(ROOT, 'assets/food')))
    for r in rows:
        fid = r['id']
        slug = fid.split(':', 1)[-1]
        def num(k):
            try:
                return float(r.get(k) or 0)
            except ValueError:
                return 0
        out.append({
            'id': fid, 'fr': r.get('fr') or r['en'], 'en': r['en'], 'k': num('k'), 'p': num('p'), 'c': num('c'),
            'f': num('f'), 'fi': num('fi'), 'su': num('su'), 'kind': r.get('kind', ''), 'g': num('g'),
            'cat': r.get('cat', ''), 'img': slug + '.webp' if slug + '.webp' in photos else '',
        })
    return out


def awards_fr():
    arb = json.loads(read('lib/l10n/app_fr.arb'))
    ids = ['firstStep', 'firstWorkout', 'firstRoutine', 'firstRecord', 'streak3', 'streak7', 'workouts10', 'tonne1',
           'sets100', 'hours10', 'workouts50', 'tonnes10', 'hours50', 'streak30', 'sets1000', 'workouts100', 'hours100',
           'streak100', 'tonnes100', 'workouts365']
    cap = lambda s: s[0].upper() + s[1:]
    return [{'id': i, 'name': arb['award' + cap(i) + 'Name'], 'line': arb['award' + cap(i) + 'Line']} for i in ids]


def main():
    ex, src = exercises()
    meta = sets_and_maps(src)
    al = {k.replace("\\'", "'"): strings(v) for k, v in
          re.findall(r"'((?:[^'\\]|\\.)+)': (\[[^\]]*\])", read('lib/catalog/exercise_aliases.dart'))}
    for e in ex:
        e['al'] = sorted(set(e['al'] + al.get(e['en'], [])))
    fr = json.load(open(os.path.join(HERE, 'noms_fr.json'), encoding='utf-8'))
    for e in ex:
        e['fr'] = fr.get(e['id'], e['en'])
    arts = sorted({e['art'] for e in ex if e['art'] and os.path.exists(os.path.join(ROOT, 'assets/art', e['art'] + '.txt'))})
    for e in ex:
        if e['art'] not in arts:
            e['art'] = ''
    data = {
        'exercises': ex, 'meta': meta, 'programs': resolve_programs(programs(), ex), 'arts': arts, 'artChunk': ART_CHUNK, 'foodChunk': FOOD_CHUNK,
        'body': {'m': body('lib/catalog/body_svg.dart', 'body'), 'f': body('lib/catalog/body_svg_female.dart', 'female')},
        'foods': foods(), 'awards': awards_fr(),
    }
    js = '/* Généré par build.py à partir des sources de GymMane. Ne pas modifier à la main. */\nwindow.GM_DATA = ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n'
    open(os.path.join(HERE, 'data.js'), 'w', encoding='utf-8').write(js)
    print('data.js', len(js) // 1024, 'Ko,', len(ex), 'exercices,', len(arts), 'dessins,', len(data['foods']), 'aliments')

    if '--bundle' in sys.argv:
        out = sys.argv[sys.argv.index('--bundle') + 1]
        os.makedirs(os.path.join(out, 'pack'), exist_ok=True)
        for i in range(0, len(arts), ART_CHUNK):
            chunk = {a: read('assets/art/%s.txt' % a) for a in arts[i:i + ART_CHUNK]}
            json.dump(chunk, open(os.path.join(out, 'pack', 'art-%d.json' % (i // ART_CHUNK)), 'w'), separators=(',', ':'))
        def b64(p):
            return 'data:image/webp;base64,' + base64.b64encode(open(os.path.join(ROOT, p), 'rb').read()).decode()
        badges = {f[:-5]: b64('assets/badges/' + f) for f in os.listdir(os.path.join(ROOT, 'assets/badges')) if f.endswith('.webp')}
        json.dump(badges, open(os.path.join(out, 'pack', 'badges.json'), 'w'), separators=(',', ':'))
        imgs = [f['img'] for f in data['foods'] if f['img']]
        for i in range(0, len(imgs), FOOD_CHUNK):
            chunk = {n: b64('assets/food/' + n) for n in imgs[i:i + FOOD_CHUNK]}
            json.dump(chunk, open(os.path.join(out, 'pack', 'food-%d.json' % (i // FOOD_CHUNK)), 'w'), separators=(',', ':'))
        print('paquets écrits dans', out)


if __name__ == '__main__':
    main()
