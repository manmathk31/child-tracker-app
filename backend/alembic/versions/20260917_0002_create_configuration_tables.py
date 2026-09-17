"""create_configuration_tables

Revision ID: 20260917_0002
Revises: 20260917_0001
Create Date: 2026-09-17 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260917_0002"
down_revision: Union[str, None] = "20260917_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True).with_variant(sa.String(length=36), "sqlite")

    # 1. zones table
    op.create_table(
        "zones",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("building", sa.String(length=64), nullable=True),
        sa.Column("floor", sa.String(length=32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_zones_name", "zones", ["name"], unique=True)

    # 2. access_points table
    op.create_table(
        "access_points",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("bssid", sa.String(length=17), nullable=False),
        sa.Column("channel", sa.Integer(), nullable=True),
        sa.Column("zone_id", uuid_type, sa.ForeignKey("zones.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_access_points_bssid", "access_points", ["bssid"], unique=True)

    # 3. students table
    op.create_table(
        "students",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("student_code", sa.String(length=64), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("class_name", sa.String(length=64), nullable=False),
        sa.Column("age", sa.Integer(), nullable=False),
        sa.Column("photo_url", sa.String(length=512), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_students_student_code", "students", ["student_code"], unique=True)

    # 4. allowed_zones join table
    op.create_table(
        "allowed_zones",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("student_id", uuid_type, sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("zone_id", uuid_type, sa.ForeignKey("zones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("student_id", "zone_id", name="uq_allowed_zones_student_zone"),
    )
    op.create_index("ix_allowed_zones_student_id", "allowed_zones", ["student_id"], unique=False)
    op.create_index("ix_allowed_zones_zone_id", "allowed_zones", ["zone_id"], unique=False)

    # 5. devices table
    op.create_table(
        "devices",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("device_code", sa.String(length=64), nullable=False),
        sa.Column("mac_address", sa.String(length=17), nullable=False),
        sa.Column("battery_percent", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("firmware_version", sa.String(length=32), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="offline"),
        sa.Column("student_id", uuid_type, sa.ForeignKey("students.id", ondelete="SET NULL"), unique=True, nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_devices_device_code", "devices", ["device_code"], unique=True)
    op.create_index("ix_devices_mac_address", "devices", ["mac_address"], unique=True)
    op.create_index("ix_devices_last_seen_at", "devices", ["last_seen_at"], unique=False)

    # 6. school_settings singleton table
    op.create_table(
        "school_settings",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("school_name", sa.String(length=255), nullable=False, server_default="ChildTrack Academy"),
        sa.Column("building_name", sa.String(length=255), nullable=False, server_default="Main Campus"),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 7. alert_settings singleton table
    op.create_table(
        "alert_settings",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("offline_threshold_minutes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("critical_offline_threshold_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("low_battery_percent", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("min_localization_confidence", sa.Float(), nullable=False, server_default="0.45"),
        sa.Column("restricted_zone_alerts_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("fall_detection_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("sos_alerts_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("alert_settings")
    op.drop_table("school_settings")
    op.drop_index("ix_devices_last_seen_at", table_name="devices")
    op.drop_index("ix_devices_mac_address", table_name="devices")
    op.drop_index("ix_devices_device_code", table_name="devices")
    op.drop_table("devices")
    op.drop_index("ix_allowed_zones_zone_id", table_name="allowed_zones")
    op.drop_index("ix_allowed_zones_student_id", table_name="allowed_zones")
    op.drop_table("allowed_zones")
    op.drop_index("ix_students_student_code", table_name="students")
    op.drop_table("students")
    op.drop_index("ix_access_points_bssid", table_name="access_points")
    op.drop_table("access_points")
    op.drop_index("ix_zones_name", table_name="zones")
    op.drop_table("zones")
