"""add observation resolution hourly/daily

Revision ID: 003
Revises: 002
Create Date: 2026-08-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "observations",
        sa.Column(
            "resolution",
            sa.String(length=16),
            nullable=False,
            server_default="hourly",
        ),
    )
    op.drop_constraint("uq_station_timestamp", "observations", type_="unique")
    op.create_unique_constraint(
        "uq_station_timestamp_resolution",
        "observations",
        ["station_id", "timestamp", "resolution"],
    )
    op.create_index(
        "ix_observations_station_resolution_ts",
        "observations",
        ["station_id", "resolution", "timestamp"],
    )


def downgrade() -> None:
    op.drop_index("ix_observations_station_resolution_ts", table_name="observations")
    op.drop_constraint("uq_station_timestamp_resolution", "observations", type_="unique")
    # May fail if both hourly and daily exist for same stamp — drop daily first in ops if needed
    op.execute("DELETE FROM observations WHERE resolution = 'daily'")
    op.create_unique_constraint(
        "uq_station_timestamp",
        "observations",
        ["station_id", "timestamp"],
    )
    op.drop_column("observations", "resolution")
