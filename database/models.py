from __future__ import annotations

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    api_type: Mapped[str] = mapped_column(String(64), nullable=False)
    update_frequency: Mapped[str] = mapped_column(String(64), nullable=False)
    attribution: Mapped[str | None] = mapped_column(Text, nullable=True)

    stations: Mapped[list["Station"]] = relationship(back_populates="provider")


class Station(Base):
    __tablename__ = "stations"
    __table_args__ = (
        UniqueConstraint("provider_id", "station_code", name="uq_provider_station_code"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("providers.id"), nullable=False, index=True
    )
    station_code: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    elevation_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    geom = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    provider: Mapped[Provider] = relationship(back_populates="stations")
    observations: Mapped[list["Observation"]] = relationship(back_populates="station")


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint(
            "station_id",
            "timestamp",
            "resolution",
            name="uq_station_timestamp_resolution",
        ),
        Index(
            "ix_observations_station_resolution_ts",
            "station_id",
            "resolution",
            "timestamp",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("stations.id"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolution: Mapped[str] = mapped_column(String(16), nullable=False, default="hourly")
    swe_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    snow_depth_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    snowfall_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    precipitation_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_flag: Mapped[str | None] = mapped_column(String(32), nullable=True)

    station: Mapped[Station] = relationship(back_populates="observations")
