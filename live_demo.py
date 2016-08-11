from collections import deque
import pickle
import os.path
import random

import sublime
import sublime_plugin

from . import ldml


class LiveDemoPlayCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        recording = ldml.parse('/Users/kkuj/Workspace/Live Demo/example_recording.ldml')
        processor = ExecutionProcessor(recording)
        processor.next_step()
        processor.save()
        self.view.run_command("live_demo_play_sub")


class LiveDemoNextStep(sublime_plugin.TextCommand):
    def run(self, edit):
        processor = ExecutionProcessor.read()
        processor.next_step()
        processor.save()
        self.view.run_command("live_demo_play_sub")


class LiveDemoStopCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        ExecutionProcessor.stop()


class LiveDemoPlaySubCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.helper = SublimeTextHelpers(edit)
        processor = ExecutionProcessor.read()
        if processor is None:
            return
        instruction = processor.next_instruction()
        if instruction:
            self.execute_instruction(instruction)

    def execute_instruction(self, instruction):
        target_view = self.view
        command, delay = instruction[:2]
        randomness_factor = 2 * random.random()
        delay = int(delay * randomness_factor)
        args = instruction[2:]

        if command == ExecutionProcessor.OPEN:
            filename, = args
            target_view = self.helper.open_file_tab(filename)
        elif command == ExecutionProcessor.MOVE:
            position, = args
            self.helper.set_cursor(target_view, position)
        elif command == ExecutionProcessor.SAVE:
            # Don't know why, but run directly saves file, but leaves "not saved" icon
            sublime.set_timeout(lambda: target_view.run_command("save"))
        elif command == ExecutionProcessor.SELECT:
            self.helper.increase_selection(target_view)
        elif command == ExecutionProcessor.DELETE:
            self.helper.erase_selection(target_view)
        elif command == ExecutionProcessor.INSERT:
            character, = args
            self.helper.write(target_view, character)

        sublime.set_timeout(lambda: target_view.run_command("live_demo_play_sub"), delay)


class SublimeTextHelpers(object):
    def __init__(self, edit):
        self.edit = edit
        self.window = sublime.active_window()

    def open_file_tab(self, filename):
        try:
            return self.window.open_file(filename)
        except:
            return self.window.new_file()

    def write(self, view, text, position=None):
        if position is None:
            position = view.sel()[0].begin()
        view.insert(self.edit, position, text)

    def set_cursor(self, view, position):
        view.sel().clear()
        view.sel().add(sublime.Region(position))

    def increase_selection(self, view, step=1):
        selection = view.sel()[0]
        view.sel().clear()
        view.sel().add(sublime.Region(selection.a, selection.b + step))

    def erase_selection(self, view):
        view.erase(self.edit, view.sel()[0])


class ExecutionProcessor(object):
    __VERSION__ = 1

    OPEN = 1    # open tabe file with give path, args: delay, filename
    MOVE = 2    # move cursor to position, args: delay, position
    SAVE = 3    # save file, args: delay
    SELECT = 4  # selects next character, args: delay
    DELETE = 5  # delete next character, or selection, args: delay
    INSERT = 6  # insert character, args: delay, character

    DEFAULT_DELAY = 70
    EXECUTION_STATE_FILE = '/tmp/sublime-live-demo-execution'

    def __init__(self, recording):
        self.recording = recording
        self.current_step = None
        self.instructions = None
        self.changes = None
        self.open_file = None

    def next_step(self):
        if self.current_step is None:
            self.current_step = 0
        else:
            self.current_step = self.current_step + 1
        step = self.recording.steps[self.current_step]
        if self.open_file is None:
            # TODO reading proper file or string
            filepath = '/Users/kkuj/Workspace/Live Demo/' + step.filename
            with open(filepath, 'w'):
                pass
            init_text = ''
            self.open_file = filepath
        else:
            with open(self.open_file, 'r') as f:
                init_text = f.read()
        self.instructions = deque([(self.OPEN, self.DEFAULT_DELAY, step.filename)])
        self.instructions.extend(self.prepare_instructions(step, init_text))

    def prepare_instructions(self, step, init_text):
        instructions = []
        changes = step.process_changes(init_text)

        for start, end, replacement in changes:
            instructions.append((self.MOVE, self.DEFAULT_DELAY, start))
            instructions.extend([(self.SELECT, self.DEFAULT_DELAY / 2)] * (end - start - 1))
            instructions.append((self.SELECT, self.DEFAULT_DELAY * 10)) # holding selection before removal
            instructions.append((self.DELETE, self.DEFAULT_DELAY))
            if step.method == ldml.LDMLStep.PASTE:
                instructions.append((self.INSERT, self.DEFAULT_DELAY, replacement))
            else:
                for c in replacement:
                    instructions.append((self.INSERT, self.DEFAULT_DELAY, c))
        instructions.append((self.SAVE, self.DEFAULT_DELAY))
        return instructions

    def next_instruction(self):
        try:
            return self.instructions.popleft()
        except IndexError:
            return
        finally:
            self.save()

    def save(self):
        pickle.dump(self, open(self.EXECUTION_STATE_FILE, "wb"))

    @classmethod
    def read(cls):
        try:
            return pickle.load(open(cls.EXECUTION_STATE_FILE, "rb"))
        except:
            pass

    @classmethod
    def stop(cls):
        os.unlink(cls.EXECUTION_STATE_FILE)
