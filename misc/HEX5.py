
from random import shuffle, choice
import os

# Define core elements and their fusion rules
core_elements = ['vann', 'jord', 'ild', 'luft']
fusions = {
    frozenset(['vann', 'jord']): 'plante',
    frozenset(['jord', 'ild']): 'metall',
    frozenset(['ild', 'vann']): 'lyn'
}

# Orientation symbols
orientations = ['↑', '↓']

# Symbol markers
def get_symbol(slot):
    if slot.get('fused', False):
        return '★'
    elif slot.get('consumed', False):
        return '○'
    else:
        return '●'

# Create a draw pot
def create_pot():
    return core_elements * 3

# Draw elements from the pot
def draw(pot, count):
    shuffle(pot)
    drawn = pot[:count]
    del pot[:count]
    return drawn

# Randomly assign orientation to an element
def with_orientation(element):
    orientation = choice(orientations)
    return {'name': element, 'orientation': orientation, 'consumed': False}

# Display the current stacks
def display_stacks(stacks):
    os.system('cls' if os.name == 'nt' else 'clear')
    print("\n")

    for line in ['L1', 'L2', 'L3', 'L4', 'L5']:
        row = []
        for h in ['H1', 'H2', 'H3', 'H4']:
            slot = stacks[h].get(line, None)
            if slot:
                symbol = get_symbol(slot)
                row.append(f"[ {slot['orientation']} {symbol} {slot['name']} ]")
            else:
                row.append("[ --- ]")
        print(f"{line}  " + "   ".join(row))
    print("\n")

# Process fusions
def process_fusions(stacks):
    for h in ['H1', 'H2', 'H3', 'H4']:
        fusion_slots = ['L4', 'L5']
        used = set()
        for upper, lower in [('L1', 'L2'), ('L2', 'L3')]:
            top = stacks[h].get(upper)
            bottom = stacks[h].get(lower)
            if not top or not bottom:
                continue
            pair = frozenset([top['name'], bottom['name']])
            if pair in fusions and (upper, lower) not in used:
                # Check orientation
                top_side = bottom['orientation']
                bottom_side = top['orientation']
                if top_side == bottom_side:
                    # Same polarity - consume one randomly
                    to_consume = choice([upper, lower])
                    stacks[h][to_consume]['consumed'] = True
                # Create fused element
                fused = with_orientation(fusions[pair])
                fused['fused'] = True
                for slot in fusion_slots:
                    if slot not in stacks[h]:
                        stacks[h][slot] = fused
                        break
                used.add((upper, lower))

# Main roll function
def roll():
    pot = create_pot()
    shuffle(pot)
    stacks = {'H1': {}, 'H2': {}, 'H3': {}, 'H4': {}}

    # Draw and place elements as described
    stacks['H4']['L3'] = with_orientation(draw(pot, 1)[0])
    pocket = draw(pot, 4) + draw(pot, 4)
    stacks['H1']['L1'] = with_orientation(draw(pot, 1)[0])
    stacks['H1']['L2'] = with_orientation(draw(pot, 1)[0])
    stacks['H1']['L3'] = with_orientation(draw(pot, 1)[0])
    pot += pocket
    pocket = draw(pot, 1) + draw(pot, 4)
    stacks['H2']['L1'] = with_orientation(draw(pot, 1)[0])
    stacks['H2']['L2'] = with_orientation(draw(pot, 1)[0])
    stacks['H2']['L3'] = with_orientation(draw(pot, 1)[0])
    pot += pocket
    stacks['H4']['L2'] = with_orientation(draw(pot, 1)[0])
    stacks['H4']['L1'] = with_orientation(draw(pot, 1)[0])
    stacks['H3']['L1'] = with_orientation(draw(pot, 1)[0])
    stacks['H3']['L2'] = with_orientation(draw(pot, 1)[0])
    stacks['H3']['L3'] = with_orientation(draw(pot, 1)[0])

    # Process fusions
    process_fusions(stacks)

    # Display final stacks
    display_stacks(stacks)

# Initial run loop
if __name__ == "__main__":
    print("Velkommen til HEX5. Skriv 'roll' for å trekke elementene.")
    while True:
        command = input(">> ").strip().lower()
        if command == 'roll':
            roll()
        elif command in ['quit', 'exit']:
            break
        else:
            print("Skriv 'roll' for å trekke eller 'exit' for å avslutte.")

# -------------------------------
# -----------
# ------------
def raw_roll():
    import subprocess
    import re

    process = subprocess.Popen(
        ["python3", "HEX5.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    out, err = process.communicate("roll\n")

    block = re.findall(r"L\d.*?(?=\n\n|\Z)", out, re.S)

    if not block:
        raise Exception("Fant ingen HEX5 output")

    clean = "\n".join(b.strip() for b in block)

    return clean
