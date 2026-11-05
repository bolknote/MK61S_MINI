"""Register the author's actual Gerber letter outlines against each render."""
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent


def bounds(points):
    xs, ys = zip(*points)
    return min(xs), min(ys), max(xs), max(ys)


def shapes(filename):
    """Read the small Gerber subset used by the supplied silkscreen layers."""
    source = (HERE / 'sources' / filename).read_text()
    assert '%FSLAX45Y45*%' in source and '%MOMM*%' in source
    assert 'G02' not in source and 'G03' not in source
    apertures = {int(n): float(d)
                 for n, d in re.findall(r'%ADD(\d+)C,([0-9.]+)', source)}
    result = []
    region, path, points = False, [], []
    last, diameter = (0, 0), 0.15
    for line in source.splitlines():
        if line == 'G36*':
            region, path, points = True, [], []
        elif line == 'G37*':
            result.append(('<path d="' + ' '.join(path) +
                           ' Z" fill-rule="evenodd"/>', bounds(points), False))
            region = False
        elif re.fullmatch(r'D\d+\*', line):
            diameter = apertures[int(line[1:-1])]
        else:
            match = re.fullmatch(r'X(-?\d+)Y(-?\d+)D0([123])\*', line)
            if not match:
                continue
            x, y, mode = int(match[1]) / 1e5, -int(match[2]) / 1e5, int(match[3])
            if region:
                if mode == 2 and path:
                    path.append('Z')
                path.append(('M' if mode == 2 else 'L') + f'{x},{y}')
                points.append((x, y))
            elif mode == 1:
                result.append((
                    f'<path d="M{last[0]},{last[1]} L{x},{y}" fill="none" '
                    f'stroke="currentColor" stroke-width="{diameter}" '
                    'stroke-linecap="round" stroke-linejoin="round"/>',
                    bounds([last, (x, y)]), True))
            elif mode == 3:
                result.append((f'<circle cx="{x}" cy="{y}" r="{diameter/2}"/>',
                               (x-diameter/2, y-diameter/2,
                                x+diameter/2, y+diameter/2), False))
            last = x, y
    assert not region
    return result


def contains(outer, inner):
    return (outer[0] <= inner[0] and outer[1] <= inner[1] and
            inner[2] <= outer[2] and inner[3] <= outer[3])


def scaled_group(paths, source, target, name):
    x0, y0, x1, y1 = source
    tx0, ty0, tx1, ty1 = target
    sx, sy = (tx1-tx0)/(x1-x0), (ty1-ty0)/(y1-y0)
    return (f'<g id="{name}" transform="matrix({sx},0,0,{sy},'
            f'{tx0-sx*x0},{ty0-sy*y0})">' + '\n'.join(paths) + '</g>')


def keyboard(config):
    source_x, source_y = config['source_x'], config['source_y']
    target_x, target_y = config['target_x'], config['target_y']
    rows, columns = len(source_y)-1, len(source_x)-1
    cells = {(r, c): [] for r in range(rows) for c in range(columns)}
    for path, box, stroke in shapes(config['source']):
        x0, y0, x1, y1 = box
        # Grid lines are already present on the generated body. Retain the
        # source's short strokes: angle arrows, rotation arrows and space mark.
        if stroke and max(x1-x0, y1-y0) >= 6:
            continue
        x, y = (x0+x1)/2, (y0+y1)/2
        for (row, col), paths in cells.items():
            if not (source_x[col] < x < source_x[col+1] and
                    source_y[row] < y < source_y[row+1]):
                continue
            # Make room for the plunger's shadow without re-typesetting any
            # glyphs. Small corner letters retain their source scale.
            scale = config.get('primary_scale', 1)
            if (not (row == 0 and 'header_baseline' in config) and
                    y > (source_y[row]+source_y[row+1])/2 and
                    x1 > source_x[col]+1.6):
                ax = (source_x[col]+source_x[col+1])/2
                ay = source_y[row+1]-0.35
                dy = config.get('primary_dy', 0)
                path = (f'<g transform="translate({ax},{ay+dy}) scale({scale}) '
                        f'translate({-ax},{-ay})">{path}</g>')
            paths.append((path, box))
            break
    assert rows*columns == 40 and all(cells.values())
    parts = []
    for (row, col), paths in cells.items():
        if row == 0 and 'header_baseline' in config:
            # 40th's first row is labelled ABOVE the buttons in the original.
            all_box = bounds([(b[i], b[i+1]) for _, b in paths for i in (0, 2)])
            sx = (target_x[col+1]-target_x[col])/(source_x[col+1]-source_x[col])
            width, height = (all_box[2]-all_box[0])*sx, (all_box[3]-all_box[1])*sx
            centre, baseline = config['header_centres'][col], config['header_baseline']
            target = [centre-width/2, baseline-height, centre+width/2, baseline]
            source = all_box
        else:
            source = [source_x[col], source_y[row], source_x[col+1], source_y[row+1]]
            target = [target_x[col], target_y[row], target_x[col+1], target_y[row+1]]
        parts.append(scaled_group([p for p, _ in paths], source, target,
                                  f'key-{row}-{col}'))
    return '\n'.join(parts)


def svg(config):
    parts = ['<g id="original-silkscreen" fill="#f3efe5" color="#f3efe5">',
             keyboard(config)]
    for index, banner in enumerate(config.get('banners', [])):
        selected = [(path, box) for path, box, _ in shapes(banner.get('source', config['source']))
                    if contains(banner['select'], box)]
        assert selected
        source = bounds([(b[i], b[i+1]) for _, b in selected for i in (0, 2)])
        parts.append(scaled_group([p for p, _ in selected], source, banner['target'],
                                  f'brand-{index}'))
    parts.append('</g>')
    return '\n'.join(parts)
