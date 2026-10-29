"""Synthetic local bookmark/history fixtures; no corpus documents modified."""
from pathlib import Path
import sys

import pikepdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.build_text_box_fixtures import build_text_boxes


def build_navigation(directory: Path):
    build_text_boxes(directory)
    with pikepdf.open(directory / 'source.pdf') as pdf:
        root = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Outlines, Count=5))
        def item(title, destination=None, action=None):
            node = pdf.make_indirect(pikepdf.Dictionary(Title=pikepdf.String(title), Parent=root))
            if destination is not None:
                node.Dest = destination
            if action is not None:
                node.A = action
            return node
        first = item('Introduction', pikepdf.Array([pdf.pages[0].obj, pikepdf.Name.Fit]))
        child = item('Named chapter', pikepdf.String('chapter-four'))
        child.Parent = first
        first.First = first.Last = child
        first.Count = 1
        last = item('Last chapter', pikepdf.Array([pdf.pages[11].obj, pikepdf.Name.Fit]))
        external = item('External website', action=pikepdf.Dictionary(S=pikepdf.Name.URI, URI=pikepdf.String('https://example.invalid/')))
        script = item('Document script', action=pikepdf.Dictionary(S=pikepdf.Name.JavaScript, JS=pikepdf.String('app.alert("Do not execute");')))
        nodes = [first, last, external, script]
        for previous, following in zip(nodes, nodes[1:]):
            previous.Next = following
            following.Prev = previous
        root.First, root.Last = nodes[0], nodes[-1]
        pdf.Root.Outlines = root
        pdf.Root.Names = pikepdf.Dictionary(Dests=pikepdf.Dictionary(Names=[
            pikepdf.String('chapter-four'), pikepdf.Array([pdf.pages[3].obj, pikepdf.Name.Fit])]))
        pdf.save(directory / 'bookmarks.pdf', min_version='1.6')


if __name__ == '__main__':
    build_navigation(Path(sys.argv[1] if len(sys.argv)>1 else '/private/tmp/pdf-tool-navigation-20261029'))
