import codecs
import os.path
import shutil
import tempfile

import sublime_plugin

from . import ldml
from .helpers import SublimeTextHelpers, StatefulProcessor


class LiveDemoStartRecordingStepCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        # TODO: check if file saved

        filename = self.view.file_name()
        filename_base = tempfile.mktemp()
        shutil.copy(filename, filename_base)

        helper = SublimeTextHelpers(edit)
        message = 'Do the changes in file %s and afterwards run "Stop recording step" command.'
        helper.message_dialog(message % os.path.basename(filename))

        processor = RecordingProcessor.read()
        relative_filename = os.path.relpath(filename, helper.get_base_dir())
        processor.start_recording(relative_filename, filename_base)

    def is_enabled(self, *args, **kwargs):
        processor = RecordingProcessor.read()
        if processor is None:
            return False
        return not bool(processor.recording_file_name)


class LiveDemoStopRecordingStepCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        # TODO: check if file saved

        helper = SublimeTextHelpers(edit)
        processor = RecordingProcessor.read()

        with open(processor.recording_file_path_before_change) as f:
            old_content = f.read()
        recording_filepath = os.path.join(helper.get_base_dir(), processor.recording_file_name)
        with codecs.open(recording_filepath, 'r', 'utf-8') as f:
            new_content = f.read()

        diffs = ldml.dmp.patch_make(old_content, new_content)
        import remote_pdb; rp = remote_pdb.set_trace(host='0.0.0.0', port=4444)
        if not diffs:
            helper.error_message('No changes found in file.')
            return

        method = 'TYPE'  # ask method: PASTE/TYPE
        clear = False  # ask clear file if exists: file

        processor.record_step(diffs, method, clear)

        if processor.filename:
            with open(processor.filename, 'w') as f:
                f.write(processor.recording.dump())
        else:
            view = helper.get_view_by_id(processor.view_id)
            helper.clear_and_write(view, processor.recording.dump())

        os.unlink(processor.recording_file_path_before_change)
        processor.stop_recording()

        helper.message_dialog('Step has been recorded and saved to output file.')

    def is_enabled(self, *args, **kwargs):
        processor = RecordingProcessor.read()
        if processor is None:
            return False
        return bool(processor.recording_file_name)


class LiveDemoCancelRecordingStepCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        processor = RecordingProcessor.read()
        # TODO: copy_content recording.recording_file_path_before_change to recording.recording_file_path_before_change
        # TODO: unlink recording.recording_file_path_before_change
        os.unlink(processor.recording_file_path_before_change)
        processor.stop_recording()
        message = (
            'Recording has been cancelled\n\n' 'All your changes since started '
            'has been rejected. You can use Sublime undo command if you need.'
        )
        SublimeTextHelpers(edit).message_dialog(message)

    def is_enabled(self, *args, **kwargs):
        processor = RecordingProcessor.read()
        if processor is None:
            return False
        return bool(processor.recording_file_name)


class LiveDemoRecordToNewFileCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        helper = SublimeTextHelpers(edit)
        new_view = helper.new_file_tab(filename='live_demo.ldml',
                                       syntax='Packages/XML/XML.sublime-syntax')
        processor = RecordingProcessor(view=new_view)
        # TODO: add event on_save to replace view_id to filename
        processor.save()
        helper.clear_and_write(new_view, processor.recording.dump())

    def is_enabled(self, *args, **kwargs):
        return not bool(RecordingProcessor.read())


class LiveDemoRecordToOpenedFileCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        filename = self.view.file_name()
        base_filename = os.path.basename(filename)
        helper = SublimeTextHelpers(edit)
        try:
            processor = RecordingProcessor(filename=filename)
        except Exception as e:
            helper.error_message('Error loading recording file %s.\n\n%r' % (base_filename, e))
        else:
            processor.save()
            msg = 'Loaded %d steps.\n\nNew recorded steps will be added to this file.'
            helper.message_dialog(msg % len(processor.recording.steps))

    def is_enabled(self, *args, **kwargs):
        return not bool(RecordingProcessor.read())


class LiveDemoRecordFinishCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        processor = RecordingProcessor.read()
        # processor.save_file()
        processor.delete()

    def is_enabled(self, *args, **kwargs):
        return bool(RecordingProcessor.read())


class RecordingProcessor(StatefulProcessor):
    STATE_FILE_KEY = 'sublime-live-demo-recording'

    filename = None
    view_id = None
    recording_file_name = None
    recording_file_path_before_change = None
    recording = None

    def __init__(self, filename=None, view=None):
        assert filename or view
        if view:
            self.view_id = view.id()
            self.recording = ldml.LDML()
        else:
            self.filename = filename
            self.recording = ldml.parse(filename)

    def record_step(self, diffs, method, clear):
        self.recording.add_step(self.recording_file_name, diffs, method, clear)

    def start_recording(self, filename, filepath_before_change):
        self.recording_file_name = filename
        self.recording_file_path_before_change = filepath_before_change
        self.save()

    def stop_recording(self):
        self.recording_file_name = None
        self.recording_file_path_before_change = None
        self.save()

    def validate(self):
        helper = SublimeTextHelpers(None)
        if self.view_id is not None:
            return bool(helper.get_view_by_id(self.view_id))
        return True
