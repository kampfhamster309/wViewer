from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wviewer.db import Base


class Import(Base):
    __tablename__ = "imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recon_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    networks: Mapped[list["Network"]] = relationship("Network", back_populates="import_", passive_deletes=True)


class Network(Base):
    __tablename__ = "networks"
    __table_args__ = (
        UniqueConstraint("mac", "latitude", "longitude", name="uq_network_mac_lat_lon"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_id: Mapped[int] = mapped_column(Integer, ForeignKey("imports.id"), nullable=False)
    mac: Mapped[str] = mapped_column(Text, nullable=False)
    ssid: Mapped[str] = mapped_column(Text, nullable=False, default="")
    auth_mode: Mapped[str] = mapped_column(Text, nullable=False, default="")
    first_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    channel: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frequency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rssi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    altitude_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    rcois: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mfgr_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    type: Mapped[str] = mapped_column(Text, nullable=False, default="WIFI")

    import_: Mapped["Import"] = relationship("Import", back_populates="networks")
