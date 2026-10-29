import faulthandler
import logging
import sys

from PySide6 import QtGui

from paragon.model.configuration import Configuration
from paragon.ui.states.ui_main_state import UIMainState

# Paragon Unlimited: write native crashes and uncaught errors to files next to the exe.
try:
    _crash_file = open("crash.log", "w", encoding="utf-8")
    faulthandler.enable(file=_crash_file, all_threads=True)
except Exception:
    faulthandler.enable(all_threads=True)

# Keep the log of the previous run (paragon.log is started fresh each time).
try:
    import os as _os

    if _os.path.exists("paragon.log") and _os.path.getsize("paragon.log") > 0:
        _os.replace("paragon.log", "paragon.previous.log")
except Exception:
    pass

_handlers = [logging.FileHandler("paragon.log", "w", "utf-8")]
if sys.stdout is not None:  # v1.5: the exe has no console window, so there may be no stdout
    _handlers.append(logging.StreamHandler(sys.stdout))
logging.basicConfig(handlers=_handlers)
logging.info("Paragon Alpha 2-3-12 / Paragon Unlimited")


def _log_uncaught(exc_type, exc, tb):
    logging.critical("Uncaught error", exc_info=(exc_type, exc, tb))


sys.excepthook = _log_uncaught

try:
    from PySide6.QtWidgets import QApplication
    from paragon.model.main_state import MainState
    from paragon.ui.states.find_project_state import FindProjectState
    from paragon.ui.states.init_state import InitState
    from paragon.ui.states.select_project_state import SelectProjectState
    from paragon.ui.states.load_state import LoadState
    from paragon.ui.states.state_machine import StateMachine
except:
    logging.exception("Failed to import a core module.")
    exit(1)

try:
    QApplication.setHighDpiScaleFactorRoundingPolicy(QtGui.Qt.HighDpiScaleFactorRoundingPolicy.Round)
    app = QApplication(sys.argv)

    config = Configuration.load("paragon.json")

    state_machine = StateMachine()
    state_machine.add_state(InitState())
    state_machine.add_state(FindProjectState())
    state_machine.add_state(SelectProjectState())
    state_machine.add_state(LoadState())
    state_machine.add_state(UIMainState())

    main_state = MainState(app=app, config=config, sm=state_machine)
    main_state.sm.transition("Init", main_state=main_state)

    app.exec()

    main_state.config.save("paragon.json")
except:
    logging.exception("Encountered a fatal error during startup or closing.")
    exit(1)

logging.info("Application exited.")
