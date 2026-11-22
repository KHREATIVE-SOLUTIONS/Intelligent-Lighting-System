"""
Console Export
==============

Writes a rig back out for a lighting console or a visualiser: a grandMA2 fixture
layer XML, a grandMA2 command-line script, and an MVR for MA3D or Capture.

    model.py    one neutral description of a rig (ExportRig), built from a
                database rig or from a demo venue preset. Every writer reads
                only this, so no writer can disagree with another.
    ma2.py      the grandMA2 XML and the command-line script.
    mvr.py      the MVR archive and its GeneralSceneDescription.xml.
    archive.py  a ZIP that is the same bytes on every run.

Nothing here opens a socket or touches the database. docs/CONSOLE_EXPORT.md says
what each file carries and what the operator still has to do on the desk.

This module imports nothing, so app.services.demo can use archive.py without a
circle: model.py is the part that reads the demo presets.
"""
