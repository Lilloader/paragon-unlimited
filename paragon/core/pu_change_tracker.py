"""Paragon Unlimited: notice unsaved changes.

Paragon's data object keeps files marked dirty for the whole session, so it cannot tell
whether something changed since the last save. TrackedGameData wraps it and sets
``pu_changed`` whenever an editing call actually changes something (setting a field to the
value it already has does not count). Everything else is passed straight through.
"""

import logging


def _widget_type():
    from PySide6.QtWidgets import QWidget

    return QWidget


# setter -> getter used to skip "changes" to the same value
_COMPARE = {
    "set_string": "string",
    "set_int": "int",
    "set_float": "float",
    "set_bool": "bool",
    "set_rid": "rid",
    "set_bytes": "bytes",
}

_ALWAYS = {
    "copy",
    "set_byte",
    "set_items",
    "set_active_variant",
    "list_insert",
    "list_insert_existing",
    "list_add",
    "list_remove",
    "list_swap",
    "list_regenerate_ids",
    "new_instance",
    "delete_instance",
    "multi_duplicate",
    "write_to_cmp",
    "delete_cmp_file",
    "new_text_data",
    "set_text_archive_title",
    "update_script",
    "new_source_only_script",
    "new_compiled_script",
    "set_forced_dirty",
    "multi_set_dirty",
}


class TrackedGameData:
    def __init__(self, gd):
        object.__setattr__(self, "_gd", gd)
        object.__setattr__(self, "pu_changed", False)

    @property
    def inner(self):
        return self._gd

    def __setattr__(self, name, value):
        if name == "pu_changed":
            object.__setattr__(self, name, value)
        else:
            setattr(self._gd, name, value)

    def __getattr__(self, name):
        attr = getattr(self._gd, name)
        if not callable(attr):
            return attr
        if name in _COMPARE:
            getter = getattr(self._gd, _COMPARE[name])

            def tracked(rid, field_id, value, *rest):
                try:
                    old = getter(rid, field_id)
                    if name == "set_bytes" and old is not None:
                        old = bytes(old)
                        same = value is not None and bytes(value) == old
                    else:
                        same = old == value
                except Exception:
                    same = False
                result = attr(rid, field_id, value, *rest)
                if not same:
                    object.__setattr__(self, "pu_changed", True)
                return result

            return tracked
        if name == "set_message":

            def tracked_message(path, localized, key, value):
                try:
                    same = self._gd.message(path, localized, key) == value
                except Exception:
                    same = False
                result = attr(path, localized, key, value)
                if not same:
                    object.__setattr__(self, "pu_changed", True)
                return result

            return tracked_message
        if name == "set_store_dirty":

            def tracked_dirty(store_id, dirty):
                if dirty:
                    object.__setattr__(self, "pu_changed", True)
                return attr(store_id, dirty)

            return tracked_dirty
        if name in _ALWAYS:

            def tracked_call(*args, **kwargs):
                result = attr(*args, **kwargs)
                object.__setattr__(self, "pu_changed", True)
                return result

            return tracked_call
        # Read-only call: cache it on the wrapper so later lookups are direct.
        object.__setattr__(self, name, attr)
        return attr


def unsaved_reasons(gs) -> list:
    """What is not saved yet, in words (empty list: nothing)."""
    reasons = []
    data = getattr(gs, "data", None)
    if not isinstance(data, TrackedGameData):
        logging.warning(f"Unsaved-changes tracking is not active (data is {type(data).__name__}).")
    if getattr(data, "pu_changed", False):
        reasons.append("edits to the game data (tables, text, FaceData fields...)")
    edits = getattr(getattr(gs, "portraits", None), "pu_edits", None)
    if edits is not None and edits.has_pending():
        reasons.append("portrait moves / imported portrait images")
    tex = getattr(gs, "pu_texture_edits", None)
    if tex is not None and tex.has_pending():
        reasons.append("imported model textures")
    sprites = getattr(gs, "pu_sprite_workshop", None)
    if sprites is not None and sprites.has_pending():
        reasons.append("map sprites exported from the Sprite Workshop")
    icons = getattr(gs, "pu_skill_icon_edits", None)
    if icons is not None and icons.has_pending():
        reasons.append("imported skill icons")
    return reasons


def has_unsaved_changes(gs) -> bool:
    return bool(unsaved_reasons(gs))


def commit_open_editors():
    """Apply what is still being typed: the field with the keyboard focus (line edits apply
    their text when they lose focus) and open conversation editors (they apply their text
    when they lose focus, which does not happen when the program is closed)."""
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        return
    app = QApplication.instance()
    if app is None:
        return
    fw = app.focusWidget()
    if fw is not None:
        try:
            fw.clearFocus()
        except Exception:
            logging.exception("Could not apply the field being edited.")
    for top in app.topLevelWidgets():
        candidates = [top] + list(top.findChildren(_widget_type()))
        for w in candidates:
            save = getattr(w, "_save", None)
            valid = getattr(w, "_has_valid_selection", None)
            if type(w).__name__.endswith("DialogueEditor") and callable(save) and callable(valid):
                try:
                    if valid():
                        save()
                except Exception:
                    logging.exception("Could not apply the conversation being edited.")


def mark_saved(gs):
    data = getattr(gs, "data", None)
    if data is not None and hasattr(data, "pu_changed"):
        data.pu_changed = False
