"""PostGIS ORM models — mirrors database/init.sql."""
import uuid

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

JOB_STATUS = Enum("PENDING", "RUNNING", "COMPLETED", "FAILED", name="job_status")


class UserAOI(Base):
    __tablename__ = "user_aois"

    aoi_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user_label = Column(String(100))
    geom = Column(Geometry("POLYGON", srid=4326), nullable=False)
    area_sqm = Column(Float)

    jobs = relationship("SRMJob", back_populates="aoi", cascade="all, delete-orphan")


class SatelliteGranule(Base):
    __tablename__ = "satellite_granules"

    granule_id = Column(String(100), primary_key=True)
    acquisition_date = Column(DateTime(timezone=True))
    cloud_cover_percentage = Column(Float)
    stac_url = Column(String(512))
    bounding_box = Column(Geometry("POLYGON", srid=4326))


class SRMJob(Base):
    __tablename__ = "srm_jobs"

    job_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aoi_id = Column(UUID(as_uuid=True), ForeignKey("user_aois.aoi_id", ondelete="CASCADE"))
    granule_id = Column(
        String(100), ForeignKey("satellite_granules.granule_id", ondelete="RESTRICT")
    )
    status = Column(JOB_STATUS, default="PENDING", nullable=False)
    scale_factor = Column(Integer, default=4)
    miou_score = Column(Float)
    cog_path = Column(String(255))
    execution_duration_sec = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    aoi = relationship("UserAOI", back_populates="jobs")
    export = relationship("COGExport", back_populates="job", uselist=False,
                          cascade="all, delete-orphan")
    metrics = relationship("ClassMetrics", back_populates="job", uselist=False,
                           cascade="all, delete-orphan")


class COGExport(Base):
    __tablename__ = "cog_exports"

    export_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("srm_jobs.job_id", ondelete="CASCADE"))
    file_path = Column(String(255), nullable=False)
    crs_projection = Column(String(32), default="EPSG:4326")
    file_size_bytes = Column(BigInteger)

    job = relationship("SRMJob", back_populates="export")


class ClassMetrics(Base):
    __tablename__ = "class_metrics"

    metric_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("srm_jobs.job_id", ondelete="CASCADE"))
    built_up_sqm = Column(Float, default=0.0)
    water_sqm = Column(Float, default=0.0)
    vegetation_sqm = Column(Float, default=0.0)
    cropland_sqm = Column(Float, default=0.0)
    bare_soil_sqm = Column(Float, default=0.0)

    job = relationship("SRMJob", back_populates="metrics")
