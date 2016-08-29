import os
import os.path
import random
from shutil import copyfile
from collections import deque

import sublime
import sublime_plugin

from . import ldml
from .helpers import StatefulProcessor, SublimeTextHelpers


PLUGIN_DIR = os.path.dirname(__file__)
TARGET_MENU_FILE_PATH = os.path.join(PLUGIN_DIR, 'Main.sublime-menu')
MENU_FILE_PATH_OFF = os.path.join(PLUGIN_DIR, 'Main.sublime-menu.off')
MENU_FILE_PATH_ON = os.path.join(PLUGIN_DIR, 'Main.sublime-menu.on')


def reload_menu():
    s = sublime.load_settings("Live Demo.sublime-settings")
    show_live_demo_menu_bar = s.get('show_menu_bar', True)
    if show_live_demo_menu_bar:
        menu_file_name = MENU_FILE_PATH_ON
    else:
        menu_file_name = MENU_FILE_PATH_OFF
    copyfile(menu_file_name, TARGET_MENU_FILE_PATH)


def plugin_loaded():
    reload_menu()


class LiveDemoLoadCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        filename = self.view.file_name()
        base_filename = os.path.basename(filename)
        helper = SublimeTextHelpers(edit)
        try:
            processor = ExecutionProcessor(filename)
        except Exception as e:
            helper.error_message('Error loading recording file %s.\n\n%r' % (base_filename, e))
        else:
            processor.save()
            msg = 'Loaded %d steps.\n\nRun "Play next step" command to start.'
            helper.message_dialog(msg % processor.total_steps)


class LiveDemoResetCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        helper = SublimeTextHelpers(edit)
        processor = ExecutionProcessor.read()
        try:
            processor.reset()
        except:
            helper.error_message('Can\'t reset. No recording file is currently loaded')
        else:
            helper.message_dialog('Reseted')

    def is_enabled(self, *args, **kwargs):
        return bool(ExecutionProcessor.read())


class LiveDemoNextStep(sublime_plugin.TextCommand):
    def run(self, edit):
        helper = SublimeTextHelpers(edit)
        processor = ExecutionProcessor.read()
        try:
            processor.next_step()
        except Exception:
            helper.error_message('No next step defined.')
            processor.stop()
        else:
            processor.save()
            self.view.run_command("live_demo_play_sub")

    def is_enabled(self, *args, **kwargs):
        processor = ExecutionProcessor.read()
        if not processor:
            return False
        return processor.has_more_steps()


class LiveDemoStopCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        ExecutionProcessor.read().stop()

    def is_enabled(self, *args, **kwargs):
        processor = ExecutionProcessor.read()
        if not processor:
            return False
        return processor.has_more_steps()


class LiveDemoPlaySubCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.helper = SublimeTextHelpers(edit)
        processor = ExecutionProcessor.read()
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


class ExecutionProcessor(StatefulProcessor):
    __VERSION__ = 1
    STATE_FILE_KEY = 'sublime-live-demo-execution'

    OPEN = 1    # open tabe file with give path, args: delay, filename
    MOVE = 2    # move cursor to position, args: delay, position
    SAVE = 3    # save file, args: delay
    SELECT = 4  # selects next character, args: delay
    DELETE = 5  # delete next character, or selection, args: delay
    INSERT = 6  # insert character, args: delay, character

    DEFAULT_DELAY = 70

    def __init__(self, filename):
        recording = ldml.parse(filename)
        self.filename = filename
        self.recording = recording
        self.current_step = None
        self.instructions = None
        self.changes = None
        self.total_steps = len(recording.steps)
        self.step_completed_instructions = None
        self.step_total_instructions = None

    def next_step(self, step=None):
        if self.current_step is None:
            self.current_step = 0
        else:
            self.current_step = self.current_step + 1
        step = self.recording.steps[self.current_step]

        filepath = os.path.join(ExecutionProcessor.get_base_dir(), step.filename)
        basedir = os.path.dirname(filepath)
        if not os.path.exists(basedir):
            os.makedirs(basedir)

        if step.clear:
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
            # hold selection before removal
            instructions.append((self.SELECT, self.DEFAULT_DELAY * 10))
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

    def has_more_steps(self):
        if self.current_step is None:
            return True
        return self.current_step + 1 < len(self.recording.steps)

    def reset(self):
        self.current_step = None
        self.save()

    def stop(self):
        self.delete()
