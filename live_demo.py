"""
TODO:
1. Recorder
2. Error messages
3. Status bar
"""

import hashlib
import os.path
import pickle
import random
import tempfile
from collections import deque

import sublime
import sublime_plugin

from . import ldml


class LiveDemoLoadCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        filename = self.view.file_name()
        base_filename = os.path.basename(filename)
        helper = SublimeTextHelpers(edit)
        try:
            recording = ldml.parse(filename)
        except Exception as e:
            helper.error_message('Error loading recording file %s.\n\n%r' % (base_filename, e))
        else:
            processor = ExecutionProcessor(recording, SublimeTextHelpers(edit).get_base_dir())
            processor.save()
            msg = 'Loaded %d steps.\n\n Run "Play next step" command to start.'
            helper.message_dialog(msg % processor.total_steps)


class LiveDemoResetCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        helper = SublimeTextHelpers(edit)
        processor = ExecutionProcessor.read(SublimeTextHelpers(edit).get_base_dir())
        try:
            processor.reset()
        except:
            helper.error_message('Can\'t reset. No recording file is currently loaded')
        else:
            helper.message_dialog('Reseted')


class LiveDemoNextStep(sublime_plugin.TextCommand):
    def run(self, edit):
        helper = SublimeTextHelpers(edit)
        processor = ExecutionProcessor.read(SublimeTextHelpers(edit).get_base_dir())
        try:
            processor.next_step()
        except Exception as e:
            helper.error_message('No next step defined.')
            processor.stop()
        else:
            processor.save()
            self.view.run_command("live_demo_play_sub")


class LiveDemoStopCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        ExecutionProcessor.read(SublimeTextHelpers(edit).get_base_dir()).stop()


class LiveDemoPlaySubCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.helper = SublimeTextHelpers(edit)
        processor = ExecutionProcessor.read(self.helper.get_base_dir())
        if processor is None:
            return
        instruction = processor.next_instruction()
        if instruction:
            self.execute_instruction(instruction, processor.step_progress())
        else:
            self.helper.set_status(self.view, '')

    def execute_instruction(self, instruction, progress):
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

        total_chars = 20
        full_chars = int(progress * total_chars)
        message = 'Step progress: |' + '#' * full_chars + '-' * (total_chars - full_chars) + '|'
        self.helper.set_status(target_view, message)
        sublime.set_timeout(lambda: target_view.run_command("live_demo_play_sub"), delay)


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

    def open_file_tab(self, filename):
        try:
            file_path = os.path.join(self.get_base_dir(), filename)
            return self.window.open_file(file_path)
        except:
            return self.window.new_file()

    def write(self, view, text, position=None):
        if position is None:
            position = view.sel()[0].begin()
        view.insert(self.edit, position, text)

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


class ExecutionProcessor(object):
    __VERSION__ = 1

    OPEN = 1    # open tabe file with give path, args: delay, filename
    MOVE = 2    # move cursor to position, args: delay, position
    SAVE = 3    # save file, args: delay
    SELECT = 4  # selects next character, args: delay
    DELETE = 5  # delete next character, or selection, args: delay
    INSERT = 6  # insert character, args: delay, character

    DEFAULT_DELAY = 70
    EXECUTION_STATE_FILE = os.path.join(tempfile.gettempdir(), 'sublime-live-demo-execution')

    def __init__(self, recording, base_dir):
        self.recording = recording
        self.current_step = None
        self.instructions = None
        self.changes = None
        self.base_dir = base_dir
        self.total_steps = len(recording.steps)
        self.step_completed_instructions = None
        self.step_total_instructions = None

    def next_step(self, step=None):
        if self.current_step is None:
            self.current_step = 0
        else:
            self.current_step = self.current_step + 1
        step = self.recording.steps[self.current_step]

        filepath = os.path.join(self.base_dir, step.filename)
        basedir = os.path.dirname(filepath)
        if not os.path.exists(basedir):
            os.makedirs(basedir)

        if step.empty:
            with open(filepath, 'w'):
                pass
            init_text = ''
        else:
            with open(filepath, 'r') as f:
                init_text = f.read()
        self.instructions = deque([(self.OPEN, self.DEFAULT_DELAY, step.filename)])
        self.instructions.extend(self.prepare_instructions(step, init_text))
        self.step_completed_instructions = 0
        self.step_total_instructions = len(self.instructions)

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
            self.step_completed_instructions = self.step_completed_instructions + 1
            self.save()

    def step_progress(self):
        return float(self.step_completed_instructions) / self.step_total_instructions

    @classmethod
    def state_filepath(cls, base_dir):
        return cls.EXECUTION_STATE_FILE + hashlib.md5(base_dir.encode('utf-8')).hexdigest()

    def save(self):
        pickle.dump(self, open(ExecutionProcessor.state_filepath(self.base_dir), "wb"))

    def reset(self):
        self.current_step = None
        self.save()

    def stop(self):
        try:
            os.unlink(ExecutionProcessor.state_filepath(self.base_dir))
        except:
            pass

    @classmethod
    def read(cls, base_dir):
        try:
            return pickle.load(open(ExecutionProcessor.state_filepath(base_dir), "rb"))
        except:
            pass
