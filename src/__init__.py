from typing import Any, List, Tuple

import aqt
import aqt.sound
from aqt import gui_hooks, mw
from aqt.qt import *
from aqt.reviewer import Reviewer
from aqt.utils import showWarning, tooltip
from aqt.webview import WebContent

config = mw.addonManager.getConfig(__name__)
mw.addonManager.setWebExports(__name__, r"web/.*\.js")
base_path = f"/_addons/{mw.addonManager.addonFromModule(__name__)}/web"


def append_webcontent(webcontent: WebContent, context: Any) -> None:
    if isinstance(context, Reviewer):
        webcontent.js.append(f"{base_path}/audio.js")


def get_speed() -> float:
    return aqt.sound.mpvManager.command("get_property", "speed")


def get_default_speed() -> float:
    return float(config.get("default_speed", 1.0))


def get_speed_factor() -> float:
    return float(config.get("speed_factor", 10)) / 100


def add_speed(speed: float) -> None:
    aqt.sound.mpvManager.command("add", "speed", speed)
    tooltip(f"Audio Speed {speed:+}<br>Current Speed: {get_speed()}")


def set_speed(speed: float) -> None:
    aqt.sound.mpvManager.command("set_property", "speed", speed)


def reset_speed() -> None:
    set_speed(get_default_speed())
    tooltip(f"Reset Speed: {get_speed()}")
    if mw.reviewer:
        mw.reviewer.web.eval("resetAudioSpeeed();")


def speed_up() -> None:
    factor = get_speed_factor()
    add_speed(factor)
    if mw.reviewer:
        mw.reviewer.web.eval(f"addAudioPlaybackRate({factor});")


def slow_down() -> None:
    factor = -get_speed_factor()
    add_speed(factor)
    if mw.reviewer:
        mw.reviewer.web.eval(f"addAudioPlaybackRate({factor});")


actions = [
    ("Speed Up Audio", config["speed_up_shortcut"], speed_up),
    ("Slow Down Audio", config["slow_down_shortcut"], slow_down),
    ("Reset Audio Speed", config["reset_speed_shortcut"], reset_speed),
]


def add_state_shortcuts(state: str, shortcuts: List[Tuple[str, Callable]]) -> None:
    if state == "review":
        for label, shortcut, cb in actions:
            shortcuts.append((shortcut, cb))


def add_menu_items(reviewer: Reviewer, menu: QMenu) -> None:
    for label, shortcut, cb in actions:
        action = menu.addAction(label)
        action.setShortcut(shortcut)
        qconnect(action.triggered, cb)


def on_profile_did_open() -> None:
    if aqt.sound.mpvManager:
        gui_hooks.reviewer_will_show_context_menu.append(add_menu_items)
        gui_hooks.state_shortcuts_will_change.append(add_state_shortcuts)
        gui_hooks.webview_will_set_content.append(append_webcontent)
        set_speed(get_default_speed())
    else:
        showWarning(
            "This add-on only works with the mpv media player.",
            title="Audio Playback Controls",
        )


gui_hooks.profile_did_open.append(on_profile_did_open)

########################################################

from PyQt5.QtCore import QThread
import re
import subprocess
import time
from anki.utils import isWin


def on_answer_did_open(card) -> None:
    class thread_function(QThread):
        finished = pyqtSignal()
        def __init__(self, var):
            self.var = 2 if var == 0.00 else var
            super().__init__()
        def run(self):
            time.sleep(self.var / get_speed())
            self.finished.emit()
    note = card.note()
    note_type = note.note_type()
    audio_fields = find_audio_fields(card)
    duration = split_audio_fields(card, note_type, audio_fields)
    worker = thread_function(duration)
    def on_timeout():
        worker.quit()
        if mw.reviewer.card == card and get_speed() == 1.2:
            mw.reviewer._answerCard(3)
    worker.finished.connect(on_timeout)
    worker.start()
    mw.destroyed.connect(worker.deleteLater)
    mw.destroyed.connect(worker.quit)


def find_audio_fields(card):
    audio_fields = []
    fields_with_audio = {}
    for field, value in card.note().items():
        match = re.findall(r"\[sound:(.*?)\]", value)
        if match:
            audio_fields.append(field)
            fields_with_audio[field] = match
    return audio_fields, fields_with_audio


def split_audio_fields(card, note_type, audio_fields):
    def helper(q):
        q_times = []
        start = 0
        while True:
            s = q.find('{{', start)
            if s == -1: break
            e = q.find('}}', s)
            if e != -1:
                if q[s + 2:e] in audio_fields[1]:
                    q_times.append(q[s + 2:e][:])
                start = e + 2
            else: break
        return q_times

    question_audio_fields = []
    answer_audio_fields = []
    if card is not None:
        t = note_type['tmpls'][card.ord]
        q = t.get("qfmt")
        a = t.get("afmt")
        question_audio_fields.extend(helper(q))
        answer_audio_fields.extend(helper(a))
    media_path = mw.col.path.rsplit('\\', 1)[0] + '\\collection.media\\' if isWin else mw.col.path.rsplit('/', 1)[0] + '/collection.media/'

    mp3set = set()
    #for audio_qfield in question_audio_fields:
        #for mp3 in audio_fields[1].get(audio_qfield):
            # mp3set.add(mp3)
    for audio_afield in answer_audio_fields:
        for mp3 in audio_fields[1].get(audio_afield):
            mp3set.add(mp3)

    total_duration = 0.0
    for mp3 in mp3set:
        p = subprocess.check_output([
        "mpv", "--term-playing-msg=DURATION=${=duration}", "--no-config",
        "--no-cache", "--quiet", "--vo=null", "--ao=null", "--frames=1",
        media_path+mp3], shell=False)
        for line in p.splitlines():
            if line.startswith(b"DURATION="):
                duration = float(line[len("DURATION="):])
                total_duration += duration
    return total_duration


def on_question_did_open(card) -> None:
    if mw.reviewer.lastCard() != card and get_speed() == 1.2:
        mw.reviewer._showAnswer()


gui_hooks.reviewer_did_show_answer.append(on_answer_did_open)
gui_hooks.reviewer_did_show_question.append(on_question_did_open)
