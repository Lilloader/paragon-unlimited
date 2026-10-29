# Paragon Unlimited

**Make Fire Emblem Awakening mods without being a programmer.** Build brand-new chapters on real
game maps, put any character's head on any class, add new characters with portraits, voices and
battle models, write supports, and pack the result into one zip your players can install, all
from one window with step-by-step tutorials built in.

Paragon Unlimited is based on Paragon, a toolkit for editing FE13, FE14 and FE15. It keeps
everything Paragon does and adds a lot on top for **Awakening (FE13)**. Fates and Echoes projects
still open as before.

- [Getting started](#getting-started)
- [Features](#features)
- [Building from source](#building-from-source)
- [Credits](#credits) · [License](#license)

---

## Getting started

**You need:** Windows, your own dump of **Fire Emblem Awakening (North American version)** with its
RomFS extracted, and the **Azahar** emulator to play your mod.

1. Download `ParagonUnlimited-windows.zip` from **Releases**, unzip it anywhere and run
   `ParagonUnlimited.exe`.
2. Create a project: *ROM path* = your extracted RomFS, *Output path* = an empty folder for your mod.
3. Open **Help → Tutorials (Start Here)**. Nine short lessons take you from your first save to
   sharing a finished mod.
4. Use **Unlimited → Copy to Azahar** to test your changes in the game right away, and
   **Unlimited → Install Game Code Patch** once for the extra supports and skill effects.

Press **F1** in any window for help about that window.

---

## Features

### Map Maker: new chapters in a few clicks
The big green button on the main window.

- **9 brand-new chapters for every mod.** The save file has room for 64 chapters and the game uses
  55, so every project gets 9 free chapter slots (U001 to U009). One button fills them all with
  ready-to-play chapters, from easy to brutal.
- **76 map templates.** Every story map and paralogue in Awakening, plus the 25 DLC maps once
  imported. Each comes with player starts, enemies and a boss.
- **Difficulty in one slider.** Six levels from *Very easy* to *Brutal* change every enemy at once:
  basic or promoted classes, levels and weapons. Hard and Lunatic get tougher on their own.
- **Six enemy armies**: Brigands, Plegian army, Valmese army, Risen, Grimleal, Mercenaries.
  Bosses get a name, a portrait and last words.
- **Drag and drop units.** Tools to move, add and remove enemies, bosses and player starts. Tiles
  a unit can't stand on turn red (fliers may cross water and peaks). Undo and redo for everything.
- **★ Joins your army.** Pick any character and click a tile: they join on turn 1, the way Donnel
  joins in Paralogue 1. Perfect for new characters.
- **Story without code.** Write the talk before and after the battle one line at a time: who
  speaks, their mood, what they say. Text boxes and portraits are handled for you.
- **Everything is built for you**: the chapter's title card, its spot and road on the world map,
  when it unlocks, its script and its map files.
- **Edit the game's own chapters** too: move, add, change and remove units. Events,
  reinforcements and everything the editor doesn't show stay as they are.

### Sprite Workshop: map sprites the easy way
- **Heads and bodies are separate**, like in Fates. Pick a character's head and any class body
  (say, Chrom as a Wyvern Rider) and it assembles the whole sprite sheet. Heads and bodies come
  from the game's own sprites.
- **Drop your own sheet** on the big preview. It finds the class body it was drawn on.
- **Drag any head** in any frame to line it up. Bodies are never changed, so the game's animations
  stay right.
- **Clean-up eraser** (1 to 3 px) for leftovers of the old head. It never erases the new head.
- **See-through like the game**: plain images are turned into the game's transparency levels.
- **All three team colors** (player, enemy, ally) are made for you. Everything is shown in English.

### Characters, portraits and battle models
- **New Character**: one dialog creates a character, both portrait entries, portrait files and a
  battle model entry.
- **Portrait editor with a game preview**: see the portrait exactly where the game draws it,
  drag it into place, drop PNG files to replace expressions, add your own expressions, place blush
  and sweat, set the crop for the unit screen.
- **3D model preview**: body, head, hair, mount and weapon, with hair color. Import your own
  textures from PNG.
- **Voices**: hear every voice line of a character and pick lines for `$PlayVoice` from a list.

### Supports and dialogue
- **60 support partners per character** (the game has 52). *Needs the game code patch.*
- **Room for 4096 support conversations** (the game has 1920). *Needs the game code patch.*
- **Supports stay consistent**: adding a partner adds both sides, a support check runs on every
  save, and broken support data (missing lists, duplicate numbers, one-sided partners) is repaired
  automatically.
- **Dialogue editor**: automatic line breaks measured with the game's own font, a conversation
  preview that plays the voice lines, and English names for expressions and characters.

### Skills
- **New skills with real effects**: damage, hit, avoid, crit and more, with conditions such as
  "when this unit starts the fight" or "HP 50% or less". *Needs the game code patch.*
- **Import skill icons** from PNG.

### Testing and sharing
- **Check My Mod** finds problems that would crash the game or show nothing (missing portraits,
  expressions, models, voice lines, file names with the wrong letter case) and can fix some of them.
- **Copy to Azahar** puts your mod into the emulator in one click, with a backup of anything it replaces.
- **Share My Mod** packs your mod into one zip: only the files you changed, in Azahar's folder
  layout, with install instructions for your players.
- **DLC maps** can be imported, edited and rebuilt.
- **Unsaved changes are never lost**: Paragon asks before closing, and every save keeps the old
  files in *Backups*.

### Game code patch
A few features (marked above) change the game's code, not just its data. The patch ships with
Paragon Unlimited (`Data/FE13/PU_CodePatch.ips`) and adds:

- 60 support partners per character (slots #052-#059),
- skill effects (each skill's Effects lines),
- room for 4096 support conversations (the game has 1920).

**Unlimited → Install Game Code Patch** puts it into your Azahar mod folder in one click. If a
`code.ips` from another mod is already there, Paragon adds its changes and keeps the other mod's;
the old file is kept as a backup, and **Remove** takes only Paragon's changes out again. Without the
patch those features are simply ignored and nothing crashes. **Share My Mod** includes it in your
mod's zip, so your players get it too. Made for the North American version 1.0 of the game.

---

## Building from source

Paragon Unlimited needs Rust and Python 3.11. To build a standalone executable you also need PyInstaller.

1. Install [Poetry](https://python-poetry.org/), used for the Python side of the build.
1. Install dependencies with `poetry install`.
1. Render module templates with `poetry run python scripts/render_templates.py`.
1. Build the Rust code with `poetry run maturin develop --release`.
1. Run `poetry run paragon/ui/main.py`.

The GitHub Actions workflow (`.github/workflows/build.yml`) builds the Windows release and runs the
tests on every push to `main`. Full release notes are in [docs/PARAGON_UNLIMITED.md](docs/PARAGON_UNLIMITED.md).

---

## Credits
* Lil loader & albinopelican for Paragon Unlimited.
* lazy for texture parsing as well as completion support for dialogue.
* Moonling for writing most of the modules.
* RainThunder for the original FE14 Nightmare modules.
* Einstein95 for DSDecmp.
* Hextator for Nightmare 2 which was a major inspiration for Paragon.
* [FontAwesome](https://fontawesome.com/) for icons. NOTE: Most icons were colorized to work better with light and dark modes.
* [3dstools](https://github.com/ObsidianX/3dstools) and xDaniel for etc1a4 decompression.
* [FEAT](https://github.com/SciresM/FEAT) and [Ohana3DS](https://github.com/gdkchan/Ohana3DS-Rebirth) for bch parsing references.

## License
Unless explicitly stated in a file, this project is licensed under the GNU General Public License 3.0
(see `LICENSE.txt`). Paragon Unlimited is based on Paragon, copyright thane98, also GPL-3.0.

BCH parsing code (stored under src/bch.rs) was created by referencing code from FEAT and Ohana. This portion is licensed under the GNU General Public License 3.0.

Fire Emblem is a trademark of Nintendo / Intelligent Systems. Paragon Unlimited is a fan tool and
does not include any game files.
