"""structured application declarations

Adds the applicant-declared facts used by the three-way consistency checks
(declared vs extracted document fields vs synthetic institutional records).

Revision ID: c3d5e7f9a1b2
Revises: b7f1c9a2d4e0
Create Date: 2026-10-25 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c3d5e7f9a1b2'
down_revision: Union[str, None] = 'b7f1c9a2d4e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'application_declarations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('application_id', sa.Uuid(), nullable=False),
        sa.Column('affiliation_number', sa.Text(), nullable=True),
        sa.Column('affiliation_valid_until', sa.Date(), nullable=True),
        sa.Column(
            'programmes',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column('total_intake', sa.Integer(), nullable=True),
        sa.Column('faculty_count', sa.Integer(), nullable=True),
        sa.Column('previous_approval_reference', sa.Text(), nullable=True),
        sa.Column('declared_by', sa.Uuid(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.CheckConstraint(
            'total_intake IS NULL OR total_intake >= 0',
            name='total_intake_non_negative',
        ),
        sa.CheckConstraint(
            'faculty_count IS NULL OR faculty_count >= 0',
            name='faculty_count_non_negative',
        ),
        sa.ForeignKeyConstraint(
            ['application_id'], ['applications.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(['declared_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('application_id'),
    )


def downgrade() -> None:
    op.drop_table('application_declarations')
