"""Paragon Unlimited: the Unlimited menu of the main window.

Paragon's MainWindow (paragon/ui/controllers/main_window.py) inherits these methods, so the
menu items (Unlimited -> Check My Mod, Copy to Emulator, Share My Mod, ...) and the
"unsaved changes" question live here instead of inside Paragon's own file.
"""
import logging
import os
import traceback

from PySide6 import QtCore
from PySide6.QtWidgets import QMessageBox

from paragon.model.game import Game
from paragon.ui.controllers.error_dialog import ErrorDialog


class UnlimitedMainWindowActions:
    """Mixed into MainWindow; uses its self.gs (game state), self.ms (main state) and menu actions."""

    def _confirm_unsaved(self, doing="closing") -> bool:
        """True when it is fine to continue (nothing unsaved, saved now, or discarded)."""
        if getattr(self, "_pu_skip_unsaved_check", False):
            return True
        try:
            from paragon.unlimited.saving.change_tracker import commit_open_editors, unsaved_reasons

            commit_open_editors()
            reasons = unsaved_reasons(self.gs)
            logging.info(f"Unsaved-changes check before {doing}: {reasons or 'nothing unsaved'}")
            if not reasons:
                return True
        except Exception:
            logging.exception("Unsaved-changes check failed.")
            reasons = ["(the check failed, see paragon.log)"]
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Paragon Unlimited - Unsaved changes")
        box.setText("You have changes that are not saved.")
        box.setInformativeText(f"Save them before {doing}?")
        box.setDetailedText("Unsaved:\n" + "\n".join(f"- {r}" for r in reasons))
        save = box.addButton("Save", QMessageBox.AcceptRole)
        discard = box.addButton("Don't Save", QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(save)
        box.exec()
        clicked = box.clickedButton()
        if clicked is discard:
            return True
        if clicked is save:
            self._on_save()
            from paragon.unlimited.saving.change_tracker import has_unsaved_changes

            return not has_unsaved_changes(self.gs)
        return False

    def _on_share(self):
        if self.gs.project.game != Game.FE13:
            QMessageBox.information(self, "Paragon Unlimited", "Share My Mod is only available for FE13 (Awakening).")
            return
        from paragon.unlimited.saving.change_tracker import has_unsaved_changes

        if has_unsaved_changes(self.gs):
            r = QMessageBox.question(self, "Share My Mod", "Save your changes first, so they are in the zip?",
                                     QMessageBox.Save | QMessageBox.Ignore | QMessageBox.Cancel)
            if r == QMessageBox.Cancel:
                return
            if r == QMessageBox.Save:
                self._on_save()
        from paragon.unlimited.tools.share_dialog import ShareDialog

        self.share_dialog = ShareDialog(self.gs, self._azahar_root(ask=False), self)
        self.share_dialog.show()

    def _on_code_patch(self):
        from paragon.unlimited.tools import code_patch

        if self.gs.project.game != Game.FE13:
            QMessageBox.information(self, "Paragon Unlimited", "The game code patch is only for FE13 (Awakening).")
            return
        root = self._azahar_root(ask=True)
        if not root:
            return
        try:
            text, can_install, can_remove = code_patch.describe(root)
        except Exception:
            logging.exception("Code patch: could not read the mod folder.")
            self.error_dialog = ErrorDialog(traceback.format_exc())
            self.error_dialog.show()
            return
        box = QMessageBox(self)
        box.setWindowTitle("Paragon Unlimited - Game Code Patch")
        box.setText(text)
        install = box.addButton("Update" if can_remove else "Install", QMessageBox.AcceptRole) if can_install else None
        remove = box.addButton("Remove", QMessageBox.DestructiveRole) if can_remove else None
        box.addButton(QMessageBox.Cancel)
        box.exec()
        clicked = box.clickedButton()
        try:
            if install is not None and clicked is install:
                res = code_patch.install(root)
                msg = f"Installed:\n{res['path']}"
            elif remove is not None and clicked is remove:
                res = code_patch.uninstall(root)
                msg = f"Removed the Paragon Unlimited patch from:\n{res['path']}"
                if not res["kept"]:
                    msg += "\n(nothing else was in it, so the file was deleted)"
            else:
                return
        except Exception:
            logging.exception("Code patch: install/remove failed.")
            self.error_dialog = ErrorDialog(traceback.format_exc())
            self.error_dialog.show()
            return
        if res.get("backup"):
            msg += f"\n\nYour previous code.ips is kept as:\n{os.path.basename(res['backup'])}"
        if res.get("kept"):
            msg += f"\n\n{res['kept']} change(s) from other patches were kept."
        msg += "\n\nRestart the game in Azahar to use it."
        QMessageBox.information(self, "Paragon Unlimited - Game Code Patch", msg)

    def _on_map_maker(self):
        if self.gs.project.game != Game.FE13 or not hasattr(self.main_widget, "_on_map_maker"):
            QMessageBox.information(self, "Paragon Unlimited", "The Map Maker is only available for FE13 (Awakening).")
            return
        self.main_widget._on_map_maker()

    def _on_mod_check(self):
        if self.gs.project.game != Game.FE13:
            QMessageBox.information(self, "Paragon Unlimited", "Check My Mod is only available for FE13 (Awakening).")
            return
        from paragon.unlimited.tools.mod_check_dialog import ModCheckDialog

        self.mod_check_dialog = ModCheckDialog(self.gs, self)
        self.mod_check_dialog.show()
        self.mod_check_dialog.run()

    def _check_before_save(self) -> bool:
        """Run the mod check; returns False when the user cancels the save."""
        from paragon.unlimited.tools.mod_check_dialog import ModCheckDialog

        dialog = ModCheckDialog(self.gs, self)
        dialog.run()
        errors = dialog.errors()
        if not errors:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("Paragon Unlimited - Check My Mod")
        box.setIcon(QMessageBox.Warning)
        box.setText(f"The check found {len(errors)} error(s) that can crash the game or show nothing.")
        box.setInformativeText("\n".join(f"- {e.where}: {e.message}" for e in errors[:6]))
        save = box.addButton("Save anyway", QMessageBox.AcceptRole)
        show = box.addButton("Show problems", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        if box.clickedButton() is save:
            return True
        if box.clickedButton() is show:
            self.mod_check_dialog = dialog
            dialog.show()
        return False

    def _azahar_root(self, ask=True):
        from paragon.unlimited.tools import azahar

        root = getattr(self.ms.config, "pu_azahar_mods", None)
        if root:
            return root
        root = azahar.detect_mod_root()
        if root and ask:
            answer = QMessageBox.question(
                self,
                "Paragon Unlimited - Azahar",
                f"Use this Azahar mod folder?\n\n{root}\n\n(You can change it with Unlimited -> Set Your Mod Folder.)",
            )
            if answer == QMessageBox.Yes:
                self.ms.config.pu_azahar_mods = root
                return root
        if ask:
            return self._on_azahar_folder()
        return None

    def _on_azahar_folder(self):
        from PySide6.QtWidgets import QFileDialog
        from paragon.unlimited.tools import azahar

        start = getattr(self.ms.config, "pu_azahar_mods", None) or azahar.detect_mod_root() or ""
        folder = QFileDialog.getExistingDirectory(
            self, "Azahar mod folder (Azahar -> File -> Open Mods Location, the 'mods' folder)", start
        )
        if not folder:
            return None
        root = azahar.normalize_mod_root(folder)
        self.ms.config.pu_azahar_mods = root
        self.statusBar().showMessage(f"Azahar mod folder: {root}", 8000)
        return root

    def _on_copy_azahar(self, after_save=False):
        from paragon.unlimited.tools import azahar

        root = self._azahar_root(ask=True)
        if not root:
            return
        dlc = None
        if self.gs.project.game == Game.FE13:
            from paragon.unlimited.map_maker import dlc_maps

            ws = dlc_maps.workspace(self.gs.project.output_path) / "romfs"
            dlc = str(ws) if ws.is_dir() else None
        try:
            res = azahar.copy_to_mods(self.gs.project.output_path, root, dlc)
        except Exception:
            logging.exception("Copy to Emulator failed.")
            self.error_dialog = ErrorDialog(traceback.format_exc())
            self.error_dialog.show()
            return
        if after_save and not res.copied:
            self.statusBar().showMessage("Azahar is up to date.", 5000)
            return
        QMessageBox.information(self, "Paragon Unlimited - Copied to Emulator", res.summary())

    def _on_new_character(self):
        if self.gs.project.game != Game.FE13:
            QMessageBox.information(self, "Paragon Unlimited", "The New Character helper is only available for FE13 (Awakening).")
            return
        from paragon.unlimited.characters.new_character_dialog import NewCharacterDialog

        dialog = NewCharacterDialog(self.gs, self)
        if dialog.exec() and dialog.result_info is not None:
            QMessageBox.information(
                self,
                "Paragon Unlimited - New Character",
                "Created:\n\n" + "\n".join("- " + n for n in dialog.result_info.notes)
                + "\n\nSave the project to write it. Drop your portrait images on the FaceData Game preview.",
            )

    def _on_import_dlc(self):
        if self.gs.project.game != Game.FE13:
            QMessageBox.information(self, "Paragon Unlimited", "DLC maps are only supported for FE13 (Awakening).")
            return
        from PySide6.QtWidgets import QFileDialog
        from paragon.unlimited.map_maker import dlc_maps

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select the decrypted Awakening DLC (.cia), or cancel to pick a folder of Exxx_MAP.arc files",
            "",
            "DLC (*.cia);;All files (*)",
        )
        try:
            if path:
                self.statusBar().showMessage("Reading DLC... this can take a moment.")
                QtCore.QCoreApplication.processEvents()
                eps = dlc_maps.import_arcs(self.gs.project.output_path, dlc_maps.arcs_from_cia(path))
            else:
                folder = QFileDialog.getExistingDirectory(self, "Folder with Exxx_MAP.arc files")
                if not folder:
                    return
                eps = dlc_maps.import_from_folder(self.gs.project.output_path, folder)
            if not eps:
                QMessageBox.warning(self, "Paragon Unlimited", "No DLC maps (Exxx_MAP.arc) were found.")
                return
            QMessageBox.information(
                self,
                "Paragon Unlimited - DLC maps",
                f"Imported {len(eps)} DLC maps ({', '.join(eps)}).\n\n"
                f"Files are in {dlc_maps.workspace(self.gs.project.output_path)}.\n"
                "Reloading the project now; they appear at the end of the Chapters list.",
            )
            self._on_reload()
        except Exception:
            logging.exception("DLC import failed.")
            self.error_dialog = ErrorDialog(traceback.format_exc())
            self.error_dialog.show()

    def _show_support_report(self, report, text, save_after_fix):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning if report.needs_attention() else QMessageBox.Information)
        box.setWindowTitle("Paragon Unlimited - Support Check")
        box.setText(text)
        fix_button = None
        pairs = {(a, b) for a, b, _t in getattr(report, "one_sided", [])}
        if pairs:
            fix_button = box.addButton(
                f"Add missing partners ({len(pairs)})", QMessageBox.ActionRole
            )
            fix_button.setToolTip(
                "For each 'A lists B but not the other way round', put A into B's first free "
                "support slot with the same support type. Uses the Unlimited slots #052-#059 "
                "when #000-#051 are full."
            )
        assign_button = None
        unassigned = list(getattr(report, "unassigned", []))
        if unassigned:
            assign_button = box.addButton(
                f"Assign support partners ({len(unassigned)})", QMessageBox.ActionRole
            )
            assign_button.setToolTip(
                "For each support conversation that no support slot reaches, list the two characters\n"
                "in each other's first free slot. Support type: Non-romantic for two women or two men,\n"
                "Slow for a woman and a man (as in the game). Uses the Unlimited slots #052-#059 when\n"
                "#000-#051 are full."
            )
        box.addButton(QMessageBox.Ok)
        box.exec()
        if assign_button is not None and box.clickedButton() is assign_button:
            self._assign_support_partners(unassigned, save_after_fix)
            return
        if fix_button is None or box.clickedButton() is not fix_button:
            return
        try:
            from paragon.unlimited.saving.save_checks import add_missing_partners

            added, failed = add_missing_partners(self.gs.data, report.one_sided)
            d = self.gs.data.display
            lines = [f"Added {len(added)} partner(s)."]
            ext = [x for x in added if x[2] >= 52]
            if ext:
                lines.append(
                    f"{len(ext)} went into the Unlimited slots #052-#059 (needs the Paragon Unlimited code.ips)."
                )
            for a, b, k in added[:15]:
                lines.append(f" - {d(b)}: slot #{k:03} = {d(a)}")
            if len(added) > 15:
                lines.append(f" ... and {len(added) - 15} more")
            if failed:
                lines.append("")
                lines.append(f"No free slot left for {len(failed)}:")
                for a, b in failed[:10]:
                    lines.append(f" - {d(b)} (to add {d(a)})")
            if save_after_fix and added:
                lines.append("")
                lines.append("Saving again now.")
            QMessageBox.information(self, "Paragon Unlimited - Missing partners", "\n".join(lines))
            if save_after_fix and added:
                self._on_save()
        except:
            logging.exception("Adding missing partners failed.")
            self.error_dialog = ErrorDialog(traceback.format_exc())
            self.error_dialog.show()

    def _assign_support_partners(self, pairs, save_after_fix):
        try:
            from paragon.unlimited.supports import support_tools as st

            assigned, full = st.assign_pairs(self.gs.data, pairs)
            d = self.gs.data.display
            lines = [f"Assigned {len(assigned)} support pair(s)."]
            ext = [x for x in assigned if (x[3] or 0) >= 52 or (x[4] or 0) >= 52]
            if ext:
                lines.append(
                    f"{len(ext)} use the Unlimited slots #052-#059 (needs the Paragon Unlimited code.ips)."
                )
            for a, b, t, ka, kb in assigned[:20]:
                where = ", ".join(
                    f"{d(c)} #{k:03}" for c, k in ((a, ka), (b, kb)) if k is not None
                )
                lines.append(f" - {d(a)} x {d(b)}: {st.type_name(t)} ({where})")
            if len(assigned) > 20:
                lines.append(f" ... and {len(assigned) - 20} more")
            if full:
                lines.append("")
                lines.append(f"No free slot left ({len(full)}):")
                for a, b, c in full[:10]:
                    lines.append(f" - {d(c)} (for {d(a)} x {d(b)})")
                lines.append("Clear a slot of that character, then run Check Supports again.")
            if save_after_fix and assigned:
                lines.append("")
                lines.append("Saving again now.")
            elif assigned:
                lines.append("")
                lines.append("Written on your next save. Open the characters to check the slots.")
            QMessageBox.information(self, "Paragon Unlimited - Assign support partners", "\n".join(lines))
            if save_after_fix and assigned:
                self._on_save()
        except Exception:
            logging.exception("Assigning support partners failed.")
            self.error_dialog = ErrorDialog(traceback.format_exc())
            self.error_dialog.show()

    def _on_support_check(self):
        if self.gs.project.game != Game.FE13:
            QMessageBox.information(
                self, "Paragon Unlimited", "The support check is only available for FE13 (Awakening)."
            )
            return
        try:
            report = self.gs.write_preprocessors.invoke(self.gs.data)
            report_path = os.path.join(os.getcwd(), "support_check.txt")
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report.to_text(limit_per_section=100000))
            self._show_support_report(
                report,
                f"(Fixes listed here are applied in memory and written on your next save.)\n"
                f"Full list: {report_path}\n\n" + report.to_text(limit_per_section=8),
                save_after_fix=False,
            )
        except:
            logging.exception("Support check failed.")
            self.error_dialog = ErrorDialog(traceback.format_exc())
            self.error_dialog.show()

    # ------------------------------------------------------------------ setup
    def _connect_unlimited_menu(self):
        self.support_check_action.triggered.connect(self._on_support_check)
        self.import_dlc_action.triggered.connect(self._on_import_dlc)
        self.mod_check_action.triggered.connect(self._on_mod_check)
        self.copy_azahar_action.triggered.connect(lambda: self._on_copy_azahar(after_save=False))
        self.azahar_folder_action.triggered.connect(self._on_azahar_folder)
        self.new_character_action.triggered.connect(self._on_new_character)
        self.map_maker_action.triggered.connect(self._on_map_maker)
        self.share_action.triggered.connect(self._on_share)
        self.code_patch_action.triggered.connect(self._on_code_patch)
        self.copy_after_save_action.setChecked(bool(getattr(self.ms.config, "pu_copy_after_save", False)))
        self.check_before_save_action.setChecked(bool(getattr(self.ms.config, "pu_check_before_save", False)))
        self.copy_after_save_action.toggled.connect(lambda on: setattr(self.ms.config, "pu_copy_after_save", on))
        self.check_before_save_action.toggled.connect(lambda on: setattr(self.ms.config, "pu_check_before_save", on))

    def _setup_help(self):
        try:
            from paragon.unlimited.app import help_window

            self.help = help_window.install(self.gs.project.game, self)
            self.context_help_action.triggered.connect(self.help.show_for_last)
            self.help_topics_action.triggered.connect(self.help.show_topics)
            self.tutorials_action.triggered.connect(lambda: self.help._dialog().show_topic("lesson_start"))
        except Exception:
            logging.exception("Could not set up help.")

    # ------------------------------------------------------------------ saving
    def _before_write(self):
        """Called by Save just before Paragon writes the game data."""
        maker = getattr(self.gs, "pu_chapter_maker", None)
        if maker is not None:
            # world map nodes of new chapters: placed before the data is written (bottom-screen spots)
            maker.edits.apply_world_map()

    def _after_write(self, report):
        """Called by Save after Paragon wrote the game data: writes the files the Unlimited
        editors keep (Map Maker, portraits, textures, sprites, skill icons, DLC maps), then shows
        what was written and the support check, and copies to Azahar if that is switched on."""
        maker = getattr(self.gs, "pu_chapter_maker", None)
        portrait_lines = []
        if maker is not None and maker.edits.files:
            logging.info("Writing Map Maker files.")
            import time as _time

            backup_dir = os.path.join("Backups", "mapmaker-before-" + _time.strftime("%Y_%m_%d_%H_%M_%S"))
            portrait_lines += ["Map Maker:"] + [
                "  " + p for p in maker.edits.flush(self.gs.project.output_path, backup_dir)
            ]
        edits = getattr(self.gs.portraits, "pu_edits", None)
        if edits is not None and edits.has_pending():
            logging.info("Writing portrait moves.")
            portrait_lines += edits.flush(self.gs.project.output_path)
        tex_edits = getattr(self.gs, "pu_texture_edits", None)
        if tex_edits is not None and tex_edits.has_pending():
            logging.info("Writing imported model textures.")
            portrait_lines += ["Model textures:"] + ["  " + p for p in tex_edits.flush(self.gs.project.output_path)]
        sprite_ws = getattr(self.gs, "pu_sprite_workshop", None)
        if sprite_ws is not None and sprite_ws.has_pending():
            logging.info("Writing Sprite Workshop sprites.")
            portrait_lines += ["Map sprites:"] + ["  " + p for p in sprite_ws.flush()]
        icon_edits = getattr(self.gs, "pu_skill_icon_edits", None)
        if icon_edits is not None and icon_edits.has_pending():
            logging.info("Writing skill icons.")
            portrait_lines += ["Skill icons:"] + ["  " + p for p in icon_edits.flush()]
        dlc_written = []
        if self.gs.project.game == Game.FE13:
            from paragon.unlimited.map_maker import dlc_maps

            if dlc_maps.unpacked_layer(self.gs.project.output_path):
                dlc_written = dlc_maps.repack(self.gs.project.output_path)
        logging.info("Save completed.")
        if dlc_written:
            ws = dlc_maps.workspace(self.gs.project.output_path) / "romfs"
            QMessageBox.information(
                self,
                "Paragon Unlimited - DLC maps",
                f"Rebuilt {len(dlc_written)} DLC map file(s) in:\n{ws}\n\n"
                "Copy the files in that folder to\n"
                "Azahar\\load\\mods\\0004008C000A0500\\romfs\\\n"
                "(the DLC's mod folder, not the base game's),\nor use Unlimited -> Copy to Emulator.",
            )
        if portrait_lines:
            QMessageBox.information(
                self,
                "Paragon Unlimited - Images",
                "Saved portrait / texture changes (previous files are in Backups):\n\n"
                + "\n".join(portrait_lines[:30]),
            )
        self.statusBar().showMessage("Save complete.", 5000)
        from paragon.unlimited.saving.change_tracker import mark_saved

        mark_saved(self.gs)
        if getattr(self.ms.config, "pu_copy_after_save", False):
            self._on_copy_azahar(after_save=True)
        if report is not None:
            report_path = os.path.join(os.getcwd(), "support_check.txt")
            try:
                with open(report_path, "w", encoding="utf-8") as f:
                    f.write(report.to_text(limit_per_section=100000))
            except Exception:
                logging.exception("Could not write support_check.txt")
            if report.needs_attention():
                self._show_support_report(
                    report,
                    "Saved. The support check found the following "
                    f"(full list in {report_path}):\n\n" + report.to_text(limit_per_section=8),
                    save_after_fix=True,
                )
