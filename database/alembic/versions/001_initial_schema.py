"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-08-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "providers",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("api_type", sa.String(length=64), nullable=False),
        sa.Column("update_frequency", sa.String(length=64), nullable=False),
        sa.Column("attribution", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "stations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("provider_id", sa.String(length=32), nullable=False),
        sa.Column("station_code", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("elevation_m", sa.Float(), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("region", sa.String(length=64), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "geom",
            Geometry(geometry_type="POINT", srid=4326, from_text="ST_GeomFromEWKT", name="geometry"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "station_code", name="uq_provider_station_code"),
    )
    op.create_index("ix_stations_provider_id", "stations", ["provider_id"])
    op.create_index("ix_stations_external_id", "stations", ["external_id"])

    op.create_table(
        "observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("station_id", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("swe_mm", sa.Float(), nullable=True),
        sa.Column("snow_depth_cm", sa.Float(), nullable=True),
        sa.Column("snowfall_cm", sa.Float(), nullable=True),
        sa.Column("temperature_c", sa.Float(), nullable=True),
        sa.Column("precipitation_mm", sa.Float(), nullable=True),
        sa.Column("wind_speed_ms", sa.Float(), nullable=True),
        sa.Column("humidity", sa.Float(), nullable=True),
        sa.Column("quality_flag", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("station_id", "timestamp", name="uq_station_timestamp"),
    )
    op.create_index("ix_observations_station_id", "observations", ["station_id"])
    op.create_index(
        "ix_observations_station_ts_desc", "observations", ["station_id", "timestamp"]
    )

    op.execute(
        """
        INSERT INTO providers (id, name, country, api_type, update_frequency, attribution)
        VALUES
        (
          'NRCS',
          'USDA NRCS AWDB',
          'US',
          'REST',
          'Hourly',
          'USDA Natural Resources Conservation Service Air-Web / AWDB'
        ),
        (
          'BCASWS',
          'BC Automated Snow Weather Stations',
          'CA',
          'CSV',
          'Hourly',
          'Province of British Columbia — Open Government Licence – British Columbia'
        )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_observations_station_ts_desc", table_name="observations")
    op.drop_index("ix_observations_station_id", table_name="observations")
    op.drop_table("observations")
    op.drop_index("ix_stations_external_id", table_name="stations")
    op.drop_index("ix_stations_provider_id", table_name="stations")
    op.drop_table("stations")
    op.drop_table("providers")
