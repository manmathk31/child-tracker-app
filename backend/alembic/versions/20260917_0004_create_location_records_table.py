"""create_location_records_table

Revision ID: 20260917_0004
Revises: 20260917_0003
Create Date: 2026-09-17 03:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260917_0004"
down_revision: str | None = "20260917_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True).with_variant(sa.String(length=36), "sqlite")

    op.create_table(
        "location_records",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column(
            "student_id",
            uuid_type,
            sa.ForeignKey("students.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            uuid_type,
            sa.ForeignKey("devices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "zone_id",
            uuid_type,
            sa.ForeignKey("zones.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("raw_scan", sa.JSON(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_location_records_student_id", "location_records", ["student_id"])
    op.create_index("ix_location_records_device_id", "location_records", ["device_id"])
    op.create_index("ix_location_records_zone_id", "location_records", ["zone_id"])
    op.create_index("ix_location_records_recorded_at", "location_records", ["recorded_at"])


def downgrade() -> None:
    op.drop_index("ix_location_records_recorded_at", table_name="location_records")
    op.drop_index("ix_location_records_zone_id", table_name="location_records")
    op.drop_index("ix_location_records_device_id", table_name="location_records")
    op.drop_index("ix_location_records_student_id", table_name="location_records")
    op.drop_table("location_records")
