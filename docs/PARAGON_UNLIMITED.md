# Paragon Unlimited

A toolkit for making Fire Emblem Awakening (FE13) mods. Free software under the GNU GPL v3; based on
Paragon (copyright thane98, GPL-3.0). Source: https://github.com/Lilloader/paragon-unlimited

Thanks to Albinopelican and lilloader.

## What's new in v2.2 – Join your army, Share My Mod
- **Map Maker -> ★ Joins your army**: pick any character in "Who joins" and click a tile. They appear
  there on turn 1 and join your army, the way Donnel joins in Paralogue 1 (a "Join" group placed by the
  chapter script). For chapters made with the Map Maker.
- **Unlimited -> Share My Mod...**: one zip with only the files your mod changes, in Azahar's folder
  layout, plus HOW_TO_INSTALL.txt; optional game code patch (code.ips) and DLC maps; Check My Mod runs first.
- Acknowledgments: thanks to Albinopelican and lilloader; license and source link.

## What's new in v2.1 – Sprite Workshop eraser
- **Eraser** in step 2 (Adjust): a 1, 2 or 3 px clean-up eraser for leftovers of the old head or body.
  Left-drag erases, right-drag puts pixels back, in all three team colors at once. Erasing only touches
  the body layer; heads are drawn on top afterwards, so the new head is never erased and the old head
  can stay as a guide until the new one is lined up. Undo erase / Restore all erased. Erased pixels are
  saved in the .pusprite project. Heads and bodies are not changed in any other way.

## What's new in v2.0 – Map Maker, chapter slots and tutorials
- **Map Maker** (big green button on the main window, or Unlimited -> Map Maker): make brand-new
  chapters and edit the units of any chapter by clicking and dragging on the map.
- **9 chapter slots in every project**: the save file keeps 64 chapters and the game uses 55, so every
  mod can add 9 (U001-U009). "Fill every empty slot" makes them all at once, ready to play, from easy
  to brutal; each gets a map, enemies and a boss, a short story, a title card and a spot and road on
  the world map. They are ordinary project files, so they travel with the mod when it is shared.
- **76 map templates**: every Awakening story map and paralogue, plus the 25 DLC maps once imported.
  Each comes with player starts and generic enemies (six armies, six difficulty levels: basic or
  promoted classes, levels, weapons). Fates maps can't be used: Awakening can't draw their 3D models.
- Map editing: Move / + Enemy / + Boss / + Player start / Remove, right-click to remove, red tiles show
  where a unit can't stand (fliers may cross water and peaks), unit box for class, level, boss and
  behavior (charge / wait / stay), difficulty slider that changes every enemy at once, undo / redo,
  Save + copy to Azahar. Game chapters keep everything the editor does not show (reinforcements,
  events, difficulty-only units).
- **Story without commands**: lines of "who / mood / text"; text boxes and portraits are handled for you.
- **Help is now a course**: Help -> Tutorials (Start Here), nine short lessons from the first save to
  sharing a mod, with Next lesson links; a Map Maker reference page.
- Fix: saving OtherData no longer adds a second copy of the GMap / Renown labels on every save.

## What's new in v1.14 – Sprite Workshop rebuilt
- **Heads and bodies are separate**, like Fates: pick a character's head and any class body
  (e.g. Chrom + Wyvern Rider) and Build sprite. The parts come from the game's own map sprites:
  for each class the generic sprite and its character versions show where the head is in every
  frame (Data/FE13/PU_SpriteParts.json, made by scripts/pu_build_sprite_parts.py). The head is
  lined up with the body frame by frame; enemy / ally colors are the game's own.
- **The big preview is the drop area** and starts empty. A dropped sheet is split into body and
  head using the class body it is drawn on (found by its outline).
- **Drag any head** in the preview to move it in that frame; right-click to reset it.
- **See-through like the game**: the game's map sprites use 53 % for normal pixels and 27 % for
  outlines (always (34,34,34) or (51,51,68)); opaque images are converted, with a slider.
- Everything is in English (classes, characters, color reference) - display only.
- US spelling everywhere ("color").

## What's new in v1.13 – head position per frame
- **Sprite Workshop -> Head position per frame**: move the head in any single frame, on top of the
  overall Move head X/Y. The body is never moved or redrawn, so the class animation stays exactly the
  game's; only the head follows it.
- Pick the frame by clicking it on the whole sheet (yellow box), or pick an animation and step
  through it with < Frame / Frame > (Pause / Play). "Use for the whole animation" copies the frame's
  position to every frame of that animation; "Reset this frame" / "Reset all frames".
- A head stays inside its own frame: pixels pushed past the frame edge are cut off (Validate warns)
  instead of showing up in the next frame. Validate also checks that, outside the head, the player
  sheet is the body pixel for pixel. Positions are saved in the .pusprite project.

## What's new in v1.12 – Sprite Workshop
- **Core Data -> Sprite Workshop**: build a map sprite from a body (a game sprite or a dropped sheet,
  PNG or .ctpk.lz) and a head layer (a dropped sheet, or a head taken from a game sprite), preview it
  as player (blue 青), enemy (red 赤) and ally (green 緑) - whole sheet or animated - and export all
  three in the game's own format (CTPK, RGBA4, the reference sprite's size and header).
- Colors follow the game: the game stores the three colors as separate full-color sheets (no
  palette). Measured on all 693 blue/red/green sets: only team-colored pixels change. The Workshop
  uses the reference sprite's own red/green pixels and color mapping, then the mapping measured on
  all game sprites (Data/FE13/PU_FactionColors.json); skin, hair and outlines stay. Head pixels taken
  from a game sprite use that sprite's own colors. Tested on game sprites rebuilt from class body +
  character head: the rebuilt blue sheet is identical to the game's, red/green 77-100 % identical.
- "Team color in this sheet: Red" for sheets drawn with red capes / trim: the sheet becomes the enemy
  version and the player version gets those parts in blue (the game's pairs used backwards).
- Export adds a BMap icon entry (animation copied from the reference) and sets characters' sprites per
  class; Validate checks all three files (exact names), the entry and the output. Projects save as
  .pusprite (relative paths + checksums of the source images, which are never changed).

## What's new in v1.11 – exact file names
- The game finds files by their exact name, letter case included ("Edelgard_fc_通常.arc" is not
  "edelgard_fc_通常.arc"). Windows ignores case, so such mismatches work in Paragon and fail in game
  (crash or invisible unit).
- **Copy to Azahar** now renames files in the mod folder whose name differs from the project's only
  in letter case (Windows keeps the old name when a file is copied over it).
- **Check My Mod** reports references whose file differs only in case (FaceData portrait files, map
  sprites), custom map sprites missing their 青 / 赤 / 緑 (player / enemy / ally) file, and sprite
  names with no file (with the closest file name). **Fix name case** renames the project files.

## What's new in v1.10 – room for 4096 support conversations
- The Paragon Unlimited code.ips **exp05** (exp04 + one change at 0x108B30) creates the Support Log
  "seen" array with 4096 bits instead of 1920, so support numbers 0-4095 are safe. The game saves
  the array with its size and loads a different size by copying what fits, so existing save files
  keep working (and keep working if the patch is removed again).
- The support check reads the code.ips in the emulator's mod folder: with exp05 the limit is 4096,
  without it 1920 (numbers above are errors). New conversations get numbers below the active limit.

## What's new in v1.9 – support repairs
- **Support number limit found**: the game keeps a "seen" flag per support conversation number in a
  1920-bit array (numbers 0-1919; created at 0x108AE4, object +0x14, set by 0x2B43C4 with no range
  check). A conversation numbered 1920 or higher writes past it when viewed. The support check now
  reports these as errors, and new conversations get a free number below 1920.
- Fixed automatically on save: the same conversation (same two characters, level and type) stored as
  several records (the lowest number is kept); a conversation also listed in the table of a
  character it does not involve; placeholder slots (one partner repeated in 4+ slots with support
  type None, as left by some older editors).

## What's new in v1.8 – supports
- **Clear** button next to every support slot (#000-#059): empties the partner and support type.
  When the partner lists this character too, choose **Clear both** (removes it from both lists) or
  **Only this slot**.
- Picking a partner for an empty slot sets the support type the game uses for the pair:
  **Non-romantic** for two women or two men, **Slow** for a woman and a man (female flag in
  Bitflags 1). A type you chose yourself is never changed.
- **Check Supports / save report: Assign support partners** - for support conversations that no
  slot reaches ("... exists, but neither character has the other in a support slot"), lists both
  characters in each other's first free slot with that type.
- New supports start with `$SetConversationType(1)`, `$LoadAssets` (first character of the support
  name at 3, second at 7), `$Wait(0)`, `$SetSpeaker` and `$Emotions(Standard)` instead of a
  placeholder line. Enter after `$SetSpeaker(...)` adds `$Emotions` and `$PlayVoice` for the speaker.

## What's new in v1.7 – line breaks
- **Auto line breaks** in the conversation editor (supports, scenes, base talk): when a line gets too
  wide for the game's text box, the word that does not fit moves to a new line (`\n`) as you type.
  Widths are measured in pixels with the game's own font (fonts/System.bfnt), since letters differ in
  width. The limits come from the widest lines in the game's English text: 320 px for supports and
  most scenes (`$SetConversationType(1)`, about 40-48 letters), 285 px for small map boxes (0), 293 px
  for narration (2). The status bar shows the current line's width and turns red when it is over.
- On save / preview the whole text is checked: pasted text is broken the same way, and a box that
  would get a third line continues in a new box (`$Pause` `$Clear`). Typed line breaks are kept; text
  that fits is not changed (none of the game's own English conversations change). `$Nu` counts as 100 px.
- The Quick Dialogue Generator uses the same pixel line breaks for Awakening.

## What's new in v1.6 – skills
- **New skills with real effects**: each skill page has an **Effects (Unlimited)** list. A line is an
  effect (damage dealt / received, hit, avoid, crit, dodge, attack speed), an amount and up to two
  conditions (who started the fight, HP thresholds, even/odd turns, enemy flier or on foot, enemy HP,
  enemy magic or physical). They work in game with the Paragon Unlimited code.ips **exp04** (included
  separately). All lines are also under **Skill Effects (Unlimited)**.
- Up to 128 skills (ids 103-127 are free; the game keeps 128 learned skills per unit).
- **Import icon (PNG)...** on the skill page puts your own 24x24 icon into a free cell of skill.tga
  (systems/icon*.ctpk.lz, every language) and selects it.
- Saving checks the skill count, gives added skills a menu order, drops effect lines with no skill,
  and adds the lines for Hit Rate +10, Sure Strike, Avoid +10 and Gamble the first time (exp04 runs those
  four from their lines).

## What's new in v1.5 – fixes
- **FaceData Reset** now goes back to the game's original position, not just to your last save.
  When the saved pictures are moved copies of the game's own, the game's pictures are put back
  (exact pixels, nothing lost at the edges) and blush/sweat move back too; written when you save.
  This needs the game's original files (the ROM folder of your project); new characters have no
  original, so for them Reset only undoes unsaved moves.
  Pictures you imported yourself are kept (Reset then only undoes unsaved moves).
- **Unsaved changes**: text you are still typing (a field with the cursor in it, an open
  conversation in the dialogue editor) is applied before the check, so closing asks about it.
  The question lists what is unsaved (Show Details), and the decision is written to paragon.log.
- **Unit info view**: the whole small face is shown, dimmed outside the game's box, so a picture
  that is not in the right place can still be seen and dragged. Faces with a 0 x 0 Portrait Menu
  size (the game then shows nothing) get the game's usual 69 x 76 when you drag them.
- **One window**: the exe no longer opens a separate console window. Closing that console used to end
  Paragon at once, without the unsaved-changes question.
- The log of the previous run is kept as paragon.previous.log.

## What's new in v1.4 – help and unsaved changes
- **Help**: press **F1** in any window, or use its **Help** button (editor toolbars, the
  dialogue editor, the FaceData preview), for a short guide to that window: FaceData explains
  dragging, importing and the text box, Characters explains stats, supports and Sprite Data,
  the dialogue editor lists every command and expression with an example support.
  Help -> Help Topics lists all guides; the credits moved to Help -> Acknowledgments.
- **Unsaved changes**: closing Paragon (or File -> Close / Reload) with unsaved changes asks
  Save / Don't Save / Cancel. Unsaved portrait and texture imports count too.

## What's new in v1.3 – mod check, Azahar, new characters, conversation preview
- **Unlimited -> Check My Mod...**: scans the project for problems that only show up in the
  game: dialogue using an expression the speaker's portrait file does not have, speakers or
  FaceData entries without portrait files, $PlayVoice lines with no English recording,
  characters without FaceData, Asset Definitions / Presets pointing at missing models or
  textures. Problems the unmodified game already has are hidden. "Check My Mod Before Saving"
  runs it on every save and asks before saving when it finds errors.
- **Unlimited -> Copy to Azahar**: copies the output folder to
  `load/mods/00040000000A0500/romfs` and the rebuilt DLC maps to
  `load/mods/0004008C000A0500/romfs`. Only changed files are copied; replaced files are
  zipped to `Backups/azahar-before-*.zip`; nothing is deleted. The mod folder is detected
  (or set with "Set Azahar Mod Folder..."). "Copy to Azahar After Saving" does it on every save.
- **Unlimited -> New Character (FE13)...**: one dialog creates the character (copy of a
  template, no supports), both FaceData entries, portrait files with the basic expressions
  and an Asset Definitions entry. Written when you save.
- **Conversation preview** (dialogue / support editor): Play steps through the conversation
  by itself and plays the English $PlayVoice lines; 2x zoom; portraits at the measured
  in-game positions.
- **Hair color** in the 3D preview: gray hair textures are colored with the character's
  FaceData hair color; "Hair color..." tries another color (preview only).
- Fixed: importing into / copying a portrait file that comes straight from the game.

## What's new in v1.2 – full 3D preview and texture import
- Asset Definitions / Presets: the 3D view now shows the whole character (body + head +
  hair placed on the body's skeleton, rest pose), plus separate views of the mount and the
  weapon. Names with % (hair variants chosen by the game) show the first variant.
- Click a texture thumbnail (or drop an image on it) to Import image..., Export PNG... or
  Undo import. The image is resized to the texture's size and re-encoded in its own format
  (ETC1 / ETC1A4 / RGB565 / RGBA8) with all mipmap levels; the 3D view updates at once and
  b/<texture>.t.lz is written when you save (the old file goes to Backups/). Textures in
  ETC1 / RGB565 have no transparency.
- A texture the reader cannot decode (seen on one weapon, wep_sw25) is shown untextured
  instead of stopping Paragon.

## v1.1 – 3D model preview (head)
- Asset Definitions / Presets: a 3D view of the entry's head model with its texture (the
  entry's own color variant when it sets one). Drag to turn it, mouse wheel to zoom,
  double-click to reset. Drawn by a small built-in renderer (no graphics card features
  needed); plain lighting, no in-game outlines or hair color. Read-only.
- Coming next: body, hair and mount put together on the skeleton.

## What's new in v1.0
- **Voices** (Characters -> "Voices (Unlimited)" tab): every English voice line of the character
  (from sound/14Iron_sound_US_EN.bcsar; Japanese lines are not listed). Double-click or Play to
  hear it, "Copy $PlayVoice(...)" to paste it into a script. The character's voice set comes from
  the Asset Definitions entry named after its PID (e.g. PID_クロム -> CHROM). "All characters"
  lists all 4342 lines.
- **$PlayVoice autofill**: in the dialogue / support editor, typing `$PlayVoice(` suggests the
  voice lines of the speaker set by the last `$SetSpeaker(...)` (all lines if none is found).
- **Asset Definitions / Presets preview**: each entry shows an English reading of its Japanese
  name, its voice/weapon/condition and the battle-model textures it uses (body, head, hair, mount),
  decoded from your game files. These are texture sheets (the model's "skin"), not a rendered
  3D model.
- **FaceData images**: drop PNG files on the Game preview (or use Import image...) to replace
  an expression, the blush or the sweat. Images of another size are scaled to fit (kept centered,
  bottom-aligned). Several files at once are matched by name (笑.png, smile.png, Chrom_angry.png).
  Export PNG... saves the current texture.
- **Expressions**: Add expression... (pick a known one such as 悲しみ / 照れ, or type any name, e.g.
  "apron"; start from an image, a copy or blank) and Remove expression (通常 cannot be removed).
- **New portrait file...**: makes a .arc for a new character with the basic expressions
  通常, 笑, 怒, 苦, キメ plus blush, sweat and hair masks, and points the FaceData entry to it.
- Everything is built into the .arc when you save (the previous file goes to Backups/).
  Supported texture formats: ETC1A4 (game default), ETC1 and RGBA8.
- **Resizable editors**: the FaceData editor is split into the preview and the fields; drag the
  divider. Zoom "Fit" scales the preview to the window. Every editor window remembers its size
  and position (saved in paragon.json when Paragon closes).

## v0.8 – DLC maps
- File -> Import DLC: the DLC episodes (E001-E027) appear in Chapters and are edited like base
  chapters (no shops / merchant). Save rebuilds the changed Exxx_MAP.arc files in
  `<output>_DLC/romfs/`; copy them to `Azahar/load/mods/0004008C000A0500/romfs/`.

## What's new in v0.7 – icons and UI colors
- Main window buttons have icons. Game-themed ones (Characters = Chrom's face, Items =
  Falchion, Classes = Master Seal, Skills = Aether, Armies = army emblem, Portraits = Lissa,
  Configure Avatar = your avatar) are read from your own game files when the project loads;
  the rest are simple drawn icons.
- Assets -> **UI**: pick colors for background, boxes/input fields, buttons, text and accent,
  or choose a preset (Classic, Midnight, Plum & Gold, Forest, Ember, Slate, Ocean). Changes
  apply immediately and are remembered. Cosmetic only - game files are never touched.
  (Applies with Options -> Theme -> Fusion Dark, the default.)

## What's new in v0.6 – blush and sweat
- Game preview has separate **Blush** and **Sweat** checkboxes.
- Drag the blush or sweat overlay to place it; this sets Blush/Sweat Position in FaceData.
  (Dragging the portrait itself still moves them along with the artwork.)

## What's new in v0.5 – Support / Reliance List
- **Add** in a character's support list now creates the entry straight away (no "New"
  click): Character1 = that character, Support Number = highest number in use + 1, level 1.
- On save, every support conversation is listed in **both** characters' lists (as in
  vanilla, where each entry is shared by both). Entries that were only in one list are
  added to the partner's list automatically and reported under "Fixed automatically".
- Class sprite lists are read as long as they really are (84 vanilla / 124 extended), so a
  project with no static.bin in its output folder opens again.

## What's new in v0.4 – "Add missing partners" button
- When the support check reports "A lists B as a partner, but not the other way round", the
  dialog has an **Add missing partners** button. It puts A into B's first free support slot
  with the same support type (the Unlimited slots #052-#059 are used if #000-#051 are full).
  If B already lists A with support type "None", that slot just gets A's support type.
  After saving, it saves again so the change is written. The same button appears for
  Unlimited -> Run Support Check (there you save yourself).

## What's new in v0.3 – FaceData game preview
- FaceData now opens on a **Game preview** tab that shows the portrait where Awakening draws it.
  The positions were measured from in-game screenshots (1:1 scale):
  - conversation: right speaker at (172, 0) as drawn; left speaker at (-28, 0) mirrored;
  - level up: (0, 0) mirrored;
  - unit info (bottom screen): the FC is mirrored and the corner of its "Portrait Menu"
    crop sits at (1, -3); the frame shows x 5–63, y 5–72.
  The support-conversation screen assumes the conversation positions (not measured yet).
  The game also darkens/tints portraits depending on the scene; the preview does not.
- **Drag a BU or FC** to move the artwork. Awakening has no position setting for portraits, so
  Paragon Unlimited moves the artwork inside every expression texture of the .arc when you
  save (normal and 反 expressions separately). Blush/sweat positions follow the normal set.
  - "4 px steps (lossless)" (default) moves whole texture blocks: the image is unchanged.
  - 1 px steps re-encode the textures (ETC1A4); quality loss is very small but adds up if you
    move the same portrait many times, so prefer 4 px steps when you can.
  - The previous .arc files are zipped into `Backups\portraits-before-<time>.zip`.
- On **Unit info (bottom screen)**, dragging the FC sets Portrait Menu Position instead
  (no texture change). The **FC texture + menu crop box** screen lets you drag the crop box.

## What's new in v0.2 – 60 support slots per character
- The FE13 character editor's **Supports** tab now shows **Support #000 to #059** for every
  character. #000–#051 are the game's built-in slots; **#052–#059** are new.
- The new slots are stored in an optional table labeled `PU_SupportEx2` at the end of
  `data/person/static.bin` (one entry per character that uses them, tied to the character so
  reordering the list is safe). Files without the table load normally.
- **The game only uses #052–#059 with the Paragon Unlimited code.ips (exp03 or later).**
  Without it, those partners are ignored and nothing crashes (the label is not found).
- Empty extra-slot entries are not written; sets whose character was deleted are removed.
- Class sprite lists in `static.bin` are read as 124 entries (like your own Paragon setup), so
  the map sprites of added classes are kept when saving. Stock Paragon data reads 84.
- The support check now counts all 60 slots, checks that extra-slot partners are listed
  on both sides, and lists who uses extra slots.

## v0.1 – "Option A"
1. **Automatic RelianceList repair on save.** Awakening's Extras → Support screen expects one RelianceList
   table for every character placed before `PID_ダミー` in `data/person/static.bin`. Adding characters with
   older Paragon left too few tables, and the game crashed on that screen. On every save,
   Paragon Unlimited now adds the missing tables, each with an empty support list (vanilla does
   the same). It also repairs tables whose list pointer was lost. Nothing else is changed.
2. **Support check report after each save.** It lists:
   - characters that have used all support slots (52 in the unpatched game, 60 with Paragon Unlimited), and those close to it;
   - partners listed on only one side;
   - support conversations that can never trigger, because neither character has the other in a slot;
   - support numbers shared by different conversations (seeing one marks the other as seen);
   - supports that use a character placed after `PID_ダミー` (the game ignores them);
   - duplicate sort ids.
3. Own name, icon (gold ∞ on purple) and window title, plus an **Unlimited → Run Support Check** menu to run the check without saving.

Not changed: data formats, file layout and project format. Projects made with Paragon open as-is.

## Why the unpatched limit is 52 partners
Each character record has exactly 52 partner slots, and each unit keeps a fixed 52-byte array of
support points that the save file trims to 52. Going beyond 52 needs an executable (`code.bin`)
patch: the Paragon Unlimited code.ips moves slots 52–59 to the `PU_SupportEx2` table and keeps
their points in the unit's existing save-file buffer.

## Using it
- Put the folder anywhere and run `ParagonUnlimited.exe`. It keeps its own `paragon.json` next to the exe,
  so your original Paragon's project list is not touched.
- Create or open a project with:
  - ROM path: your extracted RomFS (e.g. `...\paragon\romfs\00040000000A0500`)
  - Output path: a **copy** of your mod output folder while testing
- After saving, read the "Support Check" dialog. Items under **Fixed automatically** have already
  been written to your output.

## Building
See README.md (Poetry + Rust + Python 3.11). The GitHub Actions workflow `.github/workflows/build.yml`
builds the Windows release zip automatically on every push to `main`.
