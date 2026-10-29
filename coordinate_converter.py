"""Coordinate conversion helpers used by the JT/T 808 receiver."""

import math


PI = math.pi
A = 6378245.0
EE = 0.00669342162296594323


def wgs84_to_gcj02(longitude, latitude):
    """Convert a WGS84 point to GCJ-02 for the AMap/China map display."""
    longitude = float(longitude)
    latitude = float(latitude)
    if _out_of_china(longitude, latitude):
        return longitude, latitude

    delta_lat = _transform_lat(longitude - 105.0, latitude - 35.0)
    delta_lng = _transform_lng(longitude - 105.0, latitude - 35.0)
    rad_lat = latitude / 180.0 * PI
    magic = math.sin(rad_lat)
    magic = 1 - EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    delta_lat = (delta_lat * 180.0) / ((A * (1 - EE)) / (magic * sqrt_magic) * PI)
    delta_lng = (delta_lng * 180.0) / (A / sqrt_magic * math.cos(rad_lat) * PI)
    return longitude + delta_lng, latitude + delta_lat


def _out_of_china(longitude, latitude):
    return longitude < 72.004 or longitude > 137.8347 or latitude < 0.8293 or latitude > 55.8271


def _transform_lat(x, y):
    result = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    result += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    result += (20.0 * math.sin(y * PI) + 40.0 * math.sin(y / 3.0 * PI)) * 2.0 / 3.0
    result += (160.0 * math.sin(y / 12.0 * PI) + 320.0 * math.sin(y * PI / 30.0)) * 2.0 / 3.0
    return result


def _transform_lng(x, y):
    result = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    result += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    result += (20.0 * math.sin(x * PI) + 40.0 * math.sin(x / 3.0 * PI)) * 2.0 / 3.0
    result += (150.0 * math.sin(x / 12.0 * PI) + 300.0 * math.sin(x / 30.0 * PI)) * 2.0 / 3.0
    return result
