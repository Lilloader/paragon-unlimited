# Paragon Unlimited 2.4

A toolkit for making Fire Emblem Awakening (FE13) mods. Free software under the GNU GPL v3; based on
Paragon (copyright thane98, GPL-3.0). Source: https://github.com/Lilloader/paragon-unlimited

## Getting started
You need Windows, your own dump of **Fire Emblem Awakening (North American version)** with its RomFS
extracted, and the **Azahar** emulator.

1. Unzip Paragon Unlimited anywhere and run `ParagonUnlimited.exe`.
2. Create a project: *ROM path* = your extracted RomFS, *Output path* = an empty folder for your mod.
3. Open **Help -> Tutorials (Start Here)**. Nine short lessons take you from your first save to
   sharing a finished mod. Press **F1** in any window for help about that window.
4. **Unlimited -> Copy to Emulator** puts your changes into the emulator. **Unlimited -> Install Game
   Code Patch** (once) turns on the extra supports and skill effects.

Paragon never changes your game dump. Every save keeps the old files in *Backups*.

## Features
- **Map Maker**: 9 new chapter slots in every mod (U001-U009), 76 map templates (every story map and
  paralogue, plus the DLC maps once imported) with player starts, enemies and a boss, a difficulty
  slider, six enemy armies, drag-and-drop units with undo, "Joins your army", story scenes written
  line by line, and unit editing for the game's own chapters.
- **Sprite Workshop**: separate heads and class bodies, drag heads into place in any frame, a 1-3 px
  clean-up eraser, game-style transparency, and all three team colors.
- **Characters**: New Character (character, portraits, portrait files and battle model entry in one
  dialog), a portrait editor with a game-accurate preview, a 3D model preview with PNG texture import,
  a voice browser, 5 reclass classes per gender and an avatar class checklist.
- **Supports and dialogue**: 60 support partners per character, room for 4096 support conversations,
  automatic support repairs, automatic line breaks measured with the game's font, and a conversation
  preview with voices.
- **Skills**: new skills with real effects (damage, hit, avoid, crit and more, with conditions) and
  PNG skill icons.
- **DLC maps**: import, edit and rebuild.
- **Testing and sharing**: Check My Mod, Copy to Emulator, Share My Mod (one zip with only the files your
  mod changes, plus install instructions).

## Game code patch
60 support partners, skill effects, 4096 support conversations, reclass slots 4-5 and the avatar
class list change the game's code. The patch
ships with Paragon Unlimited (`Data/FE13/PU_CodePatch.ips`) and is made for the North American version
1.0 of the game. **Unlimited -> Install Game Code Patch** puts it into Azahar's mod folder
(`load/mods/00040000000A0500/code.ips`). If a code.ips from another mod is there, Paragon adds its
changes and keeps the other mod's; the old file is kept as a backup and **Remove** takes Paragon's
changes out again. Without the patch these features are ignored and nothing crashes. Save files work
with and without it.

## What's new in 2.4
- Map Maker: new win conditions (seize a tile, survive some turns); "Defeat every enemy" and
  "Defeat the boss" fixed (they were the wrong way round in the game; older chapters are corrected
  on save); a full unit page (stats, items, drops, skills, battle quotes); deploy slots, terrain
  painting, chests and villages; talk, turn and tile events with full-screen picture scenes; the
  world map spot; green allies.
- Sprite Workshop: head sheets, head eraser and copy, per-frame size / mirror / layer; a list of
  sprites with **Save all sprites**, kept between runs; every base-game class to draw on.
- Characters: reclass slots 4-5 and an avatar class checklist (game code patch); more than 124
  classes (sprite lists follow the class list); moving classes keeps sprite lists in step.
- Supports tab: add, remove, fix and retype whole supports.
- Check My Mod: short sprite lists, duplicate or missing BMap Icons, silent voice sets.
- Help: a *What's new* page, and **See what files this changes** on every page that edits game files.

## What's new in 2.3
- The game code patch is built in: **Unlimited -> Install Game Code Patch**, with merge, backup and
  remove.
- **Share My Mod** includes the code patch by default, at `00040000000A0500/code.ips`.
- New Help page: *Game code patch*.

## Known limits
- Fates maps can't be used in the Map Maker: Awakening can't draw Fates' 3D map models.
- Skill effects, the 4096 support conversations, reclass slots 4-5 and the avatar class list are new;
  please report problems on GitHub.

Fire Emblem is a trademark of Nintendo / Intelligent Systems. Paragon Unlimited is a fan tool and does
not include any game files.
