# Symbol by Flōyél — System Folder

Everything for «symbols» by Flōyél in one place: the library,
territories (AR), maps, and a few extras, all run through one hub.

## Setup

You need Python 3. Then, from inside this folder:

    pip install pywebview flask
    python3 hub.py

On Windows, use `pip` and `python` instead of `pip3` and `python3` if the
above doesn't work.

That opens the Hub, a small terminal and taskbar. Click an icon to open
the Library, Territories, or Maps. Full instructions are in the QuickGuide:
open it from the Hub's Start menu, or open `quickguide.html` directly.

## Folder structure

    hub.py            run this
    quickguide.html   full guide
    shell/            the Hub's own interface
    symbols/          shared symbol assets
    library/          symbol library & viewer
    territories/      AR territories
    maps/             maps
    misc/             small extras

Drop a new symbol folder, map, or territory into its designated folder and it shows up
automatically. There is nothing to register.