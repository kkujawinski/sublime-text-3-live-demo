import xml.etree.ElementTree as ET
from .diff_match_patch import diff_match_patch


dmp = diff_match_patch()
NS = '{http://digit11.com/live_demo}'


class LDMLStep(object):
    PASTE = 'PASTE'
    TYPE = 'TYPE'

    def __init__(self, filename, diffs, method=None, empty=False):
        self.filename = filename
        self.diffs = diffs
        self.method = method or self.TYPE
        self.empty = False if empty is None else empty

    def process_changes(self, init_text):
        final_text, _ = dmp.patch_apply(self.diffs, init_text)
        perfect_patches = dmp.patch_make(init_text, final_text)
        return dmp.patch_apply_perfect_replacements(perfect_patches, init_text)

    @classmethod
    def create_from_etree(cls, etree):
        method_element = etree.find(NS + 'method')
        empty_element = etree.find(NS + 'empty')
        return cls(
            filename=etree.find(NS + 'filename').text.strip(),
            diffs=dmp.patch_fromText(etree.find(NS + 'diff').text.strip()),
            method=None if method_element is None else method_element.text.strip().upper(),
            empty=None if empty_element is None else empty_element.text.lower() in ('true', '1', 'yes')
        )


class LDML(object):
    def __init__(self, steps):
        self.steps = steps

    @classmethod
    def create_from_etree(cls, etree):
        return cls(steps=[
            LDMLStep.create_from_etree(step_xml)
            for step_xml in etree.findall(NS + 'step')
        ])


def parse(file_path):
    tree = ET.parse(file_path)
    root = tree.getroot()
    return LDML.create_from_etree(root)
