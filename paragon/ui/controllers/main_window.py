import logging
import os
import traceback

from PySide6 import QtCore
from PySide6.QtCore import QSortFilterProxyModel
from PySide6.QtGui import QIcon, QActionGroup, QAction
from PySide6.QtWidgets import QInputDialog, QFontDialog, QMessageBox
from paragon.ui import utils

from paragon.core import backup
from paragon.model.game import Game
from paragon.model.multi_model import MultiModel
from paragon.model.node_model import NodeModel
from paragon.ui.auto_widget_generator import AutoWidgetGenerator
from paragon.ui.controllers.about import About
from paragon.ui.controllers.error_dialog import ErrorDialog
from paragon.ui.controllers.fe10_main_widget import FE10MainWidget
from paragon.ui.controllers.fe13_main_widget import FE13MainWidget
from paragon.ui.controllers.fe14_main_widget import FE14MainWidget
from paragon.ui.controllers.fe15_main_widget import FE15MainWidget
from paragon.ui.controllers.fe9_main_widget import FE9MainWidget
from paragon.ui.views.ui_main_window import Ui_MainWindow


class MainWindow(Ui_MainWindow):
    def __init__(self, ms, gs):
        super().__init__()
        self.ms = ms
        self.gs = gs
        self.gen = AutoWidgetGenerator(ms, gs)
        self.about_dialog = About()
        self.error_dialog = None
        self.open_uis = {}

        self.node_model = NodeModel(gs.data)
        self.multi_model = MultiModel(gs.data)
        self.node_proxy_model = QSortFilterProxyModel()
        self.node_proxy_model.setSourceModel(self.node_model)
        self.node_proxy_model.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.multi_proxy_model = QSortFilterProxyModel()
        self.multi_proxy_model.setSourceModel(self.multi_model)
        self.multi_proxy_model.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.nodes_list.setModel(self.node_proxy_model)
        self.multis_list.setModel(self.multi_proxy_model)

        self.nodes_list.activated.connect(self._on_node_activated)
        self.multis_list.activated.connect(self._on_multi_activated)
        self.save_action.triggered.connect(self._on_save)
        self.reload_action.triggered.connect(self._on_reload)
        self.close_action.triggered.connect(self._on_close)
        self.quit_action.triggered.connect(self.close)
        self.about_action.triggered.connect(self._on_about)
        self.support_check_action.triggered.connect(self._on_support_check)
        self.import_dlc_action.triggered.connect(self._on_import_dlc)
        self.show_animations_action.triggered.connect(self._on_show_animations)
        self.nodes_search.textChanged.connect(self._on_node_search)
        self.multis_search.textChanged.connect(self._on_multi_search)

        self.debug_log_level_action.triggered.connect(
            lambda: self._on_log_level_changed(logging.DEBUG)
        )
        self.info_log_level_action.triggered.connect(
            lambda: self._on_log_level_changed(logging.INFO)
        )
        self.warning_log_level_action.triggered.connect(
            lambda: self._on_log_level_changed(logging.WARNING)
        )
        self.error_log_level_action.triggered.connect(
            lambda: self._on_log_level_changed(logging.ERROR)
        )
        self.change_font_action.triggered.connect(self._on_change_font)
        self.mod_check_action.triggered.connect(self._on_mod_check)
        self.copy_azahar_action.triggered.connect(lambda: self._on_copy_azahar(after_save=False))
        self.azahar_folder_action.triggered.connect(self._on_azahar_folder)
        self.new_character_action.triggered.connect(self._on_new_character)
        self.map_maker_action.triggered.connect(self._on_map_maker)
        self.share_action.triggered.connect(self._on_share)
        self.copy_after_save_action.setChecked(bool(getattr(self.ms.config, "pu_copy_after_save", False)))
        self.check_before_save_action.setChecked(bool(getattr(self.ms.config, "pu_check_before_save", False)))
        self.copy_after_save_action.toggled.connect(lambda on: setattr(self.ms.config, "pu_copy_after_save", on))
        self.check_before_save_action.toggled.connect(lambda on: setattr(self.ms.config, "pu_check_before_save", on))

        self._add_main_widget()

        self._setup_config()
        try:
            from paragon.ui import pu_help

            self.help = pu_help.install(self.gs.project.game, self)
            self.context_help_action.triggered.connect(self.help.show_for_last)
            self.help_topics_action.triggered.connect(self.help.show_topics)
            self.tutorials_action.triggered.connect(lambda: self.help._dialog().show_topic("lesson_start"))
        except Exception:
            logging.exception("Could not set up help.")

    def closeEvent(self, event) -> None:
        # Paragon Unlimited: ask before throwing away unsaved changes.
        if not self._confirm_unsaved("closing"):
            event.ignore()
            return
        self.open_uis.clear()
        if hasattr(self, "main_widget"):
            self.main_widget.on_close()
        super().closeEvent(event)

    def _setup_config(self):
        from paragon.ui import pu_window_memory

        pu_window_memory.set_config(self.ms.config)
        if self.ms.config.show_animations:
            self.show_animations_action.setChecked(self.ms.config.show_animations)
            self._on_show_animations(self.ms.config.show_animations)

        self.theme_action_group = QActionGroup(self)
        for theme in self.ms.config.available_themes():
            action = QAction(theme)
            action.setCheckable(True)
            if theme == self.ms.config.theme:
                action.setChecked(True)
            self.theme_action_group.addAction(action)
            self.theme_menu.addAction(action)
            action.triggered.connect(lambda b=True, t=theme: self._on_theme_changed(t))

        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
            self.debug_log_level_action.setChecked(True)
        elif logging.getLogger().getEffectiveLevel() == logging.INFO:
            self.info_log_level_action.setChecked(True)
        elif logging.getLogger().getEffectiveLevel() == logging.WARNING:
            self.warning_log_level_action.setChecked(True)
        elif logging.getLogger().getEffectiveLevel() == logging.ERROR:
            self.error_log_level_action.setChecked(True)

    def _on_log_level_changed(self, new_log_level):
        logging.getLogger().setLevel(new_log_level)
        self.ms.config.log_level = new_log_level

    def _on_theme_changed(self, new_theme):
        self.ms.config.theme = new_theme
        utils.info(
            "Theme set. Please restart Paragon to use the new theme.", "Theme Updated"
        )

    def _on_node_search(self):
        self.node_proxy_model.setFilterRegularExpression(self.nodes_search.text())

    def _on_multi_search(self):
        self.multi_proxy_model.setFilterRegularExpression(self.multis_search.text())

    def _add_main_widget(self):
        g = self.gs.project.game
        if g == Game.FE15:
            self.main_widget = FE15MainWidget(self.ms, self.gs, self)
            self.splitter.addWidget(self.main_widget)
            self.splitter.setStretchFactor(1, 1)
        elif g == Game.FE14:
            self.main_widget = FE14MainWidget(self.ms, self.gs, self)
            self.splitter.addWidget(self.main_widget)
            self.splitter.setStretchFactor(1, 1)
            self.resize(950, 600)
        elif g == Game.FE13:
            self.main_widget = FE13MainWidget(self.ms, self.gs, self)
            self.splitter.addWidget(self.main_widget)
            self.splitter.setStretchFactor(1, 1)
        elif g == Game.FE10:
            self.main_widget = FE10MainWidget(self.ms, self.gs, self)
            self.splitter.addWidget(self.main_widget)
            self.splitter.setStretchFactor(1, 1)
        elif g == Game.FE9:
            self.main_widget = FE9MainWidget(self.ms, self.gs, self)
            self.splitter.addWidget(self.main_widget)
            self.splitter.setStretchFactor(1, 1)

    def _on_close(self):
        if not self.close():
            return
        self.ms.sm.transition("SelectProject", main_state=self.ms)

    def _on_reload(self):
        if not self.close():
            return
        self.ms.sm.transition("Load", main_state=self.ms, project=self.gs.project)

    def _confirm_unsaved(self, doing="closing") -> bool:
        """True when it is fine to continue (nothing unsaved, saved now, or discarded)."""
        if getattr(self, "_pu_skip_unsaved_check", False):
            return True
        try:
            from paragon.core.pu_change_tracker import commit_open_editors, unsaved_reasons

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
            from paragon.core.pu_change_tracker import has_unsaved_changes

            return not has_unsaved_changes(self.gs)
        return False

    def _on_save(self):
        if getattr(self.ms.config, "pu_check_before_save", False) and self.gs.project.game == Game.FE13:
            if not self._check_before_save():
                return
        if self.ms.config.backup != "None":
            try:
                backup.backup(
                    self.gs.data,
                    self.gs.project.output_path,
                    self.ms.config.backup == "Smart",
                )
            except:
                logging.exception("Backup failed.")
                self.error_dialog = ErrorDialog(traceback.format_exc())
                self.error_dialog.show()
                return
        try:
            logging.info("Save started.")
            logging.info("Invoking preprocessors before saving.")
            report = self.gs.write_preprocessors.invoke(self.gs.data)
            logging.info("Preprocessing completed. Saving...")
            maker = getattr(self.gs, "pu_chapter_maker", None)
            if maker is not None:
                # world map nodes of new chapters: placed before the data is written (bottom-screen spots)
                maker.edits.apply_world_map()
            result = self.gs.data.write()
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
                from paragon.core.services import fe13_dlc

                if fe13_dlc.unpacked_layer(self.gs.project.output_path):
                    dlc_written = fe13_dlc.repack(self.gs.project.output_path)
            logging.info("Save completed.")
            if dlc_written:
                ws = fe13_dlc.workspace(self.gs.project.output_path) / "romfs"
                QMessageBox.information(
                    self,
                    "Paragon Unlimited - DLC maps",
                    f"Rebuilt {len(dlc_written)} DLC map file(s) in:\n{ws}\n\n"
                    "Copy the files in that folder to\n"
                    "Azahar\\load\\mods\\0004008C000A0500\\romfs\\\n"
                    "(the DLC's mod folder, not the base game's),\nor use Unlimited -> Copy to Azahar.",
                )
            if portrait_lines:
                QMessageBox.information(
                    self,
                    "Paragon Unlimited - Images",
                    "Saved portrait / texture changes (previous files are in Backups):\n\n"
                    + "\n".join(portrait_lines[:30]),
                )
            self.statusBar().showMessage("Save complete.", 5000)
            from paragon.core.pu_change_tracker import mark_saved

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

            if self.main_widget.process_compile_result(result.script_compile_result):
                QMessageBox.critical(
                    self,
                    "Script Compiler Error",
                    "Some scripts failed to compile. See the script editor for details.",
                )
        except:
            logging.exception("Save failed.")
            self.error_dialog = ErrorDialog(traceback.format_exc())
            self.error_dialog.show()

    # ------------------------------------------------------------------ Paragon Unlimited
    def _on_share(self):
        if self.gs.project.game != Game.FE13:
            QMessageBox.information(self, "Paragon Unlimited", "Share My Mod is only available for FE13 (Awakening).")
            return
        from paragon.core.pu_change_tracker import has_unsaved_changes

        if has_unsaved_changes(self.gs):
            r = QMessageBox.question(self, "Share My Mod", "Save your changes first, so they are in the zip?",
                                     QMessageBox.Save | QMessageBox.Ignore | QMessageBox.Cancel)
            if r == QMessageBox.Cancel:
                return
            if r == QMessageBox.Save:
                self._on_save()
        from paragon.ui.controllers.pu_share_dialog import ShareDialog

        self.share_dialog = ShareDialog(self.gs, self._azahar_root(ask=False), self)
        self.share_dialog.show()

    def _on_map_maker(self):
        if self.gs.project.game != Game.FE13 or not hasattr(self.main_widget, "_on_map_maker"):
            QMessageBox.information(self, "Paragon Unlimited", "The Map Maker is only available for FE13 (Awakening).")
            return
        self.main_widget._on_map_maker()

    def _on_mod_check(self):
        if self.gs.project.game != Game.FE13:
            QMessageBox.information(self, "Paragon Unlimited", "Check My Mod is only available for FE13 (Awakening).")
            return
        from paragon.ui.controllers.pu_mod_check_dialog import ModCheckDialog

        self.mod_check_dialog = ModCheckDialog(self.gs, self)
        self.mod_check_dialog.show()
        self.mod_check_dialog.run()

    def _check_before_save(self) -> bool:
        """Run the mod check; returns False when the user cancels the save."""
        from paragon.ui.controllers.pu_mod_check_dialog import ModCheckDialog

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
        from paragon.core.services import pu_azahar

        root = getattr(self.ms.config, "pu_azahar_mods", None)
        if root:
            return root
        root = pu_azahar.detect_mod_root()
        if root and ask:
            answer = QMessageBox.question(
                self,
                "Paragon Unlimited - Azahar",
                f"Use this Azahar mod folder?\n\n{root}\n\n(You can change it with Unlimited -> Set Azahar Mod Folder.)",
            )
            if answer == QMessageBox.Yes:
                self.ms.config.pu_azahar_mods = root
                return root
        if ask:
            return self._on_azahar_folder()
        return None

    def _on_azahar_folder(self):
        from PySide6.QtWidgets import QFileDialog
        from paragon.core.services import pu_azahar

        start = getattr(self.ms.config, "pu_azahar_mods", None) or pu_azahar.detect_mod_root() or ""
        folder = QFileDialog.getExistingDirectory(
            self, "Azahar mod folder (Azahar -> File -> Open Mods Location, the 'mods' folder)", start
        )
        if not folder:
            return None
        root = pu_azahar.normalize_mod_root(folder)
        self.ms.config.pu_azahar_mods = root
        self.statusBar().showMessage(f"Azahar mod folder: {root}", 8000)
        return root

    def _on_copy_azahar(self, after_save=False):
        from paragon.core.services import pu_azahar

        root = self._azahar_root(ask=True)
        if not root:
            return
        dlc = None
        if self.gs.project.game == Game.FE13:
            from paragon.core.services import fe13_dlc

            ws = fe13_dlc.workspace(self.gs.project.output_path) / "romfs"
            dlc = str(ws) if ws.is_dir() else None
        try:
            res = pu_azahar.copy_to_mods(self.gs.project.output_path, root, dlc)
        except Exception:
            logging.exception("Copy to Azahar failed.")
            self.error_dialog = ErrorDialog(traceback.format_exc())
            self.error_dialog.show()
            return
        if after_save and not res.copied:
            self.statusBar().showMessage("Azahar is up to date.", 5000)
            return
        QMessageBox.information(self, "Paragon Unlimited - Copied to Azahar", res.summary())

    def _on_new_character(self):
        if self.gs.project.game != Game.FE13:
            QMessageBox.information(self, "Paragon Unlimited", "The New Character helper is only available for FE13 (Awakening).")
            return
        from paragon.ui.controllers.pu_new_character_dialog import NewCharacterDialog

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
        from paragon.core.services import fe13_dlc

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
                eps = fe13_dlc.import_arcs(self.gs.project.output_path, fe13_dlc.arcs_from_cia(path))
            else:
                folder = QFileDialog.getExistingDirectory(self, "Folder with Exxx_MAP.arc files")
                if not folder:
                    return
                eps = fe13_dlc.import_from_folder(self.gs.project.output_path, folder)
            if not eps:
                QMessageBox.warning(self, "Paragon Unlimited", "No DLC maps (Exxx_MAP.arc) were found.")
                return
            QMessageBox.information(
                self,
                "Paragon Unlimited - DLC maps",
                f"Imported {len(eps)} DLC maps ({', '.join(eps)}).\n\n"
                f"Files are in {fe13_dlc.workspace(self.gs.project.output_path)}.\n"
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
            from paragon.core.services.fe13_write_preprocessors import add_missing_partners

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
            from paragon.core.services import fe13_support_tools as st

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

    def _on_about(self):
        help_manager = getattr(self, "help", None)
        if help_manager is not None:
            help_manager.show_acknowledgments()
        else:
            self.about_dialog.show()

    def _on_show_animations(self, triggered):
        try:
            if triggered:
                self.gs.sprite_animation.start()
            else:
                self.gs.sprite_animation.stop()
        except:
            logging.exception("Failed to start animations.")

    def _on_change_font(self):
        current_font = self.ms.app.font()
        dialog = QFontDialog()
        dialog.setCurrentFont(current_font)
        dialog.exec_()
        self.ms.config.font = dialog.currentFont().toString()
        utils.info(
            "Your changes will be applied after you restart Paragon. "
            "Note that some interfaces may not render as expected with a different font size.",
            "Font Updated",
        )

    def _on_node_activated(self, index):
        node = self.nodes_list.model().data(index, QtCore.Qt.UserRole)
        self.open_node(node)

    def open_node_by_id(self, node_id):
        return self.open_node(self.nodes_list.model().sourceModel().get_by_id(node_id))

    def open_node(self, node):
        try:
            # Check if the UI was generated previously.
            if node in self.open_uis:
                # Use the version we already have.
                self.open_uis[node].show()
                return

            # Not cached. Generate the UI from the typename.
            typename = self.gs.data.type_of(node.rid)
            ui = self.gen.generate_for_type(typename)
            ui.setWindowTitle(f"Paragon Unlimited - {node.name}")
            ui.setWindowIcon(QIcon("paragon.ico"))
            ui.set_target(node.rid)
            from paragon.ui import pu_window_memory

            pu_window_memory.remember_window(ui, getattr(node, "id", None) or node.name)
            from paragon.ui import pu_help

            pu_help.add_help_action(ui, getattr(node, "id", None) or typename, typename)
            self.open_uis[node] = ui
            ui.show()
        except:
            logging.exception(f"Failed to generate ui for node {node.name}.")
            utils.error(self)

    def _on_multi_activated(self, index):
        # Prompt the user to select a file.
        data = self.gs.data
        multi = self.multis_list.model().data(index, QtCore.Qt.UserRole)
        try:
            keys = data.multi_keys(multi.id)
            choice, ok = QInputDialog.getItem(self, "Select File", "File", keys, -1)
            if not ok:
                return

            # Check if the UI was generated previously.
            key = (multi.id, choice)
            if key in self.open_uis:
                self.open_uis[key].show()
                return

            # Not cached. Open the file and generate a UI.
            rid = data.multi_open(multi.id, choice)
            ui = self.gen.generate_for_type(
                data.type_of(rid), multi_wrap_ids=multi.wrap_ids
            )
            ui.setWindowTitle(f"Paragon Unlimited - {multi.name}")
            ui.setWindowIcon(QIcon("paragon.ico"))
            if multi.wrap_ids:
                ui.set_target(rid, multi_id=key[0], multi_key=key[1])
            else:
                ui.set_target(rid)
            from paragon.ui import pu_window_memory

            pu_window_memory.remember_window(ui, "multi:" + str(multi.id))
            from paragon.ui import pu_help

            pu_help.add_help_action(ui, data.type_of(rid))
            self.open_uis[key] = ui
            ui.show()
        except:
            logging.exception(f"Failed to open multi {multi.name}.")
            utils.error(self)
