import xml.etree.ElementTree as ET
from xml.dom import minidom

from .diff_match_patch import diff_match_patch

_NS = 'http://digit11.com/live_demo'
NS = '{' + _NS + '}'

dmp = diff_match_patch()
ET.register_namespace('ld', _NS)


class LDMLStep(object):
    PASTE = 'PASTE'
    TYPE = 'TYPE'

    def __init__(self, filename, diffs, method=None, clear=False):
        self.filename = filename
        self.diffs = diffs
        self.method = method or self.TYPE
        self.clear = False if clear is None else clear

    def process_changes(self, init_text):
        final_text, _ = dmp.patch_apply(self.diffs, init_text)
        perfect_patches = dmp.patch_make(init_text, final_text)
        return dmp.patch_apply_perfect_replacements(perfect_patches, init_text)

    def generate_etree(self):
        element = ET.Element(NS + 'step')
        subelement = ET.SubElement(element, NS + 'filename')
        subelement.text = self.filename
        subelement = ET.SubElement(element, NS + 'method')
        subelement.text = self.method
        subelement = ET.SubElement(element, NS + 'clear')
        subelement.text = str(self.clear).lower()
        subelement = ET.SubElement(element, NS + 'diffs')
        subelement.text = '\n'.join(map(str, self.diffs))
        return element

    @classmethod
    def create_from_etree(cls, etree):
        method_element = etree.find(NS + 'method')
        clear_element = etree.find(NS + 'clear')
        return cls(
            filename=etree.find(NS + 'filename').text.strip(),
            diffs=dmp.patch_fromText(etree.find(NS + 'diffs').text.strip()),
            method=None if method_element is None else method_element.text.strip().upper(),
            clear=None if clear_element is None else clear_element.text.lower() in ('true', '1', 'yes')
        )


class LDML(object):
    def __init__(self, steps=None):
        self.steps = steps or []

    def generate_etree(self):
        element = ET.Element(NS + 'recording')
        for step in self.steps:
            subelement = step.generate_etree()
            element.append(subelement)
        return element

    def dump(self):
        element = self.generate_etree()
        output = ET.tostring(element).decode('utf-8')
        output_minidom = minidom.parseString(output)
        return output_minidom.toprettyxml()

    def add_step(self, filename, diffs, method, clear):
        self.steps.append(
            LDMLStep(filename, diffs, method, clear)
        )

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
