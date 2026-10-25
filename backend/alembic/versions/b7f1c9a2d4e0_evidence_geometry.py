"""evidence geometry for document viewer

Adds page dimensions captured at extraction time so evidence bounding boxes can
be positioned on the rendered page. Both coordinate spaces are supported:
PDF text-layer boxes are in points, OCR'd raster boxes are in pixels.

Revision ID: b7f1c9a2d4e0
Revises: 4eeaf2dbd8cc
Create Date: 2026-10-25 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7f1c9a2d4e0'
down_revision: Union[str, None] = '4eeaf2dbd8cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('extracted_fields', sa.Column('page_width', sa.Numeric(10, 3), nullable=True))
    op.add_column('extracted_fields', sa.Column('page_height', sa.Numeric(10, 3), nullable=True))


def downgrade() -> None:
    op.drop_column('extracted_fields', 'page_height')
    op.drop_column('extracted_fields', 'page_width')
