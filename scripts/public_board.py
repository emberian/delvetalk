"""Physical formatting of source-selected original 11 by 11 board cells."""

def _items(value):
    items = []
    while isinstance(value, dict) and value.get('variant') == 'cons' and len(items) < 11:
        items.append(value['payload']['head'])
        value = value['payload']['tail']
    if not isinstance(value, dict) or value.get('variant') != 'nil' or len(items) != 11:
        raise ValueError('Public board requires eleven source-selected rows and cells')
    return items


def render(view):
    """Format only the board cells and opened moves selected by source."""
    width, height = view['width'], view['height']
    if width != 11 or height != 11:
        raise ValueError('This companion displays the original 11 by 11 two-player table')
    rows = [_items(row) for row in _items(view['rows'])]
    if any(type(cell) is not int or not 0 <= cell <= 3 for row in rows for cell in row):
        raise ValueError('Public board cells must be source-selected piece digits')
    lines = [f'Round {view["round"]}', '     A B C D E F G H I J K']
    for row, cells in enumerate(rows):
        lines.append(f'{row + 1:>3}  ' + ' '.join('.+-@'[cell] for cell in cells))
    marks = [chr(65 + i % width) + str(i // width + 1)
             for i in range(width * height) if view['marks'] & (1 << i)]
    lines += ['Marked: ' + (', '.join(marks) if marks else 'none'),
              'A1 is index 0; K1 is 10; A2 is 11; K11 is 120. Rows increase downward.',
              '+ attractor, - repulsor, @ automaton. North owns top corners; South owns bottom corners.']
    def coordinate(index):
        return (chr(65 + index % width) + str(index // width + 1) if index < width * height
                else 'index ' + str(index) + ' (outside board)')
    for key, name in (('north', 'North'), ('south', 'South')):
        opened = view[key]
        if opened['opened']:
            lines.append(name + ' opened: ' + coordinate(opened['source']) + ' to ' + coordinate(opened['target']))
    return '\n'.join(lines)

