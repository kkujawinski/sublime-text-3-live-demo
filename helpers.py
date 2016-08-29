import hashlib
import os.path
import pickle
import tempfile

import sublime


class SublimeTextHelpers(object):
    def __init__(self, edit):
        self.edit = edit
        self.window = sublime.active_window()

    def get_base_dir(self):
        return sublime.active_window().folders()[0]

    def error_message(self, text):
        sublime.error_message(text)

    def message_dialog(self, text):
        sublime.message_dialog(text)

    def new_file_tab(self, filename=None, syntax=None):
        view = self.window.new_file()
        if filename is not None:
            view.set_name(filename)
        if syntax is not None:
            view.set_syntax_file(syntax)
        return view

    def open_file_tab(self, filename):
        file_path = os.path.join(self.get_base_dir(), filename)
        return self.window.open_file(file_path)

    def get_view_by_id(self, view_id):
        views = self.window.views()
        for view in views:
            if view.id() == view_id:
                return view

    def get_view_by_file_name(self, file_name):
        views = self.window.views()
        for view in views:
            if view.file_name() == file_name:
                return view

    def write(self, view, text, position=None):
        if position is None:
            position = view.sel()[0].begin()
        view.insert(self.edit, position, text)

    def clear_and_write(self, view, text):
        size = view.size()
        if size:
            view.erase(self.edit, sublime.Region(0, view.size()))
        self.write(view, text)

    def set_cursor(self, view, position):
        view.sel().clear()
        view.sel().add(sublime.Region(position))

    def set_status(self, view, text):
        view.set_status('live_demo', text)

    def increase_selection(self, view, step=1):
        selection = view.sel()[0]
        view.sel().clear()
        view.sel().add(sublime.Region(selection.a, selection.b + step))

    def erase_selection(self, view):
        view.erase(self.edit, view.sel()[0])

    def view_content(self, view):
        return view.substr(sublime.Region(0, view.size()))


class StatefulProcessor(object):
    __VERSION__ = None
    STATE_FILE_KEY = None

    @classmethod
    def get_base_dir(cls):
        return sublime.active_window().folders()[0]

    @classmethod
    def state_filepath(cls):
        base_dir = cls.get_base_dir()
        return os.path.join(tempfile.gettempdir(), cls.STATE_FILE_KEY) + hashlib.md5(base_dir.encode('utf-8')).hexdigest()

    def save(self):
        pickle.dump(self, open(self.state_filepath(), "wb"))

    def delete(self):
        try:
            os.unlink(self.state_filepath())
        except:
            pass

    def validate(self):
        return True

    @classmethod
    def read(cls):
        try:
            obj = pickle.load(open(cls.state_filepath(), "rb"))
            if obj.__VERSION__ != cls.__VERSION__:
                raise Exception('Version mismatch')
            if obj.validate():
                return obj
        except:
            pass
