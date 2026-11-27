"""
Stage Plot Model
================

A stage plot image (a PNG, JPEG or WebP of the venue's plot or a photo of it)
kept with a rig as an underlay for the 2D plan, and how it is laid onto the
room. docs/STAGE_PLOT.md.

Kept in a table of its own, one row per rig, rather than as columns on `rigs`:
the image can be several megabytes and must never be read with the rig, and
uploading, calibrating or removing it must not change the rig (not even its
`updated_at`). Scenery only: nothing reaches a device and no fixture moves.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, LargeBinary, String

from app.db.database import Base


class RigStagePlot(Base):
    """The stage plot underlay of one rig."""

    __tablename__ = "rig_stage_plots"

    rig_id = Column(Integer, ForeignKey("rigs.id", ondelete="CASCADE"), primary_key=True)
    filename = Column(String(255), nullable=True)
    # Read from the file's first bytes, never from what the client said it was.
    content_type = Column(String(50), nullable=False)
    byte_size = Column(Integer, nullable=False)
    # The image's size in pixels, read from its header: what calibration points are measured in.
    width_px = Column(Integer, nullable=False)
    height_px = Column(Integer, nullable=False)
    data = Column(LargeBinary, nullable=False)
    # What the operator set (two points, the distance between them, the origin,
    # rotation, opacity) and the transform worked out from it
    # (services/stage_plot.py). Null until calibrated; a new upload clears it.
    calibration = Column(JSON, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
