# How Paragon Unlimited is organized

Paragon Unlimited is Paragon plus a set of features for Fire Emblem Awakening (FE13). Paragon's
own code is left where it was; everything Unlimited adds lives in **`paragon/unlimited/`**, one
folder per feature. Paragon's files were only changed where a feature has to plug in (a menu, a
button, a step when loading or saving); those places are listed at the end.

## Where things are

| Folder | What is in it |
|---|---|
| `paragon/unlimited/app/` | Unlimited menu (`main_window_actions.py`), help window, UI colors, button icons, remembered window sizes, extra buttons of the FE13 main window |
| `paragon/unlimited/map_maker/` | Map Maker window (`map_maker_window.py`, unit page in `map_maker_details.py`), building a chapter (`chapter_builder.py`), its events and win conditions (`chapter_events.py`), the Seize / Survive banner (`mission_banner.py`), scene pictures (`telop_pictures.py`), world map spots (`world_map.py`, `world_spot_picker.py`), DLC maps |
| `paragon/unlimited/sprites/` | Sprite Workshop window, sprite sheets and the autosaved sprite list (`sprite_sheets.py`), heads and bodies (`sprite_parts.py`) |
| `paragon/unlimited/portraits/` | FaceData game preview (`portrait_stage.py`), reading and changing portrait files |
| `paragon/unlimited/models/` | battle model reading and preview, texture import, English names of asset entries |
| `paragon/unlimited/characters/` | New Character, reclass slots 4-5 and the avatar class list (`class_slots.py`), keeping sprite lists in step with the class list (`job_rows.py`) |
| `paragon/unlimited/supports/` | the Supports tab (add / remove / fix a whole support: `support_list.py`), support slots #052-#059, support list repairs, Clear / Assign partners |
| `paragon/unlimited/skills/` | skill effect rules and their editor, skill icon import |
| `paragon/unlimited/dialogue/` | automatic line breaks, voice lines, conversation editor and preview additions |
| `paragon/unlimited/saving/` | checks and repairs on save (`save_checks.py`: supports, skills, class slots, sprite list length, Map Maker win rules), the unsaved-changes check |
| `paragon/unlimited/tools/` | Check My Mod, Copy to Emulator, Share My Mod, installing the game code patch, file-name case |
| `Data/FE13/Help/` | the help pages and tutorials, one text file each (`_HOW_TO_WRITE.txt` explains the format) |
| `Data/FE13/PU_Heads/` | ready-made head sheets for the Sprite Workshop (`heads.json` says where each sheet's heads sit) |
| `Data/FE13/PU_*.json`, `PU_*.yml`, `PU_*.txt` | data made from the unmodified game: map templates, sprite heads and bodies, team colors, portrait positions, problems the game already has (hidden by Check My Mod) |
| `Data/FE13/Types/`, `Data/FE13/UI/` | Paragon's data descriptions, plus the Unlimited tables (`PUSkillFx`, `PUSupportEx`, `PUClassSlots`) and their editor pages; `GameData.yml`, `ComboTblEntry.yml`, `FaceData.yml`, `Skill.yml` and `Person.yml` were changed to show them |
| `code_patch/` | source of the game code patch, with a README listing every change it makes |
| `scripts/build_map_templates.py`, `scripts/build_sprite_parts.py` | developer tools that made the `PU_*` data from the game files |
| `tests/` | one test file per feature (named after it); the GitHub workflow runs them on every push |

Every file starts with a short description of what it does.

## How a feature is connected

**Windows and menus.** The Unlimited menu items are methods of
`paragon/unlimited/app/main_window_actions.py`; Paragon's `MainWindow` inherits them. The FE13
main window's extra buttons (Map Maker, Sprite Workshop, UI colors) work the same way
(`app/fe13_main_widget_features.py`), and so do the conversation editor and preview additions
(`dialogue/dialogue_editor_features.py`, `dialogue/dialogue_player_features.py`).

**Editor pages.** Paragon builds its editor pages from the YAML files in `Data/FE13/UI/`. Unlimited
adds a few widget types there (for example `fe13_portrait_stage`, `fe13_skill_fx_widget`); Paragon's
`paragon/model/auto_ui.py` and `paragon/ui/auto_widget_generator.py` map those names to the classes
in `paragon/unlimited/`.

**Loading.** `paragon/core/workers/load_project_worker.py` adds the DLC map folder (when DLC maps
were imported) and wraps the game data so unsaved changes can be noticed.

**Saving.** `MainWindow._on_save` runs, in order:
1. the save checks (`saving/save_checks.py`): repairs support data, checks support numbers and skills,
   makes every sprite list as long as the class list, corrects older Map Maker win rules;
2. `_before_write`: places world map spots of new chapters (and takes deleted chapters off the map);
3. Paragon writes the game data;
4. `_after_write`: writes the files the Unlimited editors keep until saving (Map Maker files,
   portraits, textures, sprites, skill icons, rebuilt DLC maps), shows what was written, and copies
   to the emulator if that is switched on. Replaced files are kept in `Backups/`.

**The game code patch** (`code_patch/`, installed by `tools/code_patch.py`) is optional. The data
Paragon writes for the features that need it (support slots #052-#059, skill effects, support
numbers 1920+, reclass slots 4-5, the avatar class list, the Seize / Survive banner) is ignored by
the game without it.

## Paragon files that were changed

| File | Why |
|---|---|
| `paragon/ui/controllers/main_window.py` | inherits the Unlimited menu; asks before closing with unsaved changes; save steps above |
| `paragon/ui/views/ui_main_window.py` | the Unlimited and Help menus |
| `paragon/ui/controllers/fe13_main_widget.py`, `ui/views/ui_fe13_main_widget.py` | Map Maker, Sprite Workshop and UI colors buttons, icons |
| `paragon/ui/controllers/dialogue_editor.py`, `ui/views/ui_dialogue_editor.py` | line breaks, speaker lines, voice line suggestions |
| `paragon/ui/controllers/dialogue_player.py`, `ui/views/ui_dialogue_player.py` | Play and 2x in the preview |
| `paragon/core/dialogue/commands.py`, `model/dialogue_*.py`, `ui/renderers/awakening_standard_dialogue_renderer.py` | the preview remembers which voice lines to play |
| `paragon/ui/controllers/chapter_editor.py`, `core/services/fe13_chapters.py` | DLC maps in the chapter list |
| `paragon/core/services/fe13_portraits.py` | shows imported portrait pictures before they are saved |
| `paragon/core/workers/load_project_worker.py` | DLC map folder, unsaved-changes tracking |
| `paragon/model/auto_ui.py`, `ui/auto_widget_generator.py` | the Unlimited widget types |
| `Data/FE13/UI/Modules/Person.yml` | the Supports tab; the 60 slots moved to *Support Slots (advanced)* |
| `paragon/core/display.py` | names in lists (extra supports, skill effects, English names of presets) |
| `paragon/ui/controllers/auto/list_widget.py`, `auto/awakening_support_dialogue_button.py` | new support entries get their characters and number right away |
| `paragon/ui/controllers/quick_dialogue_generator.py` | Awakening line breaks by pixel width |
| `paragon/model/configuration.py` | settings: UI colors, window sizes, Azahar folder, Copy/Check on save |
| `paragon/ui/main.py`, `ui/states/init_state.py`, `ui/views/ui_project_select.py` | crash log, colors at start-up, window title |
| `paragon/model/list_field_model.py` | moving, adding or removing a class also does it to every sprite list (asks once before a move); drag and drop below the last row |
