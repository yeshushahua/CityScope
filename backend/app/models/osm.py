from typing import Any

from geoalchemy2 import Geometry
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Identity, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RoadNode(Base):
    __tablename__ = "road_nodes"

    osm_node_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    geometry: Mapped[Any] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=True), nullable=False
    )


class RoadEdge(Base):
    __tablename__ = "road_edges"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    u: Mapped[int] = mapped_column(BigInteger, nullable=False)
    v: Mapped[int] = mapped_column(BigInteger, nullable=False)
    edge_key: Mapped[int] = mapped_column(Integer, nullable=False)
    osm_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    highway: Mapped[str | None] = mapped_column(Text)
    maxspeed: Mapped[str | None] = mapped_column(Text)
    oneway: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    length_m: Mapped[float] = mapped_column(Float, nullable=False)
    geometry: Mapped[Any] = mapped_column(
        Geometry("LINESTRING", srid=4326, spatial_index=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("u", "v", "edge_key", name="uq_road_edges_uvkey"),
    )


class RoutingEdge(Base):
    """Directed routing projection of one raw OSMnx edge.

    Each row is traversable from source to target. OSMnx represents two-way
    streets as two directed rows, so reverse_cost stays negative and never
    invents a direction that is absent from the source graph.
    """

    __tablename__ = "routing_edges"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    road_edge_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("road_edges.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    source: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("road_nodes.osm_node_id"), nullable=False
    )
    target: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("road_nodes.osm_node_id"), nullable=False
    )
    osm_id: Mapped[str] = mapped_column(Text, nullable=False)
    edge_key: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    highway: Mapped[str | None] = mapped_column(Text)
    oneway: Mapped[bool] = mapped_column(Boolean, nullable=False)
    maxspeed: Mapped[str | None] = mapped_column(Text)
    speed_kph: Mapped[float] = mapped_column(Float, nullable=False)
    speed_source: Mapped[str] = mapped_column(String(16), nullable=False)
    length_m: Mapped[float] = mapped_column(Float, nullable=False)
    travel_time_s: Mapped[float] = mapped_column(Float, nullable=False)
    cost: Mapped[float] = mapped_column(Float, nullable=False)
    reverse_cost: Mapped[float] = mapped_column(Float, nullable=False)
    geometry: Mapped[Any] = mapped_column(
        Geometry("LINESTRING", srid=4326, spatial_index=True), nullable=False
    )

    __table_args__ = (
        Index("ix_routing_edges_source", "source"),
        Index("ix_routing_edges_target", "target"),
        Index("ix_routing_edges_highway", "highway"),
        CheckConstraint("length_m > 0", name="ck_routing_edges_length_positive"),
        CheckConstraint("speed_kph > 0", name="ck_routing_edges_speed_positive"),
        CheckConstraint("travel_time_s > 0", name="ck_routing_edges_time_positive"),
        CheckConstraint("cost > 0", name="ck_routing_edges_cost_positive"),
        CheckConstraint("speed_source IN ('osm', 'default')", name="ck_routing_edges_speed_source"),
    )


class Building(Base):
    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    osm_type: Mapped[str] = mapped_column(String(16), nullable=False)
    osm_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    building_type: Mapped[str | None] = mapped_column(String(120))
    area_m2: Mapped[float] = mapped_column(Float, nullable=False)
    geometry: Mapped[Any] = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("osm_type", "osm_id", name="uq_buildings_osm_identity"),
    )


class Poi(Base):
    __tablename__ = "pois"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    osm_type: Mapped[str] = mapped_column(String(16), nullable=False)
    osm_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    subcategory: Mapped[str] = mapped_column(String(80), nullable=False)
    source_tags: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    geometry: Mapped[Any] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("osm_type", "osm_id", name="uq_pois_osm_identity"),
        Index("ix_pois_category", "category"),
        Index("ix_pois_subcategory", "subcategory"),
    )


class PoiRoutingAccess(Base):
    __tablename__ = "poi_routing_access"

    poi_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pois.id", ondelete="CASCADE"), primary_key=True
    )
    node_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("road_nodes.osm_node_id"), nullable=False
    )
    snap_distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_poi_routing_access_node_id", "node_id"),
        CheckConstraint(
            "snap_distance_m >= 0 AND snap_distance_m <= 500",
            name="ck_poi_routing_access_snap_distance",
        ),
    )
