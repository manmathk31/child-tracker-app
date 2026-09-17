"""create_fingerprints_tables

Revision ID: 20260917_0003
Revises: 20260917_0002
Create Date: 2026-09-17 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260917_0003"
down_revision: Union[str, None] = "20260917_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True).with_variant(sa.String(length=36), "sqlite")

    # 1. fingerprints table
    op.create_table(
        "fingerprints",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("zone_id", uuid_type, sa.ForeignKey("zones.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_by", uuid_type, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("min_rssi_cutoff", sa.Integer(), nullable=False, server_default="-85"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_fingerprints_zone_id", "fingerprints", ["zone_id"])
    op.create_index("ix_fingerprints_created_by", "fingerprints", ["created_by"])
    op.create_index("ix_fingerprints_status", "fingerprints", ["status"])

    # 2. fingerprint_ap_stats table
    op.create_table(
        "fingerprint_ap_stats",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("fingerprint_id", uuid_type, sa.ForeignKey("fingerprints.id", ondelete="CASCADE"), nullable=False),
        sa.Column("access_point_id", uuid_type, sa.ForeignKey("access_points.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("median_rssi", sa.Float(), nullable=False),
        sa.Column("mean_rssi", sa.Float(), nullable=False),
        sa.Column("stddev_rssi", sa.Float(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
    )
    op.create_index("ix_fingerprint_ap_stats_fingerprint_id", "fingerprint_ap_stats", ["fingerprint_id"])
    op.create_index("ix_fingerprint_ap_stats_access_point_id", "fingerprint_ap_stats", ["access_point_id"])

    # 3. fingerprint_samples table
    op.create_table(
        "fingerprint_samples",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("fingerprint_id", uuid_type, sa.ForeignKey("fingerprints.id", ondelete="CASCADE"), nullable=False),
        sa.Column("access_point_id", uuid_type, sa.ForeignKey("access_points.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("rssi", sa.Integer(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_fingerprint_samples_fingerprint_id", "fingerprint_samples", ["fingerprint_id"])
    op.create_index("ix_fingerprint_samples_access_point_id", "fingerprint_samples", ["access_point_id"])


def downgrade() -> None:
    op.drop_index("ix_fingerprint_samples_access_point_id", table_name="fingerprint_samples")
    op.drop_index("ix_fingerprint_samples_fingerprint_id", table_name="fingerprint_samples")
    op.drop_table("fingerprint_samples")

    op.drop_index("ix_fingerprint_ap_stats_access_point_id", table_name="fingerprint_ap_stats")
    op.drop_index("ix_fingerprint_ap_stats_fingerprint_id", table_name="fingerprint_ap_stats")
    op.drop_table("fingerprint_ap_stats")

    op.drop_index("ix_fingerprints_status", table_name="fingerprints")
    op.drop_index("ix_fingerprints_created_by", table_name="fingerprints")
    op.drop_index("ix_fingerprints_zone_id", table_name="fingerprints")
    op.drop_table("fingerprints")
